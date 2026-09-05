"""Position valuation and concentration."""
from __future__ import annotations

import pandas as pd


def value_positions(pos: pd.DataFrame, last: pd.Series) -> pd.DataFrame:
    """pos columns: account, symbol, quantity, avg_cost. Adds price/value/cost/gain/weights."""
    df = pos.copy()
    df["price"] = df["symbol"].map(last).astype(float)
    df["value"] = df["quantity"] * df["price"]
    df["cost"] = df["quantity"] * df["avg_cost"].fillna(0)
    df["gain"] = df["value"] - df["cost"]
    df["gain_pct"] = (df["gain"] / df["cost"]).where(df["cost"] > 0)
    df["weight_account"] = df["value"] / df.groupby("account")["value"].transform("sum")
    df["weight_total"] = df["value"] / df["value"].sum()
    return df.sort_values(["account", "value"], ascending=[True, False]).reset_index(drop=True)


def account_summary(df: pd.DataFrame) -> pd.DataFrame:
    acct = df.groupby("account").agg(value=("value", "sum"), cost=("cost", "sum"))
    acct["gain"] = acct["value"] - acct["cost"]
    acct["gain_pct"] = (acct["gain"] / acct["cost"]).where(acct["cost"] > 0)
    total = acct["value"].sum()
    acct["share_of_total"] = acct["value"] / total if total else 0.0
    return acct


def concentration(df: pd.DataFrame) -> dict:
    combined = df.groupby("symbol")["value"].sum().sort_values(ascending=False)
    total = combined.sum()
    w = combined / total if total else combined
    hhi = float((w ** 2).sum()) if total else 0.0
    return {
        "top1": {"symbol": w.index[0], "weight": float(w.iloc[0])} if len(w) else None,
        "top3_weight": float(w.iloc[:3].sum()),
        "top3": list(w.index[:3]),
        "top5_weight": float(w.iloc[:5].sum()),
        "hhi": hhi,
        "effective_positions": (1 / hhi) if hhi else None,
        "weights": {k: float(v) for k, v in w.items()},
    }
