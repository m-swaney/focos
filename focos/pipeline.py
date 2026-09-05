"""Stage B: deterministic pipeline from the latest holdings snapshot (any source) to state/derived/latest/*.json.

Without holdings (source none, or nothing captured yet) the portfolio analytics are written as
{"available": false} and the ledger, plan, alerts, and sandbox sections still run.
"""
from __future__ import annotations

import shutil
from datetime import date as _date

from . import holdings, paths, settings
from .analytics import run as analytics_run
from .holdings.base import empty_snapshot
from .run import alerts as alerts_mod
from .run import diff as diff_mod
from .sandbox import state as sandbox_state
from .sources import robinhood_snapshot as rh

PORTFOLIO_FILES = ("portfolio.json", "risk.json", "optimizer.json", "tax_lots.json", "drift.json")


def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


def run(mode: str, date: str | None = None, heavy: bool | None = None, bump: bool = True) -> dict:
    paths.ensure_dirs()
    date = date or _date.today().isoformat()
    heavy = (mode != "daily") if heavy is None else heavy
    cfg = settings.analytics()

    cur, prev = holdings.latest_two()
    if cur is not None and cur.get("date") != date and cur.get("accounts"):
        date = cur["date"]  # re-running for the newest snapshot even if the calendar date differs
    if cur is None:
        cur = empty_snapshot(date, mode, "none")
    has_holdings = bool(cur.get("accounts")) and any(a.get("positions") for a in cur["accounts"])

    outputs: dict[str, dict] = {}
    tearsheet_dir = paths.TEARSHEETS / date
    if has_holdings:
        pos = rh.positions_frame(cur)
        lots = rh.lots_for_tax(cur) or None
        res = analytics_run.compute(pos, cfg, mode=mode, lots=lots, live_prices=rh.live_prices(cur),
                                    tearsheet_dir=tearsheet_dir, heavy=heavy)
        # Broker-reported totals (include cash, crypto, pending deposits) next to the position-only valuation
        res["meta"]["broker_accounts"] = {
            a["key"]: {"total_value": (a.get("portfolio") or {}).get("total_value"),
                       "equity_value": (a.get("portfolio") or {}).get("equity_value"),
                       "cash": (a.get("portfolio") or {}).get("cash"),
                       "crypto_value": (a.get("portfolio") or {}).get("crypto_value"),
                       "pending_deposits": (a.get("portfolio") or {}).get("pending_deposits")}
            for a in cur["accounts"]
        }
        res["meta"]["broker_total_value"] = cur.get("total_value") or res["meta"]["total_value"]
        res["meta"]["source"] = cur.get("source") or "robinhood_mcp"
        res["meta"]["valuation_note"] = (f"positions valued at quotes captured in the snapshot (source: {res['meta']['source']}); "
                                         "broker totals add cash, crypto, and pending deposits and may use slightly different marks")
        outputs.update(analytics_run.split_outputs(res))
        total_value = res["meta"]["total_value"]
    else:
        reason = "no holdings source configured" if (cur.get("source") in (None, "none")) else "no positions in the latest snapshot"
        for name in PORTFOLIO_FILES:
            outputs[name] = _unavailable(reason)
        total_value = None

    outputs["diff.json"] = diff_mod.diff(cur, prev, float(cfg.get("big_move_pct", 5.0))) if has_holdings else \
        {"date": date, "previous_date": None, "available": False, "accounts": [], "new_positions": [], "closed_positions": [],
         "quantity_changes": [], "movers": [], "orders": []}
    outputs["catalysts.json"] = rh.catalysts(cur)

    from .ledger import stage as ledger_stage
    ledger = ledger_stage.run(cur if has_holdings else None, date, mode)
    outputs["consolidated.json"] = ledger["consolidated"]
    outputs["entities.json"] = ledger["entities"]

    from . import plan as plan_mod
    try:
        outputs["plan.json"] = plan_mod.build(outputs["portfolio.json"] if has_holdings else None, outputs["consolidated.json"],
                                              outputs.get("risk.json") if has_holdings else None, date,
                                              entities=outputs["entities.json"])
    except Exception as e:  # noqa: BLE001
        outputs["plan.json"] = {"available": False, "error": str(e)}

    history = [settings.read_json(f, {}) for f in holdings.snapshot_files()[-400:]]
    from .run import tokens as tokens_mod
    token_alerts = tokens_mod.alerts() if (settings.focos().get("ai") or {}).get("mode") == "agent" else []
    outputs["alerts.json"] = {
        "date": date,
        "alerts": alerts_mod.build(cur, outputs["portfolio.json"] if has_holdings else {}, settings.profile_v2(),
                                   outputs["catalysts.json"], history, outputs.get("tax_lots.json") if has_holdings else None,
                                   sure_ok=ledger["ok"], consolidated=outputs["consolidated.json"]) + token_alerts,
        "tokens": tokens_mod.expiries(),
    }
    if bump:
        sandbox_state.bump_run()
    try:
        from .sandbox import paper
        paper.update(date)
    except Exception as e:  # noqa: BLE001
        settings.write_json(paths.SANDBOX / "scorecard.json", {"available": False, "error": str(e)})
    outputs["sandbox.json"] = sandbox_state.summary(cur if has_holdings else None)
    outputs["snapshot_summary.json"] = {
        "date": cur.get("date", date), "captured_at": cur.get("captured_at"), "total_value": cur.get("total_value"),
        "source": cur.get("source"), "available": has_holdings,
        "accounts": [{"key": a["key"], "last4": a.get("last4"), "type": a.get("brokerage_account_type"),
                      "agentic_allowed": a.get("agentic_allowed", False), "portfolio": a.get("portfolio"),
                      "n_positions": len(a.get("positions", []))} for a in cur.get("accounts", [])],
    }

    day_dir = paths.derived_for(date)
    for name, obj in outputs.items():
        settings.write_json(day_dir / name, obj)
        settings.write_json(paths.LATEST / name, obj)
    for art in ("correlation.png", "tearsheet.html"):
        src = tearsheet_dir / art
        if src.exists():
            shutil.copy(src, paths.LATEST / art)
    return {"date": date, "files": sorted(outputs.keys()), "total_value": total_value, "holdings": has_holdings,
            "alerts": len(outputs["alerts.json"]["alerts"]), "heavy": heavy,
            "ledger": {k: v for k, v in ledger.items() if k not in ("consolidated", "entities")}}
