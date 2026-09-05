"""No brokerage data: the pipeline runs ledger, plan, and alerts only."""
from __future__ import annotations

from . import write_snapshot
from .base import empty_snapshot


class NoneSource:
    name = "none"

    def available(self) -> tuple[bool, str | None]:
        return True, None

    def capture(self, asof: str, mode: str, run_id: str) -> dict | None:
        snap = empty_snapshot(asof, mode, self.name)
        write_snapshot(snap)
        return snap
