from pathlib import Path

import pytest
import yaml

from focos import holdings, settings
from focos.holdings.base import SourceError
from focos.holdings.csv_source import CSVSource
from focos.sources import robinhood_snapshot as rh

CSV = "account_key,symbol,quantity,avg_cost,price\nbrk,VTI,10,200,\nbrk,aapl,2,150,180\nira,VXUS,5,55,\nbrk,ZERO,0,1,\n"


def fake_prices(symbols):
    return {"VTI": (250.0, 245.0), "VXUS": (60.0, 60.0)}


def test_csv_capture_builds_snapshot(initialized_home: Path):
    (initialized_home / "config" / "accounts.yml").write_text(yaml.safe_dump({"version": 2, "brokerage": [
        {"key": "brk", "label": "Brokerage", "role": "taxable"}, {"key": "ira", "label": "Roth", "role": "roth_ira"}]}))
    settings.reset()
    (initialized_home / "data" / "holdings.csv").write_text(CSV, encoding="utf-8")
    src = CSVSource(price_fetcher=fake_prices)
    assert src.available() == (True, None)
    snap = src.capture("2026-03-01", "daily", "t")
    assert snap["source"] == "csv" and snap["total_value"] == 10 * 250 + 2 * 180 + 5 * 60
    keys = {a["key"]: a for a in snap["accounts"]}
    assert keys["brk"]["nickname"] == "Brokerage" and keys["brk"]["brokerage_account_type"] == "taxable"
    assert [p["symbol"] for p in keys["brk"]["positions"]] == ["VTI", "AAPL"]  # value desc, uppercased, zero-qty dropped
    vti = keys["brk"]["positions"][0]
    assert vti["price"] == 250.0 and abs(vti["day_change_pct"] - (250 / 245 - 1)) < 1e-9
    assert keys["ira"]["agentic_allowed"] is False
    assert {q["symbol"] for q in snap["quotes"]} == {"VTI", "AAPL", "VXUS"}
    assert (initialized_home / "state" / "snapshots" / "holdings" / "2026-03-01.json").exists()
    cur, prev = holdings.latest_two()
    assert cur["date"] == "2026-03-01" and prev is None
    df = rh.positions_frame(cur)
    assert set(df["symbol"]) == {"VTI", "AAPL", "VXUS"}
    assert rh.live_prices(cur)["AAPL"] == 180.0


def test_csv_missing_price_is_noted_not_fatal(initialized_home: Path):
    (initialized_home / "data" / "holdings.csv").write_text("account_key,symbol,quantity,avg_cost\nbrk,XYZ,1,1\n")
    snap = CSVSource(price_fetcher=lambda s: {}).capture("2026-03-01", "daily", "t")
    assert "no price for XYZ" in snap["notes"]
    assert snap["accounts"][0]["positions"][0]["value"] is None


def test_csv_bad_columns(initialized_home: Path):
    (initialized_home / "data" / "holdings.csv").write_text("ticker,qty\nX,1\n")
    with pytest.raises(SourceError):
        CSVSource(price_fetcher=fake_prices).capture("2026-03-01", "daily", "t")


def test_csv_unavailable_when_absent(initialized_home: Path):
    ok, why = CSVSource().available()
    assert not ok and "holdings.csv" in why


def test_none_source_and_factory(initialized_home: Path):
    src = holdings.current("none")
    snap = src.capture("2026-03-02", "daily", "t")
    assert snap["accounts"] == [] and snap["total_value"] is None
    assert holdings.current("csv").name == "csv"
    assert holdings.current().name == "none"  # template default


def test_snapshot_files_merge_legacy_folder(initialized_home: Path):
    legacy = initialized_home / "state" / "snapshots" / "robinhood"
    legacy.mkdir(parents=True)
    (legacy / "2026-01-01.json").write_text('{"date": "2026-01-01", "accounts": []}')
    (legacy / "2026-01-02.json").write_text('{"date": "2026-01-02", "accounts": [], "legacy": true}')
    (initialized_home / "state" / "snapshots" / "holdings" / "2026-01-02.json").write_text('{"date": "2026-01-02", "accounts": [], "legacy": false}')
    files = holdings.snapshot_files()
    assert [f.name for f in files] == ["2026-01-01.json", "2026-01-02.json"]
    assert "holdings" in files[-1].parts  # new folder wins on the same date
