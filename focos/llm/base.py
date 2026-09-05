"""Minimal LLM provider interface: one completion call (optionally with tools), one structured-output call,
usage and cost. Three operations are all the brief writer and the setup interview need."""
from __future__ import annotations

import json
from typing import Any, Literal, Protocol

from jsonschema import Draft202012Validator
from pydantic import BaseModel


class LLMError(RuntimeError):
    pass


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = False


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Completion(BaseModel):
    text: str = ""
    tool_calls: list[dict[str, Any]] = []      # [{"name": str, "input": dict}]
    usage: Usage = Usage()
    cost_usd: float | None = None
    model: str = ""
    stop_reason: str | None = None
    raw: dict[str, Any] = {}


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[Message], *, max_tokens: int, tools: list[ToolSpec] | None = None,
                 tool_choice: str | None = None, cache_system: bool = True) -> Completion: ...

    def structured(self, system: str, messages: list[Message], schema: dict[str, Any], *, max_tokens: int) -> tuple[dict, Completion]: ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None: ...

    def test(self) -> Completion: ...


def validate_against(schema: dict[str, Any], data: dict) -> list[str]:
    v = Draft202012Validator(schema)
    return [f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in sorted(v.iter_errors(data), key=str)]


def parse_json_text(text: str) -> dict:
    from ..run.claude_io import extract_json

    return extract_json(text)


def structured_via_text(provider: LLMProvider, system: str, messages: list[Message], schema: dict[str, Any], *,
                        max_tokens: int, retries: int = 1) -> tuple[dict, Completion]:
    """Fallback for providers/models without native JSON-schema output: ask for a fenced JSON block, validate,
    and retry once with the validation errors appended."""
    ask = Message(role="user", content="Respond with ONLY a fenced ```json block that matches this JSON Schema exactly:\n"
                                       + json.dumps(schema, indent=1))
    convo = list(messages) + [ask]
    last_err = ""
    completion = Completion()
    for attempt in range(retries + 1):
        completion = provider.complete(system, convo, max_tokens=max_tokens, cache_system=True)
        try:
            data = parse_json_text(completion.text)
            errors = validate_against(schema, data)
        except (ValueError, json.JSONDecodeError) as e:
            data, errors = {}, [f"not valid JSON: {e}"]
        if not errors:
            return data, completion
        last_err = "; ".join(errors[:5])
        convo = convo + [Message(role="assistant", content=completion.text),
                         Message(role="user", content=f"That did not validate: {last_err}. Return ONLY the corrected fenced JSON.")]
    raise LLMError(f"structured output did not validate after {retries + 1} attempts: {last_err}")
