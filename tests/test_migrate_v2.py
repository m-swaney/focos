"""focos migrate on a made-up v1 data dir."""
from pathlib import Path

import yaml

from focos import settings
from focos.config import CONFIG_VERSION
from focos.config.migrate import home_version, run as migrate_run
from focos.config.validate import has_errors, validate_all
from tests.test_compat import V1_ACCOUNTS, V1_ENTITIES, V1_GOALS, V1_PROFILE


def _seed_v1(home: Path) -> None:
    cdir = home / "config"
    cdir.mkdir(parents=True)
    for name, data in (("accounts.yml", V1_ACCOUNTS), ("entities.yml", V1_ENTITIES), ("profile.yml", V1_PROFILE),
                       ("goals.yml", V1_GOALS)):
        (cdir / name).write_text("# old header\n" + yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    snaps = home / "state" / "snapshots" / "robinhood"
    snaps.mkdir(parents=True)
    (snaps / "2026-01-01.json").write_text("{}", encoding="utf-8")
    settings.reset()


def test_dry_run_changes_nothing(home: Path):
    _seed_v1(home)
    before = {p.name: p.read_text() for p in (home / "config").glob("*.yml")}
    res = migrate_run(home, dry_run=True)
    assert res["from"] == 1 and res["to"] == CONFIG_VERSION and res["dry_run"]
    assert any("accounts.yml" in c for c in res["changes"]) and any("focos.yml" in c for c in res["changes"])
    assert {p.name: p.read_text() for p in (home / "config").glob("*.yml")} == before
    assert not (home / "VERSION").exists()


def test_migrate_converts_and_validates(home: Path):
    _seed_v1(home)
    assert home_version(home) == 1
    res = migrate_run(home)
    assert "error" not in res
    assert (home / "VERSION").read_text().strip() == str(CONFIG_VERSION)
    assert (home / "config" / "backup-v1" / "profile.yml").exists()
    acc = yaml.safe_load((home / "config" / "accounts.yml").read_text())
    assert acc["version"] == 2 and {a["key"] for a in acc["brokerage"]} == {"brokerage", "ira", "play"}
    prof = yaml.safe_load((home / "config" / "profile.yml").read_text())
    assert prof["owner"]["name"] == "Sam" and prof["household"]["timezone"]
    goals = yaml.safe_load((home / "config" / "goals.yml").read_text())
    assert all("kind" in g for g in goals["goals"])
    focos_yml = yaml.safe_load((home / "config" / "focos.yml").read_text())
    assert focos_yml["ledger"]["provider"] == "none"          # no SIMPLEFIN_ACCESS_URL in the environment
    assert focos_yml["holdings"]["source"] == "robinhood_mcp"
    assert focos_yml["ai"]["mode"] == "agent" and focos_yml["agent"]["sandbox_enabled"] is True
    assert (home / "state" / "snapshots" / "holdings" / "2026-01-01.json").exists()
    issues = validate_all(home / "config")
    assert not has_errors(issues), [i.as_dict() for i in issues]
    # second run is a no-op
    res2 = migrate_run(home)
    assert res2["changes"] == []
    settings.reset()
    assert settings.accounts_by_role("sandbox") == ["play"]
    assert settings.owner_name() == "Sam"
