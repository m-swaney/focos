"""LLM providers for API mode (brief writing, setup interview). Pick with focos.yml ai.provider / ai.model."""
from __future__ import annotations

from .base import Completion, LLMError, LLMProvider, Message, ToolSpec, Usage  # noqa: F401

DEFAULT_MODELS = {"anthropic": "claude-opus-5", "openai": "gpt-5.6-terra", "gemini": "gemini-3.1-pro", "ollama": "llama3.1"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": None}


def provider_for(ai_cfg: dict | None = None, heavy: bool = False) -> LLMProvider:
    from .. import settings

    ai = ai_cfg if ai_cfg is not None else (settings.focos().get("ai") or {})
    name = str(ai.get("provider") or "anthropic")
    model = (ai.get("model_heavy") if heavy else None) or ai.get("model") or DEFAULT_MODELS.get(name)
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)
    if name in ("openai", "ollama"):
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(name=name, model=model, base_url=ai.get("base_url"), temperature=ai.get("temperature"))
    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(model=model)
    raise LLMError(f"unknown ai.provider {name!r}")


def key_status(name: str) -> tuple[bool, str]:
    """(configured, detail) without revealing the key."""
    import os

    env = KEY_ENV.get(name)
    if env is None:
        return True, "local (no key needed)"
    val = os.environ.get(env)
    return bool(val), (f"{env} set" if val else f"{env} missing")
