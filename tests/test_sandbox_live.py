"""The live pre-trade read of the Agentic account, and the gate's use of it for sizing."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from focos import settings
from focos.sandbox import live

ET = ZoneInfo("America/New_York")


def test_normalize_masks_the_account_number(initialized_home: Path):
    view = live.normalize({"account_number": "87651234", "portfolio": {"cash": 500.0, "total_value": 1100.0},
                           "positions": [], "quotes": []})
    assert view["last4"] == "1234"
    assert "87651234" not in str(view)


def test_normalize_accepts_the_shapes_the_model_drifts_into(initialized_home: Path):
    view = live.normalize({
        "account_number": "55550011",
        "portfolio": {"cash": "250", "total_value": "1100", "buying_power": 250},
        # positions under the broker's own key, price under last_trade_price, sellable under the long name
        "equity_positions": [{"symbol": "aapl", "quantity": 3, "last_trade_price": 200.0,
                              "shares_available_for_sells": 2, "average_buy_price": 180.0}],
        "quotes": [{"symbol": "MSFT", "last_trade_price": 400.0}],
    })
    aapl = view["positions"][0]
    assert aapl["symbol"] == "AAPL" and aapl["quantity"] == 3 and aapl["sellable"] == 2
    assert aapl["price"] == 200.0 and aapl["value"] == 600.0 and aapl["avg_cost"] == 180.0
    assert view["portfolio"]["cash"] == 250.0        # strings coerced
    assert view["quotes"]["MSFT"] == 400.0
    assert view["quotes"]["AAPL"] == 200.0           # a held position is its own quote for sizing


def test_freshness_window(initialized_home: Path):
    now = datetime(2026, 9, 18, 10, 35, tzinfo=timezone.utc)
    recent = {"asof": (now - timedelta(minutes=2)).isoformat()}
    stale = {"asof": (now - timedelta(minutes=live.MAX_AGE_MINUTES + 1)).isoformat()}
    assert live.fresh(recent, now) and not live.fresh(stale, now)
    assert not live.fresh(None, now) and not live.fresh({}, now)
    assert not live.fresh({"asof": "not a date"}, now)


def test_gate_prefers_a_fresh_live_read_over_the_overnight_snapshot(initialized_home: Path, monkeypatch):
    """The whole point of the live read: cash and prices at order time, not at last night's close."""
    from focos.sandbox import gate

    monkeypatch.setattr(gate, "_latest_raw", lambda: {"accounts": [{"account_number": "1111", "agentic_allowed": True}]})
    monkeypatch.setattr("focos.sources.robinhood_snapshot.latest_two", lambda: (None, None))

    now = datetime(2026, 9, 18, 10, 35, tzinfo=ET)
    live.write({**live.normalize({"account_number": "1111", "portfolio": {"cash": 640.0, "total_value": 1100.0},
                                  "positions": [{"symbol": "AAPL", "quantity": 2, "price": 230.0}],
                                  "quotes": [{"symbol": "NVDA", "last": 175.0}]}),
                "asof": now.isoformat(timespec="seconds")})
    ctx = gate.build_context("place", {"symbol": "NVDA", "side": "buy"}, now=now)
    assert ctx["live"]["used"] is True
    assert ctx["cash"] == 640.0 and ctx["equity"] == 1100.0
    assert ctx["prices"]["NVDA"] == 175.0
    assert ctx["positions"]["AAPL"]["quantity"] == 2


def test_gate_falls_back_to_the_snapshot_when_the_live_read_is_stale(initialized_home: Path, monkeypatch):
    """A stalled pass must not size orders on an hours-old cash figure."""
    from focos.sandbox import gate

    monkeypatch.setattr(gate, "_latest_raw", lambda: {"accounts": [{"account_number": "1111", "agentic_allowed": True}]})
    monkeypatch.setattr("focos.sources.robinhood_snapshot.latest_two", lambda: (None, None))

    now = datetime(2026, 9, 18, 15, 0, tzinfo=ET)
    live.write({**live.normalize({"account_number": "1111", "portfolio": {"cash": 640.0}, "positions": [], "quotes": []}),
                "asof": (now - timedelta(hours=4)).isoformat(timespec="seconds")})
    ctx = gate.build_context("place", {"symbol": "NVDA", "side": "buy"}, now=now)
    assert ctx["live"]["used"] is False
    assert ctx["cash"] == 0.0       # no snapshot in this fixture, so the conservative value stands
    assert ctx["live"]["age_minutes"] > live.MAX_AGE_MINUTES


def test_read_survives_a_corrupt_file(initialized_home: Path):
    live.path().parent.mkdir(parents=True, exist_ok=True)
    live.path().write_text("{not json", encoding="utf-8")
    assert live.read() is None
    assert live.fresh() is False
