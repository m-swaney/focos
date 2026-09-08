"""v2 -> v3: goals carry a status, tax-agenda entries become items with an id and a status. Both files are
rewritten in place with ruamel so hand-written comments survive; originals go to config/backup-v2/ first."""
from __future__ import annotations

import shutil
from pathlib import Path

from .migrate import register
from .models import tax_agenda_items
from .writer import _yaml


def _load(path: Path):
    return _yaml().load(path.read_text(encoding="utf-8")) or {}


def _dump(path: Path, doc) -> None:
    import io

    buf = io.StringIO()
    _yaml().dump(doc, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")


@register(2, 3)
def v2_to_v3(home: Path, dry_run: bool) -> list[str]:
    cdir = home / "config"
    changes: list[str] = []
    backup = cdir / "backup-v2"
    todo: list[tuple[Path, object]] = []

    profile = cdir / "profile.yml"
    if profile.exists():
        doc = _load(profile)
        ta = doc.get("tax_agenda") if isinstance(doc, dict) else None
        if isinstance(ta, list) and any(isinstance(x, str) for x in ta):
            items = tax_agenda_items(list(ta))
            del ta[:]
            ta.extend(items)
            changes.append(f"profile.yml: tax_agenda entries now carry id/status ({len(items)} items)")
            todo.append((profile, doc))

    goals = cdir / "goals.yml"
    if goals.exists():
        doc = _load(goals)
        rows = doc.get("goals") if isinstance(doc, dict) else None
        n = 0
        for g in rows or []:
            if isinstance(g, dict) and "status" not in g:
                g["status"] = "active"
                n += 1
        if n:
            changes.append(f"goals.yml: {n} goal(s) marked status: active")
            todo.append((goals, doc))

    if not dry_run and todo:
        backup.mkdir(parents=True, exist_ok=True)
        for path, doc in todo:
            shutil.copy2(path, backup / path.name)
            _dump(path, doc)
    return changes
