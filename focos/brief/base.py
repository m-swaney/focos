from __future__ import annotations

import json
from typing import Literal, Protocol

from jsonschema import Draft202012Validator
from pydantic import BaseModel

from .. import paths, settings


class BriefOutcome(BaseModel):
    ok: bool
    result: dict | None = None
    report_path: str | None = None
    meta: dict = {}
    error: str | None = None


class BriefWriter(Protocol):
    mode_name: Literal["agent", "api"]

    def write(self, mode: str, date: str, run_id: str) -> BriefOutcome: ...


def validate_result(payload: dict) -> list[str]:
    schema = json.loads((paths.AGENT / "schemas" / "brief_result.schema.json").read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in sorted(v.iter_errors(payload), key=str)]


def record_result(payload: dict, meta: dict, date: str, mode: str) -> None:
    settings.write_json(paths.LATEST / "brief_result.json", {**payload, "_meta": meta, "date": date, "mode": mode})


def prepare_inbox(run_id: str, mode: str) -> dict:
    """Collect what the owner told us and what changed recently into state/derived/latest/inbox.json (agent mode reads
    the file; api mode inlines it). Marks pending notes as consumed by this run."""
    from .. import inbox
    from ..updates import apply as apply_mod

    prof = settings.profile_v2()
    goals = (settings.goals_v2() or {}).get("goals") or []
    payload = {
        "run_id": run_id, "mode": mode,
        "notes": inbox.consume(run_id),
        "recent_changes": apply_mod.recent_changes(20, days=14),
        "tax_agenda_open": [it for it in (prof.get("tax_agenda") or []) if it.get("status", "open") == "open"],
        "goals_active": [{"id": g.get("id"), "name": g.get("name"), "status": g.get("status") or "active"}
                         for g in goals if (g.get("status") or "active") == "active"],
        "goals_done": [g.get("id") for g in goals if g.get("status") == "done"],
    }
    settings.write_json(paths.LATEST / "inbox.json", payload)
    return payload


def apply_updates(payload: dict, *, run_id: str, date: str, extra_updates: list | None = None,
                  extra_replies: list | None = None) -> list[dict]:
    """Apply the model's `updates` and `note_replies` (inline in the result and/or from the agent-mode file), record
    the count, and surface rejected ones in needs_user so nothing fails silently."""
    from ..updates import apply as apply_mod

    updates = [u for u in (payload.pop("updates", None) or []) if isinstance(u, dict)] + [u for u in (extra_updates or []) if isinstance(u, dict)]
    replies = [r for r in (payload.pop("note_replies", None) or []) if isinstance(r, dict)] + [r for r in (extra_replies or []) if isinstance(r, dict)]
    changes = apply_mod.apply(updates, actor="model", run=run_id, date=date)
    apply_mod.apply_replies(replies, run_id)
    payload["updates_applied"] = sum(1 for c in changes if c["ok"])
    rejected = [apply_mod.describe(c) for c in changes if not c["ok"]]
    if rejected:
        payload["needs_user"] = list(payload.get("needs_user") or []) + [f"Could not apply: {r}" for r in rejected]
    return changes
