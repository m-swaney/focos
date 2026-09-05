from datetime import datetime
from zoneinfo import ZoneInfo

from focos.sandbox import rules

ET = ZoneInfo("America/New_York")
RULES = {"warmup_runs": 10, "require_approval_first_n": 5, "budget_usd": 1000, "max_position_weight": 0.25,
         "max_order_usd": 250, "weekly_budget_usd": 500, "cash_floor_pct": 0.05, "max_orders_per_run": 2,
         "max_orders_per_week": 4, "min_price": 5.0, "blocklist_patterns": ["^(TQQQ|SQQQ)$", "3X"],
         "market_orders_only_during_rth": True}


def ctx(**over):
    base = {"tool": "place", "now": datetime(2026, 9, 3, 11, 0, tzinfo=ET), "killed": False, "mode": "live",
            "run_count": 12, "live_orders": 6, "agentic_account_number": "90003333", "equity": 1000.0,
            "cash": 600.0, "positions": {"AMD": {"value": 200.0, "quantity": 0.45, "sellable": 0.45}},
            "prices": {"AMD": 450.0, "TQQQ": 60.0, "PENNY": 2.0, "NVDA": 225.0},
            "orders_this_run": 0, "orders_this_week": 0, "buy_notional_this_week": 0.0,
            "proposal": {"ref_id": "r1", "symbol": "NVDA", "side": "buy", "thesis": "t", "exit_plan": "e",
                         "stop_loss": 200, "horizon_days": 30}, "approved": False}
    base.update(over)
    return base


def order(**over):
    o = {"account_number": "90003333", "symbol": "NVDA", "side": "buy", "type": "market",
         "dollar_amount": "100.00", "ref_id": "r1"}
    o.update(over)
    return o


def test_happy_path_passes():
    v = rules.validate(order(), ctx(), RULES)
    assert v.ok, v.reasons
    assert v.notional == 100.0


def test_kill_switch_blocks():
    v = rules.validate(order(), ctx(killed=True), RULES)
    assert not v.ok and any("KILL" in r for r in v.reasons)


def test_paper_mode_and_warmup_block():
    assert not rules.validate(order(), ctx(mode="paper"), RULES).ok
    v = rules.validate(order(), ctx(run_count=3), RULES)
    assert any("warmup" in r for r in v.reasons)


def test_wrong_account_blocks():
    v = rules.validate(order(account_number="90001111"), ctx(), RULES)
    assert any("Agentic" in r for r in v.reasons)


def test_oversized_order_and_weight_cap():
    v = rules.validate(order(dollar_amount="300"), ctx(), RULES)
    assert any("max_order_usd" in r for r in v.reasons)
    v = rules.validate(order(symbol="AMD", dollar_amount="100"), ctx(proposal={"ref_id": "r1", "symbol": "AMD", "side": "buy",
                                                                            "thesis": "t", "exit_plan": "e", "stop_loss": 1, "horizon_days": 5}), RULES)
    assert any("post-trade weight" in r for r in v.reasons)  # 200+100 = 30% > 25%


def test_cash_floor_and_no_margin():
    v = rules.validate(order(dollar_amount="240"), ctx(cash=250.0), RULES)
    assert any("cash floor" in r for r in v.reasons)
    v = rules.validate(order(dollar_amount="200"), ctx(cash=100.0), RULES)
    assert any("no margin" in r for r in v.reasons)


def test_blocklist_min_price_and_symbol_shape():
    bad = {"ref_id": "r1", "symbol": "TQQQ", "side": "buy", "thesis": "t", "exit_plan": "e", "stop_loss": 1, "horizon_days": 5}
    v = rules.validate(order(symbol="TQQQ"), ctx(proposal=bad), RULES)
    assert any("blocklist" in r for r in v.reasons)
    bad["symbol"] = "PENNY"
    v = rules.validate(order(symbol="PENNY"), ctx(proposal=bad), RULES)
    assert any("minimum" in r for r in v.reasons)
    v = rules.validate(order(symbol="nvda$"), ctx(), RULES)
    assert any("plain US ticker" in r for r in v.reasons)


def test_market_hours_and_order_shape():
    v = rules.validate(order(), ctx(now=datetime(2026, 9, 5, 11, 0, tzinfo=ET)), RULES)  # Saturday
    assert any("09:30" in r for r in v.reasons)
    v = rules.validate(order(type="limit", dollar_amount="100"), ctx(), RULES)
    assert any("dollar_amount requires" in r for r in v.reasons) and any("limit_price" in r for r in v.reasons)
    v = rules.validate(order(type="stop_market"), ctx(), RULES)
    assert any("market or limit" in r for r in v.reasons)
    v = rules.validate(order(time_in_force="gtc"), ctx(), RULES)
    assert any("gtc" in r for r in v.reasons)


def test_frequency_limits():
    assert any("per run" in r for r in rules.validate(order(), ctx(orders_this_run=2), RULES).reasons)
    assert any("per week" in r for r in rules.validate(order(), ctx(orders_this_week=4), RULES).reasons)
    assert any("weekly buy budget" in r for r in rules.validate(order(), ctx(buy_notional_this_week=450), RULES).reasons)


def test_proposal_and_approval_requirements():
    v = rules.validate(order(ref_id=None), ctx(), RULES)
    assert any("ref_id is required" in r for r in v.reasons)
    v = rules.validate(order(), ctx(proposal=None), RULES)
    assert any("no proposal file" in r for r in v.reasons)
    v = rules.validate(order(), ctx(live_orders=2, approved=False), RULES)
    assert any("approval required" in r for r in v.reasons)
    v = rules.validate(order(), ctx(live_orders=2, approved=True), RULES)
    assert v.ok, v.reasons
    # review does not need approval
    v = rules.validate(order(), ctx(tool="review", live_orders=0, approved=False), RULES)
    assert v.ok, v.reasons


def test_sell_requires_position():
    sell_prop = {"ref_id": "r1", "symbol": "AMD", "side": "sell", "thesis": "t", "exit_plan": "e", "stop_loss": 1, "horizon_days": 5}
    v = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="0.4"), ctx(proposal=sell_prop), RULES)
    assert v.ok, v.reasons
    v = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="1"), ctx(proposal=sell_prop), RULES)
    assert any("exceeds sellable" in r for r in v.reasons)


def test_budget_ceiling_grows_with_recurring_deposits():
    from datetime import datetime as _dt
    r = {**RULES, "budget_usd": 1000, "budget_growth_per_week_usd": 50, "funded_on": "2026-09-04"}
    # 20 weeks later the ceiling is (1000 + 50*20) * 1.5 = 3000; equity 2500 must pass
    c = ctx(now=_dt(2027, 1, 21, 11, 0, tzinfo=ET), equity=2500.0, cash=1500.0)
    v = rules.validate(order(), c, r)
    assert not any("far above" in x for x in v.reasons), v.reasons
    # without growth it would be flagged
    v2 = rules.validate(order(), c, {**RULES, "budget_usd": 1000})
    assert any("far above" in x for x in v2.reasons)
