"""Mirror brokerage values into the ledger for brokerage entries that name a ledger account, so net worth
includes them exactly once (consolidate.broker_in_ledger decides per account)."""
from __future__ import annotations

from datetime import date

from .. import settings
from .providers.base import LedgerProvider


def push_values(provider: LedgerProvider, snapshot: dict) -> list[dict]:
    """One balance point per brokerage account that names a ledger_account_id, for the snapshot date."""
    on = date.fromisoformat(snapshot["date"])
    targets = {a["key"]: a.get("ledger_account_id") for a in settings.brokerage() if a.get("ledger_account_id")}
    out = []
    for a in snapshot.get("accounts", []):
        lid = targets.get(a["key"])
        total = (a.get("portfolio") or {}).get("total_value")
        if not lid or total is None:
            continue
        try:
            ok = provider.mirror_broker_value(lid, on, float(total))
        except Exception as e:  # noqa: BLE001
            out.append({"account": a["key"], "ledger_account_id": lid, "amount": total, "ok": False, "error": str(e)[:200]})
            continue
        out.append({"account": a["key"], "ledger_account_id": lid, "amount": total, "ok": ok})
    return out
