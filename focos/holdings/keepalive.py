"""Daily Robinhood keep-alive: one cheap read call through `claude -p` so the MCP OAuth token is refreshed while
it is still fresh (the access token lives about two days; briefs run on weekdays only). Records what happened in
state/keepalive.json for the dashboard and doctor, and keeps a short history plus a Claude debug log under
state/logs so an auth failure is diagnosable from files."""
from __future__ import annotations

import json
import re
import time
from datetime import date as _date
from datetime import datetime, timedelta, timezone

from .. import paths, settings
from ..agent_runtime import claude_cli, settings_render
from ..run import claude_io, tokens
from ..sandbox import brokers

AUTH_ERROR = re.compile(
    r"unauthori[sz]ed|\b401\b|\b403\b|needs?[ -]auth|authentication (?:required|failed)|not authenticated|"
    r"please (?:re-?)?authenticate|invalid_grant|invalid_token|token (?:has )?expired|login (?:has )?expired",
    re.I)
PROMPT = "Call the `get_accounts` tool once. Do not call any other tool. Reply with exactly: OK"
KEEP_DAYS = 14
TIMEOUT_S = 300


def is_auth_error(text: str | None) -> bool:
    return bool(text) and bool(AUTH_ERROR.search(str(text)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(date: str | None = None) -> dict:
    date = date or _date.today().isoformat()
    paths.ensure_dirs()
    cfg = settings.focos()
    agent = cfg.get("agent") or {}
    before = tokens.robinhood_status()
    rec = {"ts": _now(), "date": date, "ok": False, "auth_error": False, "token_before": before, "token_after": None,
           "refreshed": False, "duration_ms": None, "error": None}
    if not before["present"]:
        rec.update(auth_error=True, error=f"Robinhood is not connected; {tokens.AUTH_FIX}")
        return _record(rec)
    adapter = brokers.current()
    files = settings_render.render(adapter)
    args = claude_cli.keepalive_args(adapter, model=agent.get("model_keepalive") or "haiku",
                                     budget_usd=float((agent.get("budget_usd") or {}).get("keepalive") or 0.25),
                                     mcp_config=files["mcp"], debug_file=paths.LOGS / f"{date}-keepalive.debug.log")
    log = paths.LOGS / f"{date}-keepalive.json"
    t0 = time.time()
    try:
        result = claude_cli.run(PROMPT, args, log_path=log, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto",
                                timeout_s=TIMEOUT_S)
    except Exception as e:  # CLI missing, timeout, unreadable output (stderr tail is in the message)
        rec["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        rec["auth_error"] = is_auth_error(rec["error"])
        rec["duration_ms"] = int((time.time() - t0) * 1000)
        rec["token_after"] = tokens.robinhood_status()
        return _record(rec)
    meta = claude_io.summarize(result)
    rec["duration_ms"] = meta.get("duration_ms") or int((time.time() - t0) * 1000)
    text = str(result.get("result") or result.get("error") or "")
    evidence = "\n".join(s for s in (text, str(result.get("_stderr_tail") or ""), str(result.get("api_error_status") or "")) if s)
    servers = result.get("mcp_servers") or []
    server_bad = any(isinstance(s, dict) and str(s.get("status", "")).lower() in ("needs-auth", "needs_auth", "failed")
                     for s in servers)
    if meta["is_error"] or server_bad or is_auth_error(evidence):
        rec["error"] = (text or meta.get("subtype") or "claude error")[:500]
        rec["auth_error"] = server_bad or is_auth_error(evidence)
    else:
        rec["ok"] = True
    after = tokens.robinhood_status()
    rec["token_after"] = after
    rec["refreshed"] = bool(after.get("expires_at") and after.get("expires_at") != before.get("expires_at"))
    return _record(rec)


def _record(rec: dict) -> dict:
    settings.write_json(paths.KEEPALIVE, rec)
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    with (paths.LOGS / "keepalive.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    _prune(rec["date"])
    return rec


def _prune(today: str) -> None:
    """Drop per-day keep-alive logs older than KEEP_DAYS (names start with YYYY-MM-DD)."""
    try:
        cutoff = _date.fromisoformat(today) - timedelta(days=KEEP_DAYS)
    except ValueError:
        return
    for p in paths.LOGS.glob("*-keepalive.*"):
        try:
            if _date.fromisoformat(p.name[:10]) < cutoff:
                p.unlink(missing_ok=True)
        except ValueError:
            continue
