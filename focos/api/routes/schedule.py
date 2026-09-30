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
        result = scheduler.install_app()["jobs"]
    return {"ok": all(r.get("installed") for r in result) if result else True, "jobs": _job_rows(),
            "schedule": settings.focos().get("schedule"), "platform": scheduler.current().platform}


def _job_rows() -> list[dict]:
    """The schedule as the setup page lists it: one row per job the app runs, with its next time. `installed`
    means the app that runs it is registered with the OS."""
    from datetime import datetime

    from ... import heartbeat

    app_ok = any(s.installed for s in scheduler.current().status())
    now = datetime.now(settings.tz())
    rows = []
    for job in scheduler.run_jobs():
        nxt = heartbeat.next_slot(job, now)
        rows.append({"name": job.description, "key": job.key, "installed": app_ok, "_at": nxt.isoformat() if nxt else "~",
                     "next_run": nxt.strftime("%a %b %d %H:%M") if nxt else None})
    return [{k: v for k, v in r.items() if k != "_at"} for r in sorted(rows, key=lambda r: r["_at"])]


@router.get("/status")
def status():
    from ... import heartbeat

    return {"platform": scheduler.current().platform, "jobs": _job_rows(), "running": heartbeat.alive(),
            "schedule": settings.focos().get("schedule"), "timezone": settings.timezone_name()}


@router.post("/uninstall")
def uninstall():
    return {"removed": scheduler.current().uninstall()}
