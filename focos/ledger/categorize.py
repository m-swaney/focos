"""Spending categorization, rules first and a model only for what the rules do not know.

Every run: apply the merchant rules (seed, model, user) to the transactions in the window. Then, at most once a
day and only when there are new merchants, ask the configured model to label them in one batch; confident answers
become rules, unsure ones are parked as `uncategorized` and re-asked after STALE_DAYS. The brief model never
labels merchants and never touches the ledger.
"""
from __future__ import annotations

import json
import re
from datetime import date as _date
from datetime import timedelta

from .. import paths, settings
from ..llm import LLMError, Message, key_status, provider_for
from . import categories, merchants

WINDOW_DAYS = 95
MAX_MERCHANTS = 60
MIN_CONFIDENCE = 0.6
STALE_DAYS = 30
META_KEY = "last_categorize_date"

SYSTEM = ("You label merchants from a household's bank and card feeds into a fixed set of spending categories. "
          "You see only merchant names, counts, and typical amounts, never account numbers. Reply only with the JSON asked for.")
SCHEMA = {"type": "object", "required": ["labels"],
          "properties": {"labels": {"type": "array", "items": {"type": "object", "required": ["merchant_key", "category", "confidence"],
                                                                "properties": {"merchant_key": {"type": "string"},
                                                                               "category": {"type": "string", "enum": list(categories.CATEGORIES)},
                                                                               "confidence": {"type": "number", "minimum": 0, "maximum": 1}}}}}}


def _transfer_patterns() -> list[re.Pattern]:
    """Merchants config/transfer_rules.yml already classifies; asking about them would be wasted."""
    pats: list[re.Pattern] = []
    for r in (settings.transfer_rules() or {}).get("rules") or []:
        try:
            pats.append(re.compile(r["match"], re.I))
        except (re.error, KeyError, TypeError):
            continue
    return pats


def _looks_like_transfer(m: dict, pats: list[re.Pattern]) -> bool:
    hay = " ".join(str(m.get(k) or "") for k in ("merchant_key", "sample_description", "sample_payee"))
    return any(p.search(hay) for p in pats)


def _prompt(rows: list[dict], entity_kinds: dict[str, str]) -> str:
    lines = [f"{m['merchant_key']} | sample: {(m.get('sample_payee') or m.get('sample_description') or '')[:60]} | n={m['n']} | "
             f"typical ${m['avg_abs_amount']:.0f} | account: {m.get('account_types') or '?'} | entity: {entity_kinds.get(m.get('entity') or '', m.get('entity') or 'household')}"
             for m in rows]
    return ("Categories (use exactly these names):\n" + categories.taxonomy_text() +
            "\n\nExamples: STARBUCKS -> dining 0.95; FPL -> utilities 0.9; SUREPAYROLL -> professional_services 0.8; "
            "CHASE CREDIT CRD AUTOPAY -> transfer 0.95; an unfamiliar name with no clue -> uncategorized 0.2.\n"
            "Credit card payments, loan payments, brokerage deposits, and moves between the household's own accounts are "
            "`transfer`, never spending.\n"
            "Business entities (kind business) spend on operations; label their software, hosting, and services as business_ops or "
            "professional_services.\n\nMerchants (one per line: key | sample | count | typical amount | account type | entity):\n"
            + "\n".join(lines) +
            '\n\nReturn {"labels": [{"merchant_key": <key exactly as given>, "category": <one of the names>, "confidence": 0..1}]} '
            "with one entry per merchant.")


def pick_provider(ai: dict | None = None):
    """The configured API provider when it can run (key present, or ollama); else, in agent mode, the Claude CLI.
    Returns (provider, reason_if_none)."""
    from ..agent_runtime import claude_cli

    cfg = settings.focos()
    ai = ai if ai is not None else (cfg.get("ai") or {})
    name = str(ai.get("provider") or "anthropic")
    ok, detail = key_status(name)
    if ok:
        try:
            return provider_for(ai), None
        except LLMError as e:  # noqa: BLE001
            detail = str(e)
    if ai.get("mode") == "agent":
        agent = cfg.get("agent") or {}
        if claude_cli.find_claude(agent.get("claude_cli") or "auto"):
            from ..llm.claude_cli_provider import ClaudeCLIProvider

            return ClaudeCLIProvider(model=agent.get("model_keepalive") or "haiku", budget_usd=0.2,
                                     claude=agent.get("claude_cli") or "auto", label="categorize"), None
        return None, "Claude Code CLI not found"
    return None, f"no model available for merchant labeling ({detail}); set an API key, run Ollama, or use agent mode"


def _ask(provider, rows: list[dict], entity_kinds: dict[str, str]) -> tuple[list[dict], str]:
    """Labels from the provider; on failure in agent mode, retry once with the Claude CLI."""
    msgs = [Message(role="user", content=_prompt(rows, entity_kinds))]
    try:
        data, _ = provider.structured(SYSTEM, msgs, SCHEMA, max_tokens=2048)
        return list(data.get("labels") or []), provider.name
    except LLMError as e:
        ai = settings.focos().get("ai") or {}
        if ai.get("mode") == "agent" and getattr(provider, "name", "") != "claude_cli":
            from ..agent_runtime import claude_cli
            from ..llm.claude_cli_provider import ClaudeCLIProvider

            agent = settings.focos().get("agent") or {}
            if claude_cli.find_claude(agent.get("claude_cli") or "auto"):
                fb = ClaudeCLIProvider(model=agent.get("model_keepalive") or "haiku", claude=agent.get("claude_cli") or "auto", label="categorize")
                data, _ = fb.structured(SYSTEM, msgs, SCHEMA, max_tokens=2048)
                return list(data.get("labels") or []), fb.name
        raise e


def run(store, asof: str, *, force: bool = False, provider=None, dry_run: bool = False, entity_of: dict[str, str] | None = None) -> dict:
    """Categorize the window ending at asof. Returns a summary (also written to state/derived/latest/categorize.json)."""
    start = (_date.fromisoformat(asof) - timedelta(days=WINDOW_DAYS)).isoformat()
    out = {"date": asof, "rules_applied": 0, "seeded": 0, "asked": 0, "labeled": 0, "low_confidence": 0, "skipped": None,
           "provider": None, "error": None, "new_rules": []}
    out["rules_applied"] += store.apply_category_rules(start)
    # 1. seeds for anything the rules do not know
    for m in store.uncategorized_merchants(start, asof, limit=1000, stale_days=STALE_DAYS):
        cat = categories.seed_category(m["merchant_key"])
        if cat:
            if not dry_run:
                store.set_merchant_rule(m["merchant_key"], cat, "seed", 0.9, merchants.display_name(m["merchant_key"]))
            out["seeded"] += 1
    # a transfer seed beats an earlier model label: card payments the model once called "fees" become transfers
    for key, rule in store.merchant_rules().items():
        if rule.get("source") == "model" and rule.get("category") != categories.TRANSFER and categories.seed_category(key) == categories.TRANSFER:
            if not dry_run:
                store.set_merchant_rule(key, categories.TRANSFER, "seed", 0.9, rule.get("display_name"))
            out["seeded"] += 1
    if out["seeded"] and not dry_run:
        out["rules_applied"] += store.apply_category_rules(start)
    # 2. one batch model call a day for the rest
    pats = _transfer_patterns()
    pending = [m for m in store.uncategorized_merchants(start, asof, limit=MAX_MERCHANTS, stale_days=STALE_DAYS)
               if not _looks_like_transfer(m, pats)]
    out["pending"] = [m["merchant_key"] for m in pending]
    if store.get_meta(META_KEY) == asof and not force:
        out["skipped"] = "already labeled today"
        return _finish(store, out, dry_run)
    if not pending:
        out["skipped"] = "no new merchants"
        if not dry_run:
            store.set_meta(META_KEY, asof)
        return _finish(store, out, dry_run)
    if dry_run:
        out["skipped"] = "dry run"
        return _finish(store, out, dry_run)
    if provider is None:
        provider, why = pick_provider()
        if provider is None:
            out["error"] = why
            return _finish(store, out, dry_run)
    entity_kinds = {k: (v or {}).get("kind") or "household" for k, v in ((settings.entities_v2() or {}).get("entities") or {}).items()}
    if entity_of:
        for m in pending:
            m["entity"] = entity_of.get(str(m.get("account_id") or ""), m.get("entity"))
    out["asked"] = len(pending)
    try:
        labels, used = _ask(provider, pending, entity_kinds)
        out["provider"] = used
    except LLMError as e:
        out["error"] = f"model call failed: {str(e)[:300]}"
        return _finish(store, out, dry_run)
    wanted = {m["merchant_key"] for m in pending}
    for lab in labels:
        if not isinstance(lab, dict):
            continue
        key, cat = str(lab.get("merchant_key") or "").strip(), str(lab.get("category") or "")
        try:
            conf = float(lab.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if key not in wanted or not categories.is_category(cat):
            continue
        if conf >= MIN_CONFIDENCE and cat != categories.UNCATEGORIZED:
            store.set_merchant_rule(key, cat, "model", conf, merchants.display_name(key))
            out["labeled"] += 1
            out["new_rules"].append({"merchant_key": key, "category": cat, "confidence": round(conf, 2)})
        else:
            store.set_merchant_rule(key, categories.UNCATEGORIZED, "model", conf, merchants.display_name(key))
            out["low_confidence"] += 1
    store.set_meta(META_KEY, asof)
    out["rules_applied"] += store.apply_category_rules(start)
    if out["labeled"]:
        from ..updates import apply as apply_mod

        apply_mod.record(target="merchant_rule", op="add", id=None, before=None,
                         after={"n": out["labeled"], "low_confidence": out["low_confidence"],
                                "examples": [f"{r['merchant_key']} -> {r['category']}" for r in out["new_rules"][:6]]},
                         reason=f"labeled {out['asked']} new merchant(s) with {out['provider']}", actor="system", run=f"pipeline-{asof}", date=asof)
    return _finish(store, out, dry_run)


def _finish(store, out: dict, dry_run: bool) -> dict:
    try:
        out["counts"] = store.category_counts()
    except Exception:  # noqa: BLE001
        out["counts"] = {}
    if not dry_run:
        try:
            settings.write_json(paths.LATEST / "categorize.json", out)
        except OSError:
            pass
    return out


def summary_line(out: dict) -> str:
    if out.get("error"):
        return f"categorize: {out['error']}"
    return (f"categorize: {out['rules_applied']} rows re-labeled, {out['seeded']} seeded, {out['asked']} asked, "
            f"{out['labeled']} learned, {out['low_confidence']} unsure" + (f" ({out['skipped']})" if out.get("skipped") else ""))


def dumps(out: dict) -> str:
    return json.dumps(out, indent=2, default=str)
