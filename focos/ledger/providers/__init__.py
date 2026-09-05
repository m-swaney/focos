"""Ledger providers: where bank, card, and loan data comes from. `current()` picks by focos.yml ledger.provider."""
from __future__ import annotations

from ... import settings
from .base import (BalancePoint, Holding, LedgerAccount, LedgerProvider, ManualAccountSpec, ProviderError,  # noqa: F401
                   ProviderHealth, PullResult, SyncStatus, Transaction)


def configured_name() -> str:
    return str((settings.focos().get("ledger") or {}).get("provider") or "none")


def current(name: str | None = None) -> LedgerProvider | None:
    name = name or configured_name()
    if name == "simplefin":
        from .simplefin import SimpleFINProvider
        return SimpleFINProvider()
    if name == "sure":
        from .sure import SureProvider
        return SureProvider()
    return None
