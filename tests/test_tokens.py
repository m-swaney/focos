"""Token expiry reading and the Robinhood alerts it drives (fake ~/.claude/.credentials.json, never a real one)."""
import json
import time
from pathlib import Path

import yaml

from focos import paths, settings
from focos.run import tokens


def _creds(home: Path, rh: dict | None, claude_refresh_in_s: float = 30 * 86400) -> None:
    d = {"claudeAiOauth": {"expiresAt": (time.time() + 3600) * 1000, "refreshTokenExpiresAt": (time.time() + claude_refresh_in_s) * 1000,
                           "subscriptionType": "max"}}
    if rh is not None:
        d["mcpOAuth"] = {"robinhood-trading|abc123": {"serverName": "robinhood-trading", "serverUrl": "https://agent.robinhood.com/mcp/trading",
                                                       "accessToken": "x", **rh}}
    p = tokens.creds_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def _want_robinhood(home: Path) -> None:
    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "agent"}, "holdings": {"source": "robinhood_mcp"}}))
    settings.reset()


def test_status_valid_token(initialized_home: Path):
    _creds(initialized_home, {"expiresAt": (time.time() + 40 * 3600) * 1000, "refreshToken": "r"})
    st = tokens.robinhood_status()
    assert st["present"] and st["has_refresh"] and not st["expired"] and 39 < st["hours_left"] < 41
    e = tokens.expiries()
    assert e["subscription"] == "max" and e["keepalive"] is None


def test_status_expired_without_refresh_is_critical(initialized_home: Path):
    _want_robinhood(initialized_home)
    _creds(initialized_home, {"expiresAt": (time.time() - 3600) * 1000})
    st = tokens.robinhood_status()
    assert st["present"] and st["expired"] and not st["has_refresh"]
    codes = {a["code"]: a for a in tokens.alerts()}
    assert codes["robinhood_login_expired"]["severity"] == "critical" and "focos auth robinhood" in codes["robinhood_login_expired"]["text"]


def test_status_expired_with_refresh_is_warn(initialized_home: Path):
    _want_robinhood(initialized_home)
    _creds(initialized_home, {"expiresAt": (time.time() - 3600) * 1000, "refreshToken": "r"})
    codes = {a["code"]: a for a in tokens.alerts()}
    assert codes["robinhood_access_expired"]["severity"] == "warn" and "robinhood_login_expired" not in codes


def test_not_connected(initialized_home: Path):
    _want_robinhood(initialized_home)
    _creds(initialized_home, None)
    assert not tokens.robinhood_status()["present"]
    assert [a["code"] for a in tokens.alerts()] == ["robinhood_not_connected"]


def test_no_robinhood_alerts_when_not_configured(initialized_home: Path):
    _creds(initialized_home, None)  # holdings.source is none in a fresh home
    assert tokens.alerts() == []


def test_keepalive_auth_failure_escalates(initialized_home: Path):
    _want_robinhood(initialized_home)
    _creds(initialized_home, {"expiresAt": (time.time() + 3600) * 1000, "refreshToken": "r"})
    settings.write_json(paths.KEEPALIVE, {"date": "2026-09-06", "ok": False, "auth_error": True, "error": "needs authentication"})
    codes = {a["code"]: a for a in tokens.alerts()}
    assert codes["robinhood_login_expired"]["severity"] == "critical" and "2026-09-06" in codes["robinhood_login_expired"]["text"]
    assert tokens.expiries()["keepalive"]["auth_error"] is True


def test_claude_login_expiring(initialized_home: Path):
    _creds(initialized_home, None, claude_refresh_in_s=2 * 86400)
    codes = [a["code"] for a in tokens.alerts()]
    assert codes == ["claude_login_expiring"]


def test_missing_credentials(initialized_home: Path):
    assert not tokens.creds_path().exists()
    assert [a["code"] for a in tokens.alerts()] == ["credentials_missing"]
