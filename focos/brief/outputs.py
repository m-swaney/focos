"""Files a brief run produces: the markdown report, decisions.jsonl entries, sandbox proposal files."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date as _date
from datetime import datetime
from pathlib import Path

from .. import paths

SLUG = re.compile(r"[^A-Za-z0-9\-_.]+")


def week_label(date: str) -> str:
    d = _date.fromisoformat(date)
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


def report_id(mode: str, date: str) -> str:
    return {"daily": date, "weekly": week_label(date), "monthly": date[:7]}[mode]


def report_path(mode: str, date: str) -> Path:
    return paths.REPORTS / mode / f"{report_id(mode, date)}.md"


def report_rel(mode: str, date: str) -> str:
    return f"reports/{mode}/{report_id(mode, date)}.md"


def previous_brief_path(mode: str, date: str) -> str | None:
    folder = paths.REPORTS / mode
    cur = report_id(mode, date)
    prev = sorted(p for p in folder.glob("*.md") if p.stem != cur) if folder.exists() else []
    return f"reports/{mode}/{prev[-1].name}" if prev else None


def write_report(mode: str, date: str, markdown: str) -> str:
    p = report_path(mode, date)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return report_rel(mode, date)


def decision_id(date: str, text: str) -> str:
    """Stable id for a decision line; legacy lines without one get it on read, so the dashboard and the model agree."""
    return hashlib.sha1(f"{date}|{text}".encode("utf-8")).hexdigest()[:8]


def all_decisions() -> list[dict]:
    if not paths.DECISIONS.exists():
        return []
    rows = []
    for line in paths.DECISIONS.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            if not row.get("id") and row.get("kind") != "resolution":
                row["id"] = decision_id(str(row.get("date") or ""), str(row.get("text") or ""))
            rows.append(row)
    return rows


def decision_status(rows: list[dict] | None = None) -> dict[str, str]:
    """id -> acted|retired|standing from the latest resolution line that references it."""
    out: dict[str, str] = {}
    for r in rows if rows is not None else all_decisions():
        if r.get("kind") == "resolution" and r.get("ref") and r.get("status"):
            out[str(r["ref"])] = str(r["status"])
    return out


def recent_decisions(n: int = 20) -> list[dict]:
    """The last n entries with ids and, for recommendations/proposals, their current status."""
    rows = all_decisions()
    status = decision_status(rows)
    out = []
    for r in rows[-n:]:
        if r.get("kind") != "resolution":
            r = dict(r, status=status.get(str(r.get("id")), "open"))
        out.append(r)
    return out


def append_resolution(ref: str, status: str, note: str, date: str, run: str, actor: str = "user") -> dict:
    paths.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    entry = {"date": date, "run": run, "kind": "resolution", "ref": ref, "status": status, "text": note or "", "by": actor}
    with paths.DECISIONS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def append_decisions(rows: list[dict], date: str, mode: str) -> int:
    if not rows:
        return 0
    paths.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with paths.DECISIONS.open("a", encoding="utf-8") as f:
        for r in rows:
            if not isinstance(r, dict) or not r.get("text"):
                continue
            d = r.get("date") or date
            entry = {"id": r.get("id") or decision_id(str(d), str(r["text"])), "date": d, "run": r.get("run") or mode,
                     "kind": r.get("kind") or "recommendation", "text": str(r["text"]), "evidence": r.get("evidence") or "",
                     "review_on": r.get("review_on") or None}
            f.write(json.dumps(entry) + "\n")
            n += 1
    return n


def write_proposals(specs: list[dict], date: str) -> list[str]:
    """Sandbox proposals as files the gate and paper scorecard understand. Always paper unless a later stage flips it."""
    out = []
    paths.PROPOSALS.mkdir(parents=True, exist_ok=True)
    for s in specs or []:
        if not isinstance(s, dict) or not s.get("symbol") or not s.get("side"):
            continue
        symbol = str(s["symbol"]).upper()
        side = "sell" if str(s["side"]).lower() == "sell" else "buy"
        ref = SLUG.sub("-", str(s.get("ref_id") or f"{date}-{symbol}-{side}"))[:80]
        body = {"ref_id": ref, "date": s.get("date") or date, "symbol": symbol, "side": side,
                "dollar_amount": float(s.get("dollar_amount") or 0), "thesis": s.get("thesis") or "",
                "entry_reason": s.get("entry_reason") or "", "stop_loss": s.get("stop_loss"),
                "exit_plan": s.get("exit_plan") or "", "horizon_days": s.get("horizon_days"), "paper": True,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        p = paths.PROPOSALS / f"{ref}.json"
        p.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        out.append(p.name)
    return out
