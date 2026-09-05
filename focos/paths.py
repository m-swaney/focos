"""Path resolution.

Two roots:
  APP   this checkout: the python package, agent/ prompts and schemas, config templates.
  HOME  the household data dir: config/, state/, reports/, .env. Resolved by `resolve_home()`.

Resolution order for HOME: explicit argument (CLI --home) -> FOCOS_HOME -> FOCOS_REPO_ROOT (deprecated)
-> pointer file ~/.focos/home.txt -> cwd if it holds config/focos.yml -> this checkout if it holds config/
(legacy single-repo layout) -> ~/focos-home.

Everything else in the package reads `paths.<NAME>` at call time, so `rebind()` can repoint a process
(tests, the setup wizard) without re-importing.
"""
from __future__ import annotations

import os
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent
TEMPLATES = PACKAGE / "config" / "templates"
AGENT = APP / "agent"                     # prompts, schemas, mcp server definitions (shipped with the app)
POINTER_DIR_NAME = ".focos"
DEFAULT_HOME_NAME = "focos-home"


def user_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home()).expanduser()


def pointer_file() -> Path:
    return user_home() / POINTER_DIR_NAME / "home.txt"


def resolve_home(explicit: str | os.PathLike | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    for var in ("FOCOS_HOME", "FOCOS_REPO_ROOT"):
        v = os.environ.get(var)
        if v:
            return Path(v).expanduser().resolve()
    ptr = pointer_file()
    if ptr.exists():
        try:
            txt = ptr.read_text(encoding="utf-8").strip()
        except OSError:
            txt = ""
        if txt and Path(txt).expanduser().exists():
            return Path(txt).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "config" / "focos.yml").exists():
        return cwd.resolve()
    if (APP / "config").is_dir():
        return APP
    return (user_home() / DEFAULT_HOME_NAME).resolve()


# ---- bound paths (module globals, repointed by rebind)
ROOT: Path
HOME: Path
CONFIG: Path
HOME_AGENT: Path
STATE: Path
RAW: Path
LOGS: Path
CACHE: Path
BACKUPS: Path
SNAPSHOTS_RH: Path
SNAPSHOTS_HOLDINGS: Path
SNAPSHOTS_SURE: Path
SNAPSHOTS_LEDGER: Path
DERIVED: Path
LATEST: Path
SANDBOX: Path
PROPOSALS: Path
APPROVALS: Path
STATUS: Path
DECISIONS: Path
REPORTS: Path
TEARSHEETS: Path
DATA: Path
VERSION_FILE: Path
ENV_FILE: Path
LEDGER_DB: Path


def _bind(home: Path) -> None:
    g = globals()
    g["ROOT"] = g["HOME"] = home
    g["CONFIG"] = home / "config"
    g["HOME_AGENT"] = home / "agent"
    g["STATE"] = home / "state"
    g["RAW"] = g["STATE"] / "raw"
    g["LOGS"] = g["STATE"] / "logs"
    g["CACHE"] = g["STATE"] / "cache"
    g["BACKUPS"] = g["STATE"] / "backups"
    g["SNAPSHOTS_RH"] = g["STATE"] / "snapshots" / "robinhood"
    g["SNAPSHOTS_HOLDINGS"] = g["STATE"] / "snapshots" / "holdings"
    g["SNAPSHOTS_SURE"] = g["STATE"] / "snapshots" / "sure"
    g["SNAPSHOTS_LEDGER"] = g["STATE"] / "snapshots" / "ledger"
    g["DERIVED"] = g["STATE"] / "derived"
    g["LATEST"] = g["DERIVED"] / "latest"
    g["SANDBOX"] = g["STATE"] / "sandbox"
    g["PROPOSALS"] = g["SANDBOX"] / "proposals"
    g["APPROVALS"] = g["SANDBOX"] / "approvals"
    g["STATUS"] = g["STATE"] / "status.json"
    g["DECISIONS"] = g["STATE"] / "decisions.jsonl"
    g["REPORTS"] = home / "reports"
    g["TEARSHEETS"] = g["REPORTS"] / "tearsheets"
    g["DATA"] = home / "data"
    g["VERSION_FILE"] = home / "VERSION"
    g["ENV_FILE"] = home / ".env"
    g["LEDGER_DB"] = g["STATE"] / "ledger.sqlite"


def rebind(home: str | os.PathLike | None = None) -> Path:
    """Repoint every HOME-derived path. Callers that cache config must call settings.reset() afterwards."""
    _bind(resolve_home(home))
    return HOME


_bind(resolve_home())


def ensure_dirs() -> None:
    for p in (CONFIG, RAW, LOGS, CACHE, BACKUPS, SNAPSHOTS_HOLDINGS, SNAPSHOTS_LEDGER, LATEST, PROPOSALS, APPROVALS,
              REPORTS / "daily", REPORTS / "weekly", REPORTS / "monthly", TEARSHEETS, DATA):
        p.mkdir(parents=True, exist_ok=True)


def derived_for(date: str) -> Path:
    p = DERIVED / date
    p.mkdir(parents=True, exist_ok=True)
    return p
