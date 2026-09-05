"""macOS launchd user agents (~/Library/LaunchAgents/com.focos.<job>.plist). A missed StartCalendarInterval fires
on wake from sleep, not after a full shutdown; `StartWhenAvailable` has no launchd equivalent."""
from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

from .base import DAY_INDEX, Job, JobStatus

PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def label(job_name: str) -> str:
    return "com." + job_name.replace("-", ".")


def plist_path(job_name: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label(job_name)}.plist"


def plist_dict(job: Job, home: str | None = None) -> dict:
    d: dict = {"Label": label(job.name), "ProgramArguments": job.argv, "WorkingDirectory": job.cwd,
               "EnvironmentVariables": {"PATH": PATH, **({"FOCOS_HOME": home} if home else {})},
               "ProcessType": "Background"}
    if job.log:
        d["StandardOutPath"] = job.log
        d["StandardErrorPath"] = job.log + ".err"
    if job.schedule is None:
        d["RunAtLoad"] = True
        d["KeepAlive"] = bool(job.keep_alive)
    else:
        s = job.schedule
        if s.kind == "monthly":
            d["StartCalendarInterval"] = {"Day": int(s.day or 1), "Hour": s.hour, "Minute": s.minute}
        else:
            d["StartCalendarInterval"] = [{"Weekday": DAY_INDEX[w], "Hour": s.hour, "Minute": s.minute} for w in s.weekdays()]
        d["RunAtLoad"] = False
    if job.time_limit_minutes:
        d["ExitTimeOut"] = job.time_limit_minutes * 60
    return d


def plist_text(job: Job, home: str | None = None) -> str:
    return plistlib.dumps(plist_dict(job, home), sort_keys=True).decode("utf-8")


def _domain() -> str:
    return f"gui/{os.getuid()}"  # type: ignore[attr-defined]


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


class LaunchdScheduler:
    platform = "macos"

    def install(self, jobs: list[Job]) -> list[JobStatus]:
        from .. import paths

        out = []
        for job in jobs:
            p = plist_path(job.name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(plist_text(job, str(paths.HOME)), encoding="utf-8")
            _launchctl("bootout", _domain(), str(p))  # ignore: not loaded yet
            r = _launchctl("bootstrap", _domain(), str(p))
            if r.returncode != 0:
                out.append(JobStatus(name=job.name, installed=False, detail={"error": (r.stderr or r.stdout).strip()[:300], "plist": str(p)}))
            else:
                out.append(self.status([job.name])[0])
        return out

    def uninstall(self, names: list[str] | None = None) -> list[str]:
        from .base import JOB_NAMES

        removed = []
        for n in names or list(JOB_NAMES.values()):
            p = plist_path(n)
            _launchctl("bootout", _domain(), str(p))
            if p.exists():
                p.unlink()
                removed.append(n)
        return removed

    def status(self, names: list[str] | None = None) -> list[JobStatus]:
        from .base import JOB_NAMES

        out = []
        for n in names or list(JOB_NAMES.values()):
            p = plist_path(n)
            if not p.exists():
                out.append(JobStatus(name=n, installed=False))
                continue
            r = _launchctl("print", f"{_domain()}/{label(n)}")
            state = last = None
            for line in (r.stdout or "").splitlines():
                t = line.strip()
                if t.startswith("state = "):
                    state = t.split("=", 1)[1].strip()
                elif t.startswith("last exit code = "):
                    last = t.split("=", 1)[1].strip()
            out.append(JobStatus(name=n, installed=r.returncode == 0, last_result=last, detail={"state": state, "plist": str(p)}))
        return out

    def start(self, name: str) -> bool:
        return _launchctl("kickstart", "-k", f"{_domain()}/{label(name)}").returncode == 0

    def stop(self, name: str) -> bool:
        return _launchctl("kill", "SIGTERM", f"{_domain()}/{label(name)}").returncode == 0
