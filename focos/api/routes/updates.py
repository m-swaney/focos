from __future__ import annotations

from datetime import date as _date

from fastapi import APIRouter
from pydantic import BaseModel

from ...updates import apply as apply_mod

router = APIRouter()


class Updates(BaseModel):
    updates: list[dict]


@router.post("/updates")
def apply(body: Updates):
    """Owner-initiated updates (Done buttons, category picks). Applied immediately and logged as actor=user."""
    changes = apply_mod.apply(body.updates, actor="user", run="user", date=_date.today().isoformat())
    return {"ok": bool(changes) and all(c["ok"] for c in changes),
            "changes": [dict(c, summary=apply_mod.describe(c)) for c in changes]}


@router.get("/changes")
def changes(n: int = 50, days: int | None = None):
    return {"changes": list(reversed(apply_mod.recent_changes(n, days)))}
