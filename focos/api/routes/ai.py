from __future__ import annotations

import time

from fastapi import APIRouter
from pydantic import BaseModel

from ... import settings
from ...config import writer
from ...llm import DEFAULT_MODELS, KEY_ENV, LLMError, key_status, provider_for
from ...llm.cost import table

router = APIRouter(prefix="/ai")


class Configure(BaseModel):
    provider: str
    model: str | None = None
    model_heavy: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    mode: str | None = None          # api | agent


@router.get("/models")
def models():
    return {"defaults": DEFAULT_MODELS, "pricing_per_mtok": table(), "keys": {n: key_status(n) for n in DEFAULT_MODELS}}


@router.post("/configure")
def configure(body: Configure):
    if body.provider not in DEFAULT_MODELS:
        return {"ok": False, "error": f"unknown provider {body.provider}"}
    ai = dict(settings.focos().get("ai") or {})
    ai["provider"] = body.provider
    ai["model"] = body.model or None
    ai["model_heavy"] = body.model_heavy or None
    ai["base_url"] = body.base_url or None
    if body.mode in ("api", "agent"):
        ai["mode"] = body.mode
    writer.write_section("focos.yml", "ai", ai)
    env = KEY_ENV.get(body.provider)
    if env and body.api_key:
        writer.set_env(env, body.api_key.strip())
    if body.provider == "ollama" and body.base_url:
        writer.set_env("OLLAMA_BASE_URL", body.base_url.strip())
    ok, detail = key_status(body.provider)
    return {"ok": True, "ai": settings.focos().get("ai"), "key": detail, "key_ok": ok}


@router.post("/test")
def test():
    ai = settings.focos().get("ai") or {}
    ok, detail = key_status(str(ai.get("provider") or "anthropic"))
    if not ok:
        return {"ok": False, "error": detail}
    p = provider_for(ai)
    t0 = time.time()
    try:
        c = p.test()
    except LLMError as e:
        return {"ok": False, "provider": p.name, "model": p.model, "error": str(e)}
    return {"ok": True, "provider": p.name, "model": c.model or p.model, "latency_ms": int((time.time() - t0) * 1000),
            "cost_usd": c.cost_usd, "reply": c.text.strip()[:40]}
