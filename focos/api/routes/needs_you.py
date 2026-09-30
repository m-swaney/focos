from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ... import needs_you

router = APIRouter(prefix="/needs-you")


class Act(BaseModel):
    id: str
    action: str                 # dismiss | snooze | restore
    days: int = 7


@router.get("")
def get():
    return needs_you.refresh()


@router.post("")
def act(body: Act):
    """Mark a non-decision item handled, snooze it, or bring it back. Decisions resolve through /updates."""
    try:
        return {"ok": True, **needs_you.act(body.id, body.action, body.days)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


@router.post("/start-fresh")
def start_fresh():
    return {"ok": True, **needs_you.start_fresh()}
