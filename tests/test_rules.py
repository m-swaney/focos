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
    assert not v.ok and any("weekend" in r for r in v.reasons)
    v = rules.validate(order(), ctx(now=datetime(2026, 9, 4, 17, 0, tzinfo=ET)), RULES)  # Friday, after the close
    assert not v.ok and any("regular hours" in r for r in v.reasons)
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


def test_review_does_not_need_a_ref_id():
    """review_equity_order has no ref_id field, so requiring one refused every pre-trade check and left no
    legitimate route to an order. The check belongs to place alone."""
    v = rules.validate(order(ref_id=None), ctx(tool="review", proposal=None), RULES)
    assert v.ok, v.reasons
    # place still has to name its proposal
    v2 = rules.validate(order(ref_id=None), ctx(), RULES)
    assert any("ref_id is required" in x for x in v2.reasons)


def test_a_new_name_needs_a_limit_price_to_be_sized():
    prop = {"ref_id": "r1", "symbol": "INTC", "side": "buy", "thesis": "t", "exit_plan": "e",
            "stop_loss": 112, "horizon_days": 5}
    # the gate has no quote for a name the account does not hold
    v = rules.validate(order(symbol="INTC", dollar_amount="364.50"), ctx(proposal=prop), RULES)
    assert any("use a limit order" in x for x in v.reasons)
    # a limit order carries its own price
    v2 = rules.validate(order(symbol="INTC", type="limit", dollar_amount=None, quantity="2", limit_price="121.50"),
                        ctx(proposal=prop), RULES)
    assert v2.ok, v2.reasons
    assert v2.notional == 243.0


def test_sell_requires_position():
    sell_prop = {"ref_id": "r1", "symbol": "AMD", "side": "sell", "thesis": "t", "exit_plan": "e", "stop_loss": 1, "horizon_days": 5}
    v = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="0.4"), ctx(proposal=sell_prop), RULES)
    assert v.ok, v.reasons
    v = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="1"), ctx(proposal=sell_prop), RULES)
    assert any("exceeds sellable" in r for r in v.reasons)


def test_budget_ceiling_is_opt_in_and_grows_with_recurring_deposits():
    from datetime import datetime as _dt
    c = ctx(now=_dt(2027, 1, 21, 11, 0, tzinfo=ET), equity=2500.0, cash=1500.0)
    # off by default: an account that has grown its own way past the budget can still buy
    assert not any("above" in x for x in rules.validate(order(), c, {**RULES, "budget_usd": 1000}).reasons)
    # switched on, 20 weeks of $50 deposits lift the basis to 2000, so 1.5x = 3000 and equity 2500 passes
    r = {**RULES, "budget_usd": 1000, "budget_growth_per_week_usd": 50, "funded_on": "2026-09-04",
         "equity_ceiling_multiple": 1.5}
    v = rules.validate(order(), c, r)
    assert not any("above" in x for x in v.reasons), v.reasons
    # without the deposits the basis stays 1000 and 2500 is over the 1500 ceiling
    v2 = rules.validate(order(), c, {**RULES, "budget_usd": 1000, "equity_ceiling_multiple": 1.5})
    assert any("above 1.5x" in x for x in v2.reasons)


def test_capital_basis_counts_deposits_not_gains():
    from datetime import datetime as _dt
    now = _dt(2027, 1, 21, 11, 0, tzinfo=ET)
    assert rules.capital_basis({"budget_usd": 1000}, now) == 1000
    # 139 days after funding is 19 whole weeks of $50 deposits; a part week does not count
    assert rules.capital_basis({"budget_usd": 1000, "budget_growth_per_week_usd": 50,
                                "funded_on": "2026-09-04"}, now) == 1950


def test_drawdown_halt_blocks_buys_and_allows_sells():
    r = {**RULES, "budget_usd": 1000, "budget_growth_per_week_usd": 0, "max_drawdown_pct": 0.5}
    # equity 400 is below half the 1000 contributed
    v = rules.validate(order(), ctx(equity=400.0, cash=400.0), r)
    assert any("drawdown halt" in x and "resume" in x for x in v.reasons), v.reasons
    # just above the line is fine
    assert not any("drawdown halt" in x for x in rules.validate(order(), ctx(equity=600.0, cash=600.0), r).reasons)
    # a halted account must still be able to get out
    sell_prop = {"ref_id": "r1", "symbol": "AMD", "side": "sell", "thesis": "t", "exit_plan": "e",
                 "stop_loss": 1, "horizon_days": 5}
    v3 = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="0.4"),
                        ctx(equity=400.0, cash=400.0, proposal=sell_prop), r)
    assert v3.ok, v3.reasons
    # the override from `focos sandbox resume` re-bases it
    v4 = rules.validate(order(), ctx(equity=400.0, cash=400.0, drawdown_basis=500.0), r)
    assert not any("drawdown halt" in x for x in v4.reasons), v4.reasons


def test_exits_only_pass_blocks_buys_and_allows_sells():
    v = rules.validate(order(), ctx(pass_kind="exits"), RULES)
    assert any("exits-only pass" in x for x in v.reasons)
    sell_prop = {"ref_id": "r1", "symbol": "AMD", "side": "sell", "thesis": "t", "exit_plan": "e",
                 "stop_loss": 1, "horizon_days": 5}
    v2 = rules.validate(order(symbol="AMD", side="sell", dollar_amount=None, quantity="0.4"),
                        ctx(pass_kind="exits", proposal=sell_prop), RULES)
    assert v2.ok, v2.reasons


def test_aggressive_caps_and_leveraged_etfs():
    """The live sandbox config: bigger orders, a 40% position cap, no blocklist, no approvals, no cash floor."""
    r = {**RULES, "max_order_usd": 500, "max_position_weight": 0.40, "cash_floor_pct": 0.0,
         "require_approval_first_n": 0, "blocklist_patterns": [], "max_orders_per_run": 3,
         "max_orders_per_week": 10, "weekly_budget_usd": 2500}
    c = ctx(equity=1100.0, cash=1100.0, live_orders=0, approved=False, prices={"TQQQ": 90.0})
    prop = {"ref_id": "r1", "symbol": "TQQQ", "side": "buy", "thesis": "t", "exit_plan": "e",
            "stop_loss": 80, "horizon_days": 5}
    # a leveraged ETF at $440 = 40% of 1100, unapproved, with every cent of cash committed
    v = rules.validate(order(symbol="TQQQ", dollar_amount="440"), {**c, "proposal": prop}, r)
    assert v.ok, v.reasons
    # one dollar more breaches the weight cap
    v2 = rules.validate(order(symbol="TQQQ", dollar_amount="441"), {**c, "proposal": prop}, r)
    assert any("exceeds 40% cap" in x for x in v2.reasons)
    # the blocklist still bites when it is configured
    v3 = rules.validate(order(symbol="TQQQ", dollar_amount="440"),
                        {**c, "proposal": prop}, {**r, "blocklist_patterns": ["3X", "^TQQQ$"]})
    assert any("blocklist" in x for x in v3.reasons)
