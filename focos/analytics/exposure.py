"""Look-through and sector exposure."""
from __future__ import annotations

import pandas as pd


def normalize_holding(name: str) -> str:
    n = name.upper().strip()
    aliases = {"GOOG": "GOOGL", "BRK.B": "BRK-B", "BRK-B": "BRK-B"}
    return aliases.get(n, n)


def pretty_sector(s: str) -> str:
    return s.replace("_", " ").title().replace("Realestate", "Real Estate")


def look_through(df: pd.DataFrame, meta: dict) -> pd.Series:
    exposure: dict[str, float] = {}
    for _, r in df.iterrows():
        s, v = r["symbol"], float(r["value"])
        m = meta.get(s, {})
        if m.get("quote_type") == "ETF" and m.get("top_holdings"):
            covered = 0.0
            for name, pct in m["top_holdings"].items():
                key = normalize_holding(name)
                exposure[key] = exposure.get(key, 0.0) + v * pct
                covered += pct
            rest = f"{s} (other holdings)"
            exposure[rest] = exposure.get(rest, 0.0) + v * max(0.0, 1 - covered)
        else:
            exposure[s] = exposure.get(s, 0.0) + v
    return pd.Series(exposure, dtype=float).sort_values(ascending=False)


def sector_exposure(df: pd.DataFrame, meta: dict) -> pd.Series:
    out: dict[str, float] = {}
    for _, r in df.iterrows():
        s, v = r["symbol"], float(r["value"])
        m = meta.get(s, {})
        if m.get("quote_type") == "ETF" and m.get("sector_weights"):
            for sec, w in m["sector_weights"].items():
                k = pretty_sector(sec)
                out[k] = out.get(k, 0.0) + v * w
        else:
            sec = m.get("sector") or "Unknown"
            out[sec] = out.get(sec, 0.0) + v
    return pd.Series(out, dtype=float).sort_values(ascending=False)


def class_weights(df: pd.DataFrame, classes: dict[str, str]) -> pd.DataFrame:
    """Per-account weights by asset class (for drift vs profile targets)."""
    d = df.copy()
    d["asset_class"] = d["symbol"].map(lambda s: classes.get(s, "individual_stocks"))
    g = d.groupby(["account", "asset_class"])["value"].sum()
    tot = d.groupby("account")["value"].sum()
    return (g / tot).rename("weight").reset_index()
