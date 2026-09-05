import zipfile
from pathlib import Path

from focos import updater


def test_version_compare():
    assert updater.is_newer("v0.2.0", "0.1.0")
    assert updater.is_newer("0.1.1", "0.1.0")
    assert not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("v0.0.9", "0.1.0")
    assert updater.installed_version(Path(__file__).parent.parent) != "0"


def test_extract_unwraps_single_folder(tmp_path: Path):
    z = tmp_path / "focos-1.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("focos-1/pyproject.toml", "[project]\nname='x'\n")
        f.writestr("focos-1/focos/__init__.py", "")
    dest = tmp_path / "app"
    updater._extract(z, dest)
    assert (dest / "pyproject.toml").exists() and (dest / "focos" / "__init__.py").exists()
    assert not (dest / "focos-1").exists()


def test_check_handles_network_failure(monkeypatch):
    monkeypatch.setattr(updater, "latest_release", lambda repo: (_ for _ in ()).throw(RuntimeError("offline")))
    r = updater.check()
    assert r["available"] is None and "offline" in r["error"]
