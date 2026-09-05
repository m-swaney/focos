"""SimpleFIN Bridge (https://bridge.simplefin.org) as the default ledger: one setup token, no Docker. Extra
feeds (focos.ledger.feeds, e.g. Mercury) write into the same SQLite store and are pulled by the same refresh().

Protocol (https://www.simplefin.org/protocol.html): a setup token is the base64 of a claim URL; POSTing to it
once returns an access URL that embeds credentials. GET <access_url>/accounts?start-date=<unix>&end-date=<unix>
&pending=1 returns every account with balances, transactions in the window, and (for some brokerages) holdings.
"""
from __future__ import annotations

import base64
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from ... import paths, settings
from .base import (BalancePoint, Holding, LedgerAccount, ManualAccountSpec, ProviderError, ProviderHealth, PullResult,
                   SyncStatus, Transaction)
from .sqlite_store import SQLiteStore

ENV_ACCESS_URL = "SIMPLEFIN_ACCESS_URL"
SOFT_NOTICE = re.compile(r"exceeds limit|was capped|capped at", re.I)   # Bridge notices that do not fail a pull
PROVIDER = "simplefin"
PRIMARY_PROVIDERS = ("simplefin", "mercury")   # live feeds writing into the store
MANUAL_PROVIDER = "manual"


# ---------------------------------------------------------------- parsing helpers
def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(Decimal(str(v)))
    except (InvalidOperation, ValueError):
        return None


def _local_date(unix: Any) -> str | None:
    try:
        ts = float(unix)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(settings.tz()).date().isoformat()


def infer_type(name: str, hint: str = "") -> tuple[str, str | None, str]:
    """(account_type, subtype, classification) from the account name (ported from the Sure link script)."""
    t = f"{hint} {name}".lower()
    if re.search(r"credit|card|amex|american express|visa|mastercard", t):
        return "credit_card", None, "liability"
    if re.search(r"mortgage|heloc|home equity", t):
        return "loan", "mortgage", "liability"
    if re.search(r"\bloan\b|auto loan|student|financing", t):
        return "loan", None, "liability"
    if re.search(r"roth", t):
        return "investment", "roth_ira", "asset"
    if re.search(r"\bira\b|401|403b|retirement", t):
        return "investment", "retirement", "asset"
    if re.search(r"invest|broker|trading|529|hsa", t):
        return "investment", "brokerage", "asset"
    if re.search(r"saving|money market|\bmm\b|cd\b", t):
        return "depository", "savings", "asset"
    return "depository", "checking", "asset"


def account_id(raw_id: str) -> str:
    return f"{PROVIDER}:{raw_id}"


def parse_account(raw: dict, type_overrides: dict[str, tuple[str, str | None, str]] | None = None) -> LedgerAccount:
    org = raw.get("org") or {}
    aid = account_id(str(raw.get("id")))
    hint = " ".join(str(raw.get(k) or "") for k in ("type", "account_type", "subtype")) if isinstance(raw, dict) else ""
    account_type, subtype, classification = (type_overrides or {}).get(aid) or infer_type(str(raw.get("name") or ""), hint)
    bal = _num(raw.get("balance")) or 0.0
    return LedgerAccount(
        id=aid, provider=PROVIDER, name=str(raw.get("name") or raw.get("id")), institution_name=org.get("name") or org.get("domain"),
        org_domain=org.get("domain"), currency=str(raw.get("currency") or "USD"), account_type=account_type, subtype=subtype,
        classification=classification, balance=bal, balance_cents=int(round(bal * 100)),
        available_balance=_num(raw.get("available-balance")), balance_date=_local_date(raw.get("balance-date")))


def parse_transactions(raw_account: dict) -> list[dict]:
    aid = account_id(str(raw_account.get("id")))
    out = []
    for t in raw_account.get("transactions") or []:
        posted = _local_date(t.get("posted")) or _local_date(t.get("transacted_at"))
        amt = _num(t.get("amount"))
        if posted is None or amt is None or not t.get("id"):
            continue
        out.append({"id": f"{aid}:{t['id']}", "posted_date": posted, "amount": amt, "description": t.get("description"),
                    "payee": t.get("payee"), "memo": t.get("memo"), "pending": bool(t.get("pending")), "raw": t})
    return out


def parse_holdings(raw_account: dict) -> list[dict]:
    out = []
    for h in raw_account.get("holdings") or []:
        out.append({"id": h.get("id"), "symbol": (h.get("symbol") or None), "description": h.get("description"),
                    "shares": _num(h.get("shares")), "cost_basis": _num(h.get("cost_basis")),
                    "market_value": _num(h.get("market_value")), "currency": h.get("currency") or "USD"})
    return out


# ---------------------------------------------------------------- HTTP client
class SimpleFINClient:
    def __init__(self, access_url: str | None = None, timeout: float = 60.0):
        self.access_url = (access_url or "").strip()
        self.timeout = timeout

    @staticmethod
    def claim(setup_token: str, timeout: float = 30.0) -> str:
        """Exchange a one-time setup token for the access URL (which must then be stored in .env)."""
        token = setup_token.strip()
        try:
            claim_url = base64.b64decode(token + "=" * (-len(token) % 4)).decode("utf-8").strip()
        except Exception as e:  # noqa: BLE001
            raise ProviderError("setup token is not valid base64") from e
        if not claim_url.startswith("http"):
            raise ProviderError("setup token did not decode to a claim URL")
        r = httpx.post(claim_url, timeout=timeout)
        if r.status_code >= 400:
            raise ProviderError(f"claim failed ({r.status_code}): {r.text[:200]}")
        access = r.text.strip()
        if not access.startswith("http"):
            raise ProviderError("claim response was not an access URL")
        return access

    def _split(self) -> tuple[str, tuple[str, str] | None]:
        u = urlsplit(self.access_url)
        auth = (u.username or "", u.password or "") if u.username else None
        host = u.hostname or ""
        if u.port:
            host += f":{u.port}"
        clean = urlunsplit((u.scheme, host, u.path.rstrip("/"), "", ""))
        return clean, auth

    def fetch(self, start: date, end: date, pending: bool = True, balances_only: bool = False) -> dict:
        if not self.access_url:
            raise ProviderError(f"{ENV_ACCESS_URL} is not set")
        base, auth = self._split()
        params: dict[str, Any] = {"start-date": int(datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).timestamp()),
                                  "end-date": int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())}
        if pending:
            params["pending"] = 1
        if balances_only:
            params["balances-only"] = 1
        r = httpx.get(f"{base}/accounts", params=params, auth=auth, timeout=self.timeout)
        if r.status_code == 402:
            raise ProviderError("SimpleFIN Bridge subscription lapsed (402)")
        if r.status_code == 403:
            raise ProviderError("SimpleFIN access URL rejected (403); claim a new setup token")
        if r.status_code >= 400:
            raise ProviderError(f"SimpleFIN error {r.status_code}: {r.text[:200]}")
        return r.json()


# ---------------------------------------------------------------- provider
def merge_results(results: list[PullResult]) -> PullResult:
    """One PullResult for several feeds: ok only if every feed was ok, skipped only if every feed skipped."""
    starts = [r.start for r in results if r.start]
    ends = [r.end for r in results if r.end]
    return PullResult(ok=all(r.ok for r in results), skipped=all(r.skipped for r in results),
                      accounts=sum(r.accounts for r in results), transactions_new=sum(r.transactions_new for r in results),
                      transactions_updated=sum(r.transactions_updated for r in results), holdings=sum(r.holdings for r in results),
                      errors=[e for r in results for e in r.errors], warnings=[w for r in results for w in r.warnings],
                      start=min(starts) if starts else None, end=max(ends) if ends else None)


class SimpleFINProvider:
    name = PROVIDER
    refreshes_synchronously = True

    def __init__(self, store: SQLiteStore | None = None, fetcher: Callable[[date, date, bool], dict] | None = None,
                 access_url: str | None = None, feeds: list | None = None):
        import os

        self.store = store or SQLiteStore(paths.LEDGER_DB)
        self.access_url = access_url if access_url is not None else os.environ.get(ENV_ACCESS_URL, "")
        self._fetch = fetcher or (lambda s, e, bo: SimpleFINClient(self.access_url).fetch(s, e, balances_only=bo))
        cfg = settings.focos().get("ledger") or {}
        self.refresh_min_hours = float(cfg.get("refresh_min_hours") or 20)
        self.history_days_initial = int(cfg.get("history_days_initial") or 365)
        if feeds is None:
            from ..feeds import configured_feeds
            feeds = configured_feeds(self.store)
        self.feeds = feeds

    # -- health / status
    def health(self) -> ProviderHealth:
        if not self.access_url and not self.feeds:
            return ProviderHealth(ok=None, reason="no bank feed configured; paste a SimpleFIN setup token (or a Mercury token) in Setup")
        if self.access_url:
            last = self.store.last_pull(self.name, ok_only=False)
            if last and last.get("errors") not in (None, "[]") and self.store.last_pull(self.name) is None:
                return ProviderHealth(ok=False, reason=f"every pull so far failed: {last['errors'][:200]}")
        return ProviderHealth(ok=True)

    def feed_names(self) -> list[str]:
        return ([self.name] if self.access_url else []) + [f.name for f in self.feeds]

    def sync_status(self) -> SyncStatus:
        oks = [p["ts"] for n in self.feed_names() if (p := self.store.last_pull(n))]
        bads = [f"{n}: {p['errors'][:200]}" for n in self.feed_names()
                if (p := self.store.last_pull(n, ok_only=False)) and p.get("errors") not in (None, "[]")]
        return SyncStatus(provider=self.name, last_success=max(oks) if oks else None, last_error="; ".join(bads) or None,
                          accounts=len(self.store.accounts(providers=PRIMARY_PROVIDERS)),
                          transactions_window_days=95, detail={"counts": self.store.counts(), "feeds": self.feed_names()})

    # -- pull
    def _window(self, asof: date, force: bool) -> tuple[date, date]:
        last = self.store.last_pull(self.name)
        if last and last.get("end_date"):
            start = min(date.fromisoformat(last["end_date"]) - timedelta(days=7), asof - timedelta(days=95))
        else:
            start = asof - timedelta(days=self.history_days_initial)
        return start, asof

    def refresh(self, asof: date, force: bool = False) -> PullResult:
        results = []
        if self.access_url:
            results.append(self._refresh_simplefin(asof, force))
        for feed in self.feeds:
            results.append(feed.pull(asof, force=force))
        if not results:
            return PullResult(ok=False, errors=[f"{ENV_ACCESS_URL} is not set"])
        return merge_results(results)

    def _refresh_simplefin(self, asof: date, force: bool = False) -> PullResult:
        age = self.store.last_pull_age_hours(self.name)
        if not force and age is not None and age < self.refresh_min_hours:
            return PullResult(ok=True, skipped=True, accounts=len(self.store.accounts(providers=(self.name,))))
        start, end = self._window(asof, force)
        try:
            payload = self._fetch(start, end, False)
        except Exception as e:  # noqa: BLE001
            self.store.record_pull(self.name, start.isoformat(), end.isoformat(), 0, 0, [f"{type(e).__name__}: {str(e)[:200]}"])
            return PullResult(ok=False, errors=[str(e)[:300]], start=start.isoformat(), end=end.isoformat())
        return self.ingest(payload, start, end)

    def ingest(self, payload: dict, start: date, end: date) -> PullResult:
        messages = [str(e) for e in (payload.get("errors") or [])]
        warnings = [m for m in messages if SOFT_NOTICE.search(m)]
        errors = [m for m in messages if m not in warnings]
        overrides = self._type_overrides()
        n_tx_new = n_tx_upd = n_hold = 0
        accounts = payload.get("accounts") or []
        for raw in accounts:
            acct = parse_account(raw, overrides)
            self.store.upsert_account(acct, raw={k: v for k, v in raw.items() if k not in ("transactions", "holdings")})
            if acct.balance_date:
                self.store.upsert_balance(acct.id, acct.balance_date, acct.balance, acct.available_balance,
                                          int(float(raw.get("balance-date") or 0)) or None)
            new, upd = self.store.upsert_transactions(acct.id, parse_transactions(raw))
            n_tx_new += new
            n_tx_upd += upd
            holdings = parse_holdings(raw)
            if holdings:
                n_hold += self.store.upsert_holdings(acct.id, acct.balance_date or end.isoformat(), holdings)
        self.store.record_pull(self.name, start.isoformat(), end.isoformat(), len(accounts), n_tx_new + n_tx_upd, errors)
        return PullResult(ok=not errors or bool(accounts), accounts=len(accounts), transactions_new=n_tx_new,
                          transactions_updated=n_tx_upd, holdings=n_hold, errors=errors, warnings=warnings,
                          start=start.isoformat(), end=end.isoformat())

    def _type_overrides(self) -> dict[str, tuple[str, str | None, str]]:
        """Account types confirmed in the wizard live in entities.yml account_types: {<id>: {type, subtype, classification}}."""
        out = {}
        for aid, spec in ((settings.entities_v2().get("account_types") or {}).items()):
            if isinstance(spec, dict) and spec.get("type"):
                out[aid] = (spec["type"], spec.get("subtype"), spec.get("classification") or ("liability" if spec["type"] in ("credit_card", "loan") else "asset"))
        return out

    # -- reads
    def accounts(self, include_manual: bool = True) -> list[LedgerAccount]:
        provs = (*PRIMARY_PROVIDERS, MANUAL_PROVIDER) if include_manual else PRIMARY_PROVIDERS
        return self.store.accounts(providers=provs)

    def balances(self, start: date, end: date, account_ids: list[str] | None = None) -> list[BalancePoint]:
        return self.store.balances(start, end, account_ids)

    def transactions(self, start: date, end: date, account_ids: list[str] | None = None) -> list[Transaction]:
        legacy = [p for p in self.store.providers_present() if p not in PRIMARY_PROVIDERS and p != MANUAL_PROVIDER]
        return self.store.transactions(start, end, account_ids, legacy_providers=legacy,
                                       legacy_before=self.store.legacy_cutoffs(PRIMARY_PROVIDERS, legacy) if legacy else None)

    def holdings(self, asof: date | None = None) -> list[Holding]:
        return self.store.holdings(asof)

    # -- manual accounts
    def manual_accounts(self) -> list[LedgerAccount]:
        return self.store.accounts(providers=("manual",))

    def upsert_manual_account(self, spec: ManualAccountSpec) -> LedgerAccount:
        return self.store.upsert_manual_account(spec)

    def set_manual_balance(self, account_id: str, on: date, balance: float, note: str | None = None) -> None:
        self.store.upsert_balance(account_id, on.isoformat(), balance, source="manual")

    def mirror_broker_value(self, account_id: str, on: date, amount: float) -> bool:
        if not any(a.id == account_id for a in self.accounts()):
            return False
        self.store.upsert_balance(account_id, on.isoformat(), amount, source="broker")
        return True

    def backup(self, dest: Path) -> Path | None:
        return self.store.backup(dest)
