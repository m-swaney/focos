from focos.run import diff as diff_mod
from focos.sources import robinhood_snapshot as rh

ACCOUNTS_CFG = {"robinhood": {"individual": {"last4": "1111"}, "roth": {"last4": "2222"}, "agentic": {"last4": "3333"}}}

RAW = {
    "accounts": [
        {"account_number": "90001111", "brokerage_account_type": "individual", "agentic_allowed": False,
         "portfolio": {"total_value": 1000.0, "cash": 10.0, "buying_power": 10.0},
         "equity_positions": [{"symbol": "NVDA", "quantity": 2.0, "average_buy_price": 100.0},
                              {"symbol": "SPY", "quantity": 1.0, "average_buy_price": 500.0}]},
        {"account_number": "90003333", "brokerage_account_type": "individual", "agentic_allowed": True,
         "nickname": "Agentic", "portfolio": {"total_value": 0.0, "cash": 0.0, "buying_power": 0.0},
         "equity_positions": []},
    ],
    "quotes": [{"symbol": "NVDA", "last_trade_price": 220.0, "previous_close": 200.0},
               {"symbol": "SPY", "last_trade_price": 760.0, "previous_close": 758.0}],
    "tax_lots": [{"account_number": "90001111", "symbol": "NVDA", "quantity": 1.0, "cost_per_share": 50.0,
                  "open_date": "2024-01-01", "term": "lt"}],
}


def test_validate_and_normalize_masks_numbers():
    assert rh.validate(RAW) == []
    snap = rh.normalize(RAW, "2026-09-02", "daily", ACCOUNTS_CFG)
    keys = [a["key"] for a in snap["accounts"]]
    assert keys == ["individual", "agentic"]
    assert all("account_number" not in a for a in snap["accounts"])
    assert snap["accounts"][0]["last4"] == "1111"
    nvda = next(p for p in snap["accounts"][0]["positions"] if p["symbol"] == "NVDA")
    assert nvda["value"] == 440.0
    assert snap["accounts"][0]["positions"][0]["symbol"] == "SPY"  # sorted by value desc
    assert abs(nvda["day_change_pct"] - 0.10) < 1e-9
    assert snap["tax_lots"][0]["account"] == "individual"
    assert "account_number" not in snap["tax_lots"][0]


def test_positions_frame_and_diff():
    prev = rh.normalize(RAW, "2026-09-01", "daily", ACCOUNTS_CFG)
    raw2 = {**RAW, "accounts": [dict(RAW["accounts"][0]), dict(RAW["accounts"][1])]}
    raw2["accounts"][0] = {**raw2["accounts"][0], "portfolio": {"total_value": 1100.0, "cash": 5.0, "buying_power": 5.0},
                           "equity_positions": [{"symbol": "NVDA", "quantity": 2.5, "average_buy_price": 110.0},
                                                {"symbol": "AMD", "quantity": 1.0, "average_buy_price": 400.0}]}
    raw2["quotes"] = raw2["quotes"] + [{"symbol": "AMD", "last_trade_price": 450.0, "previous_close": 440.0}]
    cur = rh.normalize(raw2, "2026-09-02", "daily", ACCOUNTS_CFG)
    df = rh.positions_frame(cur)
    assert set(df["symbol"]) == {"NVDA", "AMD"}
    d = diff_mod.diff(cur, prev, big_move_pct=5.0)
    assert d["total_change"] == 100.0
    assert [p["symbol"] for p in d["new_positions"]] == ["AMD"]
    assert [p["symbol"] for p in d["closed_positions"]] == ["SPY"]
    assert d["quantity_changes"][0]["symbol"] == "NVDA"
    assert d["movers"][0]["symbol"] == "NVDA"
