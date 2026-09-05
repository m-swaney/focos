"""Mirror brokerage values (and, for Sure, filled sandbox trades) into the ledger so net worth includes them
without double counting. Replaces sure_push.py."""
from __future__ import annotations

from datetime import date

from .. import paths, settings
from .providers.base import LedgerProvider


def _pushed_file():
    return paths.SANDBOX / "pushed_orders.json"


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
        out.append({"account": a["key"], "ledger_account_id": lid, "sure_account_id": lid.split(":", 1)[-1], "amount": total, "ok": ok})
    return out


def mirror_trades(provider: LedgerProvider, snapshot: dict) -> list[dict]:
    """Filled sandbox orders become ledger trades when the provider supports it (Sure). Idempotent via a local log."""
    mirror = getattr(provider, "mirror_trade", None)
    if mirror is None:
        return []
    sandbox_keys = settings.accounts_by_role("sandbox")
    if not sandbox_keys:
        return []
    entry = settings.brokerage_entry(sandbox_keys[0]) or {}
    lid = entry.get("ledger_account_id")
    if not lid:
        return []
    pushed: dict = settings.read_json(_pushed_file(), {}) or {}
    acct = next((a for a in snapshot.get("accounts", []) if a["key"] == sandbox_keys[0]), None)
    out = []
    for o in (acct or {}).get("recent_orders", []) or []:
        oid = str(o.get("id") or "")
        if not oid or oid in pushed or str(o.get("state", "")).lower() != "filled":
            continue
        qty, price = o.get("quantity"), o.get("average_price")
        if not qty or not price or not o.get("symbol"):
            continue
        side = "buy" if str(o.get("side", "")).lower() == "buy" else "sell"
        try:
            mirror(lid, o["symbol"], side, float(qty), float(price), str(o.get("created_at"))[:10])
        except Exception as e:  # noqa: BLE001
            out.append({"order_id": oid, "symbol": o["symbol"], "error": str(e)[:200]})
            continue
        pushed[oid] = {"symbol": o["symbol"], "side": side, "qty": qty, "price": price}
        out.append({"order_id": oid, "symbol": o["symbol"]})
    settings.write_json(_pushed_file(), pushed)
    return out
