"""Read token expiries from ~/.claude/.credentials.json without ever exposing the tokens, plus the record the
daily Robinhood keep-alive leaves behind. Nothing here returns a token value."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import paths, settings

AUTH_FIX = "run `focos auth robinhood`"


def creds_path() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home()) / ".claude" / ".credentials.json"


def _ts(v) -> datetime | None:
    if v is None:
        return None
    try:
        v = float(v)
        if v > 1e12:
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def keepalive_record() -> dict | None:
    """What the last `focos holdings keepalive` wrote (state/keepalive.json), or None."""
    rec = settings.read_json(paths.KEEPALIVE, None)
    return rec if isinstance(rec, dict) else None


def expiries() -> dict:
    """{"robinhood_access_expires": iso|None, "robinhood_has_refresh": bool, "claude_refresh_expires": iso|None,
    "subscription": str|None, "keepalive": {...}|None, ...}"""
    creds = creds_path()
    out = {"available": creds.exists(), "robinhood_access_expires": None, "robinhood_has_refresh": False,
           "claude_access_expires": None, "claude_refresh_expires": None, "subscription": None,
           "keepalive": keepalive_record()}
    if not creds.exists():
        return out
    try:
        d = json.loads(creds.read_text(encoding="utf-8"))
    except Exception:
        out["available"] = False
        return out
    try:
        from ..sandbox import brokers

        server = brokers.current().mcp_server_name
    except Exception:  # noqa: BLE001
        server = "robinhood-trading"
    for key, entry in (d.get("mcpOAuth") or {}).items():
        if isinstance(entry, dict) and (entry.get("serverName") == server or str(key).split("|")[0] == server):
            exp = _ts(entry.get("expiresAt"))
            out["robinhood_access_expires"] = exp.isoformat() if exp else None
            out["robinhood_has_refresh"] = bool(entry.get("refreshToken"))
    ca = d.get("claudeAiOauth") or {}
    a, r = _ts(ca.get("expiresAt")), _ts(ca.get("refreshTokenExpiresAt"))
    out["claude_access_expires"] = a.isoformat() if a else None
    out["claude_refresh_expires"] = r.isoformat() if r else None
    out["subscription"] = ca.get("subscriptionType")
    return out


def robinhood_status(e: dict | None = None) -> dict:
    """{"present", "expires_at", "has_refresh", "hours_left", "expired"} for the broker MCP login."""
    e = e if e is not None else expiries()
    exp = e.get("robinhood_access_expires")
    has_refresh = bool(e.get("robinhood_has_refresh"))
    hours_left = None
    expired = False
    if exp:
        dt = datetime.fromisoformat(exp)
        hours_left = round((dt - datetime.now(timezone.utc)).total_seconds() / 3600, 2)
        expired = hours_left <= 0
    return {"present": bool(exp or has_refresh), "expires_at": exp, "has_refresh": has_refresh,
            "hours_left": hours_left, "expired": expired}


def _robinhood_wanted() -> bool:
    try:
        return (settings.focos().get("holdings") or {}).get("source") == "robinhood_mcp"
    except Exception:  # noqa: BLE001
        return False


def alerts(days_ahead: int = 5) -> list[dict]:
    e = expiries()
    out: list[dict] = []
    now = datetime.now(timezone.utc)
    if not e["available"]:
        return [{"severity": "warn", "code": "credentials_missing", "text": "Claude credentials file not found; headless runs will fail"}]
    if _robinhood_wanted():
        rs = robinhood_status(e)
        ka = e.get("keepalive") or {}
        if not rs["present"]:
            out.append({"severity": "warn", "code": "robinhood_not_connected",
                        "text": f"Robinhood is not connected; {AUTH_FIX}"})
        elif rs["expired"] and not rs["has_refresh"]:
            out.append({"severity": "critical", "code": "robinhood_login_expired",
                        "text": f"Robinhood login expired and cannot refresh; {AUTH_FIX}"})
        elif rs["expired"]:
            out.append({"severity": "warn", "code": "robinhood_access_expired",
                        "text": f"Robinhood access token expired; the next run will try to refresh it. If it fails, {AUTH_FIX}"})
        if ka.get("ok") is False and ka.get("auth_error") and not any(a["code"] == "robinhood_login_expired" for a in out):
            out.append({"severity": "critical", "code": "robinhood_login_expired",
                        "text": f"The Robinhood keep-alive on {ka.get('date')} could not authenticate; {AUTH_FIX}"})
    if e["claude_refresh_expires"]:
        r = datetime.fromisoformat(e["claude_refresh_expires"])
        if r - now < timedelta(days=days_ahead):
            out.append({"severity": "critical" if r < now else "warn", "code": "claude_login_expiring",
                        "text": f"Claude login refresh token expires {r.date()}; open an interactive `claude` session to renew"})
    return out
