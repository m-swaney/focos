"""Self-hosted Sure (we-promise/sure) behind the LedgerProvider interface. Kept for households that already run
it; new installs use SimpleFIN directly. Manual accounts under Sure stay inside Sure."""
from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

from ... import paths, settings
from ...sources.sure import SureClient, SureError, normalize_transaction
from .base import (BalancePoint, Holding, LedgerAccount, ManualAccountSpec, ProviderHealth, PullResult, SyncStatus,
                   Transaction)

PROVIDER = "sure"


def account_id(uuid: str) -> str:
    return f"{PROVIDER}:{uuid}"


def bare(aid: str) -> str:
    return aid.split(":", 1)[1] if aid.startswith(f"{PROVIDER}:") else aid


class SureProvider:
    name = PROVIDER
    refreshes_synchronously = False

    def __init__(self, client: SureClient | None = None):
        self._client = client
        self.calls = 0

    @property
    def client(self) -> SureClient:
        if self._client is None:
            self._client = SureClient()
        return self._client

    def _rw(self) -> bool:
        return bool(os.environ.get("SURE_API_KEY_RW"))

    def health(self) -> ProviderHealth:
        if not (os.environ.get("SURE_API_KEY_RW") or os.environ.get("SURE_API_KEY_RO")):
            return ProviderHealth(ok=None, reason="set SURE_API_KEY_RW in .env after creating a key in Sure")
        try:
            if not self.client.health():
                return ProviderHealth(ok=False, reason=f"Sure not reachable at {self.client.base_url}")
        except SureError as e:
            return ProviderHealth(ok=False, reason=str(e)[:200])
        return ProviderHealth(ok=True)

    def refresh(self, asof: date, force: bool = False) -> PullResult:
        """Sure syncs its own connections; this just asks it to do so now (needs the read-write key)."""
        if not self._rw():
            return PullResult(ok=True, skipped=True)
        try:
            self.client.trigger_sync()
        except SureError as e:
            return PullResult(ok=False, errors=[str(e)[:200]])
        return PullResult(ok=True)

    def accounts(self, include_manual: bool = True) -> list[LedgerAccount]:
        out = []
        for a in self.client.accounts():
            from ..entities import money

            bal = money(a)
            out.append(LedgerAccount(id=account_id(str(a.get("id"))), provider=PROVIDER, name=str(a.get("name") or ""),
                                     institution_name=a.get("institution_name"), org_domain=a.get("institution_domain"),
                                     currency=str(a.get("currency") or "USD"), account_type=str(a.get("account_type") or "other"),
                                     subtype=a.get("subtype"), classification=("liability" if a.get("classification") == "liability" else "asset"),
                                     balance=bal, balance_cents=int(round(bal * 100)),
                                     available_balance=money(a, "cash_balance") if a.get("cash_balance") is not None else None,
                                     balance_date=str(a.get("updated_at") or "")[:10] or None, is_manual=False,
                                     raw=a))
        return out

    def balance_sheet(self) -> dict:
        try:
            return self.client.balance_sheet()
        except SureError:
            return {}

    def balances(self, start: date, end: date, account_ids: list[str] | None = None) -> list[BalancePoint]:
        return []  # Sure keeps its own history; the daily ledger snapshots under state/ carry ours

    def transactions(self, start: date, end: date, account_ids: list[str] | None = None) -> list[Transaction]:
        ids = [bare(i) for i in account_ids] if account_ids else None
        out = []
        for t in self.client.transactions(start, end, ids):
            t["id"] = f"{PROVIDER}:{t['id']}"
            if t.get("account_id"):
                t["account_id"] = account_id(str(t["account_id"]))
            if t.get("other_account_id"):
                t["other_account_id"] = account_id(str(t["other_account_id"]))
            out.append(Transaction(**t))
        return out

    def holdings(self, asof: date | None = None) -> list[Holding]:
        try:
            rows = self.client.holdings()
        except SureError:
            return []
        out = []
        for h in rows:
            out.append(Holding(account_id=account_id(str((h.get("account") or {}).get("id") or h.get("account_id") or "")),
                               date=str(h.get("date") or (asof or date.today()))[:10], symbol=h.get("ticker") or h.get("symbol"),
                               description=h.get("name"), shares=float(h.get("qty") or h.get("quantity") or 0),
                               cost_basis=None, market_value=float(str(h.get("amount") or 0).replace("$", "").replace(",", "") or 0)))
        return out

    def sync_status(self) -> SyncStatus:
        try:
            s = self.client.latest_sync() or {}
        except SureError as e:
            return SyncStatus(provider=PROVIDER, last_error=str(e)[:200])
        return SyncStatus(provider=PROVIDER, last_success=str(s.get("completed_at") or s.get("created_at") or "") or None,
                          last_error=s.get("error"), transactions_window_days=95, detail=s)

    def manual_accounts(self) -> list[LedgerAccount]:
        return [a for a in self.accounts() if str(a.account_type).lower() in ("property", "vehicle", "other_asset", "other_liability")]

    def upsert_manual_account(self, spec: ManualAccountSpec) -> LedgerAccount:
        raise NotImplementedError("create manual accounts in the Sure UI (or switch the ledger provider to simplefin)")

    def set_manual_balance(self, account_id_: str, on: date, balance: float, note: str | None = None) -> None:
        self.client.create_valuation(bare(account_id_), on, balance, notes=note or "focos manual balance")

    def mirror_broker_value(self, account_id_: str, on: date, amount: float) -> bool:
        if not self._rw():
            return False
        return bool(self.client.create_valuation(bare(account_id_), on, amount, notes=f"focos {on} snapshot"))

    def mirror_trade(self, account_id_: str, symbol: str, side: str, qty: float, price: float, on: str) -> bool:
        if not self._rw():
            return False
        return bool(self.client.create_trade(bare(account_id_), symbol, side, qty, price, on))

    def backup(self, dest: Path) -> Path | None:
        """pg_dump through docker compose when the stack lives under <home>/<compose_dir>."""
        cfg = ((settings.focos().get("ledger") or {}).get("sure") or {})
        compose_dir = paths.HOME / (cfg.get("compose_dir") or "sure")
        env_file = compose_dir / ".env"
        if not env_file.exists() or not shutil.which("docker"):
            return None
        kv = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
        user, db = kv.get("POSTGRES_USER", "").strip(), kv.get("POSTGRES_DB", "").strip()
        if not user or not db:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            subprocess.run(["docker", "compose", "exec", "-T", "db", "pg_dump", "-U", user, db], cwd=compose_dir,
                           stdout=f, stderr=subprocess.DEVNULL, check=True, timeout=600)
        return dest
