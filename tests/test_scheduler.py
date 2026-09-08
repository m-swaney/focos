"""Job definitions and the rendered Task Scheduler XML / launchd plist (pure; nothing is installed)."""
import sys
from datetime import datetime
from pathlib import Path

import yaml

from focos import paths, scheduler, settings
from focos.scheduler import launchd, windows
from focos.scheduler.base import Schedule


def test_run_jobs_from_config(initialized_home: Path):
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"schedule": {
        "daily": {"days": "daily", "time": "07:05"}, "weekly": {"day": "sat", "time": "09:00"}, "monthly": {"day": 3, "time": "20:15"}}}))
    settings.reset()
    jobs = {j.key: j for j in scheduler.run_jobs()}
    assert set(jobs) == {"daily", "weekly", "monthly"}
    d = jobs["daily"]
    assert d.schedule.kind == "daily" and d.schedule.hour == 7 and d.schedule.minute == 5
    assert d.argv[1:4] == ["-I", "-m", "focos"] and "--home" in d.argv and str(paths.HOME) in d.argv
    assert d.argv[-3:] == ["run", "--mode", "daily"]
    if sys.platform == "win32":
        assert d.argv[0].lower().endswith("pythonw.exe")
    assert jobs["weekly"].schedule.weekdays() == ["sat"]
    assert jobs["monthly"].schedule.day == 3 and jobs["monthly"].schedule.weekdays() == []
    svc = scheduler.service_job()
    assert svc.schedule is None and svc.keep_alive and svc.argv[-2:] == ["serve", "--with-dashboard"]


def test_keepalive_job_only_for_robinhood(initialized_home: Path):
    assert "keepalive" not in {j.key for j in scheduler.run_jobs()}
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"holdings": {"source": "robinhood_mcp"},
                                                                          "schedule": {"keepalive": {"time": "08:30"}}}))
    settings.reset()
    jobs = {j.key: j for j in scheduler.run_jobs()}
    k = jobs["keepalive"]
    assert k.name == "focos-keepalive" and k.schedule.kind == "daily" and k.schedule.hour == 8 and k.schedule.minute == 30
    assert k.argv[-2:] == ["holdings", "keepalive"] and k.time_limit_minutes == 10
    xml = windows.task_xml(k, start=datetime(2026, 9, 5, 12, 0), user="u")
    assert "<Saturday/>" in xml and "<Sunday/>" in xml and "holdings keepalive" in xml and "PT10M" in xml
    assert launchd.plist_dict(k)["StartCalendarInterval"] == [{"Weekday": w, "Hour": 8, "Minute": 30} for w in (1, 2, 3, 4, 5, 6, 0)]
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"holdings": {"source": "robinhood_mcp"},
                                                                          "schedule": {"keepalive": {"enabled": False}}}))
    settings.reset()
    assert "keepalive" not in {j.key for j in scheduler.run_jobs()}


def test_windows_xml(initialized_home: Path):
    jobs = {j.key: j for j in scheduler.run_jobs()}
    xml = windows.task_xml(jobs["daily"], start=datetime(2026, 9, 5, 12, 0), user="BOX\\ann")
    assert "<StartBoundary>2026-09-05T16:35:00</StartBoundary>" in xml
    assert "<Monday/><Tuesday/><Wednesday/><Thursday/><Friday/>" in xml and "<Saturday/>" not in xml
    assert "<UserId>BOX\\ann</UserId>" in xml and "<LogonType>InteractiveToken</LogonType>" in xml
    assert "<WakeToRun>true</WakeToRun>" in xml and "<ExecutionTimeLimit>PT45M</ExecutionTimeLimit>" in xml
    assert '--home "' in xml or "--home " in xml
    assert "run --mode daily" in xml
    monthly = windows.task_xml(jobs["monthly"], start=datetime(2026, 9, 5), user="u")
    assert "<DaysOfMonth><Day>1</Day></DaysOfMonth>" in monthly and "<December/>" in monthly
    svc = windows.task_xml(scheduler.service_job(), user="u")
    assert "<LogonTrigger>" in svc and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in svc and "<RestartOnFailure>" in svc
    assert windows.task_name("focos-daily") == "focos\\focos-daily"


def test_launchd_plist(initialized_home: Path):
    jobs = {j.key: j for j in scheduler.run_jobs()}
    d = launchd.plist_dict(jobs["daily"], home="/Users/ann/focos-home")
    assert d["Label"] == "com.focos.daily"
    assert d["StartCalendarInterval"] == [{"Weekday": w, "Hour": 16, "Minute": 35} for w in (1, 2, 3, 4, 5)]
    assert d["EnvironmentVariables"]["FOCOS_HOME"] == "/Users/ann/focos-home" and d["RunAtLoad"] is False
    w = launchd.plist_dict(jobs["weekly"])
    assert w["StartCalendarInterval"] == [{"Weekday": 0, "Hour": 18, "Minute": 0}]
    m = launchd.plist_dict(jobs["monthly"])
    assert m["StartCalendarInterval"] == {"Day": 1, "Hour": 19, "Minute": 0}
    s = launchd.plist_dict(scheduler.service_job())
    assert s["RunAtLoad"] is True and s["KeepAlive"] is True and "ExitTimeOut" not in s
    text = launchd.plist_text(jobs["daily"])
    assert text.startswith("<?xml") and "com.focos.daily" in text


def test_schedule_model_helpers():
    assert Schedule(kind="weekdays", time="16:35").weekdays() == ["mon", "tue", "wed", "thu", "fri"]
    assert len(Schedule(kind="daily", time="00:00").weekdays()) == 7
    assert scheduler.current().platform in ("windows", "macos", sys.platform)
