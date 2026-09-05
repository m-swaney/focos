"""Config loading: YAML under <home>/config, secrets from <home>/.env, env-var overlay for focos.yml.

Loaders return plain dicts (call sites use .get). Validation lives in focos.config.validate; the only
file validated on load is focos.yml because it is new and always produced by this code or the wizard.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from . import paths

ENV_PREFIX = "FOCOS_"


RESOLUTION_VARS = ("FOCOS_HOME", "FOCOS_REPO_ROOT")


def load_env() -> None:
    """Load <home>/.env into the process without overriding real env vars. FOCOS_HOME / FOCOS_REPO_ROOT are
    inputs to home resolution, so a value inside .env is ignored (it would otherwise repoint the next rebind)."""
    if not paths.ENV_FILE.exists():
        return
    for k, v in dotenv_values(paths.ENV_FILE).items():
        if k in RESOLUTION_VARS or v is None:
            continue
        os.environ.setdefault(k, v)


load_env()


def _load_yaml(name: str) -> dict[str, Any]:
    p = paths.CONFIG / name
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _env_overlay() -> dict[str, Any]:
    """FOCOS_AI__PROVIDER=openai -> {"ai": {"provider": "openai"}}. Only keys containing '__' apply."""
    out: dict[str, Any] = {}
    for k, v in os.environ.items():
        if not k.startswith(ENV_PREFIX) or "__" not in k:
            continue
        parts = [p.lower() for p in k[len(ENV_PREFIX):].split("__") if p]
        if not parts:
            continue
        try:
            val = yaml.safe_load(v)
        except yaml.YAMLError:
            val = v
        cur = out
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = val
    return out


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def focos_yml_exists() -> bool:
    return (paths.CONFIG / "focos.yml").exists()


@lru_cache(maxsize=None)
def focos() -> dict[str, Any]:
    """focos.yml with defaults and the env overlay applied, validated."""
    from .config.models import FocosSettings

    raw = _load_yaml("focos.yml")
    if not raw and not focos_yml_exists():
        raw = _legacy_focos_defaults()
    raw = _deep_merge(raw, _env_overlay())
    return FocosSettings.model_validate(raw).model_dump(mode="json")


def _legacy_focos_defaults() -> dict[str, Any]:
    """A pre-portability home has no focos.yml: infer agent mode, the Robinhood snapshot, and the ledger from what
    accounts.yml and .env say (same inference `focos migrate` writes down)."""
    acc = _load_yaml("accounts.yml")
    if not acc or "robinhood" not in acc:
        return {}
    from .config.compat import accounts_v2
    from .config.migrate_v2 import _infer_focos_yml

    return _infer_focos_yml(paths.HOME, accounts_v2(acc))


@lru_cache(maxsize=None)
def analytics() -> dict[str, Any]:
    cfg = _load_yaml("analytics.yml")
    cfg.setdefault("benchmark", "SPY")
    cfg.setdefault("max_weight", 0.15)
    cfg.setdefault("years", 3)
    cfg.setdefault("big_move_pct", 5.0)
    cfg.setdefault("etf_labels", {})
    cfg.setdefault("classes", {})
    return cfg


@lru_cache(maxsize=None)
def profile() -> dict[str, Any]:
    return _load_yaml("profile.yml")


@lru_cache(maxsize=None)
def goals() -> dict[str, Any]:
    return _load_yaml("goals.yml")


@lru_cache(maxsize=None)
def accounts() -> dict[str, Any]:
    return _load_yaml("accounts.yml")


@lru_cache(maxsize=None)
def entities() -> dict[str, Any]:
    return _load_yaml("entities.yml")


@lru_cache(maxsize=None)
def sandbox_rules() -> dict[str, Any]:
    return _load_yaml("sandbox_rules.yml")


@lru_cache(maxsize=None)
def transfer_rules() -> dict[str, Any]:
    return _load_yaml("transfer_rules.yml")


@lru_cache(maxsize=None)
def properties() -> dict[str, Any]:
    return _load_yaml("properties.yml")


_CACHED = (focos, analytics, profile, goals, accounts, entities, sandbox_rules, transfer_rules, properties)


def reset() -> None:
    """Drop cached config (after the wizard writes files or paths.rebind())."""
    for fn in _CACHED:
        fn.cache_clear()


def owner_name() -> str:
    p = profile()
    return str(((p.get("owner") or {}).get("name") or (p.get("person") or {}).get("name") or "you"))


def timezone_name() -> str:
    p = profile()
    return str(((p.get("household") or {}).get("timezone") or "America/New_York"))


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name())
    except Exception:  # invalid zone in config; doctor reports it, runs keep going
        return ZoneInfo("America/New_York")


def read_json(p: Path, default: Any = None) -> Any:
    if not p.exists():
        return default
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=_json_default)


def _json_default(o: Any) -> Any:
    try:
        import numpy as np  # noqa: WPS433

        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
    except Exception:  # pragma: no cover
        pass
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


# ---- v2 views (accept v1 files transparently; see focos.config.compat)
def accounts_v2() -> dict[str, Any]:
    from .config.compat import accounts_v2 as _a
    return _a(accounts())


def brokerage() -> list[dict[str, Any]]:
    return list(accounts_v2().get("brokerage") or [])


def accounts_by_role(role: str) -> list[str]:
    return [a["key"] for a in brokerage() if a.get("role") == role]


def account_role(key: str) -> str | None:
    return next((a.get("role") for a in brokerage() if a.get("key") == key), None)


def brokerage_entry(key: str) -> dict[str, Any] | None:
    return next((a for a in brokerage() if a.get("key") == key), None)


def entities_v2() -> dict[str, Any]:
    from .config.compat import entities_v2 as _e
    return _e(entities())


def profile_v2() -> dict[str, Any]:
    from .config.compat import profile_v2 as _p
    return _p(profile(), entities_v2())


def goals_v2() -> dict[str, Any]:
    from .config.compat import goals_v2 as _g
    return _g(goals())
