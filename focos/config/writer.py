"""Write config files from the wizard/API without losing hand-written comments (ruamel round-trip)."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

from .. import paths, settings
from .validate import Issue, validate_data

HEADERS = {
    "focos.yml": "# focos settings (written by the setup wizard; safe to edit by hand).\n",
    "profile.yml": "# Household profile (v2). No account numbers here. Estimates are fine.\n",
    "goals.yml": "# Goals the monthly review measures progress against. Order = priority.\n",
    "accounts.yml": "# Brokerage accounts whose holdings get analyzed (v2). Matching uses last-4 digits or ledger ids only.\n",
    "entities.yml": "# Entities and the ledger accounts that belong to them (v2).\n",
    "transfer_rules.yml": "# Transfer classification rules (seeded by the wizard from discovered institutions; edit freely).\n",
}


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 120
    return y


AMBIGUOUS = re.compile(r"^(\d{1,2}:\d{2}(:\d{2})?|[Yy]es|[Nn]o|[Oo]n|[Oo]ff|[Tt]rue|[Ff]alse|0[0-7]+|\d+(\.\d+)?([eE][+-]?\d+)?|~|null|Null|NULL)$")


def _plain(obj: Any) -> Any:
    """pydantic models / dates -> plain YAML-able values; strings that YAML 1.1 would mis-type get quoted."""
    if isinstance(obj, str) and AMBIGUOUS.match(obj):
        return DoubleQuotedScalarString(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", exclude_none=False)
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def load(name: str) -> Any:
    p = paths.CONFIG / name
    if not p.exists():
        return {}
    return _yaml().load(p.read_text(encoding="utf-8")) or {}


def dump(name: str, data: Any) -> Path:
    p = paths.CONFIG / name
    p.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    _yaml().dump(data, buf)
    text = buf.getvalue()
    if not text.lstrip().startswith("#") and name in HEADERS:
        text = HEADERS[name] + text
    p.write_text(text, encoding="utf-8")
    settings.reset()
    return p


def write_file(name: str, data: dict[str, Any], validate: bool = True) -> list[Issue]:
    """Replace a whole config file (comments in the old file are lost; the header comment is kept)."""
    data = _plain(data)
    if validate:
        issues = validate_data(name, data)
        if any(i.severity == "error" for i in issues):
            return issues
    dump(name, data)
    return []


def write_section(name: str, key: str, value: Any, validate: bool = True) -> list[Issue]:
    """Replace one top-level key, keeping everything else (and its comments) in place."""
    doc = load(name)
    if not isinstance(doc, dict):
        doc = {}
    merged = dict(doc)
    merged[key] = _plain(value)
    if validate:
        issues = validate_data(name, {k: _plain(v) for k, v in merged.items()})
        if any(i.severity == "error" for i in issues):
            return issues
    doc[key] = _plain(value)
    if name in ("profile.yml", "goals.yml", "accounts.yml", "entities.yml") and "version" not in doc:
        doc.insert(0, "version", 2) if hasattr(doc, "insert") else doc.__setitem__("version", 2)
    dump(name, doc)
    return []


def set_env(key: str, value: str | None) -> None:
    """Set/replace (or remove when value is None) one KEY=value line in <home>/.env."""
    import os

    env = paths.ENV_FILE
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    out, done = [], False
    for line in lines:
        k = line.split("=", 1)[0].strip()
        if k == key:
            if value is not None and not done:
                out.append(f"{key}={value}")
                done = True
            continue
        out.append(line)
    if value is not None and not done:
        out.append(f"{key}={value}")
    env.write_text("\n".join(out) + "\n", encoding="utf-8")
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
