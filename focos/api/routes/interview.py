from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ... import settings
from ...interview import engine, schemas

router = APIRouter(prefix="/interview")


@router.get("/schema")
def schema():
    return {"sections": schemas.SECTIONS, "hints": schemas.SECTION_HINTS, "schemas": schemas.all_schemas()}


@router.get("/current")
def current():
    prof = settings.profile_v2()
    return {"profile": {s: prof.get(s) for s in schemas.PROFILE_SECTIONS}, "goals": settings.goals_v2().get("goals") or []}


class Start(BaseModel):
    sections: list[str] | None = None


@router.post("/start")
def start(body: Start):
    return engine.start(sections=body.sections).model_dump()


class Reply(BaseModel):
    session_id: str
    text: str


@router.post("/reply")
def reply(body: Reply):
    try:
        return engine.reply(body.session_id, body.text).model_dump()
    except KeyError:
        raise HTTPException(404, "unknown session")


class Confirm(BaseModel):
    session_id: str | None = None
    section: str
    data: Any


@router.post("/confirm")
def confirm(body: Confirm):
    if body.section not in schemas.SECTIONS:
        raise HTTPException(400, "unknown section")
    errors, norm = engine.confirm(body.session_id, body.section, body.data)
    return {"ok": not errors, "errors": errors, "section": body.section, "data": norm}


class Skip(BaseModel):
    session_id: str
    section: str


@router.post("/skip")
def skip(body: Skip):
    try:
        s = engine.skip(body.session_id, body.section)
    except KeyError:
        raise HTTPException(404, "unknown session")
    return {"ok": True, "skipped": s.skipped, "confirmed": s.confirmed}
