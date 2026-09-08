from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ... import inbox

router = APIRouter(prefix="/inbox")


class Note(BaseModel):
    text: str
    about: dict | None = None


@router.get("")
def list_notes(n: int = 20):
    return {"pending": inbox.pending(), "recent": inbox.recent(n), "unaddressed": inbox.unaddressed()}


@router.post("")
def add(body: Note):
    try:
        note = inbox.add(body.text, about=body.about, source="dashboard")
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "note": note}


@router.post("/{note_id}/dismiss")
def dismiss(note_id: str):
    note = inbox.dismiss(note_id)
    return {"ok": note is not None, "note": note, "error": None if note else "unknown note"}
