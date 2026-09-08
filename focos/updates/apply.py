"""Apply structured updates to config/goals.yml, config/profile.yml, and state/decisions.jsonl through the
comment-preserving config writer, and log every attempt to state/changes.jsonl.

Only these files are ever touched: config/profile.yml, config/goals.yml, state/decisions.jsonl,
state/changes.jsonl, state/inbox.jsonl.
"""
from __future__ import annotations

import copy
import json
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any

from .. import inbox, paths, settings
from ..config import writer
from ..config.models import slug, tax_agenda_items
from ..config.validate import validate_data
from .models import (DecisionUpdate, GoalUpdate, MerchantRuleUpdate, ProfileNoteUpdate, SpendingUpdate, TaxAgendaUpdate,
                     UpdateError, validate_update)

SPENDING_ACTORS = ("user", "system")


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _plain(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str))


def _save(name: str, doc: Any) -> None:
    issues = validate_data(name, writer._plain(dict(doc)))
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise UpdateError(f"{name} would not validate: {errors[0].path}: {errors[0].message}")
    writer.dump(name, doc)


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


# ---------------------------------------------------------------- handlers (return before, after)

def _goal(u: GoalUpdate, actor: str, date: str) -> tuple[dict, dict]:
    doc = writer.load("goals.yml")
    goals = doc.get("goals") if isinstance(doc, dict) else None
    if not goals:
        raise UpdateError("no goals in config/goals.yml")
    hit = next((g for g in goals if isinstance(g, dict) and (g.get("id") or slug(str(g.get("name") or ""))) == u.id), None)
    if hit is None:
        raise UpdateError(f"unknown goal id {u.id!r}")
    fields = u.set.model_dump(exclude_none=True)
    if not fields:
        raise UpdateError("nothing to set")
    before, after = {}, {}
    for k, v in fields.items():
        if k == "funded_amount":
            params = hit.get("params")
            if not isinstance(params, dict):
                params = {}
                hit["params"] = params
            before[k] = params.get("funded_amount")
            params["funded_amount"] = v
        else:
            before[k] = _iso(hit.get(k))
            hit[k] = _iso(v)
        after[k] = _iso(v)
    if fields.get("status") == "done" and "completed_on" not in fields and not hit.get("completed_on"):
        hit["completed_on"] = date
        after["completed_on"] = date
    if fields.get("status") in ("active", "paused") and hit.get("completed_on") and "completed_on" not in fields:
        before["completed_on"] = _iso(hit.get("completed_on"))
        hit["completed_on"] = None
        after["completed_on"] = None
    _save("goals.yml", doc)
    return before, after


def _tax_agenda(u: TaxAgendaUpdate, actor: str, date: str) -> tuple[dict | None, dict]:
    doc = writer.load("profile.yml")
    if not isinstance(doc, dict):
        raise UpdateError("config/profile.yml is missing")
    raw = doc.get("tax_agenda")
    items = raw if isinstance(raw, list) else []
    if raw is None or not isinstance(raw, list):
        doc["tax_agenda"] = items
    # bare strings (pre-v3) become items in place, keeping the list object so comments survive
    for i, it in enumerate(list(items)):
        if isinstance(it, str):
            items[i] = tax_agenda_items([it])[0]
    if u.op == "add":
        text = (u.text or "").strip()
        if not text:
            raise UpdateError("tax_agenda add needs text")
        ids = {it.get("id") for it in items if isinstance(it, dict)}
        item = tax_agenda_items([text])[0]
        base, n = item["id"], 2
        while item["id"] in ids:
            item["id"] = f"{base}_{n}"
            n += 1
        item["added_on"] = date
        items.append(item)
        _save("profile.yml", doc)
        return None, item
    if not u.id or u.set is None:
        raise UpdateError("tax_agenda set needs id and set")
    hit = next((it for it in items if isinstance(it, dict) and it.get("id") == u.id), None)
    if hit is None:
        raise UpdateError(f"unknown tax_agenda id {u.id!r}")
    fields = u.set.model_dump(exclude_none=True)
    if not fields:
        raise UpdateError("nothing to set")
    before = {k: _iso(hit.get(k)) for k in fields}
    for k, v in fields.items():
        hit[k] = _iso(v)
    if fields.get("status") == "done" and "done_on" not in fields and not hit.get("done_on"):
        hit["done_on"] = date
    if fields.get("status") == "open" and hit.get("done_on"):
        hit["done_on"] = None
    _save("profile.yml", doc)
    return before, {k: hit.get(k) for k in set(fields) | ({"done_on"} if "done_on" in hit else set())}


def _profile_note(u: ProfileNoteUpdate, actor: str, date: str) -> tuple[dict, dict]:
    section, key = u.path.split(".", 1)
    doc = writer.load("profile.yml")
    if not isinstance(doc, dict):
        raise UpdateError("config/profile.yml is missing")
    sec = doc.get(section)
    if not isinstance(sec, dict):
        sec = {}
        doc[section] = sec
    text = (u.text or "").strip()
    if not text:
        raise UpdateError("nothing to append")
    old = str(sec.get(key) or "").rstrip()
    new = (old + "\n" if old else "") + f"[{date}] {text}"
    sec[key] = new
    _save("profile.yml", doc)
    return {key: old or None}, {key: new}


def _spending(u: SpendingUpdate, actor: str, date: str) -> tuple[dict, dict]:
    if actor not in SPENDING_ACTORS and not u.source_note_id:
        raise UpdateError("spending figures change only from a note by the owner or the observed-spend rule")
    fields = u.set.model_dump(exclude_none=True)
    if not fields:
        raise UpdateError("nothing to set")
    doc = writer.load("profile.yml")
    if not isinstance(doc, dict):
        raise UpdateError("config/profile.yml is missing")
    sp = doc.get("spending")
    if not isinstance(sp, dict):
        sp = {}
        doc["spending"] = sp
    before = {k: sp.get(k) for k in fields}
    for k, v in fields.items():
        sp[k] = v
    if actor == "system":
        sp["monthly_core_source"] = "observed"
        sp["observed_asof"] = date
    else:
        sp["monthly_core_source"] = "user"
    _save("profile.yml", doc)
    return before, dict(fields)


def _decision(u: DecisionUpdate, actor: str, date: str, run: str) -> tuple[dict, dict]:
    from ..brief import outputs

    rows = outputs.all_decisions()
    hit = next((r for r in rows if r.get("id") == u.id and r.get("kind") != "resolution"), None)
    if hit is None:
        raise UpdateError(f"unknown decision id {u.id!r}")
    current = outputs.decision_status(rows).get(u.id, "open")
    outputs.append_resolution(u.id, u.set.status, u.set.note or "", date, run, actor)
    return {"status": current}, {"status": u.set.status, "text": str(hit.get("text") or "")[:160]}


def _merchant_rule(u: MerchantRuleUpdate, actor: str, date: str) -> tuple[dict, dict]:
    from ..ledger import categories, merchants
    from ..ledger.providers.sqlite_store import SQLiteStore

    if not categories.is_category(u.category):
        raise UpdateError(f"unknown category {u.category!r}")
    if not paths.LEDGER_DB.exists():
        raise UpdateError("no ledger database yet")
    store = SQLiteStore(paths.LEDGER_DB)
    try:
        old = store.merchant_rule(u.id)
        source = "user" if actor == "user" else actor
        store.set_merchant_rule(u.id, u.category, source, 1.0 if actor == "user" else None, merchants.display_name(u.id))
        n = store.apply_category_rules((_date.fromisoformat(date) - timedelta(days=400)).isoformat())
    finally:
        store.close()
    return {"category": old["category"] if old else None, "source": old["source"] if old else None}, {"category": u.category, "transactions": n}


def record(*, target: str, op: str, id: str | None, before: Any, after: Any, reason: str, actor: str, run: str, date: str,
           source_note_id: str | None = None, ok: bool = True, error: str | None = None) -> dict:
    """Log a change that was applied elsewhere (the categorizer writes rules straight into the ledger)."""
    return _log({"ts": _now(), "date": date, "run": run, "actor": actor, "target": target, "op": op, "id": id, "before": _plain(before),
                 "after": _plain(after), "reason": reason[:500], "source_note_id": source_note_id, "ok": ok, "error": error})


# ---------------------------------------------------------------- public API

def apply(updates: list[dict] | None, *, actor: str, run: str, date: str | None = None) -> list[dict]:
    """Validate and apply each update; return one change record per update (ok or not). Never raises for a bad
    update: the record carries `ok: false` and `error` instead, and is still logged."""
    date = date or _date.today().isoformat()
    out: list[dict] = []
    for raw in updates or []:
        if not isinstance(raw, dict):
            continue
        rec = {"ts": _now(), "date": date, "run": run, "actor": actor, "target": raw.get("target"),
               "op": raw.get("op") or ("resolve" if raw.get("target") == "decision" else "set"), "id": raw.get("id"),
               "before": None, "after": None, "reason": str(raw.get("reason") or "")[:500],
               "source_note_id": raw.get("source_note_id"), "ok": False, "error": None}
        upd, err = validate_update(raw)
        if upd is None:
            rec["error"] = f"invalid update: {err}"
            out.append(_log(rec))
            continue
        rec["op"] = getattr(upd, "op", rec["op"])
        try:
            if isinstance(upd, GoalUpdate):
                before, after = _goal(upd, actor, date)
            elif isinstance(upd, TaxAgendaUpdate):
                before, after = _tax_agenda(upd, actor, date)
                if upd.op == "add":
                    rec["id"] = after.get("id")
            elif isinstance(upd, ProfileNoteUpdate):
                before, after = _profile_note(upd, actor, date)
                rec["id"] = upd.path
            elif isinstance(upd, SpendingUpdate):
                before, after = _spending(upd, actor, date)
            elif isinstance(upd, DecisionUpdate):
                before, after = _decision(upd, actor, date, run)
            else:
                before, after = _merchant_rule(upd, actor, date)
            rec.update(before=_plain(before), after=_plain(after), ok=True)
        except UpdateError as e:
            rec["error"] = str(e)
        except Exception as e:  # noqa: BLE001  (a bug must not take the brief down)
            rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        _log(rec)
        if rec["ok"] and upd.target in ("goal", "tax_agenda"):
            refresh_plan()
        if rec["ok"] and upd.source_note_id:
            inbox.resolve(upd.source_note_id, "applied", describe(rec))
        out.append(rec)
    return out


def refresh_plan() -> bool:
    """Mirror goal status and tax-agenda items into state/derived/latest/plan.json so the dashboard shows an edit at
    once instead of after the next run (the pipeline rebuilds the whole file anyway)."""
    p = paths.LATEST / "plan.json"
    plan = settings.read_json(p, None)
    if not isinstance(plan, dict) or not plan.get("available"):
        return False
    try:
        settings.reset()
        prof = settings.profile_v2()
        goals = {g.get("id"): g for g in (settings.goals_v2() or {}).get("goals") or []}
        plan["tax_agenda"] = prof.get("tax_agenda") or []
        for row in plan.get("goals") or []:
            g = goals.get(row.get("id"))
            if g:
                row["status"] = g.get("status") or "active"
                row["completed_on"] = _iso(g.get("completed_on"))
                row["name"] = g.get("name") or row.get("name")
                row["deadline"] = _iso(g.get("deadline"))
        rows = plan.get("goals") or []
        plan["goals_summary"] = {s: sum(1 for r in rows if (r.get("status") or "active") == s) for s in ("active", "done", "paused")}
        settings.write_json(p, plan)
        return True
    except Exception:  # noqa: BLE001  (a stale plan.json is not worth failing an update over)
        return False


def apply_replies(replies: list[dict] | None, run: str) -> int:
    n = 0
    for r in replies or []:
        if isinstance(r, dict) and r.get("note_id") and inbox.resolve(str(r["note_id"]), "answered", str(r.get("reply") or "")[:1000]):
            n += 1
    return n


def describe(rec: dict) -> str:
    """One line for the dashboard and the brief: 'goal heloc_payoff: status active -> done'."""
    head = f"{rec.get('target')} {rec.get('id') or ''}".strip()
    if not rec.get("ok"):
        return f"{head}: not applied ({rec.get('error')})"
    before, after = rec.get("before") or {}, rec.get("after") or {}
    parts = []
    if rec.get("target") == "merchant_rule" and isinstance(after, dict) and "n" in after:
        return f"merchant rules: learned {after['n']} ({', '.join(after.get('examples') or [])[:120]})"
    for k, v in after.items():
        if k in ("text",):
            continue
        b = before.get(k) if isinstance(before, dict) else None
        parts.append(f"{k} {b} -> {v}" if b not in (None, "") and b != v else f"{k} = {v}")
    return f"{head}: {', '.join(parts) if parts else rec.get('op')}"


def _log(rec: dict) -> dict:
    paths.CHANGES.parent.mkdir(parents=True, exist_ok=True)
    with paths.CHANGES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec


def all_changes() -> list[dict]:
    if not paths.CHANGES.exists():
        return []
    rows = []
    for line in paths.CHANGES.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def recent_changes(n: int = 30, days: int | None = None) -> list[dict]:
    rows = all_changes()
    if days is not None:
        cutoff = (datetime.now().astimezone() - timedelta(days=days)).date().isoformat()
        rows = [r for r in rows if str(r.get("date") or "") >= cutoff]
    return [dict(r, summary=describe(r)) for r in rows[-n:]]
