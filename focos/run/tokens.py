"""Read token expiries from ~/.claude/.credentials.json without ever exposing the tokens."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def expiries() -> dict:
    """{"robinhood_access_expires": iso|None, "robinhood_has_refresh": bool, "claude_refresh_expires": iso|None, ...}"""
    creds = creds_path()
    out = {"available": creds.exists(), "robinhood_access_expires": None, "robinhood_has_refresh": False,
           "claude_access_expires": None, "claude_refresh_expires": None, "subscription": None}
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
        if isinstance(entry, dict) and entry.get("serverName") == server:
            exp = _ts(entry.get("expiresAt"))
            out["robinhood_access_expires"] = exp.isoformat() if exp else None
            out["robinhood_has_refresh"] = bool(entry.get("refreshToken"))
    ca = d.get("claudeAiOauth") or {}
    a, r = _ts(ca.get("expiresAt")), _ts(ca.get("refreshTokenExpiresAt"))
    out["claude_access_expires"] = a.isoformat() if a else None
    out["claude_refresh_expires"] = r.isoformat() if r else None
    out["subscription"] = ca.get("subscriptionType")
    return out


def alerts(days_ahead: int = 5) -> list[dict]:
    e = expiries()
    out: list[dict] = []
    now = datetime.now(timezone.utc)
    if not e["available"]:
        return [{"severity": "warn", "code": "credentials_missing", "text": "Claude credentials file not found; headless runs will fail"}]
    if not e["robinhood_has_refresh"]:
        out.append({"severity": "warn", "code": "robinhood_no_refresh",
                    "text": "Robinhood MCP has no refresh token; re-authenticate with /mcp before the access token expires"})
    if e["claude_refresh_expires"]:
        r = datetime.fromisoformat(e["claude_refresh_expires"])
        if r - now < timedelta(days=days_ahead):
            out.append({"severity": "critical" if r < now else "warn", "code": "claude_login_expiring",
                        "text": f"Claude login refresh token expires {r.date()}; open an interactive `claude` session to renew"})
    return out
