"""Create a household data dir: config from templates, .env with a generated dashboard token, VERSION,
.gitignore, git init, and (optionally) the ~/.focos/home.txt pointer."""
from __future__ import annotations

import secrets
import shutil
import subprocess
from pathlib import Path

from .. import paths
from . import CONFIG_FILES, CONFIG_VERSION
from .migrate import write_version

TEMPLATE_OF = {name: f"{name[:-4]}.example.yml" for name in CONFIG_FILES}


def _copy_if_missing(src: Path, dst: Path, created: list[str]) -> None:
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    created.append(str(dst.relative_to(dst.parents[1]) if dst.parent.name == "config" else dst.name))


def write_env(home: Path, created: list[str]) -> None:
    env = home / ".env"
    if env.exists():
        return
    text = (paths.TEMPLATES / "env.template").read_text(encoding="utf-8")
    text = text.replace("FOCOS_DASH_TOKEN=\n", f"FOCOS_DASH_TOKEN={secrets.token_urlsafe(32)}\n", 1)
    env.write_text(text, encoding="utf-8")
    created.append(".env")


def git_init(home: Path) -> str:
    if (home / ".git").exists():
        return "exists"
    git = shutil.which("git")
    if not git:
        return "skipped: git not found (history will be added when git is available)"
    try:
        subprocess.run([git, "init", "-q"], cwd=home, check=True, capture_output=True, text=True)
        return "initialized"
    except (subprocess.CalledProcessError, OSError) as e:
        return f"failed: {str(e)[:120]}"


def set_default_home(home: Path) -> Path:
    ptr = paths.pointer_file()
    ptr.parent.mkdir(parents=True, exist_ok=True)
    ptr.write_text(str(home) + "\n", encoding="utf-8")
    return ptr


def init_home(home: Path, set_default: bool = False) -> dict:
    home = home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    from .migrate import home_version

    existing = home_version(home) if (home / "config").exists() else CONFIG_VERSION
    legacy = existing < CONFIG_VERSION
    for name, tmpl in TEMPLATE_OF.items():
        if legacy and name == "focos.yml":
            continue  # `focos migrate` derives focos.yml from the old layout (agent mode, holdings source, sandbox)
        _copy_if_missing(paths.TEMPLATES / tmpl, home / "config" / name, created)
    write_env(home, created)
    gi = home / ".gitignore"
    if not gi.exists():
        shutil.copyfile(paths.TEMPLATES / "gitignore.template", gi)
        created.append(".gitignore")
    if not (home / "VERSION").exists():
        write_version(home, existing)
        created.append("VERSION")
    for sub in ("state/raw", "state/logs", "state/cache", "state/backups", "state/snapshots/holdings",
                "state/snapshots/ledger", "state/derived/latest", "state/sandbox/proposals",
                "state/sandbox/approvals", "reports/daily", "reports/weekly", "reports/monthly",
                "reports/tearsheets", "data", "agent"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    result = {"home": str(home), "created": created, "git": git_init(home), "version": existing, "needs_migration": legacy}
    if set_default:
        result["pointer"] = str(set_default_home(home))
    return result
