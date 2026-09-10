"""Prices via Yahoo Finance with an on-disk fallback cache: the multi-year history the analytics need, and a
small delayed-quote fetch the intraday refresh can afford to repeat every few minutes."""
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


def quote_cache_file():
    return paths.CACHE / "quotes.json"


def fetch_quotes(symbols: list[str]) -> tuple[dict[str, dict], bool]:
    """{symbol: {"last": float, "prev_close": float|None}} plus stale.

    Deliberately small: five daily bars rather than the multi-year frame `fetch_prices` pulls, because this runs
    every few minutes. During a session Yahoo's bar for today is the in-progress one, so `last` is a delayed live
    price and the bar before it is the previous close. Yahoo failing is not an error here: the last good quotes
    come back with stale=True and the caller keeps showing them, labelled.
    """
    from .. import settings

    symbols = sorted({str(s).upper() for s in symbols if s})
    if not symbols:
        return {}, False
    try:
        px = yf.download(symbols, period="5d", interval="1d", auto_adjust=True, progress=False)["Close"]
        if isinstance(px, pd.Series):
            px = px.to_frame(symbols[0])
        px = px.dropna(how="all")
        if px.empty:
            raise RuntimeError("empty quote frame")
        out: dict[str, dict] = {}
        for s in symbols:
            if s not in px.columns:
                continue
            col = px[s].dropna()
            if col.empty:
                continue
            out[s] = {"last": float(col.iloc[-1]), "prev_close": float(col.iloc[-2]) if len(col) > 1 else None}
        if not out:
            raise RuntimeError("no quotes returned")
        cached = settings.read_json(quote_cache_file(), {}) or {}
        settings.write_json(quote_cache_file(), {**cached, **out})
        return out, False
    except Exception:
        cached = settings.read_json(quote_cache_file(), {}) or {}
        hit = {s: q for s, q in cached.items() if s in set(symbols) and isinstance(q, dict) and q.get("last")}
        return hit, True
