"""PreToolUse hook: block any order that fails the sandbox rules. Exit 2 = block (reason on stderr).

Claude Code passes JSON on stdin: {"tool_name": ..., "tool_input": {...}, "session_id": ...}.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .. import paths, settings
from . import brokers
from . import rules as rules_mod
from . import state as sb_state


def market_tz() -> ZoneInfo:
    return ZoneInfo(brokers.current().market_tz)
def gate_log():
    return paths.SANDBOX / "gate_log.jsonl"




def _apply_home_arg() -> None:
    """Hooks are launched as `python -m focos.sandbox.<hook> --home <dir>`; honor it before touching paths."""
    if "--home" in sys.argv:
        i = sys.argv.index("--home")
        if i + 1 < len(sys.argv):
            paths.rebind(sys.argv[i + 1])
            settings.reset()


def _latest_raw() -> dict | None:
    files = sorted(paths.RAW.glob("*.json"))
    return settings.read_json(files[-1]) if files else None


def _agentic_number(raw: dict | None) -> str | None:
    return brokers.current().sandbox_account_number(raw)


def _recent_gate_entries(days: int = 7) -> list[dict]:
    log = gate_log()
    if not log.exists():
        return []
    cutoff = datetime.now(market_tz()) - timedelta(days=days)
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
            if datetime.fromisoformat(e["ts"]) >= cutoff:
                out.append(e)
        except Exception:
            continue
    return out


def build_context(tool: str, order: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(market_tz())
    raw = _latest_raw()
    from ..sources import robinhood_snapshot as rh
    cur, _ = rh.latest_two()
    sb = sb_state.summary(cur)
    acct = sb.get("account") or {}
    portfolio = acct.get("portfolio") or {}
    positions = {p["symbol"]: {"value": p.get("value") or 0.0, "quantity": p.get("quantity") or 0.0,
                               "sellable": p.get("sellable") or p.get("quantity") or 0.0}
                 for p in (acct.get("positions") or [])}
    prices = {q["symbol"]: q["last"] for q in (cur or {}).get("quotes", []) if q.get("last")}
    recent = [e for e in _recent_gate_entries(7) if e.get("tool") == "place" and e.get("ok")]
    run_window = now - timedelta(minutes=90)
    this_run = [e for e in recent if datetime.fromisoformat(e["ts"]) >= run_window]
    ref_id = order.get("ref_id")
    proposal = None
    if ref_id:
        for f in paths.PROPOSALS.glob("*.json"):
            p = settings.read_json(f, {}) or {}
            if str(p.get("ref_id")) == str(ref_id):
                proposal = p
                break
    return {
        "tool": tool,
        "now": now,
        "killed": sb.get("killed"),
        "mode": sb.get("mode"),
        "run_count": sb.get("run_count", 0),
        "live_orders": sb.get("live_orders", 0),
        "agentic_account_number": _agentic_number(raw),
        "equity": float(portfolio.get("total_value") or 0),
        "cash": float(portfolio.get("cash") or 0),
        "positions": positions,
        "prices": prices,
        "orders_this_run": len(this_run),
        "orders_this_week": len(recent),
        "buy_notional_this_week": sum(float(e.get("notional") or 0) for e in recent if e.get("side") == "buy"),
        "proposal": proposal,
        "approved": bool(ref_id) and (paths.APPROVALS / f"{ref_id}.approved").exists(),
    }


def _log(entry: dict) -> None:
    log = gate_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def main() -> int:
    _apply_home_arg()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # not a hook invocation we understand; do not block unrelated tools
    tool_name = payload.get("tool_name", "")
    adapter = brokers.current()
    guarded = adapter.guarded_tools()
    if tool_name not in guarded:
        return 0
    tool = guarded[tool_name]
    order = adapter.order_from_tool_input(payload.get("tool_input") or {}).model_dump(exclude_none=True)
    try:
        ctx = build_context(tool, order)
        verdict = rules_mod.validate(order, ctx, settings.sandbox_rules())
    except Exception as e:  # fail closed
        verdict = rules_mod.Verdict(ok=False, reasons=[f"gate error: {type(e).__name__}: {e}"])
    redacted = {k: v for k, v in order.items() if k != "account_number"}
    redacted["account_last4"] = str(order.get("account_number", ""))[-4:]
    _log({"ts": datetime.now(settings.tz()).isoformat(timespec="seconds"), "tool": tool, "ok": verdict.ok,
          "reasons": verdict.reasons, "symbol": verdict.symbol, "side": verdict.side,
          "notional": verdict.notional, "order": redacted, "session_id": payload.get("session_id")})
    if not verdict.ok:
        sys.stderr.write("SANDBOX GATE BLOCKED this order:\n- " + "\n- ".join(verdict.reasons) +
                         "\nDo not retry or work around this. Record the refusal in the brief.\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
