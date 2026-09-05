"""FastAPI app factory + `run_in_thread` used by `focos serve`."""
from __future__ import annotations

import hmac
import os
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import paths
from ..llm import LLMError
from ..ledger.providers.base import ProviderError


def _token() -> str | None:
    return os.environ.get("FOCOS_DASH_TOKEN")


def create_app(token: str | None = None) -> FastAPI:
    from .routes import ai, config, doctor, holdings, interview, ledger, run, schedule, setup

    app = FastAPI(title="focos local api", docs_url=None, redoc_url=None, openapi_url=None)
    expected = token if token is not None else _token()

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        if not expected:
            return JSONResponse({"error": "FOCOS_DASH_TOKEN is not set in <home>/.env; run `focos init`"}, status_code=500)
        got = request.headers.get("x-focos-token") or ""
        if not hmac.compare_digest(got, expected):
            return JSONResponse({"error": "bad token"}, status_code=401)
        return await call_next(request)

    @app.exception_handler(LLMError)
    async def _llm(_, exc: LLMError):
        return JSONResponse({"error": str(exc), "kind": "llm"}, status_code=502)

    @app.exception_handler(ProviderError)
    async def _prov(_, exc: ProviderError):
        return JSONResponse({"error": str(exc), "kind": "ledger"}, status_code=502)

    @app.get("/health")
    def health():
        return {"ok": True, "home": str(paths.HOME)}

    for r in (setup, ai, ledger, holdings, interview, config, schedule, run, doctor):
        app.include_router(r.router)
    return app


def run_in_thread(port: int, host: str = "127.0.0.1") -> threading.Thread:
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(create_app(), host=host, port=port, log_level="warning"))
    t = threading.Thread(target=server.run, name="focos-api", daemon=True)
    t.start()
    return t


def serve_blocking(port: int, host: str = "127.0.0.1") -> None:
    import uvicorn

    uvicorn.run(create_app(), host=host, port=port, log_level="info")
