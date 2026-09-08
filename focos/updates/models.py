"""The update vocabulary. Kept deliberately small: each target lists exactly the fields that may change, so a
misread note cannot rewrite a config file. agent/schemas/updates.schema.json mirrors this for the prompts."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

TARGETS = ("goal", "tax_agenda", "profile", "spending", "decision", "merchant_rule")
PROFILE_NOTE_PATHS = ("income.notes", "cash_policy.notes", "risk.notes", "family.notes")


class UpdateError(Exception):
    """A valid-looking update that cannot be applied (unknown id, policy, config validation)."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Base(_Strict):
    reason: str = ""
    source_note_id: str | None = None


class GoalSet(_Strict):
    status: Literal["active", "done", "paused"] | None = None
    completed_on: date | None = None
    target_amount: float | None = None
    deadline: date | None = None
    notes: str | None = None
    funded_amount: float | None = None


class GoalUpdate(_Base):
    target: Literal["goal"]
    op: Literal["set"] = "set"
    id: str
    set: GoalSet


class TaxAgendaSet(_Strict):
    status: Literal["open", "done", "dropped"] | None = None
    done_on: date | None = None
    notes: str | None = None


class TaxAgendaUpdate(_Base):
    target: Literal["tax_agenda"]
    op: Literal["set", "add"] = "set"
    id: str | None = None          # set: which item
    text: str | None = None        # add: the new item
    set: TaxAgendaSet | None = None


class ProfileNoteUpdate(_Base):
    target: Literal["profile"]
    op: Literal["append"] = "append"
    path: Literal["income.notes", "cash_policy.notes", "risk.notes", "family.notes"]
    text: str


class SpendingSet(_Strict):
    monthly_core_expenses: float | None = None
    monthly_discretionary: float | None = None


class SpendingUpdate(_Base):
    target: Literal["spending"]
    op: Literal["set"] = "set"
    set: SpendingSet


class DecisionSet(_Strict):
    status: Literal["acted", "retired", "standing"]
    note: str | None = None


class DecisionUpdate(_Base):
    target: Literal["decision"]
    op: Literal["resolve"] = "resolve"
    id: str
    set: DecisionSet


class MerchantRuleUpdate(_Base):
    """A merchant -> category rule (the owner correcting a label, or the categorizer)."""
    target: Literal["merchant_rule"]
    op: Literal["set"] = "set"
    id: str                        # merchant key
    category: str

    @field_validator("category")
    @classmethod
    def _known(cls, v: str) -> str:
        from ..ledger.categories import CATEGORIES

        if v not in CATEGORIES:
            raise ValueError(f"unknown category {v!r}; expected one of {', '.join(CATEGORIES)}")
        return v


Update = Annotated[Union[GoalUpdate, TaxAgendaUpdate, ProfileNoteUpdate, SpendingUpdate, DecisionUpdate, MerchantRuleUpdate],
                   Field(discriminator="target")]
_ADAPTER = TypeAdapter(Update)


def validate_update(raw: dict) -> tuple[BaseModel | None, str | None]:
    """(model, None) for a well-formed update, (None, message) otherwise."""
    try:
        return _ADAPTER.validate_python(raw), None
    except ValidationError as e:
        err = e.errors()[0]
        loc = ".".join(str(p) for p in err["loc"])
        return None, f"{loc or 'update'}: {err['msg']}"
