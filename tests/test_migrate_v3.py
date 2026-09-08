"""v2 -> v3: tax_agenda strings become items, goals get status, comments survive, second run is a no-op."""
from pathlib import Path

import yaml

from focos import settings
from focos.config import CONFIG_VERSION
from focos.config.migrate import home_version, run as migrate_run
from focos.config.validate import has_errors, validate_all

PROFILE = """# Household profile (v2 layout). No account numbers here.
version: 2
owner:
  name: Ann   # first name
tax_agenda:
- Fix payroll over-withholding
- Fix payroll over-withholding
- Choose a retirement plan   # with the CPA
risk:
  tolerance: aggressive
"""
GOALS = """# Goals. Order = priority.
version: 2
goals:
- id: roof
  kind: purchase
  name: New roof   # keep
  target_amount: 12000
- id: paused_one
  kind: custom
  name: Later
  status: paused
"""


def _seed(home: Path) -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / "profile.yml").write_text(PROFILE, encoding="utf-8")
    (home / "config" / "goals.yml").write_text(GOALS, encoding="utf-8")
    (home / "VERSION").write_text("2\n", encoding="utf-8")
    settings.reset()


def test_v2_to_v3(initialized_home: Path):
    _seed(initialized_home)
    assert home_version(initialized_home) == 2 and CONFIG_VERSION == 3
    dry = migrate_run(initialized_home, dry_run=True)
    assert dry["dry_run"] and any("tax_agenda" in c for c in dry["changes"]) and any("goals.yml" in c for c in dry["changes"])
    assert "Fix payroll over-withholding\n-" in (initialized_home / "config" / "profile.yml").read_text()  # untouched
    res = migrate_run(initialized_home)
    assert res["from"] == 2 and res["to"] == 3 and home_version(initialized_home) == 3
    ptxt = (initialized_home / "config" / "profile.yml").read_text(encoding="utf-8")
    assert "# first name" in ptxt and "No account numbers here" in ptxt  # comments on other keys survive
    prof = yaml.safe_load(ptxt)
    assert [i["id"] for i in prof["tax_agenda"]] == ["fix_payroll_over_withholding", "fix_payroll_over_withholding_2", "choose_a_retirement_plan"]
    assert all(i["status"] == "open" for i in prof["tax_agenda"]) and prof["risk"]["tolerance"] == "aggressive"
    gtxt = (initialized_home / "config" / "goals.yml").read_text(encoding="utf-8")
    assert "# keep" in gtxt
    goals = yaml.safe_load(gtxt)["goals"]
    assert goals[0]["status"] == "active" and goals[1]["status"] == "paused"
    assert (initialized_home / "config" / "backup-v2" / "profile.yml").exists()
    assert not has_errors(validate_all(initialized_home / "config"))
    again = migrate_run(initialized_home)
    assert again["changes"] == [] and again["from"] == 3


def test_fresh_home_is_current(initialized_home: Path):
    assert home_version(initialized_home) == CONFIG_VERSION
    assert migrate_run(initialized_home)["changes"] == []
