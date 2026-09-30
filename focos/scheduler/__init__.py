"""Platform schedulers: Windows Task Scheduler, macOS launchd."""
from __future__ import annotations

import sys

from .base import (APP_JOB, JOB_NAMES, LEGACY_JOB_NAMES, TRADE_JOB_PREFIX, Job, JobStatus, Schedule,  # noqa: F401
                   Scheduler, app_job, os_jobs, run_jobs, service_job, trade_job_name)


class UnsupportedScheduler:
    platform = sys.platform

    def install(self, jobs: list[Job]) -> list[JobStatus]:
        return [JobStatus(name=j.name, installed=False, detail={"error": f"no scheduler backend for {sys.platform}; run "
                                                                        f"`focos run --mode <mode>` from cron"}) for j in jobs]

    def uninstall(self, names: list[str] | None = None) -> list[str]:
        return []

    def status(self, names: list[str] | None = None) -> list[JobStatus]:
        return [JobStatus(name=n, installed=False) for n in (names or [APP_JOB])]

    def start(self, name: str) -> bool:
        return False

    def stop(self, name: str) -> bool:
        return False


def current() -> Scheduler:
    if sys.platform == "win32":
        from .windows import WindowsScheduler
        return WindowsScheduler()
    if sys.platform == "darwin":
        from .launchd import LaunchdScheduler
        return LaunchdScheduler()
    return UnsupportedScheduler()


def install_app(start: bool = True) -> dict:
    """Register the one OS task (the app), remove the per-job tasks from before 0.4, and write the `focos`
    command shims. Starting is a no-op while the app already runs; a running app restarts itself when it sees a
    newer version installed."""
    from .. import updater

    sch = current()
    res = sch.install(os_jobs())
    started = False
    if start and res and res[0].installed:
        if getattr(sch, "last_removed", None):
            _wait_ports_free()      # the old dashboard was just stopped; let its ports go before the app binds them
        started = sch.start(APP_JOB)
    updater.write_shims(log=lambda m: None)
    return {"platform": sch.platform, "started": started, "jobs": [s.model_dump() for s in res]}


def _wait_ports_free(timeout_s: float = 20.0) -> bool:
    import socket
    import time

    from .. import settings

    dash = settings.focos().get("dashboard") or {}
    ports = [int(dash.get("port") or 3100), int(dash.get("api_port") or 3101)]
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        busy = False
        for port in ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    busy = True
        if not busy:
            return True
        time.sleep(0.5)
    return False
