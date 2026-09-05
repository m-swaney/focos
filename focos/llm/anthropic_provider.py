"""Anthropic Claude through the official SDK (anthropic >= 1.4). Adaptive thinking is the model default on Claude
Opus 5, so no thinking/sampling parameters are sent; server-side refusal fallbacks are on."""
from __future__ import annotations

import json
import os
from typing import Any

from .base import Completion, LLMError, Message, ToolSpec, Usage, structured_via_text
from .cost import estimate

DEFAULT_MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NO_FORCED_TOOL_CHOICE = ("claude-fable", "claude-mythos")


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            # zero-arg resolves ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / an `ant auth login` profile
            self._client = anthropic.Anthropic(api_key=self._api_key) if self._api_key else anthropic.Anthropic()
        return self._client

    def _usage(self, msg) -> Usage:
        u = getattr(msg, "usage", None)
        return Usage(input_tokens=getattr(u, "input_tokens", 0) or 0, output_tokens=getattr(u, "output_tokens", 0) or 0,
                     cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                     cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0)

    def _finish(self, msg) -> Completion:
        if getattr(msg, "stop_reason", None) == "refusal":
            det = getattr(msg, "stop_details", None)
            raise LLMError(f"model refused the request ({getattr(det, 'category', None)}): {getattr(det, 'explanation', '')}")
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        calls = [{"name": b.name, "input": b.input} for b in msg.content if getattr(b, "type", "") == "tool_use"]
        usage = self._usage(msg)
        return Completion(text=text, tool_calls=calls, usage=usage, cost_usd=estimate(self.name, self.model, usage),
                          model=getattr(msg, "model", self.model), stop_reason=getattr(msg, "stop_reason", None),
                          raw={"request_id": getattr(msg, "_request_id", None)})

    def _request(self, system: str, messages: list[Message], max_tokens: int, cache_system: bool) -> dict[str, Any]:
        sys_block: dict[str, Any] = {"type": "text", "text": system}
        if cache_system:
            sys_block["cache_control"] = {"type": "ephemeral"}
        return {"model": self.model, "max_tokens": max_tokens, "system": [sys_block],
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "betas": [FALLBACK_BETA], "fallbacks": "default"}

    def _run(self, kwargs: dict[str, Any]):
        import anthropic

        try:
            with self.client.beta.messages.stream(**kwargs) as stream:
                return stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic rate limit; try again in a minute") from e
        except anthropic.BadRequestError as e:
            raise LLMError(f"Anthropic bad request: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("cannot reach the Anthropic API (network)") from e

    def complete(self, system: str, messages: list[Message], *, max_tokens: int, tools: list[ToolSpec] | None = None,
                 tool_choice: str | None = None, cache_system: bool = True) -> Completion:
        kwargs = self._request(system, messages, max_tokens, cache_system)
        if tools:
            kwargs["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.input_schema,
                                **({"strict": True} if t.strict else {})} for t in tools]
            if tool_choice and not self.model.startswith(NO_FORCED_TOOL_CHOICE):
                kwargs["tool_choice"] = {"type": "tool", "name": tool_choice}
            else:
                kwargs["tool_choice"] = {"type": "auto"}
        return self._finish(self._run(kwargs))

    def structured(self, system: str, messages: list[Message], schema: dict[str, Any], *, max_tokens: int) -> tuple[dict, Completion]:
        kwargs = self._request(system, messages, max_tokens, True)
        kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        try:
            comp = self._finish(self._run(kwargs))
            return json.loads(comp.text), comp
        except LLMError as e:
            if "bad request" not in str(e):
                raise
            return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        return estimate(self.name, self.model, Usage(input_tokens=input_tokens, output_tokens=output_tokens))

    def test(self) -> Completion:
        return self.complete("Reply with the single word OK.", [Message(role="user", content="ping")], max_tokens=16, cache_system=False)
