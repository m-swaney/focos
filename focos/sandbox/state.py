"""Sandbox mode, run counter, kill switch, and the sandbox.json summary Stage C reads."""
from __future__ import annotations

from datetime import datetime, timezone

from .. import paths, settings

def mode_file():
    return paths.SANDBOX / "mode.json"


def kill_file():
    return paths.SANDBOX / "KILL"




def load_mode() -> dict:
    default = {"mode": settings.sandbox_rules().get("mode_default", "paper"), "run_count": 0,
               "live_orders": 0, "changed_at": None}
    return {**default, **(settings.read_json(mode_file(), {}) or {})}


def save_mode(m: dict) -> None:
    settings.write_json(mode_file(), m)


def set_mode(mode: str) -> dict:
    m = load_mode()
    m["mode"] = mode
    m["changed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save_mode(m)
    return m


def bump_run() -> dict:
    m = load_mode()
    m["run_count"] = int(m.get("run_count", 0)) + 1
    save_mode(m)
    return m


def killed() -> bool:
    return kill_file().exists()


def trading_enabled() -> bool:
    m = load_mode()
    rules = settings.sandbox_rules()
    return (m["mode"] == "live" and not killed() and int(m.get("run_count", 0)) >= int(rules.get("warmup_runs", 10)))


def allowed_tools_extra() -> list[str]:
    from . import brokers

    return brokers.current().trade_tools() if trading_enabled() else []


def proposals(limit: int = 50) -> list[dict]:
    files = sorted(paths.PROPOSALS.glob("*.json"))[-limit:]
    out = []
    for f in files:
        p = settings.read_json(f, {}) or {}
        p["_file"] = f.name
        p["approved"] = (paths.APPROVALS / f"{p.get('ref_id', f.stem)}.approved").exists()
        out.append(p)
    return out


def summary(snapshot: dict | None) -> dict:
    m = load_mode()
    rules = settings.sandbox_rules()
    agentic = None
    if snapshot:
        keys = set(settings.accounts_by_role("sandbox"))
        accts = snapshot.get("accounts", [])
        agentic = next((a for a in accts if a.get("key") in keys), None) if keys else None
        if agentic is None:
            agentic = next((a for a in accts if a.get("agentic_allowed")), None)
    return {
        "mode": m["mode"],
        "killed": killed(),
        "run_count": m.get("run_count", 0),
        "warmup_runs": rules.get("warmup_runs", 10),
        "warmup_remaining": max(0, int(rules.get("warmup_runs", 10)) - int(m.get("run_count", 0))),
        "trading_enabled": trading_enabled(),
        "live_orders": m.get("live_orders", 0),
        "rules": {k: rules.get(k) for k in ("budget_usd", "max_position_weight", "max_order_usd", "weekly_budget_usd",
                                             "max_orders_per_run", "max_orders_per_week", "instruments", "min_price")},
        "account": {
            "last4": agentic.get("last4") if agentic else None,
            "portfolio": agentic.get("portfolio") if agentic else None,
            "positions": agentic.get("positions") if agentic else [],
            "recent_orders": agentic.get("recent_orders") if agentic else [],
        },
        "proposals": proposals(),
        "scorecard": settings.read_json(paths.SANDBOX / "scorecard.json", {"available": False}),
    }
