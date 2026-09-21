"""Scoring the live sandbox: what the real fills earned, matched FIFO and measured against SPY."""
import json
from pathlib import Path

from focos import paths, settings
from focos.sandbox import performance


def _order(day: str, symbol: str, side: str, qty: float, price: float, ok: bool = True) -> str:
    return json.dumps({"ts": f"{day}T11:00:00-04:00", "ok": ok,
                       "order": {"symbol": symbol, "side": side, "quantity": str(qty), "ref_id": f"{day}-{symbol}"},
                       "response": {"average_price": str(price), "state": "filled"}})


def _write_orders(lines: list[str]) -> None:
    paths.SANDBOX.mkdir(parents=True, exist_ok=True)
    (paths.SANDBOX / "orders.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_no_fills_reports_unavailable_with_the_account_still_scored(initialized_home: Path):
    out = performance.update("2026-09-20")
    assert out["available"] is False
    assert out["account"]["capital_basis"] > 0


def test_round_trip_is_scored_realized_and_the_rest_marked_open(initialized_home: Path, monkeypatch):
    _write_orders([
        _order("2026-09-21", "TQQQ", "buy", 4, 100.0),
        _order("2026-09-23", "TQQQ", "sell", 4, 110.0),      # +$40 realized
        _order("2026-09-24", "NVDA", "buy", 2, 200.0),       # still open
        _order("2026-09-24", "FAIL", "buy", 1, 50.0, ok=False),  # broker refused it; not a position
    ])
    monkeypatch.setattr(performance, "_snapshots", lambda: [
        {"date": "2026-09-21", "quotes": [{"symbol": "SPY", "last": 500.0}]},
        {"date": "2026-09-23", "quotes": [{"symbol": "SPY", "last": 505.0}]},
        {"date": "2026-09-24", "quotes": [{"symbol": "SPY", "last": 510.0}, {"symbol": "NVDA", "last": 220.0}]},
    ])
    monkeypatch.setattr(performance.live, "read", lambda: {
        "portfolio": {"total_value": 1240.0}, "positions": [{"symbol": "NVDA", "price": 220.0}]})

    out = performance.update("2026-09-24")
    assert out["available"] and out["n_closed"] == 1 and out["n_open"] == 1
    closed = out["closed"][0]
    assert closed["symbol"] == "TQQQ" and round(closed["pnl_usd"], 2) == 40.0
    assert round(closed["return_pct"], 4) == 0.1
    assert round(closed["spy_return_pct"], 4) == 0.01        # 500 -> 505 over the same window
    assert round(closed["alpha_pct"], 4) == 0.09
    assert round(out["unrealized_pnl_usd"], 2) == 40.0       # NVDA 200 -> 220 on 2 shares
    assert round(out["total_pnl_usd"], 2) == 80.0
    assert out["hit_rate"] == 1.0 and out["beat_spy_rate"] == 1.0
    assert "FAIL" not in json.dumps(out)


def test_partial_sells_close_the_oldest_lot_first(initialized_home: Path, monkeypatch):
    _write_orders([
        _order("2026-09-21", "AMD", "buy", 2, 100.0),
        _order("2026-09-22", "AMD", "buy", 2, 120.0),
        _order("2026-09-23", "AMD", "sell", 3, 130.0),
    ])
    monkeypatch.setattr(performance, "_snapshots", lambda: [
        {"date": "2026-09-23", "quotes": [{"symbol": "SPY", "last": 500.0}, {"symbol": "AMD", "last": 130.0}]}])
    monkeypatch.setattr(performance.live, "read", lambda: None)

    out = performance.update("2026-09-23")
    # the $100 lot goes first in full, then one share of the $120 lot; one share of it is left open
    assert [round(t["pnl_usd"], 2) for t in out["closed"]] == [60.0, 10.0]
    assert out["n_open"] == 1 and out["open"][0]["quantity"] == 1


def test_account_block_tracks_the_drawdown_halt(initialized_home: Path, monkeypatch):
    (initialized_home / "config" / "sandbox_rules.yml").write_text(
        "budget_usd: 1000\nmax_drawdown_pct: 0.5\nbudget_growth_per_week_usd: 0\n", encoding="utf-8")
    settings.reset()
    monkeypatch.setattr(performance.live, "read", lambda: {"portfolio": {"total_value": 400.0}})
    acct = performance._account([], performance.live.read())
    assert acct["capital_basis"] == 1000 and acct["pnl_usd"] == -600.0
    assert round(acct["drawdown_pct"], 2) == 0.6 and acct["halted"] is True

    monkeypatch.setattr(performance.live, "read", lambda: {"portfolio": {"total_value": 900.0}})
    ok = performance._account([], performance.live.read())
    assert ok["halted"] is False and round(ok["return_pct"], 2) == -0.1


def test_merge_keeps_the_paper_keys_where_older_readers_expect_them(initialized_home: Path):
    merged = performance.merge_into_scorecard({"available": True, "n_positions": 2, "hit_rate": 0.5},
                                              {"available": True, "total_pnl_usd": 12.0,
                                               "account": {"equity": 1112.0}})
    assert merged["n_positions"] == 2 and merged["hit_rate"] == 0.5
    assert merged["live"]["total_pnl_usd"] == 12.0 and merged["account"]["equity"] == 1112.0
    from focos.sandbox import paper
    assert settings.read_json(paper.scorecard_file(), {})["live"]["total_pnl_usd"] == 12.0
