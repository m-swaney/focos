"""The Robinhood keep-alive job: what it runs, what it records, how it classifies failures. `claude` is never invoked."""
import json
import time
from pathlib import Path

import yaml

from focos import paths, settings
from focos.holdings import keepalive
from focos.run import tokens
from focos.sandbox.brokers.robinhood import PLACE, PREFIX


def _setup(home: Path, expires_in_s: float = 3600, connected: bool = True) -> None:
    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "agent"}, "holdings": {"source": "robinhood_mcp"}}))
    settings.reset()
    d = {"claudeAiOauth": {"expiresAt": (time.time() + 3600) * 1000, "refreshTokenExpiresAt": (time.time() + 86400 * 20) * 1000}}
    if connected:
        d["mcpOAuth"] = {"robinhood-trading|x": {"serverName": "robinhood-trading", "accessToken": "a", "refreshToken": "r",
                                                 "expiresAt": (time.time() + expires_in_s) * 1000}}
    p = tokens.creds_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


def _bump_expiry(hours: float) -> None:
    p = tokens.creds_path()
    d = json.loads(p.read_text(encoding="utf-8"))
    d["mcpOAuth"]["robinhood-trading|x"]["expiresAt"] = (time.time() + hours * 3600) * 1000
    p.write_text(json.dumps(d), encoding="utf-8")


def test_keepalive_success_records_refresh(initialized_home: Path, monkeypatch):
    _setup(initialized_home)
    seen = {}

    def fake_run(prompt, args, *, log_path, cwd, claude="auto", timeout_s=0):
        seen.update(prompt=prompt, args=args, log_path=log_path, cwd=cwd)
        _bump_expiry(48)  # the CLI refreshed the token while it ran
        return {"is_error": False, "result": "OK", "duration_ms": 1234, "num_turns": 2}

    monkeypatch.setattr(keepalive.claude_cli, "run", fake_run)
    rec = keepalive.run("2026-09-06")
    assert rec["ok"] and rec["refreshed"] and not rec["auth_error"] and rec["duration_ms"] == 1234
    assert rec["token_after"]["hours_left"] > rec["token_before"]["hours_left"]
    assert "get_accounts" in seen["prompt"] and seen["cwd"] == paths.HOME
    assert seen["log_path"] == paths.LOGS / "2026-09-06-keepalive.json"
    args = seen["args"]
    assert args[args.index("--allowedTools") + 1] == PREFIX + "get_accounts"
    assert PLACE in args[args.index("--disallowedTools") + 1] and "--debug-file" in args
    assert args[args.index("--model") + 1] == "haiku" and args[args.index("--max-budget-usd") + 1] == "0.25"
    saved = settings.read_json(paths.KEEPALIVE)
    assert saved["ok"] is True and saved["date"] == "2026-09-06"
    lines = (paths.LOGS / "keepalive.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["ok"] is True
    assert tokens.expiries()["keepalive"]["ok"] is True


def test_keepalive_auth_error_is_classified(initialized_home: Path, monkeypatch):
    _setup(initialized_home)
    monkeypatch.setattr(keepalive.claude_cli, "run",
                        lambda *a, **k: {"is_error": True, "result": "MCP server robinhood-trading needs authentication", "subtype": "error"})
    rec = keepalive.run("2026-09-06")
    assert not rec["ok"] and rec["auth_error"] and "needs authentication" in rec["error"]
    assert not rec["refreshed"]
    assert [a["code"] for a in tokens.alerts()] == ["robinhood_login_expired"]


def test_keepalive_server_status_needs_auth(initialized_home: Path, monkeypatch):
    _setup(initialized_home)
    monkeypatch.setattr(keepalive.claude_cli, "run",
                        lambda *a, **k: {"is_error": False, "result": "OK", "mcp_servers": [{"name": "robinhood-trading", "status": "needs-auth"}]})
    rec = keepalive.run("2026-09-06")
    assert not rec["ok"] and rec["auth_error"]


def test_keepalive_other_error_is_not_auth(initialized_home: Path, monkeypatch):
    _setup(initialized_home)
    monkeypatch.setattr(keepalive.claude_cli, "run", lambda *a, **k: {"is_error": True, "result": "rate limited, try later", "subtype": "error"})
    rec = keepalive.run("2026-09-06")
    assert not rec["ok"] and not rec["auth_error"]
    assert tokens.alerts() == []  # token itself is fine; a transient failure is not a login problem


def test_keepalive_cli_exception_captures_stderr(initialized_home: Path, monkeypatch):
    _setup(initialized_home)

    def boom(*a, **k):
        raise RuntimeError("state/logs/x.json is empty; stderr: Error: 401 Unauthorized from robinhood-trading")

    monkeypatch.setattr(keepalive.claude_cli, "run", boom)
    rec = keepalive.run("2026-09-06")
    assert not rec["ok"] and rec["auth_error"] and "401" in rec["error"]


def test_keepalive_not_connected_skips_cli(initialized_home: Path, monkeypatch):
    _setup(initialized_home, connected=False)
    monkeypatch.setattr(keepalive.claude_cli, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    rec = keepalive.run("2026-09-06")
    assert not rec["ok"] and rec["auth_error"] and "focos auth robinhood" in rec["error"]


def test_keepalive_prunes_old_logs(initialized_home: Path, monkeypatch):
    _setup(initialized_home)
    paths.LOGS.mkdir(parents=True, exist_ok=True)
    old, recent = paths.LOGS / "2026-08-01-keepalive.json", paths.LOGS / "2026-09-01-keepalive.debug.log"
    old.write_text("{}"), recent.write_text("")
    monkeypatch.setattr(keepalive.claude_cli, "run", lambda *a, **k: {"is_error": False, "result": "OK"})
    keepalive.run("2026-09-06")
    assert not old.exists() and recent.exists()
