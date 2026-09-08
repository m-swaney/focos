"""Build consolidated.json and entities.json from the ledger accounts plus the brokerage holdings snapshot."""
from __future__ import annotations

from datetime import date, timedelta

from .. import settings
from . import entities as ent
from . import merchants, netting


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


def _spending(windows: dict, r90: dict | None, transactions: list[dict], sp_cfg: dict) -> dict:
    """Observed household spending from categorized ledger data next to the configured profile figures."""
    hh90 = ((windows.get("90d") or {}).get("per_entity") or {}).get(ent.HOUSEHOLD) or {}
    hh30 = ((windows.get("30d") or {}).get("per_entity") or {}).get(ent.HOUSEHOLD) or {}
    exp90 = float(hh90.get("expense") or 0.0)
    unc90 = float(hh90.get("uncategorized_expense") or 0.0)
    dates = sorted(str(t["date"])[:10] for t in transactions if t.get("date"))
    history_days = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days + 1 if dates else 0
    agg: dict[str, dict] = {}
    for t in (r90 or {}).get("transactions") or []:
        if t.get("kind") == "normal" and t.get("amount", 0) < 0 and not t.get("category") and t.get("entity") == ent.HOUSEHOLD:
            key = t.get("merchant_key") or merchants.merchant_key(t.get("merchant"), t.get("name"))
            a = agg.setdefault(key, {"merchant_key": key, "display_name": merchants.display_name(key), "total": 0.0, "n": 0,
                                     "sample": (t.get("merchant") or t.get("name") or "")[:60]})
            a["total"] += -float(t["amount"])
            a["n"] += 1
    top = sorted(agg.values(), key=lambda a: -a["total"])[:10]
    configured = sp_cfg.get("monthly_core_expenses") or None
    return {
        "observed_monthly_core_30d": round(float(hh30.get("core_expense") or 0.0), 2),
        "observed_monthly_core_90d": round(float(hh90.get("core_expense") or 0.0) / 3, 2),
        "observed_monthly_discretionary_90d": round(float(hh90.get("discretionary_expense") or 0.0) / 3, 2),
        "observed_monthly_expense_90d": round(exp90 / 3, 2),
        "coverage_pct_90d": round((exp90 - unc90) / exp90, 4) if exp90 else None,
        "history_days": history_days,
        "configured_monthly_core": configured,
        "configured_monthly_discretionary": sp_cfg.get("monthly_discretionary"),
        "configured_source": sp_cfg.get("monthly_core_source") or ("user" if configured else None),
        "observed_asof": sp_cfg.get("observed_asof"),
        "by_category_90d": dict(sorted((hh90.get("expense_by_category") or {}).items(), key=lambda kv: -kv[1])),
        "top_uncategorized": [{**a, "total": round(a["total"], 2)} for a in top],
    }


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

    entity_kinds = {k: (v or {}).get("kind") or "household" for k, v in ((settings.entities_v2() or {}).get("entities") or {}).items()}
    today = date.fromisoformat(asof)
    windows = {}
    r90 = None
    for label, days in (("30d", 30), ("90d", 90)):
        start = today - timedelta(days=days)
        slice_ = [t for t in transactions if t.get("date") and date.fromisoformat(t["date"][:10]) >= start]
        r = netting.net(slice_, entity_of, _rules(), corridors, income_labels=_income_labels(),
                        ignore_patterns=_ignore_patterns(), entity_kinds=entity_kinds)
        if label == "90d":
            r90 = r
        windows[label] = {"per_entity": r["per_entity"], "consolidated": r["consolidated"],
                          "inter_entity_flows": r["inter_entity_flows"], "unmatched": r["unmatched"],
                          "counts": r["counts"]}

    profile = settings.profile()
    spending = _spending(windows, r90, transactions, (profile.get("spending") or {}))
    monthly_core = spending.get("configured_monthly_core") or spending.get("observed_monthly_core_90d") or None
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
        "spending": spending,
        "personal_runway_months": (sheets["entities"].get(ent.HOUSEHOLD, {}).get("cash", 0) / monthly_core) if monthly_core else None,
        "unmapped_accounts": sheets["unmapped_accounts"],
        "broker_in_ledger": any(in_ledger.values()),
        "broker_in_ledger_by_account": in_ledger,
        "ledger_sync": sync,
    }
    entities_out = {"asof": asof, "entities": sheets["entities"], "corridors": sorted({tuple(sorted(c)) for c in corridors})}
    return consolidated, entities_out
