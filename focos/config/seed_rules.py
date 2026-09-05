"""Seed transfer_rules.yml from the accounts the ledger discovered, so one-legged transfers (brokerage deposits,
loan payments, owner draws) never count as income or expense on day one. Regexes are escaped institution names
the user can edit in the wizard."""
from __future__ import annotations

import re
from typing import Any

from .models import HOUSEHOLD

DEFAULT_INCOME_LABELS = [
    {"label": "w2_pay", "match": "(PAYROLL|DIRECT DEP|ADP|GUSTO|PAYCHEX|SALARY)"},
    {"label": "refund_or_rebate", "match": "(REFUND|REBATE|CASHBACK|CASH BACK|REWARD)"},
    {"label": "other_income", "match": ".*"},
]


def _org_pattern(names: list[str]) -> str | None:
    parts = sorted({re.escape(n.strip().upper()) for n in names if n and n.strip()})
    return "(" + "|".join(parts) + ")" if parts else None


def seed(accounts: list[dict[str, Any]], entity_of: dict[str, str], entities_cfg: dict[str, Any]) -> dict[str, Any]:
    """accounts: ledger rows (id, name, institution_name, account_type, classification); entity_of: id -> entity."""
    ents = (entities_cfg or {}).get("entities") or {HOUSEHOLD: {"kind": "household"}}
    business = [k for k, v in ents.items() if k != HOUSEHOLD and (v or {}).get("kind") in ("business", "trust", "other")]
    rules: list[dict[str, Any]] = []

    def orgs(pred) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for a in accounts:
            if pred(a):
                out.setdefault(entity_of.get(str(a.get("id")), HOUSEHOLD), []).append(str(a.get("institution_name") or a.get("name") or ""))
        return out

    for ent, names in orgs(lambda a: str(a.get("account_type") or "").lower() == "investment").items():
        pat = _org_pattern(names)
        if pat:
            rules.append({"name": f"Brokerage deposit ({ent})", "match": pat, "direction": "outflow", "entity": ent,
                          "classify_as": "investment_contribution"})
    for ent, names in orgs(lambda a: str(a.get("account_type") or "").lower() == "loan").items():
        pat = _org_pattern(names)
        if pat:
            rules.append({"name": f"Loan payment ({ent})", "match": pat, "direction": "outflow", "entity": ent,
                          "classify_as": "debt_payment"})
    for ent, names in orgs(lambda a: str(a.get("account_type") or "").lower() == "credit_card").items():
        pat = _org_pattern(names)
        if pat:
            rules.append({"name": f"Card payment ({ent})", "match": pat, "direction": "outflow", "entity": ent,
                          "classify_as": "debt_payment"})
    bank_orgs = orgs(lambda a: str(a.get("account_type") or "").lower() == "depository")
    personal_banks = _org_pattern(bank_orgs.get(HOUSEHOLD, []))
    for biz in business:
        biz_banks = _org_pattern(bank_orgs.get(biz, []))
        if biz_banks:
            rules.append({"name": f"{biz} pays the household", "match": biz_banks, "direction": "inflow", "entity": HOUSEHOLD,
                          "counterparty": biz, "classify_as": "owner_pay"})
        if personal_banks:
            rules.append({"name": f"Household money into {biz}", "match": personal_banks, "direction": "inflow", "entity": biz,
                          "counterparty": HOUSEHOLD, "classify_as": "capital_contribution"})
    income_labels: dict[str, list[dict[str, Any]]] = {HOUSEHOLD: list(DEFAULT_INCOME_LABELS)}
    for biz in business:
        income_labels[biz] = [{"label": "other_income", "match": ".*"}]
    return {"rules": rules, "ignore_patterns": [], "income_labels": income_labels}
