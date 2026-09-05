import pandas as pd

from focos.analytics import exposure, tax, valuation
from focos.run import claude_io


def test_valuation_and_concentration():
    pos = pd.DataFrame([
        {"account": "individual", "symbol": "NVDA", "quantity": 10, "avg_cost": 100.0},
        {"account": "individual", "symbol": "SPY", "quantity": 1, "avg_cost": 700.0},
        {"account": "roth", "symbol": "SPY", "quantity": 1, "avg_cost": 700.0},
    ])
    last = pd.Series({"NVDA": 200.0, "SPY": 800.0})
    df = valuation.value_positions(pos, last)
    assert df["value"].sum() == 3600.0
    c = valuation.concentration(df)
    assert c["top1"]["symbol"] == "NVDA"
    assert abs(c["top1"]["weight"] - 2000 / 3600) < 1e-9
    acct = valuation.account_summary(df)
    assert acct.loc["roth", "value"] == 800.0


def test_look_through_and_sectors():
    df = pd.DataFrame([
        {"symbol": "NVDA", "value": 100.0},
        {"symbol": "VUG", "value": 100.0},
    ])
    meta = {
        "NVDA": {"quote_type": "EQUITY", "sector": "Technology"},
        "VUG": {"quote_type": "ETF", "top_holdings": {"NVDA": 0.1, "AAPL": 0.1},
                "sector_weights": {"technology": 0.5, "healthcare": 0.5}},
    }
    lt = exposure.look_through(df, meta)
    assert lt["NVDA"] == 110.0
    assert lt["VUG (other holdings)"] == 80.0
    sec = exposure.sector_exposure(df, meta)
    assert sec["Technology"] == 150.0 and sec["Healthcare"] == 50.0


def test_tax_from_lots_crossing_and_harvest():
    from datetime import date
    today = date(2026, 9, 2)
    lots = [
        {"symbol": "NVDA", "quantity": 1, "cost_per_share": 50, "open_date": "2025-09-10", "term": "st"},  # crosses ~Sep 11
        {"symbol": "NVDA", "quantity": 1, "cost_per_share": 40, "open_date": "2024-01-01", "term": "lt"},
        {"symbol": "TSLA", "quantity": 1, "cost_per_share": 400, "open_date": "2026-06-01", "term": "st"},
    ]
    last = pd.Series({"NVDA": 220.0, "TSLA": 350.0})
    t = tax.from_lots(lots, last, today=today)
    assert t["totals"]["lots"] == 3
    assert t["crossing_to_lt"][0]["symbol"] == "NVDA"
    assert t["harvestable"][0]["symbol"] == "TSLA" and t["harvestable"][0]["loss"] == -50.0


def test_extract_json_prefers_fence():
    text = 'blah {"a": 1} more\n```json\n{"summary_line": "ok", "alerts": []}\n```\n'
    assert claude_io.extract_json(text)["summary_line"] == "ok"
    assert claude_io.extract_json('{"x": 2}')["x"] == 2
