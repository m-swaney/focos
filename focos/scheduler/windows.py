"""Windows Task Scheduler via `schtasks /Create /XML` (no admin, runs as the logged-on user)."""
from __future__ import annotations

import csv
import io
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .base import Job, JobStatus

FOLDER = "focos"
DAY_TAGS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


LEGACY_TASK_NAMES = ("FOCOS Daily", "FOCOS Weekly", "FOCOS Monthly", "FOCOS Dashboard")  # pre-1.0 PowerShell tasks


def task_name(job_name: str) -> str:
    return f"{FOLDER}\\{job_name}"


def current_user() -> str:
    dom, user = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
    return f"{dom}\\{user}" if dom and user else (user or "")


def _quote(arg: str) -> str:
    return f'"{arg}"' if (" " in arg or "\\" in arg) and not arg.startswith('"') else arg


def _trigger(job: Job, start: datetime) -> str:
    if job.schedule is None:
        return f"<LogonTrigger><Enabled>true</Enabled><UserId>{escape(current_user())}</UserId></LogonTrigger>"
    s = job.schedule
    boundary = start.replace(hour=s.hour, minute=s.minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")
    if s.kind == "monthly":
        months = "".join(f"<{m}/>" for m in MONTHS)
        body = f"<ScheduleByMonth><DaysOfMonth><Day>{int(s.day or 1)}</Day></DaysOfMonth><Months>{months}</Months></ScheduleByMonth>"
    else:
        days = "".join(f"<{DAY_TAGS[d]}/>" for d in s.weekdays())
        body = f"<ScheduleByWeek><DaysOfWeek>{days}</DaysOfWeek><WeeksInterval>1</WeeksInterval></ScheduleByWeek>"
    return f"<CalendarTrigger><StartBoundary>{boundary}</StartBoundary><Enabled>true</Enabled>{body}</CalendarTrigger>"


def task_xml(job: Job, start: datetime | None = None, user: str | None = None) -> str:
    start = start or datetime.now()
    user = user or current_user()
    limit = f"PT{job.time_limit_minutes}M" if job.time_limit_minutes else "PT0S"
    restart = "<RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>" if job.keep_alive else ""
    cmd, args = job.argv[0], " ".join(_quote(a) for a in job.argv[1:])
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{escape(job.description)}</Description></RegistrationInfo>
  <Triggers>{_trigger(job, start)}</Triggers>
  <Principals><Principal id="Author"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>{"true" if job.schedule else "false"}</RunOnlyIfNetworkAvailable>
    <WakeToRun>{"true" if job.wake else "false"}</WakeToRun>
    <ExecutionTimeLimit>{limit}</ExecutionTimeLimit>
    {restart}
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author"><Exec><Command>{escape(cmd)}</Command><Arguments>{escape(args)}</Arguments><WorkingDirectory>{escape(job.cwd)}</WorkingDirectory></Exec></Actions>
</Task>
"""


def _schtasks(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["schtasks", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


class WindowsScheduler:
    platform = "windows"

    def legacy_present(self) -> list[str]:
        return [n for n in LEGACY_TASK_NAMES if _schtasks("/Query", "/TN", n).returncode == 0]

    def remove_legacy(self) -> list[str]:
        removed = []
        for n in self.legacy_present():
            _schtasks("/End", "/TN", n)
            if _schtasks("/Delete", "/F", "/TN", n).returncode == 0:
                removed.append(n)
        return removed

    def install(self, jobs: list[Job]) -> list[JobStatus]:
        self.remove_legacy()
        out = []
        for job in jobs:
            with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as f:
                f.write(task_xml(job))
                xml_path = f.name
            try:
                r = _schtasks("/Create", "/F", "/TN", task_name(job.name), "/XML", xml_path)
            finally:
                Path(xml_path).unlink(missing_ok=True)
            if r.returncode != 0:
                out.append(JobStatus(name=job.name, installed=False, detail={"error": (r.stderr or r.stdout).strip()[:300]}))
            else:
                out.append(self.status([job.name])[0])
        return out

    def uninstall(self, names: list[str] | None = None) -> list[str]:
        from .base import JOB_NAMES

        removed = self.remove_legacy()
        for n in names or list(JOB_NAMES.values()):
            if _schtasks("/Delete", "/F", "/TN", task_name(n)).returncode == 0:
                removed.append(n)
        return removed

    def status(self, names: list[str] | None = None) -> list[JobStatus]:
        from .base import JOB_NAMES

        out = []
        for n in names or list(JOB_NAMES.values()):
            r = _schtasks("/Query", "/TN", task_name(n), "/FO", "CSV", "/V")
            if r.returncode != 0:
                out.append(JobStatus(name=n, installed=False))
                continue
            rows = list(csv.DictReader(io.StringIO(r.stdout)))
            row = rows[0] if rows else {}
            out.append(JobStatus(name=n, installed=True, next_run=row.get("Next Run Time"), last_run=row.get("Last Run Time"),
                                 last_result=row.get("Last Result"), detail={"status": row.get("Status"), "task": task_name(n)}))
        return out

    def start(self, name: str) -> bool:
        return _schtasks("/Run", "/TN", task_name(name)).returncode == 0

    def stop(self, name: str) -> bool:
        return _schtasks("/End", "/TN", task_name(name)).returncode == 0
