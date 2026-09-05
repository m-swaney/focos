from __future__ import annotations

import csv
import io
from datetime import date as _date

from fastapi import APIRouter
from pydantic import BaseModel

from ... import holdings, paths, settings
from ...config import writer
from ...holdings.base import SourceError
from ...holdings.csv_source import COLUMNS, csv_path

router = APIRouter(prefix="/holdings")
SOURCES = ("simplefin_holdings", "csv", "robinhood_mcp", "none")


@router.get("/sources")
def sources():
    out = {}
    for name in SOURCES:
        try:
            ok, why = holdings.current(name).available()
        except Exception as e:  # noqa: BLE001
            ok, why = False, str(e)[:200]
        out[name] = {"available": ok, "reason": why}
    cur, _ = holdings.latest_two()
    return {"configured": (settings.focos().get("holdings") or {}).get("source"), "sources": out,
            "latest": {"date": cur.get("date"), "source": cur.get("source"), "accounts": len(cur.get("accounts", [])),
                       "total_value": cur.get("total_value")} if cur else None}


class SetSource(BaseModel):
    source: str


@router.post("/source")
def set_source(body: SetSource):
    if body.source not in SOURCES:
        return {"ok": False, "error": "unknown source"}
    issues = writer.write_section("focos.yml", "holdings", {"source": body.source})
    return {"ok": not issues, "issues": [i.as_dict() for i in issues]}


class Row(BaseModel):
    account_key: str = "brokerage"
    symbol: str
    quantity: float
    avg_cost: float | None = None
    price: float | None = None


class ManualRows(BaseModel):
    rows: list[Row]
    accounts: list[dict] = []   # optional brokerage entries [{key,label,role}] to add to accounts.yml


def _write_rows(rows: list[Row]) -> str:
    p = csv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([*COLUMNS, "price"])
        for r in rows:
            w.writerow([r.account_key, r.symbol.upper(), r.quantity, r.avg_cost if r.avg_cost is not None else "", r.price if r.price is not None else ""])
    return str(p.relative_to(paths.HOME))


@router.post("/manual")
def manual(body: ManualRows):
    rel = _write_rows(body.rows)
    if body.accounts:
        existing = {a["key"]: a for a in settings.brokerage()}
        for a in body.accounts:
            if a.get("key"):
                existing[a["key"]] = {**existing.get(a["key"], {}), "key": a["key"], "label": a.get("label") or a["key"],
                                      "role": a.get("role") or "taxable", "source": "csv", "entity": a.get("entity") or "personal"}
        writer.write_file("accounts.yml", {"version": 2, "brokerage": list(existing.values())})
    writer.write_section("focos.yml", "holdings", {"source": "csv"})
    return {"ok": True, "file": rel, "rows": len(body.rows)}


class CSVUpload(BaseModel):
    text: str


@router.post("/csv")
def upload_csv(body: CSVUpload):
    reader = csv.DictReader(io.StringIO(body.text))
    missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        return {"ok": False, "error": f"missing column(s): {', '.join(missing)}"}
    rows = []
    for r in reader:
        try:
            rows.append(Row(account_key=(r.get("account_key") or "brokerage").strip(), symbol=(r.get("symbol") or "").strip(),
                            quantity=float(r.get("quantity") or 0), avg_cost=float(r["avg_cost"]) if (r.get("avg_cost") or "").strip() else None,
                            price=float(r["price"]) if (r.get("price") or "").strip() else None))
        except ValueError:
            continue
    rel = _write_rows([x for x in rows if x.symbol and x.quantity > 0])
    writer.write_section("focos.yml", "holdings", {"source": "csv"})
    return {"ok": True, "file": rel, "rows": len(rows)}


class Capture(BaseModel):
    source: str | None = None


@router.post("/capture")
def capture(body: Capture):
    src = holdings.current(body.source)
    ok, why = src.available()
    if not ok:
        return {"ok": False, "source": src.name, "error": why}
    try:
        snap = src.capture(_date.today().isoformat(), "manual", "wizard")
    except SourceError as e:
        return {"ok": False, "source": src.name, "error": str(e)}
    return {"ok": True, "source": src.name, "date": snap.get("date"), "total_value": snap.get("total_value"), "notes": snap.get("notes"),
            "accounts": [{"key": a["key"], "label": a.get("nickname"), "positions": len(a.get("positions", [])),
                          "total_value": (a.get("portfolio") or {}).get("total_value")} for a in snap.get("accounts", [])]}
