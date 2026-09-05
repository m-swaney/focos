"""OpenAI, and any OpenAI-compatible endpoint (Ollama at http://localhost:11434/v1, OpenRouter, LM Studio), through
the openai SDK's chat.completions API."""
from __future__ import annotations

import json
import os
from typing import Any

from .base import Completion, LLMError, Message, ToolSpec, Usage, structured_via_text
from .cost import estimate

DEFAULT_MODELS = {"openai": "gpt-5.6-terra", "ollama": "llama3.1"}
OLLAMA_URL = "http://localhost:11434/v1"


class OpenAICompatProvider:
    def __init__(self, name: str = "openai", model: str | None = None, api_key: str | None = None, base_url: str | None = None,
                 temperature: float | None = None):
        self.name = name
        self.model = model or DEFAULT_MODELS.get(name, "gpt-5.6-terra")
        if name == "ollama":
            self._api_key = api_key or "ollama"
            self._base_url = base_url or os.environ.get("OLLAMA_BASE_URL") or OLLAMA_URL
        else:
            self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
            self._base_url = base_url
        self.temperature = temperature if name == "ollama" else None  # OpenAI reasoning models reject non-default sampling
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            if not self._api_key:
                raise LLMError("OPENAI_API_KEY is not set")
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    @staticmethod
    def _messages(system: str, messages: list[Message]) -> list[dict[str, str]]:
        return [{"role": "system", "content": system}] + [{"role": m.role, "content": m.content} for m in messages]

    def _usage(self, resp) -> Usage:
        u = getattr(resp, "usage", None)
        details = getattr(u, "prompt_tokens_details", None)
        return Usage(input_tokens=getattr(u, "prompt_tokens", 0) or 0, output_tokens=getattr(u, "completion_tokens", 0) or 0,
                     cache_read_tokens=getattr(details, "cached_tokens", 0) or 0)

    def _run(self, **kwargs) -> Any:
        import openai

        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        try:
            return self.client.chat.completions.create(model=self.model, **kwargs)
        except openai.AuthenticationError as e:
            raise LLMError(f"{self.name} rejected the API key") from e
        except openai.RateLimitError as e:
            raise LLMError(f"{self.name} rate limit; try again in a minute") from e
        except openai.BadRequestError as e:
            raise LLMError(f"{self.name} bad request: {getattr(e, 'message', e)}") from e
        except openai.NotFoundError as e:
            raise LLMError(f"{self.name}: model {self.model!r} not found") from e
        except openai.APIStatusError as e:
            raise LLMError(f"{self.name} error {e.status_code}: {getattr(e, 'message', e)}") from e
        except openai.APIConnectionError as e:
            raise LLMError(f"cannot reach {self.name} at {self._base_url or 'api.openai.com'}") from e

    def _finish(self, resp) -> Completion:
        choice = resp.choices[0]
        msg = choice.message
        calls = []
        for tc in getattr(msg, "tool_calls", None) or []:
            fn = getattr(tc, "function", None)
            try:
                args = json.loads(fn.arguments) if fn and fn.arguments else {}
            except json.JSONDecodeError:
                args = {"_raw": fn.arguments}
            calls.append({"name": fn.name if fn else "", "input": args})
        usage = self._usage(resp)
        return Completion(text=msg.content or "", tool_calls=calls, usage=usage, cost_usd=estimate(self.name, self.model, usage),
                          model=getattr(resp, "model", self.model), stop_reason=getattr(choice, "finish_reason", None))

    def complete(self, system: str, messages: list[Message], *, max_tokens: int, tools: list[ToolSpec] | None = None,
                 tool_choice: str | None = None, cache_system: bool = True) -> Completion:
        kwargs: dict[str, Any] = {"messages": self._messages(system, messages), "max_completion_tokens": max_tokens}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                                 "parameters": t.input_schema}} for t in tools]
            kwargs["tool_choice"] = {"type": "function", "function": {"name": tool_choice}} if tool_choice else "auto"
        return self._finish(self._run(**kwargs))

    def structured(self, system: str, messages: list[Message], schema: dict[str, Any], *, max_tokens: int) -> tuple[dict, Completion]:
        kwargs: dict[str, Any] = {"messages": self._messages(system, messages), "max_completion_tokens": max_tokens,
                                  "response_format": {"type": "json_schema", "json_schema": {"name": "output", "schema": schema}}}
        try:
            comp = self._finish(self._run(**kwargs))
            return json.loads(comp.text), comp
        except (LLMError, json.JSONDecodeError):
            return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        return estimate(self.name, self.model, Usage(input_tokens=input_tokens, output_tokens=output_tokens))

    def test(self) -> Completion:
        return self.complete("Reply with the single word OK.", [Message(role="user", content="ping")], max_tokens=16)
