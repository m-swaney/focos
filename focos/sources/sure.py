"""Sure (we-promise/sure) REST client. X-Api-Key auth, 100 req/hour standard tier."""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

import httpx


class SureError(RuntimeError):
    pass


class SureClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, timeout: float = 30.0):
        self.base_url = (base_url or os.environ.get("SURE_API_URL") or "http://127.0.0.1:3000").rstrip("/")
        self.api_key = api_key or os.environ.get("SURE_API_KEY_RW") or os.environ.get("SURE_API_KEY_RO")
        if not self.api_key:
            raise SureError("no Sure API key (SURE_API_KEY_RW / SURE_API_KEY_RO)")
        self._c = httpx.Client(base_url=f"{self.base_url}/api/v1", timeout=timeout,
                               headers={"X-Api-Key": self.api_key, "Accept": "application/json"})
        self.calls = 0
        self.rate_remaining: int | None = None

    # ---- plumbing
    def _req(self, method: str, path: str, **kw) -> Any:
        r = self._c.request(method, path, **kw)
        self.calls += 1
        rem = r.headers.get("X-RateLimit-Remaining")
        if rem is not None:
            try:
                self.rate_remaining = int(rem)
            except ValueError:
                pass
        if r.status_code == 429:
            raise SureError(f"rate limited: {r.text[:200]}")
        if r.status_code >= 400:
            raise SureError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        if not r.content:
            return None
        return r.json()

    @staticmethod
    def _items(payload: Any, key: str) -> list[dict]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if key in payload and isinstance(payload[key], list):
                return payload[key]
            for v in payload.values():
                if isinstance(v, list):
                    return v
        return []

    @staticmethod
    def _has_more(payload: Any, page: int) -> bool:
        if not isinstance(payload, dict):
            return False
        pg = payload.get("pagination") or {}
        total_pages = pg.get("total_pages") or pg.get("pages")
        return bool(total_pages and page < int(total_pages))

    def _paged(self, path: str, key: str, params: dict | None = None, per_page: int = 100, max_pages: int = 20) -> list[dict]:
        out: list[dict] = []
        params = dict(params or {})
        for page in range(1, max_pages + 1):
            payload = self._req("GET", path, params={**params, "page": page, "per_page": per_page, "limit": per_page})
            items = self._items(payload, key)
            out.extend(items)
            if not items or not self._has_more(payload, page):
                break
        return out

    # ---- reads
    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/up", timeout=10)  # Rails health endpoint
            return r.status_code == 200
        except Exception:
            return False

    def accounts(self, include_disabled: bool = False) -> list[dict]:
        return self._paged("/accounts", "accounts", {"include_disabled": str(include_disabled).lower()})

    def balance_sheet(self) -> dict:
        return self._req("GET", "/balance_sheet") or {}

    def transactions_raw(self, start: date, end: date | None = None, account_ids: list[str] | None = None) -> list[dict]:
        params: dict = {"start_date": start.isoformat(), "end_date": (end or date.today()).isoformat()}
        if account_ids:
            params["account_ids[]"] = account_ids
        return self._paged("/transactions", "transactions", params)

    def transactions(self, start: date, end: date | None = None, account_ids: list[str] | None = None) -> list[dict]:
        return [normalize_transaction(t) for t in self.transactions_raw(start, end, account_ids)]

    def transfers(self) -> list[dict]:
        return self._paged("/transfers", "transfers")

    def holdings(self, account_id: str | None = None) -> list[dict]:
        params = {"account_id": account_id} if account_id else None
        return self._paged("/holdings", "holdings", params)

    def latest_sync(self) -> dict:
        return self._req("GET", "/syncs/latest") or {}

    # ---- writes (read_write key)
    def trigger_sync(self) -> Any:
        return self._req("POST", "/sync")

    def create_valuation(self, account_id: str, on: date | str, amount: float, notes: str | None = None,
                         upsert: bool = True) -> dict:
        body = {"valuation": {"account_id": account_id, "date": str(on)[:10], "amount": f"{amount:.2f}",
                              "notes": notes or "focos daily valuation", "upsert": upsert}}
        return self._req("POST", "/valuations", json=body) or {}

    def create_trade(self, account_id: str, ticker: str, side: str, qty: float, price: float, on: date | str,
                     currency: str = "USD", fee: float = 0.0) -> dict:
        body = {"trade": {"account_id": account_id, "type": side, "ticker": ticker, "qty": qty, "price": price,
                          "date": str(on)[:10], "currency": currency, "fee": fee}}
        return self._req("POST", "/trades", json=body) or {}

    def create_transaction(self, account_id: str, on: date | str, amount_abs: float, name: str, nature: str,
                           external_id: str, source: str = "focos", notes: str | None = None) -> dict:
        body = {"transaction": {"account_id": account_id, "date": str(on)[:10], "amount": f"{abs(amount_abs):.2f}",
                                "name": name, "nature": nature, "external_id": external_id, "source": source,
                                "notes": notes}}
        return self._req("POST", "/transactions", json=body) or {}


def normalize_transaction(t: dict) -> dict:
    """Sure transaction JSON -> internal shape (see focos.ledger)."""
    cents = t.get("signed_amount_cents")
    if cents is None:
        amt = float(str(t.get("amount", "0")).replace("$", "").replace(",", "") or 0)
        amt = amt if t.get("classification") == "income" else -abs(amt)
    else:
        amt = float(cents) / 100.0
    transfer = t.get("transfer") or {}
    other = transfer.get("other_account") or {}
    return {
        "id": t.get("id"),
        "date": str(t.get("date"))[:10],
        "account_id": (t.get("account") or {}).get("id"),
        "account_name": (t.get("account") or {}).get("name"),
        "account_type": str((t.get("account") or {}).get("account_type") or "").lower(),
        "amount": amt,
        "name": t.get("name"),
        "merchant": (t.get("merchant") or {}).get("name"),
        "category": (t.get("category") or {}).get("name"),
        "tags": [x.get("name") for x in (t.get("tags") or []) if isinstance(x, dict)],
        "transfer_id": transfer.get("id"),
        "other_account_id": other.get("id"),
        "external_id": t.get("external_id"),
        "source": t.get("source"),
    }


def default_window(days: int = 90) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=days), end
