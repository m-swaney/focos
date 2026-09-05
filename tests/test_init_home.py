from pathlib import Path

from focos import paths
from focos.config import CONFIG_FILES, CONFIG_VERSION
from focos.config.init import init_home
from focos.config.migrate import home_version, needs_migration, run as migrate_run


def test_init_creates_layout(home: Path):
    out = init_home(home)
    assert Path(out["home"]) == home.resolve()
    for name in CONFIG_FILES:
        assert (home / "config" / name).exists(), name
    assert (home / "VERSION").read_text().strip() == str(CONFIG_VERSION)
    env = (home / ".env").read_text(encoding="utf-8")
    token = next(l for l in env.splitlines() if l.startswith("FOCOS_DASH_TOKEN=")).split("=", 1)[1]
    assert len(token) >= 32
    assert "state/raw/" in (home / ".gitignore").read_text()
    assert (home / "state" / "derived" / "latest").is_dir()
    assert (home / "reports" / "daily").is_dir()
    assert out["git"] in ("initialized", "exists") or out["git"].startswith("skipped")
    assert "pointer" not in out  # never repoints the machine unless asked


def test_init_is_idempotent(home: Path):
    init_home(home)
    (home / "config" / "profile.yml").write_text("version: 2\nowner: {name: Sam}\n", encoding="utf-8")
    env_before = (home / ".env").read_text(encoding="utf-8")
    out = init_home(home)
    assert out["created"] == []
    assert "Sam" in (home / "config" / "profile.yml").read_text()
    assert (home / ".env").read_text(encoding="utf-8") == env_before


def test_init_set_default_writes_pointer(home: Path):
    out = init_home(home, set_default=True)
    ptr = paths.pointer_file()
    assert Path(out["pointer"]) == ptr
    assert ptr.read_text(encoding="utf-8").strip() == str(home.resolve())


def test_fresh_home_needs_no_migration(home: Path):
    init_home(home)
    assert home_version(home) == CONFIG_VERSION
    assert not needs_migration(home)
    res = migrate_run(home, dry_run=True)
    assert res["changes"] == [] and "error" not in res


def test_legacy_home_detected_as_v1(home: Path):
    (home / "config").mkdir(parents=True)
    (home / "config" / "accounts.yml").write_text("robinhood:\n  a:\n    last4: '0000'\n", encoding="utf-8")
    assert home_version(home) == 1
    assert needs_migration(home)
