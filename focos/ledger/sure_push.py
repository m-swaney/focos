"""Push Robinhood valuations (and Agentic trades) into Sure. Superseded by focos.ledger.broker_mirror; kept for
the `focos sure` commands."""
from __future__ import annotations

from .. import paths, settings
from ..sources.sure import SureClient

def pushed_file():
    return paths.SANDBOX / "pushed_orders.json"




def _sure_ids_by_key() -> dict[str, str]:
    """brokerage key -> Sure account uuid, from accounts.yml ledger_account_id ("sure:<uuid>")."""
    out = {}
    for a in settings.brokerage():
        lid = str(a.get("ledger_account_id") or "")
        if lid.startswith("sure:"):
            out[a["key"]] = lid[len("sure:"):]
    return out


def push_valuations(client: SureClient, snapshot: dict) -> list[dict]:
    """One valuation per mapped Robinhood account, upserted by date."""
    mapping = _sure_ids_by_key()
    results = []
    for a in snapshot.get("accounts", []):
        sid = mapping.get(a["key"])
        total = (a.get("portfolio") or {}).get("total_value")
        if not sid or total is None:
            continue
        resp = client.create_valuation(sid, snapshot["date"], float(total), notes=f"focos {snapshot['date']} snapshot")
        results.append({"account": a["key"], "sure_account_id": sid, "amount": total, "ok": bool(resp)})
    return results


def mirror_agentic_trades(client: SureClient, snapshot: dict) -> list[dict]:
    """Create Sure trades for filled Agentic orders not pushed before (idempotent via local ledger)."""
    sandbox_keys = settings.accounts_by_role("sandbox")
    sid = _sure_ids_by_key().get(sandbox_keys[0]) if sandbox_keys else None
    if not sid:
        return []
    pushed: dict = settings.read_json(pushed_file(), {}) or {}
    out = []
    agentic = next((a for a in snapshot.get("accounts", []) if a.get("agentic_allowed")), None)
    for o in (agentic or {}).get("recent_orders", []) or []:
        oid = str(o.get("id") or "")
        if not oid or oid in pushed or str(o.get("state", "")).lower() != "filled":
            continue
        qty, price = o.get("quantity"), o.get("average_price")
        if not qty or not price or not o.get("symbol"):
            continue
        client.create_trade(sid, o["symbol"], "buy" if str(o.get("side", "")).lower() == "buy" else "sell",
                            float(qty), float(price), str(o.get("created_at"))[:10])
        pushed[oid] = {"symbol": o["symbol"], "side": o.get("side"), "qty": qty, "price": price}
        out.append({"order_id": oid, "symbol": o["symbol"]})
    settings.write_json(pushed_file(), pushed)
    return out
