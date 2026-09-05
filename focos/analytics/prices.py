"""Historical prices via Yahoo Finance with an on-disk fallback cache."""
from __future__ import annotations

import pickle

import pandas as pd
import yfinance as yf

from .. import paths

def cache_file():
    return paths.CACHE / "prices.pkl"




def fetch_prices(symbols: list[str], years: int) -> tuple[pd.DataFrame, bool]:
    """Return (close prices, stale). stale=True means Yahoo failed and cached data was used."""
    symbols = sorted(set(symbols))
    try:
        px = yf.download(symbols, period=f"{years}y", auto_adjust=True, progress=False)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(symbols[0])
        px = px.dropna(how="all")
        if px.empty:
            raise RuntimeError("empty price frame")
        paths.CACHE.mkdir(parents=True, exist_ok=True)
        with cache_file().open("wb") as f:
            pickle.dump(px, f)
        return px, False
    except Exception:
        if cache_file().exists():
            with cache_file().open("rb") as f:
                cached: pd.DataFrame = pickle.load(f)
            missing = [s for s in symbols if s not in cached.columns]
            if not missing:
                return cached[symbols], True
        raise
