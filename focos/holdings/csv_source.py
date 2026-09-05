"""Holdings from <home>/data/holdings.csv (also what the setup wizard writes for manual entry).

Columns: account_key, symbol, quantity, avg_cost[, price]. Rows without a price are priced from the last
two closes via yfinance (analytics.prices), which also gives a day change.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from .. import paths, settings
from . import write_snapshot
from .base import SourceError, account_entry, empty_snapshot, finish_snapshot, position_entry

PriceFetcher = Callable[[list[str]], dict[str, tuple[float, float | None]]]
COLUMNS = ("account_key", "symbol", "quantity", "avg_cost")


def csv_path() -> Path:
    return paths.DATA / "holdings.csv"


def yahoo_prices(symbols: list[str]) -> dict[str, tuple[float, float | None]]:
    """symbol -> (last close, previous close) from the shared price cache."""
    from ..analytics import prices

    if not symbols:
        return {}
    px, _stale = prices.fetch_prices(symbols, years=1)
    px = px.ffill()
    out: dict[str, tuple[float, float | None]] = {}
    for s in symbols:
        if s in px.columns and len(px[s].dropna()):
            col = px[s].dropna()
            out[s] = (float(col.iloc[-1]), float(col.iloc[-2]) if len(col) > 1 else None)
    return out


def read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SourceError(f"{path.name}: missing column(s) {', '.join(missing)}; expected {', '.join(COLUMNS)}[, price]")
        rows = []
        for i, r in enumerate(reader, 2):
            try:
                qty = float(r["quantity"])
            except (TypeError, ValueError):
                raise SourceError(f"{path.name} line {i}: quantity must be a number") from None
            if qty <= 0 or not (r.get("symbol") or "").strip():
                continue
            rows.append({"account_key": (r["account_key"] or "").strip() or "brokerage",
                         "symbol": r["symbol"].strip().upper(), "quantity": qty,
                         "avg_cost": float(r["avg_cost"]) if (r.get("avg_cost") or "").strip() else None,
                         "price": float(r["price"]) if (r.get("price") or "").strip() else None})
    return rows


class CSVSource:
    name = "csv"

    def __init__(self, price_fetcher: PriceFetcher | None = None, path: Path | None = None):
        self._fetch = price_fetcher or yahoo_prices
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or csv_path()

    def available(self) -> tuple[bool, str | None]:
        if not self.path.exists():
            return False, f"{self.path} not found (columns: account_key, symbol, quantity, avg_cost[, price])"
        return True, None

    def capture(self, asof: str, mode: str, run_id: str) -> dict | None:
        rows = read_rows(self.path)
        snap = empty_snapshot(asof, mode, self.name)
        need = sorted({r["symbol"] for r in rows if r["price"] is None})
        fetched = self._fetch(need) if need else {}
        quotes: dict[str, dict] = {}
        by_account: dict[str, list[dict]] = {}
        labels = {a["key"]: a for a in settings.brokerage()}
        for r in rows:
            price, prev = (r["price"], None) if r["price"] is not None else fetched.get(r["symbol"], (None, None))
            if price is None:
                snap["notes"] += f"no price for {r['symbol']}; "
            by_account.setdefault(r["account_key"], []).append(position_entry(r["symbol"], r["quantity"], r["avg_cost"], price, prev))
            quotes.setdefault(r["symbol"], {"symbol": r["symbol"], "last": price, "prev_close": prev, "quote_time": None})
        for key, positions in by_account.items():
            spec = labels.get(key) or {}
            snap["accounts"].append(account_entry(key, label=spec.get("label") or key, role=spec.get("role") or "taxable",
                                                  positions=positions))
        snap["quotes"] = list(quotes.values())
        finish_snapshot(snap)
        write_snapshot(snap)
        return snap
