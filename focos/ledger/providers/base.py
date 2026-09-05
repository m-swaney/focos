"""Ledger provider interface and the normalized models every provider returns.

`LedgerAccount.as_row()` and `Transaction.model_dump()` reproduce the plain-dict shapes that
focos.ledger.entities / netting / consolidate already consume, so those modules stay provider-agnostic.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

AccountType = Literal["depository", "credit_card", "loan", "investment", "property", "vehicle", "other"]


class ProviderError(RuntimeError):
    pass


class LedgerAccount(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str                                  # "simplefin:<id>" | "sure:<uuid>" | "manual:<key>"
    provider: str
    name: str
    institution_name: str | None = None
    org_domain: str | None = None
    currency: str = "USD"
    account_type: str = "other"              # AccountType for simplefin/manual; Sure's own labels pass through
    subtype: str | None = None
    classification: Literal["asset", "liability"] = "asset"
    balance: float = 0.0
    balance_cents: int = 0
    available_balance: float | None = None
    balance_date: str | None = None          # YYYY-MM-DD
    is_manual: bool = False
    aliases: list[str] = []

    def as_row(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "balance": self.balance, "balance_cents": self.balance_cents,
                "classification": self.classification, "account_type": self.account_type, "subtype": self.subtype,
                "institution_name": self.institution_name, "currency": self.currency, "source": self.provider,
                "balance_date": self.balance_date, "is_manual": self.is_manual}


class Transaction(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    date: str
    account_id: str
    account_name: str | None = None
    account_type: str = ""
    amount: float                            # signed: + inflow, - outflow
    name: str | None = None
    merchant: str | None = None
    category: str | None = None
    tags: list[str] = []
    transfer_id: str | None = None
    other_account_id: str | None = None
    external_id: str | None = None
    source: str | None = None
    pending: bool = False


class BalancePoint(BaseModel):
    account_id: str
    date: str
    balance: float
    available: float | None = None


class Holding(BaseModel):
    model_config = ConfigDict(extra="allow")
    account_id: str
    date: str
    symbol: str | None = None
    description: str | None = None
    shares: float = 0.0
    cost_basis: float | None = None
    market_value: float | None = None
    currency: str = "USD"


class SyncStatus(BaseModel):
    provider: str
    last_success: str | None = None
    last_error: str | None = None
    accounts: int = 0
    transactions_window_days: int = 0
    detail: dict = {}


class ProviderHealth(BaseModel):
    ok: bool | None                           # None = not configured (mirrors the old stage.py contract)
    reason: str | None = None


class PullResult(BaseModel):
    ok: bool
    skipped: bool = False
    accounts: int = 0
    transactions_new: int = 0
    transactions_updated: int = 0
    holdings: int = 0
    errors: list[str] = []
    warnings: list[str] = []                  # provider notices that did not stop the pull (e.g. range capped)
    start: str | None = None
    end: str | None = None


class ManualAccountSpec(BaseModel):
    key: str
    name: str
    entity: str = "personal"
    account_type: AccountType = "other"
    subtype: str | None = None
    classification: Literal["asset", "liability"] = "asset"
    balance: float = 0.0
    currency: str = "USD"
    notes: str | None = None


class LedgerProvider(Protocol):
    name: str
    refreshes_synchronously: bool           # True: refresh() pulls data before reads; False: it only nudges an external sync

    def health(self) -> ProviderHealth: ...
    def refresh(self, asof: date, force: bool = False) -> PullResult: ...
    def accounts(self, include_manual: bool = True) -> list[LedgerAccount]: ...
    def balances(self, start: date, end: date, account_ids: list[str] | None = None) -> list[BalancePoint]: ...
    def transactions(self, start: date, end: date, account_ids: list[str] | None = None) -> list[Transaction]: ...
    def holdings(self, asof: date | None = None) -> list[Holding]: ...
    def sync_status(self) -> SyncStatus: ...
    def manual_accounts(self) -> list[LedgerAccount]: ...
    def upsert_manual_account(self, spec: ManualAccountSpec) -> LedgerAccount: ...
    def set_manual_balance(self, account_id: str, on: date, balance: float, note: str | None = None) -> None: ...
    def mirror_broker_value(self, account_id: str, on: date, amount: float) -> bool: ...
    def backup(self, dest: Path) -> Path | None: ...


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
