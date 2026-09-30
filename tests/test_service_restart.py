"""One app, one OS task: installing registers only the app (removing the per-job tasks), starting is a no-op
while it runs, and an update is picked up by the app restarting itself."""
import sys
from datetime import datetime
from pathlib import Path

from focos import scheduler
from focos.scheduler import launchd, windows


class FakeScheduler:
    platform = "fake"

    def __init__(self):
        self.calls = []

    def stop(self, name):
        self.calls.append(("stop", name))
        return True

    def install(self, jobs):
        from focos.scheduler.base import JobStatus

        self.calls.append(("install", [j.name for j in jobs]))
        return [JobStatus(name=jobs[0].name, installed=True)]

    def start(self, name):
        self.calls.append(("start", name))
        return True

    def status(self, names=None):
        from focos.scheduler.base import JobStatus

        return [JobStatus(name=n, installed=True) for n in (names or [scheduler.APP_JOB])]


def test_install_registers_only_the_app_and_never_stops_it(initialized_home: Path, monkeypatch):
    from focos import updater

    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "current", lambda: fake)
    monkeypatch.setattr(updater, "write_shims", lambda log=print: [])
    out = scheduler.install_app()
    assert fake.calls == [("install", ["focos"]), ("start", "focos")]
    assert out["started"] is True


def test_the_app_task_is_a_logon_start_with_a_watchdog(initialized_home: Path):
    job = scheduler.app_job()
    assert scheduler.os_jobs() == [job]
    assert job.argv[-2:] == ["serve", "--with-dashboard"] and job.keep_alive and job.repeat_minutes == 1
    xml = windows.task_xml(job, start=datetime(2026, 10, 1, 9, 0), user="BOX\\ann")
    assert "<LogonTrigger>" in xml and "<Interval>PT1M</Interval>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml
    assert "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml and "<WakeToRun>false</WakeToRun>" in xml
    plist = launchd.plist_dict(job)
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] is True
    assert "focos-dashboard" in scheduler.LEGACY_JOB_NAMES and "focos-trade-1" in scheduler.LEGACY_JOB_NAMES


def test_auto_update_warns_when_the_old_version_keeps_running(initialized_home: Path, monkeypatch,
                                                              _no_real_notifications):
    from focos import updater

    monkeypatch.setattr(updater, "is_dev_checkout", lambda app=None: False)
    monkeypatch.setattr(updater, "check", lambda repo=None: {"newer": True, "available": "v9.9.9"})
    monkeypatch.setattr(updater, "update", lambda repo=None, log=print: {"updated": True, "available": "v9.9.9",
                                                                        "service_version": "9.9.8"})
    updater.auto_update()
    assert any("still running the old version" in n["title"] for n in _no_real_notifications)


def test_shims_include_one_for_git_bash(tmp_path: Path, monkeypatch):
    from focos import updater

    monkeypatch.setattr(updater, "base_dir", lambda: tmp_path)
    written = updater.write_shims(log=lambda m: None)
    if sys.platform != "win32":
        assert written == []
        return
    sh = (tmp_path / "bin" / "focos").read_text(encoding="utf-8")
    assert sh.startswith("#!/bin/sh") and "app.txt" in sh and '-m focos "$@"' in sh and "\r" not in sh
    assert (tmp_path / "bin" / "focos.cmd").exists()
    assert updater.write_shims(log=lambda m: None) == []      # unchanged on a second run
