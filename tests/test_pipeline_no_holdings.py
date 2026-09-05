from pathlib import Path

from focos import paths, pipeline, settings


def test_pipeline_runs_without_holdings(initialized_home: Path):
    out = pipeline.run("daily", "2026-03-01", bump=False)
    assert out["holdings"] is False and out["total_value"] is None
    latest = paths.LATEST
    portfolio = settings.read_json(latest / "portfolio.json")
    assert portfolio["available"] is False and "no holdings" in portfolio["reason"]
    for name in ("risk.json", "optimizer.json", "tax_lots.json", "drift.json"):
        assert settings.read_json(latest / name)["available"] is False
    assert settings.read_json(latest / "diff.json")["available"] is False
    plan = settings.read_json(latest / "plan.json")
    assert plan["available"] is True and "income.sources" in plan["missing"]
    consolidated = settings.read_json(latest / "consolidated.json")
    assert consolidated["available"] is False  # no ledger configured in a fresh home
    alerts = settings.read_json(latest / "alerts.json")
    assert isinstance(alerts["alerts"], list)
    assert not any(a["code"] == "credentials_missing" for a in alerts["alerts"])  # api mode: no Claude token alerts
    summary = settings.read_json(latest / "snapshot_summary.json")
    assert summary["available"] is False and summary["accounts"] == []
    sandbox = settings.read_json(latest / "sandbox.json")
    assert sandbox["mode"] == "paper" and sandbox["account"]["positions"] == []
    assert (initialized_home / "state" / "derived" / "2026-03-01" / "plan.json").exists()
