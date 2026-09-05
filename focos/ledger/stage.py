"""Stage B sub-step: refresh the ledger feeds, mirror brokerage values, build consolidated/entities JSON.

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

        pull = provider.refresh(date.fromisoformat(asof), force=force_refresh)

        # Monthly: refresh property values (Zillow/manual) before reading balances
        properties = None
        if mode == "monthly":
            try:
                from . import properties as props_mod
                properties = props_mod.refresh(asof, push=True, provider=provider)
            except Exception as e:  # noqa: BLE001
                properties = {"error": f"{type(e).__name__}: {str(e)[:200]}"}

        pushed = broker_mirror.push_values(provider, snapshot) if snapshot else []

        accounts = [a.as_row() for a in provider.accounts()]
        start = date.fromisoformat(asof) - timedelta(days=WINDOW_DAYS)
        txs = [t.model_dump() for t in provider.transactions(start, date.fromisoformat(asof))]
        sync = provider.sync_status().model_dump()

        snap = {"date": asof, "provider": provider.name, "accounts": accounts, "transactions": txs, "sync": sync,
                "pull": pull.model_dump() if pull else None}
        settings.write_json(paths.SNAPSHOTS_LEDGER / f"{asof}.json", snap)

        consolidated, entities = consolidate.build(accounts, txs, snapshot, asof, sync)
        consolidated["pushed_valuations"] = pushed
        consolidated["provider"] = provider.name
        consolidated["pull"] = pull.model_dump() if pull else None
        if properties is not None:
            consolidated["properties_refresh"] = properties
        return {"ok": True, "provider": provider.name, "consolidated": consolidated, "entities": entities,
                "n_accounts": len(accounts), "n_transactions": len(txs),
                "pull": pull.model_dump() if pull else None}
    except Exception as e:  # any failure degrades gracefully
        return _unavailable(f"error: {type(e).__name__}: {str(e)[:300]}", asof)
