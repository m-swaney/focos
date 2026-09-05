"""Google Gemini through the google-genai SDK."""
from __future__ import annotations

import json
import os
from typing import Any

from .base import Completion, LLMError, Message, ToolSpec, Usage, structured_via_text
from .cost import estimate

DEFAULT_MODEL = "gemini-3.1-pro"


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None, api_key: str | None = None):
        self.model = model or DEFAULT_MODEL
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            if not self._api_key:
                raise LLMError("GEMINI_API_KEY is not set")
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @staticmethod
    def _contents(messages: list[Message]) -> list[dict[str, Any]]:
        return [{"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]} for m in messages]

    def _usage(self, resp) -> Usage:
        u = getattr(resp, "usage_metadata", None)
        return Usage(input_tokens=getattr(u, "prompt_token_count", 0) or 0,
                     output_tokens=(getattr(u, "candidates_token_count", 0) or 0) + (getattr(u, "thoughts_token_count", 0) or 0),
                     cache_read_tokens=getattr(u, "cached_content_token_count", 0) or 0)

    def _run(self, contents, config) -> Any:
        try:
            return self.client.models.generate_content(model=self.model, contents=contents, config=config)
        except Exception as e:  # the SDK raises google.genai.errors.APIError subclasses; keep one message shape
            msg = str(e)
            if "API key" in msg or "401" in msg or "403" in msg:
                raise LLMError("Gemini rejected the API key") from e
            if "429" in msg:
                raise LLMError("Gemini rate limit; try again in a minute") from e
            raise LLMError(f"Gemini error: {msg[:200]}") from e

    def _finish(self, resp) -> Completion:
        text = ""
        try:
            text = resp.text or ""
        except Exception:  # noqa: BLE001  (function-call-only responses have no text)
            text = ""
        calls = [{"name": fc.name, "input": dict(fc.args or {})} for fc in (getattr(resp, "function_calls", None) or [])]
        usage = self._usage(resp)
        cand = (getattr(resp, "candidates", None) or [None])[0]
        return Completion(text=text, tool_calls=calls, usage=usage, cost_usd=estimate(self.name, self.model, usage),
                          model=self.model, stop_reason=str(getattr(cand, "finish_reason", None)) if cand else None)

    def complete(self, system: str, messages: list[Message], *, max_tokens: int, tools: list[ToolSpec] | None = None,
                 tool_choice: str | None = None, cache_system: bool = True) -> Completion:
        from google.genai import types

        cfg: dict[str, Any] = {"system_instruction": system, "max_output_tokens": max_tokens}
        if tools:
            decls = []
            for t in tools:
                try:
                    decls.append(types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.input_schema))
                except Exception:  # noqa: BLE001  (older SDK field name)
                    decls.append(types.FunctionDeclaration(name=t.name, description=t.description, parameters=t.input_schema))
            cfg["tools"] = [types.Tool(function_declarations=decls)]
            if tool_choice:
                cfg["tool_config"] = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="ANY", allowed_function_names=[tool_choice]))
        return self._finish(self._run(self._contents(messages), types.GenerateContentConfig(**cfg)))

    def structured(self, system: str, messages: list[Message], schema: dict[str, Any], *, max_tokens: int) -> tuple[dict, Completion]:
        from google.genai import types

        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=max_tokens,
                                          response_mime_type="application/json", response_json_schema=schema)
        try:
            comp = self._finish(self._run(self._contents(messages), cfg))
            return json.loads(comp.text), comp
        except (LLMError, json.JSONDecodeError):
            return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        return estimate(self.name, self.model, Usage(input_tokens=input_tokens, output_tokens=output_tokens))

    def test(self) -> Completion:
        return self.complete("Reply with the single word OK.", [Message(role="user", content="ping")], max_tokens=16)
