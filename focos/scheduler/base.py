"""Scheduled jobs (daily/weekly/monthly runs, the dashboard service) described once, installed per platform."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from .. import paths, settings

JOB_NAMES = {"daily": "focos-daily", "weekly": "focos-weekly", "monthly": "focos-monthly", "keepalive": "focos-keepalive",
             "service": "focos-dashboard"}
TRADE_JOB_PREFIX = "focos-trade"


def trade_job_name(index: int) -> str:
    """One job per configured intraday time; the index keeps Task Scheduler names stable across reinstalls."""
    return f"{TRADE_JOB_PREFIX}-{index + 1}"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
DAY_INDEX = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


class Schedule(BaseModel):
    kind: Literal["weekdays", "daily", "weekly", "monthly"]
    time: str                      # HH:MM local
    day: str | int | None = None   # weekly: mon..sun; monthly: 1..28

    @property
    def hour(self) -> int:
        return int(self.time.split(":")[0])

    @property
    def minute(self) -> int:
        return int(self.time.split(":")[1])

    def weekdays(self) -> list[str]:
        if self.kind == "weekdays":
            return WEEKDAYS
        if self.kind == "daily":
            return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        if self.kind == "weekly":
            return [str(self.day or "sun")]
        return []


class Job(BaseModel):
    key: str                       # daily | weekly | monthly | service
    name: str                      # platform-neutral name, e.g. focos-daily
    description: str
    argv: list[str]
    cwd: str
    schedule: Schedule | None = None   # None = at login (service)
    keep_alive: bool = False
    wake: bool = True
    time_limit_minutes: int | None = 45
    log: str | None = None


class JobStatus(BaseModel):
    name: str
    installed: bool
    next_run: str | None = None
    last_run: str | None = None
    last_result: str | None = None
    detail: dict = {}


class Scheduler(Protocol):
    platform: str

    def install(self, jobs: list[Job]) -> list[JobStatus]: ...
    def uninstall(self, names: list[str] | None = None) -> list[str]: ...
    def status(self, names: list[str] | None = None) -> list[JobStatus]: ...


def python_exe(windowless: bool = False) -> str:
    """This interpreter (the app venv). On Windows scheduled runs use pythonw.exe so no console flashes."""
    exe = Path(sys.executable)
    if windowless and sys.platform == "win32":
        pw = exe.with_name("pythonw.exe")
        if pw.exists():
            return str(pw)
    return str(exe)


def _base_argv(windowless: bool) -> list[str]:
    return [python_exe(windowless), "-I", "-m", "focos", "--home", str(paths.HOME)]


def run_jobs(cfg: dict | None = None) -> list[Job]:
    cfg = cfg if cfg is not None else settings.focos()
    sched = cfg.get("schedule") or {}
    d, w, m = sched.get("daily") or {}, sched.get("weekly") or {}, sched.get("monthly") or {}
    specs = {
        "daily": Schedule(kind=("daily" if d.get("days") == "daily" else "weekdays"), time=str(d.get("time") or "16:35")),
        "weekly": Schedule(kind="weekly", time=str(w.get("time") or "18:00"), day=str(w.get("day") or "sun")),
        "monthly": Schedule(kind="monthly", time=str(m.get("time") or "19:00"), day=int(m.get("day") or 1)),
    }
    jobs = []
    for key, schedule in specs.items():
        jobs.append(Job(key=key, name=JOB_NAMES[key], description=f"focos {key} run", schedule=schedule,
                        argv=_base_argv(True) + ["run", "--mode", key], cwd=str(paths.HOME),
                        log=str(paths.LOGS / f"scheduler-{key}.log")))
    t = sched.get("trade") or {}
    if t.get("enabled", True):
        # Weekdays only, and only inside regular hours: an order placed outside them is rejected by the gate
        # anyway, so a job scheduled there would burn tokens to achieve nothing.
        exits = {str(x) for x in (t.get("exits_only") or [])}
        for i, at in enumerate(t.get("times") or ["10:30", "12:45", "15:00"]):
            exits_only = str(at) in exits
            kind = "exits-only pass" if exits_only else "trading pass"
            jobs.append(Job(key=f"trade{i + 1}", name=trade_job_name(i), description=f"focos intraday {kind} ({at})",
                            schedule=Schedule(kind="weekdays", time=str(at)),
                            argv=_base_argv(True) + ["run", "--mode", "trade"] + (["--exits-only"] if exits_only else []),
                            cwd=str(paths.HOME),
                            time_limit_minutes=15, log=str(paths.LOGS / f"scheduler-trade{i + 1}.log")))
    k = sched.get("keepalive") or {}
    if (cfg.get("holdings") or {}).get("source") == "robinhood_mcp" and k.get("enabled", True):
        # every day (weekends included): one cheap read so the broker OAuth token is refreshed before it lapses
        jobs.append(Job(key="keepalive", name=JOB_NAMES["keepalive"], description="focos Robinhood login keep-alive",
                        schedule=Schedule(kind="daily", time=str(k.get("time") or "09:00")),
                        argv=_base_argv(True) + ["holdings", "keepalive"], cwd=str(paths.HOME), time_limit_minutes=10,
                        log=str(paths.LOGS / "scheduler-keepalive.log")))
    return jobs


def service_job() -> Job:
    return Job(key="service", name=JOB_NAMES["service"], description="focos dashboard and local API",
               argv=_base_argv(True) + ["serve", "--with-dashboard"], cwd=str(paths.HOME), schedule=None,
               keep_alive=True, wake=False, time_limit_minutes=None, log=str(paths.LOGS / "service.log"))
