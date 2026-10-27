"""0.4.3: the entry-quality rules (reward:risk, stop distance in ATRs, minimum hold, earnings blackout) and the
forced exit before a report. Every rule is off unless set."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from focos import paths, settings
from focos.sandbox import exits, rules
from tests.test_exits_v037 import _seed, _view

ET = ZoneInfo("America/New_York")
BASE = {"warmup_runs": 10, "require_approval_first_n": 0, "budget_usd": 1000, "max_position_weight": 0.40,
        "max_order_usd": 500, "weekly_budget_usd": 2500, "cash_floor_pct": 0.0, "max_orders_per_run": 3,
        "max_orders_per_week": 10, "min_price": 5.0, "blocklist_patterns": [], "market_orders_only_during_rth": True}
STRICT = {**BASE, "min_reward_risk": 2.0, "min_stop_atr": 1.0, "min_horizon_days": 10, "earnings_blackout": True}
PROP = {"ref_id": "r1", "symbol": "ACME", "side": "buy", "thesis": "t", "exit_plan": "e", "stop_loss": 46.0,
        "target": 60.0, "atr": 2.0, "horizon_days": 15, "next_earnings": "none"}


def ctx(**over):
    base = {"tool": "place", "now": datetime(2026, 10, 28, 10, 35, tzinfo=ET), "killed": False, "mode": "live",
            "run_count": 50, "live_orders": 40, "agentic_account_number": "90003333", "equity": 1300.0,
            "cash": 600.0, "positions": {}, "prices": {}, "orders_this_run": 0, "orders_this_week": 0,
            "buy_notional_this_week": 0.0, "proposal": PROP, "approved": False, "used_ref_ids": {}, "earnings": {}}
    base.update(over)
    return base


def buy(**over):
    o = {"account_number": "90003333", "symbol": "ACME", "side": "buy", "type": "limit", "quantity": "5",
         "limit_price": "50.00", "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": "r1"}
    o.update(over)
    return o


def test_a_good_plan_passes_the_strict_rules():
    v = rules.validate(buy(), ctx(), STRICT)
    assert v.ok, v.reasons      # risk 4 = 2 ATR, reward 10 = 2.5:1, 15-day hold, no report


def test_rules_are_off_unless_set():
    thin = {**PROP, "stop_loss": 49.5, "target": 50.5, "horizon_days": 1}
    thin.pop("atr"); thin.pop("next_earnings")
    assert rules.validate(buy(), ctx(proposal=thin), BASE).ok


def test_reward_risk_below_the_minimum_is_a_limit():
    v = rules.validate(buy(), ctx(proposal={**PROP, "target": 56.0}), STRICT)   # 6/4 = 1.5
    assert any("reward:risk 1.50" in r for r in v.reasons) and not v.correctable


def test_a_stop_inside_one_atr_is_refused_and_a_missing_atr_is_fixable():
    v = rules.validate(buy(), ctx(proposal={**PROP, "stop_loss": 49.0, "target": 53.0}), STRICT)
    assert any("0.50 ATR" in r and "48.00" in r for r in v.reasons)
    no_atr = {k: x for k, x in PROP.items() if k != "atr"}
    v = rules.validate(buy(), ctx(proposal=no_atr), STRICT)
    assert v.reasons == ["proposal is missing 'atr' (the 14-day ATR from get_equity_technical_indicators)"]
    assert v.correctable


def test_short_horizon_is_refused():
    v = rules.validate(buy(), ctx(proposal={**PROP, "horizon_days": 3}), STRICT)
    assert any("minimum hold" in r for r in v.reasons)


def test_no_entry_with_a_report_inside_the_hold():
    v = rules.validate(buy(), ctx(earnings={"ACME": "2026-11-06"}), STRICT)
    assert any("reports earnings on 2026-11-06" in r for r in v.reasons)
    v = rules.validate(buy(), ctx(proposal={**PROP, "next_earnings": "2026-11-04"}), STRICT)
    assert any("2026-11-04" in r for r in v.reasons)
    assert rules.validate(buy(), ctx(earnings={"ACME": "2026-12-20"}), STRICT).ok   # well past the hold
    missing = {k: x for k, x in PROP.items() if k != "next_earnings"}
    assert rules.validate(buy(), ctx(proposal=missing), STRICT).correctable



def test_held_position_is_sold_the_session_before_its_report(initialized_home: Path, monkeypatch):
    _seed(initialized_home)
    monkeypatch.setattr(settings, "sandbox_rules", lambda: {"earnings_blackout": True})
    settings.write_json(paths.LATEST / "catalysts.json",
                        {"earnings": [{"symbol": "MUSC", "date": "2026-10-01", "time": "am"}]})
    plan = exits.build(_view(), today="2026-09-30")
    kinds = {e["symbol"]: e["kind"] for e in plan["required_exits"]}
    assert kinds == {"BIOX": "stop", "MUSC": "earnings"}
    prop = json.loads((paths.PROPOSALS / "2026-09-30-MUSC-sell-earnings.json").read_text(encoding="utf-8"))
    assert prop["kind"] == "earnings_exit" and prop["side"] == "sell"
    assert "MUSC" not in [s["symbol"] for s in plan["missing_stops"]]    # being sold, not protected
    # a report next week does not force anything yet, and the rule off means no earnings exits at all
    settings.write_json(paths.LATEST / "catalysts.json",
                        {"earnings": [{"symbol": "MUSC", "date": "2026-10-07", "time": "am"}]})
    assert "MUSC" not in [e["symbol"] for e in exits.build(_view(), today="2026-09-30")["required_exits"]]
    monkeypatch.setattr(settings, "sandbox_rules", lambda: {})
    settings.write_json(paths.LATEST / "catalysts.json",
                        {"earnings": [{"symbol": "MUSC", "date": "2026-10-01", "time": "am"}]})
    assert "MUSC" not in [e["symbol"] for e in exits.build(_view(), today="2026-09-30")["required_exits"]]


def test_earnings_exit_is_not_a_stop_alarm(initialized_home: Path, monkeypatch):
    from focos.run import attention
    from focos.sandbox import state as sb_state

    _seed(initialized_home)
    monkeypatch.setattr(settings, "sandbox_rules", lambda: {"earnings_blackout": True})
    monkeypatch.setattr(sb_state, "load_mode", lambda: {"mode": "live"})
    monkeypatch.setattr(exits, "view_from_snapshot", lambda s: _view())
    settings.write_json(paths.LATEST / "catalysts.json",
                        {"earnings": [{"symbol": "MUSC", "date": "2026-10-01", "time": "am"}]})
    alerts = attention.sandbox_alerts(None, "2026-09-30")
    assert [a.get("data", {}).get("symbol") for a in alerts if a["code"] == "sandbox_stop_breached"] == ["BIOX"]
