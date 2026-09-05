"""Mercury read-only client. Sure syncs Mercury natively; this is for cross-checks and CSV fallback."""
from __future__ import annotations

import os
from datetime import date, timedelta

import httpx

from .. import settings  # noqa: F401  (loads .env so MERCURY_TOKEN is available standalone)

BASE = "https://api.mercury.com/api/v1"


class MercuryClient:
    def __init__(self, token: str | None = None, timeout: float = 30.0):
        self.token = token or os.environ.get("MERCURY_TOKEN")
        if not self.token:
            raise RuntimeError("MERCURY_TOKEN not set")
        self._c = httpx.Client(base_url=BASE, timeout=timeout,
                               headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"})

    def accounts(self) -> list[dict]:
        r = self._c.get("/accounts")
        r.raise_for_status()
        return r.json().get("accounts", [])

    def transactions(self, account_id: str, start: date | None = None, end: date | None = None,
                     limit: int = 500) -> list[dict]:
        start = start or (date.today() - timedelta(days=90))
        end = end or date.today()
        out: list[dict] = []
        offset = 0
        while True:
            r = self._c.get(f"/account/{account_id}/transactions",
                            params={"start": start.isoformat(), "end": end.isoformat(), "limit": limit, "offset": offset})
            r.raise_for_status()
            batch = r.json().get("transactions", [])
            out.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return out

    def balances(self) -> list[dict]:
        return [{"id": a.get("id"), "name": a.get("name"), "kind": a.get("kind"),
                 "current_balance": a.get("currentBalance"), "available_balance": a.get("availableBalance"),
                 "last4": (a.get("accountNumber") or "")[-4:]} for a in self.accounts()]
