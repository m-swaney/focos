"""Section schemas for the interview, generated from the config models so the wizard, the LLM tools, and
validation all agree."""
from __future__ import annotations

from typing import Any, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

from ..config.models import Goal, Profile
from ..llm.base import ToolSpec

PROFILE_SECTIONS = ["owner", "household", "spouse", "income", "spending", "cash_policy", "debt_terms", "retirement",
                    "family", "protection", "tax_agenda", "risk", "targets"]
SECTIONS = PROFILE_SECTIONS + ["goals"]

SECTION_HINTS = {
    "owner": "first name, birth year, filing status, marginal federal bracket, employment, whether a CPA does the return",
    "household": "timezone (IANA), state, currency",
    "spouse": "whether a partner shares finances, their employment and rough annual gross",
    "income": "every income source with a label, kind (w2/business/rental/other), annual amount, and which entity earns it",
    "spending": "monthly core expenses (housing, food, utilities, insurance; excluding debt payments) and discretionary",
    "cash_policy": "emergency fund target in months, minimum checking buffer, whether business cash counts as reserve",
    "debt_terms": "for each loan/card visible in the accounts: a name regex, rate, fixed/variable, minimum payment",
    "retirement": "target age, target annual spend in today's dollars, IRA/401k contribution limits and year-to-date amounts",
    "family": "dependents, whether children are planned",
    "protection": "term life, will or trust, umbrella liability, disability insurance (true/false/unknown)",
    "tax_agenda": "open questions for a CPA",
    "risk": "tolerance, max single-stock and sector weight percentages",
    "targets": "allocation targets per account role (taxable, roth_ira, ...) as percentages by asset class",
    "goals": "named goals with a kind (emergency_fund, debt_payoff, retirement_contribution, purchase, custom), target amount, deadline",
}


def _strip(schema: dict[str, Any]) -> dict[str, Any]:
    """Inline $defs so providers that reject $ref (and strict modes) get a self-contained schema."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return walk(dict(defs.get(name, {})))
            return {k: walk(v) for k, v in node.items() if k not in ("title",)}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def section_schema(section: str) -> dict[str, Any]:
    if section == "goals":
        return {"type": "array", "items": _strip(Goal.model_json_schema())}
    ann = Profile.model_fields[section].annotation
    if get_origin(ann) is list:
        (item,) = get_args(ann)
        if isinstance(item, type) and issubclass(item, BaseModel):
            return {"type": "array", "items": _strip(item.model_json_schema())}
        return {"type": "array", "items": {"type": "string"}}
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return _strip(ann.model_json_schema())
    return _strip(TypeAdapter(ann).json_schema())


def all_schemas() -> dict[str, dict[str, Any]]:
    return {s: section_schema(s) for s in SECTIONS}


def validate_section(section: str, data: Any) -> tuple[Any, list[str]]:
    """Return (normalized data, errors). Uses the same models as config validation."""
    from pydantic import ValidationError

    try:
        if section == "goals":
            rows = [Goal.model_validate(g) for g in (data or [])]
            return [g.model_dump(mode="json", exclude_none=True) for g in rows], []
        ann = Profile.model_fields[section].annotation
        val = TypeAdapter(ann).validate_python(data)
        dumped = TypeAdapter(ann).dump_python(val, mode="json", exclude_none=True)
        return dumped, []
    except ValidationError as e:
        return data, [f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]


def tools() -> list[ToolSpec]:
    return [
        ToolSpec(name="propose_section",
                 description="Propose the contents of one profile/goals section once you know enough about it. The user reviews "
                             "and confirms; ask follow-ups rather than guessing. Amounts are numbers in the household currency.",
                 input_schema={"type": "object", "required": ["section", "data", "confidence"],
                               "properties": {"section": {"type": "string", "enum": SECTIONS},
                                              "data": {"type": "object", "description": "section contents; goals is {\"goals\": [...]}"},
                                              "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                                              "assumptions": {"type": "array", "items": {"type": "string"}}}}),
        ToolSpec(name="finish", description="Call when every relevant section has been proposed or skipped.",
                 input_schema={"type": "object", "properties": {"summary": {"type": "string"}}}),
    ]
