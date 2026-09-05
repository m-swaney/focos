"""Extra feeds that write into the same SQLite ledger as SimpleFIN. A feed is for an institution SimpleFIN
Bridge does not carry well (Mercury business banking is the first). Each feed owns a provider prefix, its own
pull log, and never touches another feed's rows."""
from __future__ import annotations

from typing import Protocol

from ..providers.base import PullResult


class Feed(Protocol):
    name: str

    def configured(self) -> bool: ...
    def pull(self, asof, force: bool = False) -> PullResult: ...


def configured_feeds(store) -> list:
    """Every extra feed with credentials present and not disabled in focos.yml."""
    from .mercury import MercuryFeed

    out = []
    for cls in (MercuryFeed,):
        feed = cls(store)
        if feed.configured():
            out.append(feed)
    return out
