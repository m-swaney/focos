"""In-memory normalization of v1 (single-household, Robinhood keyed) config into the v2 layout.

Both the runtime (settings.*_v2 helpers) and `focos migrate` use these transforms, so a data dir on the
old layout keeps working unchanged until its owner migrates.
"""
from __future__ import annotations

import copy
from typing import Any

from .models import HOUSEHOLD

V1_ROLE = {"taxable": "taxable", "roth_ira": "roth_ira", "sandbox": "sandbox", "traditional_ira": "traditional_ira"}
DEFAULT_TZ = "America/New_York"


def is_v2_accounts(raw: dict[str, Any]) -> bool:
    return "brokerage" in raw or not raw.get("robinhood")


def accounts_v2(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    if is_v2_accounts(raw):
        out = copy.deepcopy(raw)
        out.setdefault("version", 2)
        out.setdefault("brokerage", [])
        return out
    brokerage = []
    for key, spec in (raw.get("robinhood") or {}).items():
        spec = spec or {}
        entry: dict[str, Any] = {
            "key": key,
            "label": spec.get("label") or key,
            "role": V1_ROLE.get(str(spec.get("role") or ""), "other"),
            "entity": HOUSEHOLD,
            "source": "robinhood_mcp",
            "match": {"last4": str(spec["last4"])} if spec.get("last4") else {},
            "agent_access": "trade" if spec.get("agent_access") == "trade" else "read",
        }
        brokerage.append(entry)
    return {"version": 2, "brokerage": brokerage}


def is_v2_entities(raw: dict[str, Any]) -> bool:
    ents = raw.get("entities") or {}
    return "name_hints" not in raw and not any(isinstance(e, dict) and "sure_account_ids" in e for e in ents.values())


def entities_v2(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    if is_v2_entities(raw):
        out = copy.deepcopy(raw)
        out.setdefault("version", 2)
        out.setdefault("entities", {})
        out.setdefault("corridors", [])
        if HOUSEHOLD not in out["entities"]:
            out["entities"] = {HOUSEHOLD: {"label": "Personal", "kind": "household", "account_ids": []}, **out["entities"]}
        return out
    hints = raw.get("name_hints") or {}
    ents: dict[str, Any] = {}
    for key, spec in (raw.get("entities") or {}).items():
        spec = spec or {}
        ents[key] = {
            "label": spec.get("label") or key,
            "kind": "household" if key == HOUSEHOLD else "business",
            "account_ids": [f"sure:{i}" for i in (spec.get("sure_account_ids") or [])],
            "name_hints": hints.get(key),
        }
        for extra in ("color", "institution"):
            if spec.get(extra):
                ents[key][extra] = spec[extra]
    if HOUSEHOLD not in ents:
        ents = {HOUSEHOLD: {"label": "Personal", "kind": "household", "account_ids": [], "name_hints": hints.get(HOUSEHOLD)},
                **ents}
    return {"version": 2, "entities": ents, "corridors": [list(p) for p in (raw.get("corridors") or [])]}


def is_v2_profile(raw: dict[str, Any]) -> bool:
    return "owner" in raw or "person" not in raw


def profile_v2(raw: dict[str, Any] | None, entities: dict[str, Any] | None = None) -> dict[str, Any]:
    """entities: the v2 entities document; with exactly one business entity the migrated business income source
    is labeled and attributed to it instead of the household."""
    raw = raw or {}
    if is_v2_profile(raw):
        out = copy.deepcopy(raw)
        out.setdefault("version", 2)
        out.setdefault("household", {}).setdefault("timezone", DEFAULT_TZ)
        return out
    out = copy.deepcopy(raw)
    person = out.pop("person", None) or {}
    out["version"] = 2
    out["owner"] = {k: v for k, v in person.items() if k != "state"}
    out["household"] = {"timezone": DEFAULT_TZ, "currency": "USD", "country": "US", "state": person.get("state")}

    income = out.get("income") or {}
    sources: list[dict[str, Any]] = []
    biz = income.get("annual_business_income")
    if biz is not None:
        businesses = [(k, e or {}) for k, e in ((entities or {}).get("entities") or {}).items()
                      if k != HOUSEHOLD and (e or {}).get("kind", "business") == "business"]
        label, ent_key = "Business income", HOUSEHOLD
        if len(businesses) == 1:
            ent_key, spec = businesses[0]
            label = f"{spec.get('label') or ent_key} income"
        sources.append({"label": label, "kind": "business", "annual": biz,
                        "range": income.get("annual_business_income_range"), "entity": ent_key})
    w2 = income.get("annual_gross_w2")
    if w2:
        sources.append({"label": "W-2 salary", "kind": "w2", "annual": w2, "entity": HOUSEHOLD})
    out["income"] = {"sources": sources, "notes": income.get("notes")}

    ret = dict(out.get("retirement") or {})
    limit = ret.pop("roth_ira_contribution_limit", None)
    ytd = ret.pop("roth_contributed_this_year", None)
    contributions: dict[str, Any] = {}
    if limit is not None or ytd is not None:
        contributions["self"] = {"roth_ira": {"limit": limit, "ytd": ytd}}
    spouse = dict(out.get("spouse") or {})
    s_ytd = spouse.pop("roth_contributed_this_year", None)
    if s_ytd is not None:
        contributions["spouse"] = {"roth_ira": {"limit": limit, "ytd": s_ytd}}
    ret["contributions"] = contributions
    out["retirement"] = ret
    out["spouse"] = spouse

    cash = dict(out.get("cash_policy") or {})
    cash.setdefault("business_cash_is_reserve", biz is not None)
    out["cash_policy"] = cash
    return out


V1_GOAL_KINDS: dict[str, tuple[str, dict[str, Any]]] = {
    "emergency_fund": ("emergency_fund", {}),
    "roth_max": ("retirement_contribution", {"owner": "self", "account_role": "roth_ira"}),
    "spouse_roth": ("retirement_contribution", {"owner": "spouse", "account_role": "roth_ira"}),
    "heloc_payoff": ("debt_payoff", {"match": "HELOC"}),
}


def goal_v2(g: dict[str, Any]) -> dict[str, Any]:
    if "kind" in g:
        return dict(g)
    gid = str(g.get("id") or "")
    kind, params = V1_GOAL_KINDS.get(gid, (None, {}))
    if kind is None:
        if gid.endswith("_payoff"):
            kind, params = "debt_payoff", {"match": gid[: -len("_payoff")].upper()}
        else:
            kind, params = "custom", {}
    out = {"id": gid or None, "kind": kind, "name": g.get("name") or gid, "entity": g.get("entity") or HOUSEHOLD,
           "target_amount": g.get("target_amount"), "deadline": g.get("deadline"),
           "funded_by": list(g.get("funded_by") or []), "params": params}
    if g.get("notes"):
        out["notes"] = g["notes"]
    return out


def goals_v2(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    goals = [goal_v2(g) for g in (raw.get("goals") or []) if isinstance(g, dict)]
    return {"version": 2, "goals": goals}
