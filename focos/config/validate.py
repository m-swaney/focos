"""Validate <home>/config/*.yml: per-file model checks, layout-version detection, cross-file references."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from . import CONFIG_FILES
from .models import HOUSEHOLD, MODELS, ROLES, slug


@dataclass
class Issue:
    file: str
    path: str
    message: str
    severity: str = "error"  # error | warn

    def as_dict(self) -> dict:
        return asdict(self)


def detect_layout_version(name: str, data: dict[str, Any]) -> int:
    """1 = pre-portability layout (personal keys), 2 = current. Files without a layout change return 2."""
    if not data:
        return 2
    if name == "accounts.yml":
        return 1 if "robinhood" in data and "brokerage" not in data else 2
    if name == "entities.yml":
        ents = data.get("entities") or {}
        if "name_hints" in data or any(isinstance(e, dict) and "sure_account_ids" in e for e in ents.values()):
            return 1
        return 2
    if name == "profile.yml":
        return 1 if "person" in data and "owner" not in data else 2
    if name == "goals.yml":
        goals = data.get("goals") or []
        return 1 if any(isinstance(g, dict) and "kind" not in g for g in goals) else 2
    return 2


def load_yaml(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return None, f"not valid YAML: {str(e).splitlines()[0]}"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, "top level must be a mapping"
    return data, None


def validate_data(name: str, data: dict[str, Any]) -> list[Issue]:
    model = MODELS.get(name)
    if model is None:
        return [Issue(name, "", "unknown config file", "warn")]
    if detect_layout_version(name, data) == 1:
        return [Issue(name, "", "old layout (v1); run `focos migrate` to convert it", "warn")]
    try:
        model.model_validate(data)
    except ValidationError as e:
        return [Issue(name, ".".join(str(p) for p in err["loc"]), err["msg"]) for err in e.errors()]
    return []


def _cross_file(cfgs: dict[str, dict[str, Any]]) -> list[Issue]:
    out: list[Issue] = []
    ents = set(((cfgs.get("entities.yml") or {}).get("entities") or {}).keys()) or {HOUSEHOLD}
    for a in (cfgs.get("accounts.yml") or {}).get("brokerage") or []:
        if a.get("entity", HOUSEHOLD) not in ents:
            out.append(Issue("accounts.yml", f"brokerage[{a.get('key')}].entity", f"unknown entity {a.get('entity')!r}"))
    for g in (cfgs.get("goals.yml") or {}).get("goals") or []:
        if g.get("entity", HOUSEHOLD) not in ents:
            out.append(Issue("goals.yml", f"goals[{g.get('id') or slug(str(g.get('name') or ''))}].entity", f"unknown entity {g.get('entity')!r}"))
    for p in (cfgs.get("properties.yml") or {}).get("properties") or []:
        if p.get("entity", HOUSEHOLD) not in ents:
            out.append(Issue("properties.yml", f"properties[{p.get('key')}].entity", f"unknown entity {p.get('entity')!r}"))
    tr = cfgs.get("transfer_rules.yml") or {}
    for i, r in enumerate(tr.get("rules") or []):
        for fld in ("entity", "counterparty"):
            v = r.get(fld)
            if v and v not in ents:
                out.append(Issue("transfer_rules.yml", f"rules[{i}].{fld}", f"unknown entity {v!r}"))
    for ent in (tr.get("income_labels") or {}):
        if ent not in ents:
            out.append(Issue("transfer_rules.yml", f"income_labels.{ent}", f"unknown entity {ent!r}"))
    roles_present = {a.get("role") for a in (cfgs.get("accounts.yml") or {}).get("brokerage") or []}
    for role in ((cfgs.get("profile.yml") or {}).get("targets") or {}):
        if role in ROLES and roles_present and role not in roles_present:
            out.append(Issue("profile.yml", f"targets.{role}", "no brokerage account has this role; drift will be empty", "warn"))
    for src in ((cfgs.get("profile.yml") or {}).get("income") or {}).get("sources") or []:
        if src.get("entity", HOUSEHOLD) not in ents:
            out.append(Issue("profile.yml", f"income.sources[{src.get('label')}].entity", f"unknown entity {src.get('entity')!r}"))
    return out


def validate_all(config_dir: Path | None = None) -> list[Issue]:
    from .. import paths

    cdir = config_dir or paths.CONFIG
    issues: list[Issue] = []
    cfgs: dict[str, dict[str, Any]] = {}
    for name in CONFIG_FILES:
        data, err = load_yaml(cdir / name)
        if err:
            issues.append(Issue(name, "", err))
            continue
        if data is None:
            if name == "focos.yml":
                issues.append(Issue(name, "", "missing; run `focos init`", "warn"))
            continue
        cfgs[name] = data
        issues.extend(validate_data(name, data))
    if not any(i.severity == "error" for i in issues):
        from . import compat

        normalizers = {"accounts.yml": compat.accounts_v2, "entities.yml": compat.entities_v2,
                       "profile.yml": compat.profile_v2, "goals.yml": compat.goals_v2}
        v2 = {n: (normalizers[n](d) if n in normalizers else d) for n, d in cfgs.items()}
        issues.extend(_cross_file(v2))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    return any(i.severity == "error" for i in issues)
