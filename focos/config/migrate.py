"""Config layout migrations. <home>/VERSION records the layout the data dir is on.

Steps are registered as (from_version, to_version) -> function(home, dry_run) -> list[str] describing changes.
The v1 -> v2 transformation (personal keys -> roles, kinds, owner) lives in focos.config.migrate_v2.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import CONFIG_FILES, CONFIG_VERSION
from .validate import detect_layout_version, load_yaml

Step = Callable[[Path, bool], list[str]]
STEPS: dict[tuple[int, int], Step] = {}


def register(frm: int, to: int):
    def deco(fn: Step) -> Step:
        STEPS[(frm, to)] = fn
        return fn
    return deco


def home_version(home: Path) -> int:
    vf = home / "VERSION"
    if vf.exists():
        try:
            return int(vf.read_text(encoding="utf-8").strip() or CONFIG_VERSION)
        except ValueError:
            pass
    # No VERSION file: infer from the files themselves. A brand-new home is current.
    cdir = home / "config"
    if not cdir.exists():
        return CONFIG_VERSION
    versions = []
    for name in CONFIG_FILES:
        data, err = load_yaml(cdir / name)
        if data:
            versions.append(detect_layout_version(name, data))
    return min(versions) if versions else CONFIG_VERSION


def write_version(home: Path, version: int = CONFIG_VERSION) -> None:
    (home / "VERSION").write_text(f"{version}\n", encoding="utf-8")


def needs_migration(home: Path) -> bool:
    return home_version(home) < CONFIG_VERSION


def run(home: Path, dry_run: bool = False) -> dict:
    from . import migrate_v2, migrate_v3  # noqa: F401  (register the v1 -> v2 and v2 -> v3 steps)

    start = home_version(home)
    cur = start
    changes: list[str] = []
    while cur < CONFIG_VERSION:
        step = STEPS.get((cur, cur + 1))
        if step is None:
            return {"from": start, "to": cur, "changes": changes,
                    "error": f"no migration registered for v{cur} -> v{cur + 1}"}
        changes.extend(step(home, dry_run))
        cur += 1
    if not dry_run:
        write_version(home, CONFIG_VERSION)
    return {"from": start, "to": CONFIG_VERSION, "changes": changes, "dry_run": dry_run}
