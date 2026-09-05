from __future__ import annotations

import json
from typing import Literal, Protocol

from jsonschema import Draft202012Validator
from pydantic import BaseModel

from .. import paths, settings


class BriefOutcome(BaseModel):
    ok: bool
    result: dict | None = None
    report_path: str | None = None
    cost_usd: float | None = None
    meta: dict = {}
    error: str | None = None


class BriefWriter(Protocol):
    mode_name: Literal["agent", "api"]

    def write(self, mode: str, date: str, run_id: str) -> BriefOutcome: ...


def validate_result(payload: dict) -> list[str]:
    schema = json.loads((paths.AGENT / "schemas" / "brief_result.schema.json").read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in sorted(v.iter_errors(payload), key=str)]


def record_result(payload: dict, meta: dict, date: str, mode: str) -> None:
    settings.write_json(paths.LATEST / "brief_result.json", {**payload, "_meta": meta, "date": date, "mode": mode})
