from pathlib import Path

import yaml

from focos.config import CONFIG_FILES
from focos.config.validate import detect_layout_version, has_errors, validate_all, validate_data


def _write(home: Path, name: str, data: dict) -> None:
    (home / "config" / name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_templates_validate_clean(initialized_home: Path):
    issues = validate_all(initialized_home / "config")
    assert [i.as_dict() for i in issues if i.severity == "error"] == []
    assert not has_errors(issues)
    assert {(initialized_home / "config" / n).exists() for n in CONFIG_FILES} == {True}


def test_bad_timezone_and_regex(initialized_home: Path):
    _write(initialized_home, "profile.yml", {"version": 2, "household": {"timezone": "Mars/Olympus"},
                                             "debt_terms": [{"match": "(unclosed"}]})
    issues = validate_all(initialized_home / "config")
    paths = {i.path for i in issues if i.severity == "error"}
    assert "household.timezone" in paths
    assert any(p.startswith("debt_terms.0") for p in paths)


def test_goal_status_and_tax_agenda_items():
    assert validate_data("goals.yml", {"version": 2, "goals": [{"kind": "custom", "name": "X", "status": "done", "completed_on": "2026-01-02"}]}) == []
    bad = validate_data("goals.yml", {"version": 2, "goals": [{"kind": "custom", "name": "X", "status": "finished"}]})
    assert any(i.path.startswith("goals.0.status") for i in bad)
    assert validate_data("profile.yml", {"version": 2, "tax_agenda": ["a string", {"id": "x", "text": "an item", "status": "done"}]}) == []
    bad = validate_data("profile.yml", {"version": 2, "tax_agenda": [{"id": "x", "text": "t", "status": "maybe"}]})
    assert any("status" in i.path for i in bad)


def test_two_sandbox_roles_rejected():
    issues = validate_data("accounts.yml", {"version": 2, "brokerage": [
        {"key": "a", "label": "A", "role": "sandbox"}, {"key": "b", "label": "B", "role": "sandbox"}]})
    assert any("at most one" in i.message for i in issues)


def test_trade_access_needs_sandbox_role():
    issues = validate_data("accounts.yml", {"version": 2, "brokerage": [
        {"key": "c", "label": "C", "role": "taxable", "agent_access": "trade"}]})
    assert any("requires role 'sandbox'" in i.message for i in issues)


def test_cross_file_unknown_entity(initialized_home: Path):
    _write(initialized_home, "goals.yml", {"version": 2, "goals": [
        {"kind": "custom", "name": "Boat", "entity": "nope"}]})
    _write(initialized_home, "accounts.yml", {"version": 2, "brokerage": [
        {"key": "x", "label": "X", "role": "taxable", "entity": "ghost"}]})
    issues = validate_all(initialized_home / "config")
    errs = {(i.file, i.path) for i in issues if i.severity == "error"}
    assert ("goals.yml", "goals[boat].entity") in errs
    assert ("accounts.yml", "brokerage[x].entity") in errs


def test_household_entity_required(initialized_home: Path):
    _write(initialized_home, "entities.yml", {"version": 2, "entities": {"biz": {"label": "Biz", "kind": "business"}}})
    issues = validate_all(initialized_home / "config")
    assert any("personal" in i.message for i in issues if i.file == "entities.yml")


def test_v1_layout_detected_and_warned():
    assert detect_layout_version("accounts.yml", {"robinhood": {"x": {"last4": "0000"}}}) == 1
    assert detect_layout_version("accounts.yml", {"version": 2, "brokerage": []}) == 2
    assert detect_layout_version("entities.yml", {"entities": {"personal": {"sure_account_ids": []}}}) == 1
    assert detect_layout_version("profile.yml", {"person": {"name": "x"}}) == 1
    assert detect_layout_version("goals.yml", {"goals": [{"id": "a", "name": "A"}]}) == 1
    issues = validate_data("profile.yml", {"person": {"name": "x"}})
    assert issues and issues[0].severity == "warn" and "migrate" in issues[0].message


def test_goal_ids_generated_and_unique():
    issues = validate_data("goals.yml", {"version": 2, "goals": [
        {"kind": "custom", "name": "New Roof"}, {"kind": "custom", "name": "new roof!"}]})
    assert issues and "duplicate goal id 'new_roof'" in issues[0].message


def test_invalid_yaml_reported(initialized_home: Path):
    (initialized_home / "config" / "analytics.yml").write_text("benchmark: [unclosed\n", encoding="utf-8")
    issues = validate_all(initialized_home / "config")
    assert any(i.file == "analytics.yml" and "YAML" in i.message for i in issues)
