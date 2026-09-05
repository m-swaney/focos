"""`focos update`: fetch a newer release next to the current app dir, prepare its environment, migrate the data
dir, re-point the `focos` shim / service / schedule at it, and prune old app dirs. Dev checkouts (a .git dir)
just pull and sync.

Nothing is renamed while running: the new version lives in ~/.focos/app-<tag>, and ~/.focos/app.txt says
which directory the shim uses.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from . import paths

DEFAULT_REPO = "m-swaney/focos"
USER_AGENT = "focos-updater"


def base_dir() -> Path:
    return paths.user_home() / ".focos"


def app_pointer() -> Path:
    return base_dir() / "app.txt"


def current_app() -> Path:
    return paths.APP


def is_dev_checkout(app: Path | None = None) -> bool:
    return ((app or current_app()) / ".git").exists()


def installed_version(app: Path | None = None) -> str:
    app = app or current_app()
    try:
        m = re.search(r'^version\s*=\s*"([^"]+)"', (app / "pyproject.toml").read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else "0"
    except OSError:
        return "0"


def _vtuple(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-+]", v.lstrip("v"))[:4])


def is_newer(candidate: str, current: str) -> bool:
    return _vtuple(candidate) > _vtuple(current)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
        return json.loads(r.read().decode("utf-8"))


def latest_release(repo: str = DEFAULT_REPO) -> dict:
    rel = _get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    zip_name = next((n for n in assets if re.match(r"focos-.*\.zip$", n)), None)
    return {"tag": rel.get("tag_name", ""), "zip": assets.get(zip_name) if zip_name else None,
            "sha256": assets.get(f"{zip_name}.sha256") if zip_name else None, "name": zip_name, "notes": rel.get("body", "")}


def check(repo: str = DEFAULT_REPO) -> dict:
    cur = installed_version()
    try:
        rel = latest_release(repo)
    except Exception as e:  # noqa: BLE001
        return {"current": cur, "available": None, "error": str(e)[:200]}
    return {"current": cur, "available": rel["tag"], "newer": is_newer(rel["tag"], cur), "asset": rel["name"]}


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:  # noqa: S310
        shutil.copyfileobj(r, f)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract(zip_path: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)
    if not (dest / "pyproject.toml").exists():  # single wrapping folder
        inner = next((d for d in dest.iterdir() if d.is_dir() and (d / "pyproject.toml").exists()), None)
        if inner:
            for item in inner.iterdir():
                shutil.move(str(item), str(dest / item.name))
            inner.rmdir()


def _venv_python(app: Path) -> Path:
    return app / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def _prepare_env(app: Path, log) -> Path:
    uv = shutil.which("uv") or str(paths.user_home() / ".local" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv"))
    py = _venv_python(app)
    if not py.exists():
        log("creating virtualenv")
        subprocess.run([uv, "venv", str(app / ".venv"), "--python", "3.13", "-q"], check=True)
    if (app / "uv.lock").exists():
        subprocess.run([uv, "sync", "--project", str(app), "--frozen", "--all-extras", "--no-dev", "-q"], check=True)
    else:
        subprocess.run([uv, "pip", "install", "--python", str(py), "-q", "-e", f"{app}[all]"], check=True)
    return py


def _rewire(py: Path, home: Path, log) -> None:
    """Run the NEW version's migrate / settings render / service + schedule install so every absolute path points at it."""
    for args in (["migrate"], ["agent", "render-settings"], ["schedule", "install"], ["service", "install"]):
        r = subprocess.run([str(py), "-m", "focos", "--home", str(home), *args], capture_output=True, text=True)
        log(f"{' '.join(args)}: {'ok' if r.returncode == 0 else 'failed: ' + (r.stderr or r.stdout)[-200:]}")


def _prune(base: Path, keep: set[Path], log) -> None:
    dirs = sorted((d for d in base.glob("app-*") if d.is_dir() and d not in keep), key=lambda d: d.stat().st_mtime)
    for d in dirs[:-1]:  # keep the previous version as a fallback
        try:
            shutil.rmtree(d)
            log(f"removed old version {d.name}")
        except OSError:
            pass


def update(repo: str = DEFAULT_REPO, log=print, force: bool = False) -> dict:
    app = current_app()
    home = paths.HOME
    if is_dev_checkout(app):
        log("dev checkout: git pull + uv sync")
        subprocess.run(["git", "-C", str(app), "pull", "--ff-only", "-q"], check=True)
        py = _prepare_env(app, log)
        dash = app / "dashboard"
        if (dash / "node_modules").exists():
            npm = shutil.which("npm.cmd") or shutil.which("npm")
            if npm:
                subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=dash, check=True)
                subprocess.run([npm, "run", "build"], cwd=dash, check=True)
        _rewire(py, home, log)
        return {"mode": "dev", "app": str(app)}
    rel = latest_release(repo)
    cur = installed_version(app)
    if not force and not is_newer(rel["tag"], cur):
        return {"mode": "release", "current": cur, "available": rel["tag"], "updated": False}
    if not rel["zip"]:
        raise RuntimeError(f"release {rel['tag']} has no focos-*.zip asset")
    base = base_dir()
    new_app = base / f"app-{rel['tag']}"
    zip_path = base / rel["name"]
    log(f"downloading {rel['name']}")
    _download(rel["zip"], zip_path)
    if rel["sha256"]:
        expected = urllib.request.urlopen(urllib.request.Request(rel["sha256"], headers={"User-Agent": USER_AGENT}), timeout=30).read().decode().split()[0]  # noqa: S310
        if _sha256(zip_path) != expected:
            zip_path.unlink(missing_ok=True)
            raise RuntimeError("checksum mismatch; update aborted")
    _extract(zip_path, new_app)
    zip_path.unlink(missing_ok=True)
    py = _prepare_env(new_app, log)
    app_pointer().parent.mkdir(parents=True, exist_ok=True)
    app_pointer().write_text(str(new_app) + "\n", encoding="utf-8")
    _rewire(py, home, log)
    _prune(base, {new_app, app}, log)
    return {"mode": "release", "current": cur, "available": rel["tag"], "updated": True, "app": str(new_app)}
