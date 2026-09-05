"""Build consolidated.json and entities.json from the ledger accounts plus the brokerage holdings snapshot."""
from __future__ import annotations

from datetime import date, timedelta

from .. import settings
from . import entities as ent
from . import netting


def _rules() -> list[dict]:
    return (settings._load_yaml("transfer_rules.yml") or {}).get("rules", [])


def _income_labels() -> dict:
    return (settings._load_yaml("transfer_rules.yml") or {}).get("income_labels", {}) or {}


def _ignore_patterns() -> list[str]:
    return (settings._load_yaml("transfer_rules.yml") or {}).get("ignore_patterns", []) or []


def broker_in_ledger(accounts: list[dict]) -> dict[str, bool]:
    """Per brokerage key: True only when its ledger_account_id names an account the ledger actually returned
    (so its value is already on a balance sheet and must not be added again from the holdings snapshot)."""
    ids = {str(a.get("id")) for a in accounts}
    return {b["key"]: str(b.get("ledger_account_id")) in ids for b in settings.brokerage() if b.get("key")}


def build(accounts: list[dict], transactions: list[dict], snapshot: dict | None, asof: str,
          sync: dict | None = None) -> tuple[dict, dict]:
    entity_of = ent.account_entity_map(accounts=accounts)
    corridors = ent.corridors()
    in_ledger = broker_in_ledger(accounts)
    rh_totals = None
    if snapshot:
        rh_totals = {a["key"]: (a.get("portfolio") or {}).get("total_value") for a in snapshot.get("accounts", [])
                     if not in_ledger.get(a["key"])}
    broker_entity_of = {a["key"]: a.get("entity") or ent.HOUSEHOLD for a in settings.brokerage()}
    sheets = ent.balance_sheets(accounts, entity_of, rh_totals, False, broker_entity_of=broker_entity_of)

    today = date.fromisoformat(asof)
    windows = {}
    for label, days in (("30d", 30), ("90d", 90)):
        start = today - timedelta(days=days)
        slice_ = [t for t in transactions if t.get("date") and date.fromisoformat(t["date"][:10]) >= start]
        r = netting.net(slice_, entity_of, _rules(), corridors, income_labels=_income_labels(),
                        ignore_patterns=_ignore_patterns())
        windows[label] = {"per_entity": r["per_entity"], "consolidated": r["consolidated"],
                          "inter_entity_flows": r["inter_entity_flows"], "unmatched": r["unmatched"],
                          "counts": r["counts"]}

    profile = settings.profile()
    monthly_core = ((profile.get("spending") or {}).get("monthly_core_expenses")) or None
    consolidated = {
        "available": True,
        "asof": asof,
        "net_worth": sheets["consolidated"]["net_worth"],
        "assets": sheets["consolidated"]["assets"],
        "liabilities": sheets["consolidated"]["liabilities"],
        "by_entity": {k: {"label": v["label"], "net_worth": v["net_worth"], "assets": v["assets"],
                          "liabilities": v["liabilities"], "cash": v["cash"], "n_accounts": len(v["accounts"])}
                      for k, v in sheets["entities"].items()},
        "cash_flow": windows,
        "personal_runway_months": (sheets["entities"].get(ent.HOUSEHOLD, {}).get("cash", 0) / monthly_core) if monthly_core else None,
        "unmapped_accounts": sheets["unmapped_accounts"],
        "broker_in_ledger": any(in_ledger.values()),
        "broker_in_ledger_by_account": in_ledger,
        "ledger_sync": sync,
    }
    entities_out = {"asof": asof, "entities": sheets["entities"], "corridors": sorted({tuple(sorted(c)) for c in corridors})}
    return consolidated, entities_out
