"""The app's own clock: one long-running focos process runs every scheduled job itself.

Before 0.4 each job was its own operating-system task (nine on Windows), plus a separate dashboard service,
and an update had to re-register all of them. Anything that went wrong between them (a task pointing at an old
version, a service that ignored a restart) was invisible. Now the OS starts one thing, `focos serve`, and this
module decides what is due:

- **Jobs** come from `scheduler.run_jobs()` (daily, weekly, monthly, the intraday trading passes, the Robinhood
  keep-alive, the nightly update), all from `focos.yml`.
- **Catch-up.** A job whose time passed while the computer was off or asleep still runs when it comes back,
  inside a grace window that fits the job: the daily brief until midnight, a trading pass for 40 minutes (after
  that the next pass is closer), the update until 08:30.
- **One at a time.** Each job runs as its own process, so a crash cannot take the dashboard down, and a slow job
  only delays the next one.
- **Restart on update.** When `~/.focos/app.txt` points at a different version than the one running, the app
  finishes the job in flight and exits; the OS starts it again on the new version.

State lives in `state/heartbeat.json`, which `focos status` and the dashboard read.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import paths, settings

log = logging.getLogger("focos.heartbeat")

RESTART_EXIT = 75                 # "start me again": the OS task and launchd both bring the app back
TICK_SECONDS = 20
STATE_FILE = "heartbeat.json"


def state_file() -> Path:
    return paths.STATE / STATE_FILE


def enabled() -> bool:
    """On for installed releases; off for a developer checkout, which shares the household's data dir and must
    never run jobs against it by accident. FOCOS_HEARTBEAT=1/0 overrides either way."""
    flag = os.environ.get("FOCOS_HEARTBEAT")
    if flag is not None:
        return flag.strip() not in ("0", "false", "no", "")
    from . import updater

    return not updater.is_dev_checkout()


# ---------------------------------------------------------------- the schedule
def _grace(key: str, slot: datetime) -> timedelta:
    if key == "daily" or key == "keepalive":
        return (slot.replace(hour=23, minute=59, second=59) - slot)
    if key == "weekly":
        return timedelta(hours=24)
    if key == "monthly":
        return timedelta(hours=48)
    if key.startswith("trade"):
        return timedelta(minutes=40)
    if key == "update":
        return max(timedelta(0), slot.replace(hour=8, minute=30) - slot)
    return timedelta(hours=1)


def _matches(job, day: datetime) -> bool:
    s = job.schedule
    if s is None:
        return False
    if s.kind == "monthly":
        return day.day == int(s.day or 1)
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    return names[day.weekday()] in s.weekdays()


def last_slot(job, now: datetime) -> datetime | None:
    """The most recent scheduled time at or before `now`."""
    for back in range(0, 40):
        day = now - timedelta(days=back)
        if not _matches(job, day):
            continue
        slot = day.replace(hour=job.schedule.hour, minute=job.schedule.minute, second=0, microsecond=0)
        if slot <= now:
            return slot
    return None


def next_slot(job, now: datetime) -> datetime | None:
    for ahead in range(0, 40):
        day = now + timedelta(days=ahead)
        if not _matches(job, day):
            continue
        slot = day.replace(hour=job.schedule.hour, minute=job.schedule.minute, second=0, microsecond=0)
        if slot > now:
            return slot
    return None


def _parse(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=settings.tz())


def last_started(key: str, state: dict) -> datetime | None:
    """When this job last started: our own record, or the run records written by any way of running it (a manual
    `focos run`, or the OS task that ran it before 0.4), whichever is newer."""
    cands = [_parse((state.get("jobs") or {}).get(key, {}).get("started"))]
    from .run import status as run_status

    st = run_status.get() or {}
    mode = "trade" if key.startswith("trade") else key
    if mode in st:
        cands.append(_parse(st[mode].get("started")))
    if key == "keepalive":
        cands.append(_parse((settings.read_json(paths.KEEPALIVE, {}) or {}).get("ts")))
    cands = [c for c in cands if c is not None]
    return max(cands) if cands else None


def due(now: datetime, state: dict, jobs: list | None = None) -> list[tuple[datetime, object]]:
    """Jobs whose latest slot has passed, is still inside its grace window, and has not been started since."""
    from . import scheduler

    out = []
    for job in jobs if jobs is not None else scheduler.run_jobs():
        slot = last_slot(job, now)
        if slot is None or now - slot > _grace(job.key, slot):
            continue
        started = last_started(job.key, state)
        if started is not None and started >= slot:
            continue
        out.append((slot, job))
    return sorted(out, key=lambda x: x[0])


# ---------------------------------------------------------------- running jobs
def _argv(job) -> list[str]:
    """The job's own arguments, run with this interpreter (the job table was written for pythonw)."""
    i = job.argv.index("focos") if "focos" in job.argv else 3
    return [sys.executable, "-I", "-m", "focos"] + job.argv[i + 1:]


class Heartbeat:
    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.running: dict | None = None
        self.started_version = _installed_pointer()
        self.state = settings.read_json(state_file(), {}) or {}
        self._announce_version()

    # -- restart on update
    def restart_wanted(self) -> bool:
        """True once `app.txt` names a different app dir than the one this process runs from, and nothing is in
        flight. The OS then starts the app again from the new dir."""
        if self.proc is not None:
            return False
        now_pointer = _installed_pointer()
        return bool(now_pointer and self.started_version and now_pointer != self.started_version
                    and Path(now_pointer).resolve() != paths.APP.resolve())

    def _announce_version(self) -> None:
        from . import updater

        version = updater.installed_version(paths.APP)
        previous = self.state.get("version")
        self.state.update({"version": version, "app": str(paths.APP), "pid": os.getpid(),
                           "since": datetime.now(settings.tz()).isoformat(timespec="seconds")})
        self._save()
        if previous and previous != version:
            try:
                from . import notify

                notify.send("focos updated", f"Now on {version} (was {previous}).", "info", key=f"updated:{version}")
            except Exception:  # noqa: BLE001
                pass

    # -- the loop body
    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(settings.tz())
        self._reap(now)
        if self.proc is None:
            todo = due(now, self.state)
            if todo:
                slot, job = todo[0]
                self._launch(job, slot, now)
        self.state["tick_at"] = now.isoformat(timespec="seconds")
        self.state["running"] = self.running
        self.state["next"] = self._upcoming(now)
        self._save()

    def _launch(self, job, slot: datetime, now: datetime) -> None:
        paths.LOGS.mkdir(parents=True, exist_ok=True)
        logf = (paths.LOGS / f"job-{job.key}.log").open("a", encoding="utf-8")
        logf.write(f"\n=== {now.isoformat(timespec='seconds')} {job.key} (slot {slot:%Y-%m-%d %H:%M})\n")
        logf.flush()
        env = {**os.environ, "FOCOS_HEARTBEAT_CHILD": "1", "PYTHONIOENCODING": "utf-8"}
        try:
            self.proc = subprocess.Popen(_argv(job), cwd=str(paths.HOME), env=env, stdout=logf, stderr=subprocess.STDOUT,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as e:
            log.error("could not start %s: %s", job.key, e)
            self._record(job.key, {"started": now.isoformat(timespec="seconds"), "slot": slot.isoformat(),
                                   "exit": None, "error": str(e)[:200]})
            return
        finally:
            logf.close()
        limit = job.time_limit_minutes or 60
        self.running = {"key": job.key, "pid": self.proc.pid, "started": now.isoformat(timespec="seconds"),
                        "slot": slot.isoformat(), "deadline": (now + timedelta(minutes=limit)).isoformat(timespec="seconds")}
        self._record(job.key, {"started": now.isoformat(timespec="seconds"), "slot": slot.isoformat(), "exit": None})
        log.info("started %s (slot %s, pid %s)", job.key, f"{slot:%H:%M}", self.proc.pid)

    def _reap(self, now: datetime) -> None:
        if self.proc is None:
            return
        code = self.proc.poll()
        key = (self.running or {}).get("key", "?")
        if code is None:
            deadline = _parse((self.running or {}).get("deadline"))
            if deadline and now > deadline:
                log.warning("%s ran past its time limit; stopping it", key)
                self.proc.kill()
                code = -9
            else:
                return
        self._record(key, {**((self.state.get("jobs") or {}).get(key) or {}),
                           "finished": now.isoformat(timespec="seconds"), "exit": code})
        log.info("%s finished (exit %s)", key, code)
        self.proc = None
        self.running = None

    def _record(self, key: str, entry: dict) -> None:
        self.state.setdefault("jobs", {})[key] = entry

    def _upcoming(self, now: datetime) -> list[dict]:
        from . import scheduler

        rows = []
        for job in scheduler.run_jobs():
            nxt = next_slot(job, now)
            if nxt:
                rows.append({"key": job.key, "at": nxt.isoformat(timespec="minutes"), "what": job.description})
        return sorted(rows, key=lambda r: r["at"])

    def _save(self) -> None:
        try:
            settings.write_json(state_file(), self.state)
        except OSError as e:
            log.warning("could not write heartbeat state: %s", e)


def _installed_pointer() -> str | None:
    """The app dir `~/.focos/app.txt` names, or None for a checkout that is not installed that way."""
    try:
        from . import updater

        p = updater.app_pointer()
        return p.read_text(encoding="utf-8").strip() if p.exists() else None
    except OSError:
        return None


def read_state() -> dict:
    return settings.read_json(state_file(), {}) or {}


def alive(state: dict | None = None, max_age_s: int = 180) -> bool:
    st = state if state is not None else read_state()
    t = _parse(st.get("tick_at"))
    return bool(t and (datetime.now(settings.tz()) - t).total_seconds() < max_age_s)
