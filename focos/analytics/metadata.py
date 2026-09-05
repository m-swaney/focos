"""Security metadata (sector, ETF holdings) via Yahoo Finance, cached for 7 days."""
from __future__ import annotations

import time

import yfinance as yf

from .. import paths, settings

def cache_file():
    return paths.CACHE / "metadata.json"


TTL_SECONDS = 7 * 24 * 3600


def fetch_metadata(symbols: list[str], etf_labels: dict[str, str] | None = None) -> dict[str, dict]:
    etf_labels = etf_labels or {}
    cache: dict[str, dict] = settings.read_json(cache_file(), {}) or {}
    now = time.time()
    out: dict[str, dict] = {}
    changed = False
    for s in symbols:
        entry = cache.get(s)
        if entry and now - entry.get("_fetched_at", 0) < TTL_SECONDS:
            out[s] = entry
            continue
        entry = _fetch_one(s, s in etf_labels)
        entry["_fetched_at"] = now
        cache[s] = entry
        out[s] = entry
        changed = True
    if changed:
        settings.write_json(cache_file(), cache)
    return out


def _fetch_one(symbol: str, force_etf: bool) -> dict:
    t = yf.Ticker(symbol)
    info: dict = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    entry = {
        "quote_type": info.get("quoteType", "EQUITY"),
        "sector": info.get("sector"),
        "name": info.get("shortName") or info.get("longName") or symbol,
        "top_holdings": None,
        "sector_weights": None,
    }
    if entry["quote_type"] == "ETF" or force_etf:
        entry["quote_type"] = "ETF"
        try:
            fd = t.funds_data
            th = fd.top_holdings
            if th is not None and not th.empty:
                entry["top_holdings"] = {str(k): float(v) for k, v in th["Holding Percent"].items()}
            sw = fd.sector_weightings
            if sw:
                entry["sector_weights"] = {str(k): float(v) for k, v in sw.items()}
        except Exception:
            pass
    return entry
