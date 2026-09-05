"""Tax-lot analysis for the taxable account."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def from_lots(lots: list[dict], last: pd.Series, today: date | None = None, horizon_days: int = 30) -> dict:
    """lots: [{symbol, quantity, cost_per_share, open_date, term}], term 'st'|'lt'."""
    today = today or date.today()
    if not lots:
        return {"available": False, "by_symbol": [], "crossing_to_lt": [], "harvestable": [], "totals": {}}
    df = pd.DataFrame(lots)
    df["open_date"] = pd.to_datetime(df["open_date"]).dt.date
    df["cost_per_share"] = pd.to_numeric(df["cost_per_share"], errors="coerce")
    df["price"] = df["symbol"].map(last).astype(float)
    df["cost"] = df["quantity"] * df["cost_per_share"]
    df["value"] = df["quantity"] * df["price"]
    df["gain"] = df["value"] - df["cost"]
    df["lt_date"] = df["open_date"].map(lambda d: d + timedelta(days=366))
    df["is_lt"] = df["term"].str.lower().eq("lt")

    by_symbol = []
    for sym, g in df.groupby("symbol"):
        st, lt = g[~g["is_lt"]], g[g["is_lt"]]
        by_symbol.append({
            "symbol": sym,
            "st_shares": float(st["quantity"].sum()), "st_cost": float(st["cost"].sum()), "st_gain": float(st["gain"].sum()),
            "lt_shares": float(lt["quantity"].sum()), "lt_cost": float(lt["cost"].sum()), "lt_gain": float(lt["gain"].sum()),
        })
    by_symbol.sort(key=lambda r: -(r["st_gain"] + r["lt_gain"]))

    soon = df[(~df["is_lt"]) & (df["lt_date"] > today) & (df["lt_date"] <= today + timedelta(days=horizon_days))]
    crossing = [{"symbol": r.symbol, "quantity": float(r.quantity), "gain": float(r.gain), "lt_on": str(r.lt_date)}
                for r in soon.itertuples()]

    losses = df[df["gain"] < 0].groupby("symbol").agg(quantity=("quantity", "sum"), loss=("gain", "sum"),
                                                       lots=("gain", "size")).reset_index()
    harvestable = [{"symbol": r.symbol, "quantity": float(r.quantity), "loss": float(r.loss), "lots": int(r.lots)}
                   for r in losses.sort_values("loss").itertuples()]

    st_gain = float(df.loc[~df["is_lt"], "gain"].sum())
    lt_gain = float(df.loc[df["is_lt"], "gain"].sum())
    return {
        "available": True,
        "asof": str(today),
        "by_symbol": by_symbol,
        "crossing_to_lt": crossing,
        "harvestable": harvestable,
        "totals": {
            "st_gain": st_gain, "lt_gain": lt_gain,
            "lt_share_of_gain": (lt_gain / (st_gain + lt_gain)) if (st_gain + lt_gain) else None,
            "lots": int(len(df)),
        },
    }


def from_summary_csv(path, last: pd.Series) -> dict:
    """Legacy fallback: data/tax_lot_summary.csv with st/lt shares and cost per symbol."""
    t = pd.read_csv(path)
    t["price"] = t["symbol"].map(last).astype(float)
    t["st_gain"] = t["st_shares"] * t["price"] - t["st_cost"]
    t["lt_gain"] = t["lt_shares"] * t["price"] - t["lt_cost"]
    rows = t.sort_values("lt_gain", ascending=False)
    st_gain, lt_gain = float(t["st_gain"].sum()), float(t["lt_gain"].sum())
    return {
        "available": True,
        "approximate": True,
        "by_symbol": [{k: (float(v) if isinstance(v, (int, float)) else v) for k, v in r.items()
                       if k in ("symbol", "st_shares", "st_cost", "st_gain", "lt_shares", "lt_cost", "lt_gain")}
                      for r in rows.to_dict("records")],
        "crossing_to_lt": [],
        "harvestable": [],
        "totals": {"st_gain": st_gain, "lt_gain": lt_gain,
                   "lt_share_of_gain": (lt_gain / (st_gain + lt_gain)) if (st_gain + lt_gain) else None},
    }
