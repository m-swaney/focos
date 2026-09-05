"""Platform schedulers: Windows Task Scheduler, macOS launchd."""
from __future__ import annotations

import sys

from .base import JOB_NAMES, Job, JobStatus, Schedule, Scheduler, run_jobs, service_job  # noqa: F401


class UnsupportedScheduler:
    platform = sys.platform

    def install(self, jobs: list[Job]) -> list[JobStatus]:
        return [JobStatus(name=j.name, installed=False, detail={"error": f"no scheduler backend for {sys.platform}; run "
                                                                        f"`focos run --mode <mode>` from cron"}) for j in jobs]

    def uninstall(self, names: list[str] | None = None) -> list[str]:
        return []

    def status(self, names: list[str] | None = None) -> list[JobStatus]:
        return [JobStatus(name=n, installed=False) for n in (names or list(JOB_NAMES.values()))]

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
