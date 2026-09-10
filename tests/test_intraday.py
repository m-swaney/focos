"""The intraday refresh: market-hours gating, re-pricing math, stale quotes, and the once-a-day midday pull.
Yahoo is never called; quotes are injected or the fetcher is faked."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from focos import holdings, intraday, paths, settings

CT = ZoneInfo("America/Chicago")
QUOTES = {"AAA": {"last": 110.0, "prev_close": 100.0}, "BBB": {"last": 190.0, "prev_close": 200.0}}


def _pos(symbol, qty, price):
    return {"symbol": symbol, "quantity": qty, "avg_cost": price / 2, "price": price, "value": qty * price,
            "day_change_pct": 0.0, "sellable": qty}


SNAPSHOT = {
    "date": "2026-09-09", "mode": "daily", "captured_at": "2026-09-09T16:36:00+00:00",
    "accounts": [
        {"key": "taxable", "last4": "1234", "portfolio": {"total_value": 10000.0, "cash": 8000.0},
         "positions": [_pos("AAA", 10, 100.0), _pos("BBB", 5, 200.0)]},
        {"key": "roth", "last4": "5678", "portfolio": {"total_value": 5000.0, "cash": 3000.0},
         "positions": [_pos("AAA", 20, 100.0)]},
    ],
    "quotes": [{"symbol": "AAA", "last": 100.0, "prev_close": 99.0}],
    "total_value": 15000.0,
}


def _seed(home: Path, snapshot=None, timezone="America/Chicago") -> None:
    (home / "config" / "profile.yml").write_text(yaml.safe_dump({"version": 2, "owner": {"name": "Ann"},
                                                                 "household": {"timezone": timezone}}))
    settings.reset()
    holdings.write_snapshot(snapshot if snapshot is not None else SNAPSHOT)


# ---------------------------------------------------------------- gating

def test_market_window_in_the_household_timezone(initialized_home: Path):
    _seed(initialized_home)
    wed = datetime(2026, 9, 9, tzinfo=CT)
    assert not intraday.market_open_now(wed.replace(hour=9, minute=15))
    assert intraday.market_open_now(wed.replace(hour=9, minute=30))
    assert intraday.market_open_now(wed.replace(hour=13))
    assert intraday.market_open_now(wed.replace(hour=16))
    assert not intraday.market_open_now(wed.replace(hour=16, minute=1))
    saturday = datetime(2026, 9, 12, 13, tzinfo=CT)
    assert saturday.weekday() == 5 and not intraday.market_open_now(saturday)
    assert intraday.market_open_now(saturday, {"weekdays_only": False})
    assert intraday.market_open_now(wed.replace(hour=18), {"market_close": "20:00"})


def test_price_due_cadence(initialized_home: Path):
    _seed(initialized_home)
    open_time = datetime(2026, 9, 9, 13, tzinfo=CT)
    assert intraday.price_due(open_time, None, None)  # first tick after startup always runs
    assert not intraday.price_due(open_time, None, open_time - timedelta(minutes=14))
    assert intraday.price_due(open_time, None, open_time - timedelta(minutes=15))
    assert intraday.price_due(open_time, {"every_minutes": 5}, open_time - timedelta(minutes=6))
    after_hours = datetime(2026, 9, 9, 21, tzinfo=CT)
    assert not intraday.price_due(after_hours, None, after_hours - timedelta(hours=3))
    assert not intraday.price_due(open_time, {"enabled": False}, None)


def test_midday_due_once_a_day(initialized_home: Path):
    _seed(initialized_home)
    noon = datetime(2026, 9, 9, 12, 1, tzinfo=CT)
    assert intraday.midday_due(noon, None, None)
    assert not intraday.midday_due(noon.replace(hour=11), None, None)
    assert not intraday.midday_due(noon, None, "2026-09-09")
    assert intraday.midday_due(noon, None, "2026-09-08")
    assert not intraday.midday_due(noon, {"midday_ledger": None}, None)
    assert not intraday.midday_due(datetime(2026, 9, 12, 13, tzinfo=CT), None, None)  # Saturday


# ---------------------------------------------------------------- re-pricing

def test_reprices_positions_and_accounts(initialized_home: Path):
    _seed(initialized_home)
    now = datetime(2026, 9, 9, 13, tzinfo=CT)
    out = intraday.refresh(now, quotes=QUOTES)
    assert out["available"] and not out["stale"] and out["source"] == "yahoo" and out["priced"] == 3
    acct = {a["key"]: a for a in out["accounts"]}
    # taxable: 10 AAA at 110 + 5 BBB at 190 = 2,050 against 2,000 at capture, on top of the broker's 10,000
    assert acct["taxable"] == {"key": "taxable", "equity_value": 2050.0, "total_value": 10050.0, "change_since_snapshot": 50.0}
    assert acct["roth"] == {"key": "roth", "equity_value": 2200.0, "total_value": 5200.0, "change_since_snapshot": 200.0}
    assert out["change_since_snapshot"] == 250.0 and out["total_value"] == 15250.0
    assert out["snapshot_total_value"] == 15000.0 and out["snapshot_date"] == "2026-09-09"
    assert out["day_change"] == 250.0 and abs(out["day_change_pct"] - 0.0625) < 1e-9
    movers = out["movers"]
    assert [m["symbol"] for m in movers] == ["AAA", "AAA", "BBB"] and all(m["big"] for m in movers)
    assert abs(movers[0]["day_change_pct"] - 0.10) < 1e-9 and movers[0]["value_change"] > 0
    assert abs(movers[-1]["day_change_pct"] + 0.05) < 1e-9 and movers[-1]["value_change"] < 0
    assert out["skipped"] == [] and out["symbols"] == 2
    assert settings.read_json(intraday.cache_path())["total_value"] == 15250.0


def test_unquoted_symbols_keep_their_snapshot_value(initialized_home: Path):
    snap = {**SNAPSHOT, "accounts": [{**SNAPSHOT["accounts"][0],
                                      "positions": [_pos("AAA", 10, 100.0), _pos("DOGE", 100, 1.0)]}]}
    _seed(initialized_home, snap)
    out = intraday.refresh(datetime(2026, 9, 9, 13, tzinfo=CT), quotes={"AAA": QUOTES["AAA"]})
    assert out["skipped"] == ["DOGE"] and out["priced"] == 1
    # 10 AAA at 110 = 1,100, plus DOGE held at its captured 100
    assert out["accounts"][0]["equity_value"] == 1200.0 and out["accounts"][0]["change_since_snapshot"] == 100.0
    assert [m["symbol"] for m in out["movers"]] == ["AAA"]


def test_stale_quotes_are_flagged_not_fatal(initialized_home: Path, monkeypatch):
    _seed(initialized_home)
    monkeypatch.setattr("focos.analytics.prices.fetch_quotes", lambda symbols: (QUOTES, True))
    out = intraday.refresh(datetime(2026, 9, 9, 13, tzinfo=CT))
    assert out["available"] and out["stale"] and out["total_value"] == 15250.0
    monkeypatch.setattr("focos.analytics.prices.fetch_quotes", lambda symbols: ({}, True))
    out = intraday.refresh(datetime(2026, 9, 9, 13, tzinfo=CT))
    assert out["available"] and out["stale"] and out["priced"] == 0
    assert out["total_value"] == 15000.0 and out["change_since_snapshot"] == 0.0  # falls back to the capture


def test_no_snapshot_is_reported_not_raised(initialized_home: Path):
    _seed(initialized_home, {"date": "2026-09-09", "accounts": [], "total_value": 0})
    out = intraday.refresh(datetime(2026, 9, 9, 13, tzinfo=CT), quotes=QUOTES)
    assert not out["available"] and "snapshot" in out["reason"]


def test_never_touches_the_snapshot_or_the_dated_history(initialized_home: Path):
    _seed(initialized_home)
    snap_file = paths.SNAPSHOTS_HOLDINGS / "2026-09-09.json"
    before = snap_file.read_text(encoding="utf-8")
    settings.write_json(paths.derived_for("2026-09-09") / "snapshot_summary.json", {"total_value": 15000.0})
    intraday.refresh(datetime(2026, 9, 9, 13, tzinfo=CT), quotes=QUOTES)
    assert snap_file.read_text(encoding="utf-8") == before
    assert settings.read_json(paths.derived_for("2026-09-09") / "snapshot_summary.json")["total_value"] == 15000.0
    assert intraday.cache_path().parent == paths.CACHE  # gitignored, so the data dir stays clean
    assert not (paths.LATEST / "intraday.json").exists()


# ---------------------------------------------------------------- midday and the ticker

def test_midday_pull_forces_the_feed_and_rebuilds(initialized_home: Path, monkeypatch):
    _seed(initialized_home)
    calls = {}

    class FakeResult:
        ok, skipped, accounts, transactions_new, transactions_updated = True, False, 3, 2, 1

    class FakeProvider:
        def refresh(self, on, force=False):
            calls["refresh"] = {"on": on, "force": force}
            return FakeResult()

    monkeypatch.setattr("focos.ledger.providers.current", lambda name=None: FakeProvider())
    monkeypatch.setattr("focos.pipeline.run", lambda *a, **k: calls.setdefault("pipeline", (a, k)))
    out = intraday.run_midday(datetime(2026, 9, 9, 12, 5, tzinfo=CT))
    assert out["ok"] and out["date"] == "2026-09-09" and out["pull"]["transactions_new"] == 2
    assert calls["refresh"]["force"] is True  # 20h gate would skip an unforced noon pull
    assert calls["pipeline"][1] == {"heavy": False, "bump": False}  # never bump the sandbox warmup
    assert calls["pipeline"][0][0] == "daily"                       # keeps heavy analytics and Zillow off
    assert (intraday.read()["midday"] or {})["date"] == "2026-09-09"


def test_midday_failure_is_recorded_and_not_retried_all_day(initialized_home: Path, monkeypatch):
    _seed(initialized_home)

    class Boom:
        def refresh(self, on, force=False):
            raise RuntimeError("bank feed down")

    monkeypatch.setattr("focos.ledger.providers.current", lambda name=None: Boom())
    out = intraday.run_midday(datetime(2026, 9, 9, 12, 5, tzinfo=CT))
    assert not out["ok"] and "bank feed down" in out["error"]
    assert not intraday.midday_due(datetime(2026, 9, 9, 14, tzinfo=CT), None, intraday.read()["midday"]["date"])


def test_ticker_picks_the_right_job_and_stays_out_of_the_loop(initialized_home: Path, monkeypatch):
    _seed(initialized_home)
    ran: list[str] = []
    monkeypatch.setattr(intraday, "refresh", lambda *a, **k: ran.append("prices") or {"available": True})
    monkeypatch.setattr(intraday, "run_midday", lambda *a, **k: ran.append("midday") or {"ok": True})
    t = intraday.Ticker()
    assert t.enabled()
    open_time = datetime(2026, 9, 9, 10, tzinfo=CT)  # before the midday pull is due
    assert t.tick(open_time) == "prices"
    for _ in range(50):  # the supervisor ticks every two seconds; only the cadence may fire another run
        if not t._busy:
            break
        import time as _t
        _t.sleep(0.02)
    assert t.tick(open_time + timedelta(minutes=1)) is None
    assert t.tick(open_time + timedelta(minutes=16)) == "prices"
    assert ran.count("prices") == 2
    t2 = intraday.Ticker()  # the midday pull outranks a price tick until it has run for the day
    assert t2.tick(datetime(2026, 9, 9, 12, 5, tzinfo=CT)) == "midday"
    assert intraday.Ticker({"enabled": False}).tick(open_time) is None
