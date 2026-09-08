from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ... import scheduler, settings
from ...config import writer
from ...config.models import ScheduleSettings

router = APIRouter(prefix="/schedule")


class Install(BaseModel):
    schedule: dict | None = None     # same shape as focos.yml schedule
    timezone: str | None = None      # written to profile.household.timezone
    install: bool = True


@router.post("/install")
def install(body: Install):
    if body.schedule is not None:
        try:
            sched = ScheduleSettings.model_validate(body.schedule).model_dump()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:300]}
        writer.write_section("focos.yml", "schedule", sched)
    if body.timezone:
        household = dict(settings.profile_v2().get("household") or {})
        household["timezone"] = body.timezone
        issues = writer.write_section("profile.yml", "household", household)
        if issues:
            return {"ok": False, "issues": [i.as_dict() for i in issues]}
    result = []
    if body.install:
        result = [s.model_dump() for s in scheduler.current().install(scheduler.run_jobs())]
    return {"ok": all(r.get("installed") for r in result) if result else True, "jobs": result,
            "schedule": settings.focos().get("schedule"), "platform": scheduler.current().platform}


@router.get("/status")
def status():
    return {"platform": scheduler.current().platform, "jobs": [s.model_dump() for s in scheduler.current().status()],
            "schedule": settings.focos().get("schedule"), "timezone": settings.timezone_name()}


@router.post("/uninstall")
def uninstall():
    return {"removed": scheduler.current().uninstall([scheduler.JOB_NAMES[k] for k in ("daily", "weekly", "monthly", "keepalive")])}
