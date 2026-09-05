"""Account -> entity mapping and per-entity balance sheets.

`HOUSEHOLD` ("personal") is the reserved entity every install has; anything else is a business, trust,
or other unit. Ledger account ids may carry a provider prefix ("sure:<uuid>", "simplefin:<id>"); matching
ignores the prefix so a config written for one provider keeps working after a migration.
"""
from __future__ import annotations

import re

from .. import settings
from ..config.models import HOUSEHOLD  # noqa: F401  (re-exported)


def _bare(acct_id: str) -> str:
    return re.sub(r"^[a-z_]+:", "", str(acct_id))


def account_entity_map(entities_cfg: dict | None = None, accounts: list[dict] | None = None) -> dict[str, str]:
    """Explicit account_ids (or v1 sure_account_ids) first, then per-entity name_hints for the rest."""
    from ..config.compat import entities_v2

    full = entities_v2(entities_cfg if entities_cfg is not None else settings.entities())
    cfg = full.get("entities", {})
    explicit: dict[str, str] = {}
    for key, spec in cfg.items():
        for acct_id in (spec.get("account_ids") or []) + (spec.get("aliases") or []):
            explicit[_bare(acct_id)] = key
    out: dict[str, str] = {}
    for a in accounts or []:
        aid = str(a.get("id"))
        hit = explicit.get(_bare(aid))
        if hit:
            out[aid] = hit
            continue
        hay = f"{a.get('name') or ''} {a.get('institution_name') or ''}"
        for key, spec in cfg.items():
            pat = spec.get("name_hints")
            if pat and re.search(pat, hay, re.I):
                out[aid] = key
                break
    if not accounts:  # callers that only want the explicit table
        out = dict(explicit)
    return out


def corridors(entities_cfg: dict | None = None) -> set[tuple[str, str]]:
    from ..config.compat import entities_v2

    full = entities_v2(entities_cfg if entities_cfg is not None else settings.entities())
    pairs = full.get("corridors") or []
    if not pairs:  # default: every non-household entity exchanges money with the household
        pairs = [[k, HOUSEHOLD] for k in full.get("entities", {}) if k != HOUSEHOLD]
    out = set()
    for pair in pairs:
        a, b = pair
        out.add((a, b))
        out.add((b, a))
    return out


def money(a: dict, field: str = "balance") -> float:
    """Ledgers return money as formatted strings ("$1,234.56") and/or *_cents integers; prefer cents."""
    cents = a.get(f"{field}_cents")
    if cents is not None:
        try:
            return float(cents) / 100.0
        except (TypeError, ValueError):
            pass
    raw = a.get(field)
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace(",", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = s.strip("()-").strip()
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


def balance_sheets(accounts: list[dict], entity_of: dict[str, str], broker_totals: dict | None = None,
                   broker_in_ledger: bool = False, entities_cfg: dict | None = None,
                   broker_entity_of: dict[str, str] | None = None) -> dict:
    """accounts: ledger account dicts (id, name, balance, classification, account_type, subtype).

    broker_totals: {"<brokerage key>": total_value, ...} from the holdings snapshot; added to the entity that
    owns each brokerage account (broker_entity_of, default household) unless the ledger already carries
    those accounts (broker_in_ledger=True) to avoid double counting.
    """
    from ..config.compat import entities_v2

    cfg = entities_v2(entities_cfg if entities_cfg is not None else settings.entities()).get("entities", {})
    sheets: dict[str, dict] = {k: {"label": v.get("label", k), "assets": 0.0, "liabilities": 0.0, "net_worth": 0.0,
                                   "cash": 0.0, "accounts": [], "unmapped": False} for k, v in cfg.items()}
    unmapped: list[dict] = []
    for a in accounts:
        ent = entity_of.get(str(a["id"]))
        bal = money(a)
        row = {"id": a["id"], "name": a.get("name"), "type": a.get("account_type"), "subtype": a.get("subtype"),
               "classification": a.get("classification"), "balance": bal, "institution": a.get("institution_name"),
               "source": a.get("source") or "ledger"}
        if not ent or ent not in sheets:
            unmapped.append(row)
            continue
        s = sheets[ent]
        s["accounts"].append(row)
        if a.get("classification") == "liability":
            s["liabilities"] += abs(bal)
        else:
            s["assets"] += bal
            if a.get("account_type") in ("depository", "Depository") or a.get("subtype") in ("checking", "savings"):
                s["cash"] += bal
    if broker_totals and not broker_in_ledger:
        for key, val in broker_totals.items():
            if val is None:
                continue
            ent = (broker_entity_of or {}).get(key, HOUSEHOLD)
            if ent not in sheets:
                ent = HOUSEHOLD if HOUSEHOLD in sheets else next(iter(sheets), None)
            if ent is None:
                continue
            sheets[ent]["accounts"].append({"id": f"broker:{key}", "name": f"Brokerage {key}", "type": "investment",
                                            "classification": "asset", "balance": float(val), "source": "broker"})
            sheets[ent]["assets"] += float(val)
    for s in sheets.values():
        s["net_worth"] = s["assets"] - s["liabilities"]
    consolidated = {
        "assets": sum(s["assets"] for s in sheets.values()),
        "liabilities": sum(s["liabilities"] for s in sheets.values()),
    }
    consolidated["net_worth"] = consolidated["assets"] - consolidated["liabilities"]
    return {"entities": sheets, "consolidated": consolidated, "unmapped_accounts": unmapped}
