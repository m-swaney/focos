"""Transfer netting across entities. Deterministic; the double-count guard.

Pipeline:
 1. Legs Sure already matched (transfer_id set) are transfers. Pair type is intra_entity when both
    accounts map to the same entity, inter_entity otherwise.
 2. Unmatched transactions are tested against config/transfer_rules.yml (regex + direction + entity)
    and classified (investment_contribution, owner_draw, ...). These are one-legged transfers: the
    other side has no feed. They are excluded from income/expense.
 3. Remaining transactions are paired heuristically: opposite sign, equal absolute amount, different
    accounts, within `window_days`, and on a configured corridor. Pairs become transfers.
 4. Anything still unmatched whose name looks like a transfer is reported as `unmatched` for review.

Income/expense per entity exclude every transfer leg. Inter-entity flows are reported separately.
Invariant: consolidated income == sum(entity income) and consolidated expense == sum(entity expense).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from . import categories

TRANSFERISH = re.compile(r"(TRANSFER|\bXFER\b|ZELLE|\bWIRE\b|VENMO|ROBINHOOD|MERCURY|OWNER DRAW|DISTRIBUTION|CAPITAL CONTRIB|"
                         r"BANK XFER|EXTERNAL WITHDRAWAL|^WITHDRAWAL$|CASH APP|APPLE CASH)", re.I)


LIABILITY_TYPES = {"loan", "credit_card", "creditcard", "credit card", "mortgage"}


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


def label_income(t: dict, labels_for_entity: list[dict]) -> str | None:
    """First matching income label for a positive, non-transfer transaction."""
    hay = f"{t.get('name') or ''} {t.get('merchant') or ''}"
    for rule in labels_for_entity or []:
        if "amount" in rule and rule["amount"] is not None:
            if abs(abs(float(t["amount"])) - float(rule["amount"])) < 0.005:
                return rule["label"]
            continue
        if rule.get("match") and re.search(rule["match"], hay, re.I):
            return rule["label"]
    return None


def net(transactions: list[dict], entity_of: dict[str, str], rules: list[dict] | None = None,
        corridors: set[tuple[str, str]] | None = None, window_days: int = 4,
        income_labels: dict[str, list[dict]] | None = None, ignore_patterns: list[str] | None = None,
        entity_kinds: dict[str, str] | None = None) -> dict:
    rules = rules or []
    entity_kinds = entity_kinds or {}
    corridors = corridors or set()
    income_labels = income_labels or {}
    ignore_re = re.compile("|".join(f"(?:{p})" for p in ignore_patterns), re.I) if ignore_patterns else None
    txs = [dict(t) for t in transactions]
    for t in txs:
        t["entity"] = entity_of.get(str(t.get("account_id")), "unknown")
        t["kind"] = "normal"
        t["transfer_class"] = None
        t["pair_id"] = None

    by_id = {t["id"]: t for t in txs}
    inter_flows: list[dict] = []

    # 1. Sure-matched transfers
    for t in txs:
        if t.get("transfer_id"):
            t["kind"] = "transfer"
            t["pair_id"] = t["transfer_id"]
            other_ent = entity_of.get(str(t.get("other_account_id")), "unknown")
            t["transfer_class"] = "intra_entity" if other_ent == t["entity"] else "inter_entity"

    # 1b. Credits into liability accounts (loan or card payments received) are transfers, never income.
    for t in txs:
        if t["kind"] == "normal" and t["amount"] > 0 and str(t.get("account_type") or "") in LIABILITY_TYPES:
            t["kind"] = "transfer"
            t["transfer_class"] = "debt_payment_received"
            t["pair_id"] = f"liab:{t['id']}"

    # 2. Rule-based one-legged transfers
    for t in txs:
        if t["kind"] != "normal":
            continue
        for r in rules:
            pat = re.compile(r["match"], re.I)
            hay = f"{t.get('name') or ''} {t.get('merchant') or ''}"
            direction_ok = (r.get("direction") == "outflow" and t["amount"] < 0) or \
                           (r.get("direction") == "inflow" and t["amount"] > 0) or not r.get("direction")
            entity_ok = (not r.get("entity")) or r.get("entity") == t["entity"]
            if pat.search(hay) and direction_ok and entity_ok:
                t["kind"] = "transfer"
                t["pair_id"] = f"rule:{r.get('name')}:{t['id']}"
                cp = r.get("counterparty")
                if cp:  # one-legged inter-entity flow: the other entity's feed lacks the matching leg
                    t["transfer_class"] = "inter_entity"
                    t["counterparty_entity"] = cp
                    t["flow_label"] = r.get("classify_as", "inter_entity")
                else:
                    t["transfer_class"] = r.get("classify_as", "one_legged")
                break

    # 2b. Rows the categorizer or the owner labeled `transfer` (card payments, moves between own accounts)
    for t in txs:
        if t["kind"] == "normal" and t.get("category") == categories.TRANSFER:
            t["kind"] = "transfer"
            t["pair_id"] = f"cat:{t['id']}"
            t["transfer_class"] = "categorized_transfer"

    # 3. Heuristic pairing
    normal = [t for t in txs if t["kind"] == "normal"]
    normal.sort(key=lambda t: (_d(t["date"]), t["id"]))
    used: set[str] = set()
    for i, a in enumerate(normal):
        if a["id"] in used or a["amount"] == 0:
            continue
        for b in normal[i + 1:]:
            if b["id"] in used or b["account_id"] == a["account_id"]:
                continue
            if abs(_d(b["date"]) - _d(a["date"])).days > window_days:
                break
            if abs(a["amount"] + b["amount"]) > 0.005:
                continue
            pair = (a["entity"], b["entity"])
            if pair not in corridors and a["entity"] != b["entity"]:
                continue
            pid = f"heur:{a['id']}:{b['id']}"
            for t in (a, b):
                t["kind"] = "transfer"
                t["pair_id"] = pid
                t["transfer_class"] = "intra_entity" if a["entity"] == b["entity"] else "inter_entity"
            used.update({a["id"], b["id"]})
            break

    # inter-entity flows (one row per pair from the outflow leg; one-legged rule matches use their counterparty)
    seen_pairs: set[str] = set()
    for t in txs:
        if t["kind"] != "transfer" or t["transfer_class"] != "inter_entity" or t["pair_id"] in seen_pairs:
            continue
        if t.get("counterparty_entity"):
            seen_pairs.add(t["pair_id"])
            frm, to = (t["entity"], t["counterparty_entity"]) if t["amount"] < 0 else (t["counterparty_entity"], t["entity"])
            inter_flows.append({"date": t["date"], "from_entity": frm, "to_entity": to, "amount": abs(t["amount"]),
                                "name": t.get("name"), "pair_id": t["pair_id"], "label": t.get("flow_label"), "one_legged": True})
        elif t["amount"] < 0:
            seen_pairs.add(t["pair_id"])
            other = next((o for o in txs if o["pair_id"] == t["pair_id"] and o["id"] != t["id"]), None)
            inter_flows.append({"date": t["date"], "from_entity": t["entity"],
                                "to_entity": other["entity"] if other else entity_of.get(str(t.get("other_account_id")), "unknown"),
                                "amount": abs(t["amount"]), "name": t.get("name"), "pair_id": t["pair_id"]})

    # 4. Unmatched transfer-looking items (minus configured ignores)
    unmatched = []
    for t in txs:
        if t["kind"] != "normal":
            continue
        hay = f"{t.get('name') or ''} {t.get('merchant') or ''}"
        if TRANSFERISH.search(hay) and not (ignore_re and ignore_re.search(hay)):
            unmatched.append({"id": t["id"], "date": t["date"], "entity": t["entity"], "account": t.get("account_name"),
                              "amount": t["amount"], "name": t.get("name")})

    # totals
    per_entity: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expense": 0.0, "net": 0.0,
                                                       "inter_in": 0.0, "inter_out": 0.0, "one_legged_out": 0.0,
                                                       "one_legged_in": 0.0, "n_transactions": 0, "n_transfers": 0,
                                                       "income_by_label": {}, "transfers_by_class": {}, "expense_by_category": {},
                                                       "core_expense": 0.0, "discretionary_expense": 0.0, "uncategorized_expense": 0.0})
    for t in txs:
        e = per_entity[t["entity"]]
        if t["kind"] == "normal":
            e["n_transactions"] += 1
            if t["amount"] > 0:
                e["income"] += t["amount"]
                lab = label_income(t, income_labels.get(t["entity"], [])) or "unlabeled"
                t["income_label"] = lab
                e["income_by_label"][lab] = e["income_by_label"].get(lab, 0.0) + t["amount"]
            else:
                e["expense"] += -t["amount"]
                cat = t.get("category") or categories.UNCATEGORIZED
                e["expense_by_category"][cat] = e["expense_by_category"].get(cat, 0.0) + (-t["amount"])
                e[f"{categories.bucket(cat, entity_kinds.get(t['entity']))}_expense"] += -t["amount"]
        else:
            e["n_transfers"] += 1
            tc = t["transfer_class"] or "transfer"
            e["transfers_by_class"][tc] = e["transfers_by_class"].get(tc, 0.0) + abs(t["amount"])
            if t["transfer_class"] == "inter_entity":
                if t["amount"] > 0:
                    e["inter_in"] += t["amount"]
                else:
                    e["inter_out"] += -t["amount"]
            elif t["transfer_class"] not in ("intra_entity",):
                if t["amount"] > 0:
                    e["one_legged_in"] += t["amount"]
                else:
                    e["one_legged_out"] += -t["amount"]
    for e in per_entity.values():
        e["net"] = e["income"] - e["expense"]
    consolidated = {"income": sum(e["income"] for e in per_entity.values()),
                    "expense": sum(e["expense"] for e in per_entity.values()),
                    "core_expense": sum(e["core_expense"] for e in per_entity.values()),
                    "discretionary_expense": sum(e["discretionary_expense"] for e in per_entity.values()),
                    "uncategorized_expense": sum(e["uncategorized_expense"] for e in per_entity.values())}
    consolidated["net"] = consolidated["income"] - consolidated["expense"]
    by_cat: dict[str, float] = {}
    for e in per_entity.values():
        for k, v in e["expense_by_category"].items():
            by_cat[k] = by_cat.get(k, 0.0) + v
    consolidated["expense_by_category"] = by_cat
    return {
        "per_entity": dict(per_entity),
        "consolidated": consolidated,
        "inter_entity_flows": inter_flows,
        "unmatched": unmatched,
        "transactions": txs,
        "counts": {"total": len(txs), "transfers": sum(1 for t in txs if t["kind"] == "transfer"),
                   "unmatched": len(unmatched)},
    }
