"""v1 -> v2 config migration: personal account keys become roles, entities carry their own account ids and
hints, goals get kinds, the profile gets owner/household/income sources, and focos.yml is created from
what the old layout implies. Originals are copied to config/backup-v1/ first."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml

from . import compat
from .migrate import register
from .validate import detect_layout_version, load_yaml

HEADERS = {
    "accounts.yml": "# Brokerage accounts whose holdings get analyzed (v2 layout; migrated by focos).\n",
    "entities.yml": "# Entities and the ledger accounts that belong to them (v2 layout; migrated by focos).\n",
    "profile.yml": "# Household profile (v2 layout; migrated by focos). No account numbers here.\n",
    "goals.yml": "# Goals with kinds (v2 layout; migrated by focos). Order = priority.\n",
}


def _dump(path: Path, header: str, data: dict) -> None:
    path.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _infer_focos_yml(home: Path, accounts: dict) -> dict:
    brokerage = accounts.get("brokerage") or []
    has_sure = bool(os.environ.get("SURE_API_KEY_RW") or os.environ.get("SURE_API_KEY_RO")
                    or any(str(a.get("ledger_account_id") or "").startswith("sure:") for a in brokerage)
                    or (home / "sure" / "compose.yml").exists())
    out = {
        "version": 1,
        "home_label": "Household",
        "ledger": {"provider": "sure" if has_sure else "none", "refresh_min_hours": 20, "history_days_initial": 365},
        "holdings": {"source": "robinhood_mcp" if any(a.get("source") == "robinhood_mcp" for a in brokerage) else "none"},
        "ai": {"mode": "agent", "provider": "anthropic"},
        "agent": {"claude_cli": "auto", "sandbox_enabled": any(a.get("role") == "sandbox" for a in brokerage)},
    }
    if has_sure:
        out["ledger"]["sure"] = {"api_url": os.environ.get("SURE_API_URL") or "http://127.0.0.1:3000",
                                 "autostart_docker": (home / "sure" / "compose.yml").exists(),
                                 "compose_dir": "sure" if (home / "sure" / "compose.yml").exists() else None}
    return out


@register(1, 2)
def v1_to_v2(home: Path, dry_run: bool) -> list[str]:
    cdir = home / "config"
    changes: list[str] = []
    backup = cdir / "backup-v1"
    transforms = {"accounts.yml": compat.accounts_v2, "entities.yml": compat.entities_v2,
                  "profile.yml": compat.profile_v2, "goals.yml": compat.goals_v2}
    converted: dict[str, dict] = {}
    for name, fn in transforms.items():
        data, err = load_yaml(cdir / name)
        if err:
            changes.append(f"{name}: skipped ({err})")
            continue
        if data is None or detect_layout_version(name, data) == 2:
            if data is not None:
                converted[name] = fn(data)
            continue
        converted[name] = fn(data)
        changes.append(f"{name}: converted to v2 (original kept in config/backup-v1/)")
        if not dry_run:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cdir / name, backup / name)
            _dump(cdir / name, HEADERS[name], converted[name])
    if not (cdir / "focos.yml").exists():
        inferred = _infer_focos_yml(home, converted.get("accounts.yml") or {})
        changes.append(f"focos.yml: created (ledger={inferred['ledger']['provider']}, holdings={inferred['holdings']['source']}, "
                       f"ai.mode={inferred['ai']['mode']}, sandbox_enabled={inferred['agent']['sandbox_enabled']})")
        if not dry_run:
            _dump(cdir / "focos.yml", "# focos settings (created by focos migrate; edit freely).\n", inferred)
    # holdings snapshots move from the Robinhood-specific folder to the source-neutral one
    old, new = home / "state" / "snapshots" / "robinhood", home / "state" / "snapshots" / "holdings"
    if old.exists():
        files = [f for f in old.glob("*.json") if not (new / f.name).exists()]
        if files:
            changes.append(f"state/snapshots/holdings: copied {len(files)} snapshot(s) from snapshots/robinhood")
            if not dry_run:
                new.mkdir(parents=True, exist_ok=True)
                for f in files:
                    shutil.copyfile(f, new / f.name)
    for name in ("focos.yml", "transfer_rules.yml", "sandbox_rules.yml", "analytics.yml", "properties.yml"):
        pass  # no layout change for these files
    return changes
