"""Mercury (business banking) straight from its API, for households whose Mercury accounts do not sync
through SimpleFIN Bridge. Needs a read-only API token (Mercury > Settings > API tokens) in .env as
MERCURY_TOKEN. Account and routing numbers are stripped before anything is written to the ledger."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Callable

import httpx

from ... import settings
from ..providers.base import LedgerAccount, ProviderError, PullResult
from ..providers.sqlite_store import SQLiteStore

PROVIDER = "mercury"
ENV_TOKEN = "MERCURY_TOKEN"
BASE = "https://api.mercury.com/api/v1"
SKIP_STATUSES = {"cancelled", "canceled", "failed", "reversed"}
SKIP_ACCOUNT_STATUSES = {"deleted", "archived"}
STRIP_ACCOUNT_KEYS = {"accountNumber", "routingNumber", "legalBusinessName", "dashboardLink"}
STRIP_TX_KEYS = {"details", "dashboardLink", "attachments", "counterpartyId"}


class MercuryClient:
    def __init__(self, token: str | None = None, timeout: float = 30.0):
        self.token = (token or os.environ.get(ENV_TOKEN) or "").strip()
        if not self.token:
            raise ProviderError(f"{ENV_TOKEN} is not set")
        self._c = httpx.Client(base_url=BASE, timeout=timeout,
                               headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})

    def _get(self, path: str, **params: Any) -> dict:
        r = self._c.get(path, params=params or None)
        if r.status_code in (401, 403):
            raise ProviderError(f"Mercury rejected the token ({r.status_code}); create a new read-only token")
        if r.status_code >= 400:
            raise ProviderError(f"Mercury error {r.status_code}: {r.text[:200]}")
        return r.json()

    def accounts(self) -> list[dict]:
        return self._get("/accounts").get("accounts", [])

    def transactions(self, account_id: str, start: date, end: date, limit: int = 500) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            batch = self._get(f"/account/{account_id}/transactions", start=start.isoformat(), end=end.isoformat(),
                              limit=limit, offset=offset).get("transactions", [])
            out.extend(batch)
            if len(batch) < limit:
                return out
            offset += limit


def account_id(raw_id: str) -> str:
    return f"{PROVIDER}:{raw_id}"


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def parse_account(raw: dict, asof: date) -> LedgerAccount:
    kind = str(raw.get("kind") or "checking").lower()
    subtype = "savings" if kind in ("savings", "treasury") else "checking"
    bal = _f(raw.get("currentBalance")) or 0.0
    return LedgerAccount(id=account_id(str(raw.get("id"))), provider=PROVIDER, name=str(raw.get("nickname") or raw.get("name") or raw.get("id")),
                         institution_name="Mercury", org_domain="mercury.com", currency="USD", account_type="depository",
                         subtype=subtype, classification="asset", balance=bal, balance_cents=int(round(bal * 100)),
                         available_balance=_f(raw.get("availableBalance")), balance_date=asof.isoformat())


def safe_account_raw(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if k not in STRIP_ACCOUNT_KEYS}


def parse_transactions(raw_account_id: str, txs: list[dict]) -> list[dict]:
    aid = account_id(raw_account_id)
    out = []
    for t in txs:
        status = str(t.get("status") or "").lower()
        if status in SKIP_STATUSES or not t.get("id"):
            continue
        posted = (t.get("postedAt") or t.get("createdAt") or "")[:10]
        amt = _f(t.get("amount"))
        if len(posted) != 10 or amt is None:
            continue
        payee = t.get("counterpartyNickname") or t.get("counterpartyName")
        out.append({"id": f"{aid}:{t['id']}", "posted_date": posted, "amount": amt,
                    "description": t.get("bankDescription") or payee, "payee": payee,
                    "memo": t.get("note") or t.get("externalMemo"), "pending": status == "pending",
                    "raw": {k: v for k, v in t.items() if k not in STRIP_TX_KEYS}})
    return out


class MercuryFeed:
    name = PROVIDER

    def __init__(self, store: SQLiteStore, client_factory: Callable[[], Any] | None = None, token: str | None = None):
        self.store = store
        self.token = token if token is not None else os.environ.get(ENV_TOKEN, "")
        self._factory = client_factory or (lambda: MercuryClient(self.token))
        cfg = settings.focos().get("ledger") or {}
        self.enabled = (cfg.get("mercury") or {}).get("enabled")
        self.refresh_min_hours = float(cfg.get("refresh_min_hours") or 20)
        self.history_days_initial = int(cfg.get("history_days_initial") or 365)

    def configured(self) -> bool:
        return bool(self.token.strip()) and self.enabled is not False

    def _window(self, asof: date) -> tuple[date, date]:
        last = self.store.last_pull(self.name)
        if last and last.get("end_date"):
            return min(date.fromisoformat(last["end_date"]) - timedelta(days=7), asof - timedelta(days=95)), asof
        return asof - timedelta(days=self.history_days_initial), asof

    def pull(self, asof: date, force: bool = False) -> PullResult:
        if not self.configured():
            return PullResult(ok=False, errors=[f"{ENV_TOKEN} is not set"])
        age = self.store.last_pull_age_hours(self.name)
        if not force and age is not None and age < self.refresh_min_hours:
            return PullResult(ok=True, skipped=True, accounts=len(self.store.accounts(providers=(self.name,))))
        start, end = self._window(asof)
        try:
            client = self._factory()
            raw_accounts = [a for a in client.accounts() if str(a.get("status") or "active").lower() not in SKIP_ACCOUNT_STATUSES]
            txs = {str(a["id"]): client.transactions(str(a["id"]), start, end) for a in raw_accounts}
        except Exception as e:  # noqa: BLE001
            self.store.record_pull(self.name, start.isoformat(), end.isoformat(), 0, 0, [f"{type(e).__name__}: {str(e)[:200]}"])
            return PullResult(ok=False, errors=[str(e)[:300]], start=start.isoformat(), end=end.isoformat())
        return self.ingest(raw_accounts, txs, start, end)

    def ingest(self, raw_accounts: list[dict], txs_by_account: dict[str, list[dict]], start: date, end: date) -> PullResult:
        n_new = n_upd = 0
        for raw in raw_accounts:
            acct = parse_account(raw, end)
            self.store.upsert_account(acct, raw=safe_account_raw(raw))
            self.store.upsert_balance(acct.id, end.isoformat(), acct.balance, acct.available_balance)
            new, upd = self.store.upsert_transactions(acct.id, parse_transactions(str(raw["id"]), txs_by_account.get(str(raw["id"]), [])))
            n_new += new
            n_upd += upd
        self.store.record_pull(self.name, start.isoformat(), end.isoformat(), len(raw_accounts), n_new + n_upd, [])
        return PullResult(ok=True, accounts=len(raw_accounts), transactions_new=n_new, transactions_updated=n_upd,
                          start=start.isoformat(), end=end.isoformat())
