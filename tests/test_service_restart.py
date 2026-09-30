"""An update must leave the new version serving: `service install` stops the running instance before it starts
the new one, because Task Scheduler ignores a start while an instance is still running."""
from pathlib import Path

from typer.testing import CliRunner


class FakeScheduler:
    def __init__(self):
        self.calls = []

    def stop(self, name):
        self.calls.append(("stop", name))
        return True

    def install(self, jobs):
        from focos.scheduler.base import JobStatus

        self.calls.append(("install", jobs[0].name))
        return [JobStatus(name=jobs[0].name, installed=True)]

    def start(self, name):
        self.calls.append(("start", name))
        return True


def test_service_install_restarts_instead_of_leaving_the_old_one(initialized_home: Path, monkeypatch):
    from focos import cli, scheduler
    from focos.service import supervisor

    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "current", lambda: fake)
    monkeypatch.setattr(supervisor, "reap_orphans", lambda: [])
    monkeypatch.setattr(cli, "_wait_ports_free", lambda timeout_s=20.0: True)
    r = CliRunner().invoke(cli.app, ["service", "install"])
    assert r.exit_code == 0, r.output
    assert [c[0] for c in fake.calls] == ["stop", "install", "start"]


def test_install_without_start_does_not_touch_the_running_service(initialized_home: Path, monkeypatch):
    from focos import cli, scheduler

    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "current", lambda: fake)
    r = CliRunner().invoke(cli.app, ["service", "install", "--no-start"])
    assert r.exit_code == 0, r.output
    assert [c[0] for c in fake.calls] == ["install"]


def test_auto_update_warns_when_the_old_dashboard_keeps_serving(initialized_home: Path, monkeypatch,
                                                                _no_real_notifications):
    from focos import updater

    monkeypatch.setattr(updater, "is_dev_checkout", lambda app=None: False)
    monkeypatch.setattr(updater, "check", lambda repo=None: {"newer": True, "available": "v9.9.9"})
    monkeypatch.setattr(updater, "update", lambda repo=None, log=print: {"updated": True, "available": "v9.9.9",
                                                                        "service_version": "9.9.8"})
    updater.auto_update()
    assert any("still on the old version" in n["title"] for n in _no_real_notifications)
