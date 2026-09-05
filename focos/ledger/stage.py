"""Stage B sub-step: refresh the ledger provider, mirror brokerage values, build consolidated/entities JSON.

Never raises: returns {"ok": True|False|None, ...} so the rest of the pipeline continues without a ledger.
"""
from __future__ import annotations

from datetime import date, timedelta

from .. import paths, settings
from . import broker_mirror, consolidate, providers

WINDOW_DAYS = 95


def _unavailable(reason: str, asof: str) -> dict:
    return {"ok": None if reason.startswith("not configured") else False,
            "reason": reason,
            "consolidated": {"available": False, "asof": asof, "reason": reason},
            "entities": {"available": False, "asof": asof, "reason": reason}}


def configured_provider() -> str:
    return providers.configured_name()


def run(snapshot: dict | None, asof: str, mode: str, trigger_sync: bool = True, force_refresh: bool = False) -> dict:
    provider = providers.current()
    if provider is None:
        return _unavailable("not configured: no ledger provider selected in config/focos.yml", asof)
    try:
        health = provider.health()
        if health.ok is None:
            return _unavailable(f"not configured: {health.reason}", asof)
        if not health.ok:
            return _unavailable(health.reason or f"{provider.name} unavailable", asof)

        pull = None
        if provider.refreshes_synchronously:
            pull = provider.refresh(date.fromisoformat(asof), force=force_refresh)

        # Monthly: refresh property values (Zillow/manual) before reading balances (Sure-backed properties only for now)
        if mode == "monthly" and provider.name == "sure":
            try:
                from . import properties as props_mod
                props_mod.refresh(asof, push=True)
            except Exception:  # noqa: BLE001
                pass

        pushed, mirrored = [], []
        if snapshot:
            pushed = broker_mirror.push_values(provider, snapshot)
            mirrored = broker_mirror.mirror_trades(provider, snapshot)

        accounts = [a.as_row() for a in provider.accounts()]
        # Sure recomputes balances asynchronously; use the values we just pushed for the mapped accounts.
        pushed_by_id = {p["ledger_account_id"]: p["amount"] for p in pushed if p.get("ok") and p.get("ledger_account_id")}
        for a in accounts:
            if a["id"] in pushed_by_id:
                a["balance"] = pushed_by_id[a["id"]]
                a["balance_cents"] = int(round(float(pushed_by_id[a["id"]]) * 100))
        balance_sheet = provider.balance_sheet() if hasattr(provider, "balance_sheet") else None
        start = date.fromisoformat(asof) - timedelta(days=WINDOW_DAYS)
        txs = [t.model_dump() for t in provider.transactions(start, date.fromisoformat(asof))]
        sync = provider.sync_status().model_dump()

        if not provider.refreshes_synchronously and snapshot and trigger_sync and mode == "daily":
            provider.refresh(date.fromisoformat(asof))

        snap = {"date": asof, "provider": provider.name, "accounts": accounts, "balance_sheet": balance_sheet,
                "transactions": txs, "sync": sync, "pull": pull.model_dump() if pull else None}
        settings.write_json(paths.SNAPSHOTS_LEDGER / f"{asof}.json", snap)
        if provider.name == "sure":  # keep the historical folder for homes that started on Sure
            settings.write_json(paths.SNAPSHOTS_SURE / f"{asof}.json", {**snap, "api_calls": getattr(provider.client, "calls", None)})

        consolidated, entities = consolidate.build(accounts, txs, snapshot, asof, balance_sheet, sync)
        consolidated["pushed_valuations"] = pushed
        consolidated["mirrored_trades"] = mirrored
        consolidated["provider"] = provider.name
        consolidated["pull"] = pull.model_dump() if pull else None
        consolidated["api_calls"] = getattr(getattr(provider, "client", None), "calls", None)
        return {"ok": True, "provider": provider.name, "consolidated": consolidated, "entities": entities,
                "n_accounts": len(accounts), "n_transactions": len(txs),
                "pull": pull.model_dump() if pull else None}
    except Exception as e:  # any failure degrades gracefully
        return _unavailable(f"error: {type(e).__name__}: {str(e)[:300]}", asof)
