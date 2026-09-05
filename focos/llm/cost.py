from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .base import Usage


@lru_cache(maxsize=1)
def table() -> dict:
    return yaml.safe_load((Path(__file__).parent / "pricing.yml").read_text(encoding="utf-8")) or {}


def rates(provider: str, model: str) -> dict | None:
    prov = table().get(provider) or {}
    best = None
    for prefix, r in prov.items():
        if model.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, r)
    return best[1] if best else None


def estimate(provider: str, model: str, usage: Usage) -> float | None:
    r = rates(provider, model)
    if not r:
        return None
    cached = usage.cache_read_tokens
    uncached = max(0, usage.input_tokens - cached) if usage.cache_read_tokens and usage.input_tokens >= cached else usage.input_tokens
    total = (uncached * float(r.get("input", 0)) + cached * float(r.get("cache_read", r.get("input", 0)))
             + usage.cache_write_tokens * float(r.get("input", 0)) * 1.25
             + usage.output_tokens * float(r.get("output", 0))) / 1_000_000
    return round(total, 6)


def estimate_tokens(text: str) -> int:
    """Rough (chars / 4); good enough for fitting a context bundle under a budget."""
    return max(1, len(text) // 4)
