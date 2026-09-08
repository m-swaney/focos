from pathlib import Path

import yaml

from focos import paths, settings
from focos.brief.base import BriefOutcome
from focos.orchestrator import run as orch
from focos.run import status


class FakeSource:
    name = "fake"

    def __init__(self, ok=True, fail=False):
        self._ok, self._fail = ok, fail
        self.last_meta = {"num_turns": 3}

    def available(self):
        return (True, None) if self._ok else (False, "not connected")

    def capture(self, asof, mode, run_id):
        if self._fail:
            raise RuntimeError("boom")
        from focos.holdings import write_snapshot
        from focos.holdings.base import empty_snapshot
        snap = empty_snapshot(asof, mode, self.name)
        write_snapshot(snap)
        return snap


class FakeWriter:
    mode_name = "fake"

    def __init__(self, ok=True):
        self._ok = ok

    def write(self, mode, date, run_id):
        if not self._ok:
            return BriefOutcome(ok=False, error="model unavailable")
        (paths.REPORTS / mode / f"{date}.md").write_text("# brief\n", encoding="utf-8")
        payload = {"summary_line": "fine", "report_path": f"reports/{mode}/{date}.md", "alerts": [], "needs_user": []}
        settings.write_json(paths.LATEST / "brief_result.json", payload)
        return BriefOutcome(ok=True, result=payload, report_path=payload["report_path"])


def test_full_cycle_with_fakes(initialized_home: Path, monkeypatch):
    monkeypatch.setattr("focos.orchestrator.run.holdings.current", lambda: FakeSource())
    monkeypatch.setattr("focos.orchestrator.run.writer_for", lambda cfg: FakeWriter())
    res = orch.run(orch.RunOptions(mode="daily", date="2026-03-01", no_git=True))
    assert res.ok, res.stages
    assert res.stages["A"].startswith("ok (fake") and res.stages["B"].startswith("ok") and res.stages["C"].startswith("ok")
    st = status.get()["daily"]
    assert st["ok"] is True and st["stages"]["A"]["ok"] and st["stages"]["C"]["ok"]
    assert st["summary_line"] == "fine" and st["report_path"] == "reports/daily/2026-03-01.md"
    assert "cost_usd" not in st and "cost_usd" not in st["stages"]["A"]
    assert Path(res.log_file).exists()


def test_stage_a_unavailable_stops_run(initialized_home: Path, monkeypatch):
    monkeypatch.setattr("focos.orchestrator.run.holdings.current", lambda: FakeSource(ok=False))
    res = orch.run(orch.RunOptions(mode="daily", date="2026-03-01", no_git=True))
    assert not res.ok and "not connected" in res.stages["A"] and "B" not in res.stages
    assert status.get()["daily"]["ok"] is False


def test_stage_c_failure_marks_run_failed_but_finishes(initialized_home: Path, monkeypatch):
    monkeypatch.setattr("focos.orchestrator.run.holdings.current", lambda: FakeSource())
    monkeypatch.setattr("focos.orchestrator.run.writer_for", lambda cfg: FakeWriter(ok=False))
    res = orch.run(orch.RunOptions(mode="daily", date="2026-03-01", no_git=True))
    assert not res.ok and res.stages["C"].startswith("failed: model unavailable")
    assert status.get()["daily"]["finished"]


def test_skips_and_commit(initialized_home: Path, monkeypatch):
    monkeypatch.setattr("focos.orchestrator.run.writer_for", lambda cfg: FakeWriter())
    res = orch.run(orch.RunOptions(mode="daily", date="2026-03-01", skip_a=True, skip_b=True))
    assert res.ok and res.stages["A"] == "skipped" and res.stages["B"] == "skipped"
    if (initialized_home / ".git").exists():  # git available on this machine: the run committed reports/ and state/
        assert res.commit and len(res.commit) == 7
        res2 = orch.run(orch.RunOptions(mode="daily", date="2026-03-01", skip_a=True, skip_b=True))
        assert res2.commit is None or res2.commit != res.commit


def test_describe_dry_run(initialized_home: Path):
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"holdings": {"source": "csv"}, "ai": {"mode": "agent"}}))
    settings.reset()
    d = orch.describe(orch.RunOptions(mode="weekly"))
    assert d["holdings_source"]["name"] == "csv" and d["holdings_source"]["available"] is False
    assert d["brief_writer"] == "agent" and d["ledger_provider"] == "simplefin"
