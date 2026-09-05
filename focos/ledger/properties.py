"""Property accounts: one manual ledger account per property, values refreshed from Zillow or kept manual."""
from __future__ import annotations

import time
from datetime import date

import yaml

from .. import paths, settings
from ..config.models import HOUSEHOLD
from .providers.base import LedgerProvider, ManualAccountSpec

MIN_DAYS_BETWEEN_ZILLOW_CALLS = 20  # free RapidAPI plan: 25 requests/month, so refresh Zillow at most ~monthly


def cfg_path():
    return paths.CONFIG / "properties.yml"


def load() -> list[dict]:
    return (settings._load_yaml("properties.yml") or {}).get("properties", []) or []


def save(props: list[dict]) -> None:
    cfg = cfg_path()
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    header = text.split("properties:")[0] if "properties:" in text else text
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(header + yaml.safe_dump({"properties": props}, sort_keys=False, allow_unicode=True), encoding="utf-8")
    settings.reset()


def account_key(p: dict) -> str:
    return f"prop_{p['key']}"


def current_value(p: dict) -> float:
    return float(p.get("last_value") or p.get("manual_value") or p.get("initial_value") or 0)


def ensure_accounts(provider: LedgerProvider, props: list[dict]) -> list[dict]:
    """Create the manual ledger account for any property without ledger_account_id and map it to its entity."""
    from . import entities as ent

    changed = False
    for p in props:
        if p.get("ledger_account_id"):
            continue
        entity = p.get("entity") or HOUSEHOLD
        spec = ManualAccountSpec(key=account_key(p), name=p["name"], entity=entity, account_type="property",
                                 classification="asset", balance=current_value(p), notes=p.get("address"))
        acct = provider.upsert_manual_account(spec)
        p["ledger_account_id"] = acct.id
        ent.add_account_id(entity, acct.id)
        changed = True
    if changed:
        save(props)
    return props


def refresh(asof: str | None = None, push: bool = True, force: bool = False, provider: LedgerProvider | None = None) -> dict:
    """Refresh every property's value (Zillow at most every 20 days, or manual_value) and write it to the ledger."""
    asof = asof or date.today().isoformat()
    props = load()
    if provider is None and push:
        from . import providers

        provider = providers.current()
    if provider is not None and props:
        props = ensure_accounts(provider, props)
    results = []
    zillow = None
    for p in props:
        row = {"key": p["key"], "name": p["name"], "entity": p.get("entity") or HOUSEHOLD, "source": p.get("source"),
               "ledger_account_id": p.get("ledger_account_id")}
        try:
            if p.get("source") == "zillow":
                last = p.get("last_refreshed")
                fresh = last and (date.fromisoformat(asof) - date.fromisoformat(str(last)[:10])).days < MIN_DAYS_BETWEEN_ZILLOW_CALLS
                if fresh and not force and p.get("last_value"):
                    row["value"] = float(p["last_value"])
                    row["cached"] = True
                    row["last_refreshed"] = last
                else:
                    from ..sources.zillow import ZillowClient
                    zillow = zillow or ZillowClient()
                    info = zillow.value(p.get("address"), p.get("zpid"))
                    time.sleep(1.0)
                    row.update(info)
                    row["value"] = info.get("zestimate")
                    if not p.get("zpid") and info.get("zpid"):
                        p["zpid"] = info["zpid"]
                    p["last_value"] = info.get("zestimate")
                    p["last_rent_estimate"] = info.get("rent_zestimate")
                    p["last_refreshed"] = asof
            else:
                row["value"] = float(p.get("manual_value") or 0)
            if push and provider is not None and row.get("value") and p.get("ledger_account_id"):
                provider.set_manual_balance(p["ledger_account_id"], date.fromisoformat(asof), float(row["value"]),
                                            note=f"focos {p.get('source')} value {asof}")
                row["pushed"] = True
        except Exception as e:  # noqa: BLE001
            row["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        results.append(row)
    if props:
        save(props)
    out = {"asof": asof, "properties": results,
           "total_value": sum(r.get("value") or 0 for r in results if not r.get("error"))}
    settings.write_json(paths.LATEST / "properties.json", out)
    return out
