"""The app's own scheduler: what is due, catch-up after a sleep, one job at a time, and restart on update."""
import json
from datetime import datetime
from pathlib import Path

import yaml

from focos import heartbeat, paths, scheduler, settings


def _cfg(home: Path, extra: dict | None = None):
    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"agent": {"sandbox_enabled": True}, **(extra or {})}))
    settings.reset()


def _at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=settings.tz())


def _keys(now: datetime, state: dict | None = None) -> list[str]:
    return [j.key for _, j in heartbeat.due(now, state or {})]


def test_daily_catches_up_until_midnight_then_lets_go(initialized_home: Path):
    _cfg(initialized_home)
    assert "daily" not in _keys(_at("2026-09-30T16:30"))            # not yet
    assert "daily" in _keys(_at("2026-09-30T16:36"))
    assert "daily" in _keys(_at("2026-09-30T22:10"))                # the PC was off at 16:35
    assert "daily" not in _keys(_at("2026-10-01T09:00"))            # yesterday's brief is not written a day late


def test_a_trading_pass_only_runs_near_its_time(initialized_home: Path):
    _cfg(initialized_home)
    assert "trade1" in _keys(_at("2026-09-30T10:31"))
    assert "trade1" in _keys(_at("2026-09-30T11:05"))
    assert "trade1" not in _keys(_at("2026-09-30T11:20"))           # past 40 minutes: wait for the next pass
    assert not [k for k in _keys(_at("2026-10-03T10:31")) if k.startswith("trade")]   # Saturday


def test_anything_that_already_ran_is_not_run_again(initialized_home: Path):
    from focos.run import status

    _cfg(initialized_home)
    now = _at("2026-09-30T16:40")
    status.start("daily", "daily-x")
    st = json.loads(paths.STATUS.read_text(encoding="utf-8"))
    st["daily"]["started"] = "2026-09-30T20:35:00+00:00"            # 16:35 Eastern, by a manual run or an old task
    paths.STATUS.write_text(json.dumps(st), encoding="utf-8")
    if settings.timezone_name() in ("America/New_York", "US/Eastern"):
        assert "daily" not in _keys(now)
    own = {"jobs": {"daily": {"started": now.isoformat()}}}
    assert "daily" not in _keys(now, own)


def test_update_runs_overnight_only(initialized_home: Path):
    _cfg(initialized_home)
    assert "update" in _keys(_at("2026-09-30T05:20"))
    assert "update" in _keys(_at("2026-09-30T08:00"))
    assert "update" not in _keys(_at("2026-09-30T13:00"))


class FakeProc:
    def __init__(self, argv, **kw):
        self.argv, self.kw, self.code, self.pid = argv, kw, None, 4242
        FakeProc.started.append(self)

    def poll(self):
        return self.code

    def kill(self):
        self.code = -9


def test_one_job_at_a_time_and_the_record_is_kept(initialized_home: Path, monkeypatch):
    _cfg(initialized_home)
    FakeProc.started = []
    monkeypatch.setattr(heartbeat.subprocess, "Popen", FakeProc)
    hb = heartbeat.Heartbeat()
    hb.tick(_at("2026-09-30T05:20"))                                   # the nightly update is due
    assert len(FakeProc.started) == 1 and FakeProc.started[0].argv[-2:] == ["update", "--auto"]
    assert FakeProc.started[0].kw["env"]["FOCOS_HEARTBEAT_CHILD"] == "1"
    hb.tick(_at("2026-09-30T05:30"))                                   # still running: nothing new starts
    assert len(FakeProc.started) == 1
    FakeProc.started[0].code = 0
    hb.tick(_at("2026-09-30T10:31"))                                   # finished, so the 10:30 pass starts
    assert len(FakeProc.started) == 2 and FakeProc.started[1].argv[-3:] == ["run", "--mode", "trade"]
    state = heartbeat.read_state()
    assert state["jobs"]["update"]["exit"] == 0 and state["running"]["key"] == "trade1"
    assert any(r["key"] == "daily" for r in state["next"])
    # a pass that hangs is stopped at its time limit
    hb.tick(_at("2026-09-30T10:50"))
    assert FakeProc.started[1].code == -9 and hb.running is None


def test_restart_when_a_newer_version_is_installed(initialized_home: Path, monkeypatch, tmp_path):
    from focos import updater

    pointer = tmp_path / "app.txt"
    pointer.write_text(str(tmp_path / "app-v0.4.0"), encoding="utf-8")
    monkeypatch.setattr(updater, "app_pointer", lambda: pointer)
    hb = heartbeat.Heartbeat()
    assert not hb.restart_wanted()
    pointer.write_text(str(tmp_path / "app-v0.4.1"), encoding="utf-8")
    assert hb.restart_wanted()
    hb.proc = FakeProc(["x"])                                          # never mid-job
    assert not hb.restart_wanted()


def test_version_change_is_announced_once(initialized_home: Path, _no_real_notifications):
    heartbeat.state_file().parent.mkdir(parents=True, exist_ok=True)
    heartbeat.state_file().write_text(json.dumps({"version": "0.0.1"}), encoding="utf-8")
    heartbeat.Heartbeat()
    heartbeat.Heartbeat()
    assert [n["title"] for n in _no_real_notifications] == ["focos updated"]


def test_dev_checkouts_do_not_run_jobs(monkeypatch):
    from focos import updater

    monkeypatch.delenv("FOCOS_HEARTBEAT", raising=False)
    monkeypatch.setattr(updater, "is_dev_checkout", lambda app=None: True)
    assert not heartbeat.enabled()
    monkeypatch.setenv("FOCOS_HEARTBEAT", "1")
    assert heartbeat.enabled()


def test_every_job_in_the_table_has_a_schedule(initialized_home: Path):
    _cfg(initialized_home, {"holdings": {"source": "robinhood_mcp"}})
    keys = {j.key for j in scheduler.run_jobs()}
    assert {"daily", "weekly", "monthly", "trade1", "trade2", "trade3", "keepalive", "update"} <= keys


def test_a_failed_update_is_retried_but_a_failed_brief_is_not(initialized_home: Path):
    _cfg(initialized_home)
    t = "2026-09-30T05:15:10-04:00"
    state = {"jobs": {"update": {"started": t, "exit": 1}, "daily": {"started": "2026-09-30T16:35:05-04:00", "exit": 1}}}
    if settings.timezone_name() not in ("America/New_York", "US/Eastern"):
        return
    assert "update" not in _keys(_at("2026-09-30T05:30"), state)        # too soon
    assert "update" in _keys(_at("2026-09-30T05:50"), state)            # half an hour later
    assert "update" not in _keys(_at("2026-09-30T09:00"), state)        # the window closed
    assert "daily" not in _keys(_at("2026-09-30T18:00"), state)
    state["jobs"]["update"]["exit"] = 0
    assert "update" not in _keys(_at("2026-09-30T05:50"), state)
