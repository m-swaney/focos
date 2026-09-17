"""NYSE holidays, half days, and what the sandbox rules do with them."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from focos.sandbox import market_calendar as mc
from focos.sandbox import rules as rules_mod

ET = ZoneInfo("America/New_York")


def test_easter_matches_known_years():
    assert mc.easter(2024) == date(2024, 3, 31)
    assert mc.easter(2025) == date(2025, 4, 20)
    assert mc.easter(2026) == date(2026, 4, 5)
    assert mc.easter(2027) == date(2027, 3, 28)


def test_2026_holidays_match_the_published_nyse_calendar():
    assert sorted(mc.holidays(2026)) == [
        date(2026, 1, 1),    # New Year's Day
        date(2026, 1, 19),   # MLK
        date(2026, 2, 16),   # Washington's Birthday
        date(2026, 4, 3),    # Good Friday
        date(2026, 5, 25),   # Memorial Day
        date(2026, 6, 19),   # Juneteenth
        date(2026, 7, 3),    # Independence Day observed -- July 4 2026 is a Saturday
        date(2026, 9, 7),    # Labor Day
        date(2026, 11, 26),  # Thanksgiving
        date(2026, 12, 25),  # Christmas
    ]


def test_weekend_observance_shifts_both_ways():
    assert date(2026, 7, 3) in mc.holidays(2026)    # Sat July 4 -> Friday before
    assert date(2027, 7, 5) in mc.holidays(2027)    # Sun July 4 -> Monday after
    assert date(2027, 12, 24) in mc.holidays(2027)  # Sat Christmas -> Friday before


def test_half_days():
    assert mc.early_closes(2026) == {date(2026, 11, 27), date(2026, 12, 24)}
    assert mc.close_time(date(2026, 11, 27)) == mc.EARLY_CLOSE
    assert mc.close_time(date(2026, 11, 30)) == mc.REGULAR_CLOSE
    # July 3 2026 is the observed holiday, so it is not also an early close
    assert date(2026, 7, 3) not in mc.early_closes(2026)


def test_is_open_across_the_edges():
    assert mc.is_open(datetime(2026, 9, 18, 10, 30, tzinfo=ET))       # ordinary Friday
    assert not mc.is_open(datetime(2026, 9, 18, 9, 29, tzinfo=ET))    # pre-open
    assert not mc.is_open(datetime(2026, 9, 18, 16, 1, tzinfo=ET))    # post-close
    assert not mc.is_open(datetime(2026, 9, 19, 11, 0, tzinfo=ET))    # Saturday
    assert not mc.is_open(datetime(2026, 11, 26, 11, 0, tzinfo=ET))   # Thanksgiving
    # the 15:00 pass on a half day: open at 11:00, shut at 15:00
    assert mc.is_open(datetime(2026, 11, 27, 11, 0, tzinfo=ET))
    assert not mc.is_open(datetime(2026, 11, 27, 15, 0, tzinfo=ET))


def test_no_trading_days_closes_an_otherwise_open_day():
    open_day = datetime(2026, 9, 18, 11, 0, tzinfo=ET)
    assert mc.is_open(open_day)
    assert not mc.is_open(open_day, ["2026-09-18"])
    assert "no_trading_days" in mc.why_closed(open_day, ["2026-09-18"])


def test_why_closed_reads_plainly():
    assert mc.why_closed(datetime(2026, 9, 18, 11, 0, tzinfo=ET)) is None
    assert "weekend" in mc.why_closed(datetime(2026, 9, 19, 11, 0, tzinfo=ET))
    assert "holiday" in mc.why_closed(datetime(2026, 11, 26, 11, 0, tzinfo=ET))
    assert "before the 09:30 open" in mc.why_closed(datetime(2026, 9, 18, 9, 0, tzinfo=ET))
    assert "half day" in mc.why_closed(datetime(2026, 11, 27, 15, 0, tzinfo=ET))


# ---------------------------------------------------------------- the rules honour all of it

def _ctx(now):
    return {"tool": "place", "now": now, "killed": False, "mode": "live", "run_count": 99,
            "agentic_account_number": "1111", "equity": 1100.0, "cash": 1100.0, "positions": {},
            "prices": {"NVDA": 175.0}, "orders_this_run": 0, "orders_this_week": 0, "buy_notional_this_week": 0.0,
            "proposal": {"ref_id": "r1", "symbol": "NVDA", "side": "buy", "thesis": "t", "entry_reason": "e",
                         "exit_plan": "x", "stop_loss": 150.0, "horizon_days": 30}, "approved": True}


def _order(**kw):
    return {"account_number": "1111", "symbol": "NVDA", "side": "buy", "type": "market", "dollar_amount": "200",
            "ref_id": "r1", "time_in_force": "gfd", "market_hours": "regular_hours", **kw}


BASE_RULES = {"warmup_runs": 10, "require_approval_first_n": 0, "budget_usd": 1000, "max_position_weight": 0.25,
              "max_order_usd": 250, "weekly_budget_usd": 500, "cash_floor_pct": 0.05, "max_orders_per_run": 2,
              "max_orders_per_week": 4, "min_price": 5.0, "market_orders_only_during_rth": True}


def test_gate_allows_a_clean_order_in_regular_hours():
    v = rules_mod.validate(_order(), _ctx(datetime(2026, 9, 18, 10, 35, tzinfo=ET)), BASE_RULES)
    assert v.ok, v.reasons


def test_gate_blocks_every_order_type_on_a_holiday():
    """A holiday is not a time-of-day problem: a resting limit order is wrong too, so both are refused."""
    thanksgiving = _ctx(datetime(2026, 11, 26, 11, 0, tzinfo=ET))
    market = rules_mod.validate(_order(), thanksgiving, BASE_RULES)
    limit = rules_mod.validate(_order(type="limit", dollar_amount=None, quantity="1", limit_price="175"),
                               thanksgiving, BASE_RULES)
    assert not market.ok and any("no trading today" in x for x in market.reasons)
    assert not limit.ok and any("no trading today" in x for x in limit.reasons)


def test_gate_blocks_the_1500_pass_on_a_half_day():
    """The bug this calendar exists for: 15:00 on Black Friday is an hour after the close."""
    v = rules_mod.validate(_order(), _ctx(datetime(2026, 11, 27, 15, 0, tzinfo=ET)), BASE_RULES)
    assert not v.ok and any("regular hours" in x and "half day" in x for x in v.reasons)


def test_gate_honours_no_trading_days():
    rules = {**BASE_RULES, "no_trading_days": ["2026-09-18"]}
    v = rules_mod.validate(_order(), _ctx(datetime(2026, 9, 18, 10, 35, tzinfo=ET)), rules)
    assert not v.ok and any("no_trading_days" in x for x in v.reasons)


def test_a_limit_order_may_still_rest_outside_hours_when_the_rule_allows_it():
    """Time of day only constrains market orders, and only while market_orders_only_during_rth is on."""
    after_close = _ctx(datetime(2026, 9, 18, 16, 37, tzinfo=ET))
    limit = _order(type="limit", dollar_amount=None, quantity="1", limit_price="175")
    assert rules_mod.validate(limit, after_close, BASE_RULES).ok
    off = rules_mod.validate(_order(), after_close, {**BASE_RULES, "market_orders_only_during_rth": False})
    assert off.ok, off.reasons


@pytest.mark.parametrize("hhmm,expect_ok", [((9, 29), False), ((9, 30), True), ((16, 0), True), ((16, 1), False)])
def test_session_boundaries_are_inclusive(hhmm, expect_ok):
    v = rules_mod.validate(_order(), _ctx(datetime(2026, 9, 18, *hhmm, tzinfo=ET)), BASE_RULES)
    assert v.ok is expect_ok, v.reasons
