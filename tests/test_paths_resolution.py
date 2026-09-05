from pathlib import Path

from focos import paths, settings


def test_explicit_beats_env(home: Path, tmp_path: Path):
    other = tmp_path / "other"
    other.mkdir()
    assert paths.resolve_home(other) == other.resolve()
    assert paths.resolve_home() == home.resolve()


def test_env_order(home: Path, monkeypatch, tmp_path: Path):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.delenv("FOCOS_HOME")
    monkeypatch.setenv("FOCOS_REPO_ROOT", str(legacy))
    assert paths.resolve_home() == legacy.resolve()
    monkeypatch.setenv("FOCOS_HOME", str(home))
    assert paths.resolve_home() == home.resolve()


def test_pointer_file_then_default(home: Path, monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FOCOS_HOME")
    monkeypatch.chdir(tmp_path)  # no config/focos.yml here
    ptr = paths.pointer_file()
    assert str(tmp_path / "user") in str(ptr)
    pointed = tmp_path / "pointed"
    pointed.mkdir()
    ptr.parent.mkdir(parents=True)
    ptr.write_text(str(pointed), encoding="utf-8")
    assert paths.resolve_home() == pointed.resolve()
    ptr.unlink()
    resolved = paths.resolve_home()
    assert resolved.name in (paths.DEFAULT_HOME_NAME, paths.APP.name)


def test_cwd_with_focos_yml(home: Path, monkeypatch, tmp_path: Path):
    monkeypatch.delenv("FOCOS_HOME")
    here = tmp_path / "cwdhome"
    (here / "config").mkdir(parents=True)
    (here / "config" / "focos.yml").write_text("version: 1\n", encoding="utf-8")
    monkeypatch.chdir(here)
    assert paths.resolve_home() == here.resolve()


def test_rebind_updates_derived_paths(home: Path, tmp_path: Path):
    assert paths.CONFIG == home / "config"
    assert paths.LATEST == home / "state" / "derived" / "latest"
    other = tmp_path / "second"
    other.mkdir()
    paths.rebind(other)
    settings.reset()
    assert paths.HOME == other.resolve()
    assert paths.STATUS == other.resolve() / "state" / "status.json"
    assert paths.AGENT == paths.APP / "agent"  # app assets do not move with HOME


def test_env_overlay_applies_to_focos_yml(initialized_home: Path, monkeypatch):
    monkeypatch.setenv("FOCOS_AI__PROVIDER", "openai")
    monkeypatch.setenv("FOCOS_DASHBOARD__PORT", "4100")
    settings.reset()
    cfg = settings.focos()
    assert cfg["ai"]["provider"] == "openai"
    assert cfg["dashboard"]["port"] == 4100
    assert cfg["ledger"]["provider"] == "simplefin"  # from the template


def test_focos_defaults_without_file(home: Path):
    cfg = settings.focos()
    assert cfg["ai"]["mode"] == "api"
    assert cfg["schedule"]["daily"]["time"] == "16:35"
    assert settings.owner_name() == "you"
    assert settings.timezone_name() == "America/New_York"


def test_legacy_home_infers_agent_defaults(home: Path, monkeypatch):
    (home / "config").mkdir(parents=True)
    (home / "config" / "accounts.yml").write_text(
        "robinhood:\n  main: {last4: '0000', role: taxable}\n  play: {last4: '0001', role: sandbox, agent_access: trade}\n"
        "sure:\n  robinhood_main: abc\n", encoding="utf-8")
    settings.reset()
    cfg = settings.focos()
    assert cfg["ai"]["mode"] == "agent"
    assert cfg["holdings"]["source"] == "robinhood_mcp"
    assert cfg["ledger"]["provider"] == "sure"
    assert cfg["agent"]["sandbox_enabled"] is True
    (home / "config" / "focos.yml").write_text("ai: {mode: api}\n", encoding="utf-8")
    settings.reset()
    assert settings.focos()["ai"]["mode"] == "api" and settings.focos()["holdings"]["source"] == "none"
