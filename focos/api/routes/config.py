from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ... import settings
from ...config import CONFIG_FILES
from ...config import writer
from ...config.models import MODELS
from ...config.validate import has_errors, validate_all

router = APIRouter(prefix="/config")


def _name(file: str) -> str:
    name = file if file.endswith(".yml") else f"{file}.yml"
    if name not in CONFIG_FILES:
        raise HTTPException(404, "unknown config file")
    return name


@router.get("/validate")
def validate():
    issues = validate_all()
    return {"ok": not has_errors(issues), "issues": [i.as_dict() for i in issues]}


@router.get("/schema/{file}")
def schema(file: str):
    return MODELS[_name(file)].model_json_schema()


@router.get("/{file}")
def get_file(file: str):
    name = _name(file)
    if name == "focos.yml":
        return settings.focos()
    view = {"profile.yml": settings.profile_v2, "goals.yml": settings.goals_v2, "accounts.yml": settings.accounts_v2,
            "entities.yml": settings.entities_v2}.get(name)
    return view() if view else settings._load_yaml(name)


@router.put("/{file}")
def put_file(file: str, body: dict[str, Any]):
    name = _name(file)
    issues = writer.write_file(name, body)
    return {"ok": not issues, "issues": [i.as_dict() for i in issues]}


@router.patch("/{file}/{key}")
def patch_key(file: str, key: str, body: Any = Body(...)):
    name = _name(file)
    issues = writer.write_section(name, key, body)
    return {"ok": not issues, "issues": [i.as_dict() for i in issues]}
