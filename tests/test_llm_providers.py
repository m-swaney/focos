"""Provider construction is lazy (no network, no key needed) and pricing lookups resolve by prefix."""
import pytest

from focos.llm import DEFAULT_MODELS, key_status, provider_for
from focos.llm.base import LLMError, Usage
from focos.llm.cost import estimate, rates


def test_provider_for_each_backend(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    a = provider_for({"provider": "anthropic"})
    assert a.name == "anthropic" and a.model == DEFAULT_MODELS["anthropic"]
    o = provider_for({"provider": "openai", "model": "gpt-5.6-luna"})
    assert o.name == "openai" and o.model == "gpt-5.6-luna" and o.temperature is None
    l = provider_for({"provider": "ollama", "base_url": "http://box:11434/v1", "temperature": 0.3}, heavy=True)
    assert l.name == "ollama" and l._base_url == "http://box:11434/v1" and l.temperature == 0.3
    g = provider_for({"provider": "gemini", "model": "x", "model_heavy": "gemini-3.6-flash"}, heavy=True)
    assert g.model == "gemini-3.6-flash"
    with pytest.raises(LLMError):
        provider_for({"provider": "nope"})
    with pytest.raises(LLMError):
        o.client  # no key -> clear error, not an SDK stack trace
    assert key_status("ollama") == (True, "local (no key needed)")
    assert key_status("openai") == (False, "OPENAI_API_KEY missing")


def test_pricing_prefix_and_estimate():
    assert rates("anthropic", "claude-opus-5")["input"] == 5.0
    assert rates("anthropic", "claude-sonnet-5")["output"] == 10.0
    assert rates("openai", "gpt-5.6-luna")["input"] == 0.2
    assert rates("openai", "unknown-model") is None
    assert rates("ollama", "anything")["input"] == 0.0
    cost = estimate("anthropic", "claude-sonnet-5", Usage(input_tokens=1_000_000, output_tokens=100_000, cache_read_tokens=500_000))
    # 500k uncached @2 + 500k cached @0.2 + 100k out @10 = 1.0 + 0.1 + 1.0
    assert abs(cost - 2.1) < 1e-6
    assert estimate("openai", "mystery", Usage(input_tokens=10)) is None
