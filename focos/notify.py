"""Tell the household when something needs them, instead of hoping they read the brief.

0.3.6 wrote every problem into prose: a breached stop the gate would not let the agent sell was a paragraph in
daily brief after daily brief and nothing else. This module pushes it.

Two channels, both optional and both best-effort (a failed notification never fails a run):

- **Desktop toast** on the machine that runs focos (Windows toast, macOS Notification Center, Linux notify-send).
  On by default. Nothing leaves the machine.
- **Phone push via ntfy** (https://ntfy.sh, free, no account). Off until `focos notify phone` sets it up. The
  topic name is the only secret, so it is random and lives in `.env` (FOCOS_NTFY_TOPIC), never in config. The
  message text travels through the ntfy server: keep that in mind, or point `notify.ntfy_server` at your own.

Repeats are suppressed: a keyed message goes out once, and a standing issue is re-sent at most once a week.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import date as _date
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

from . import paths, settings

SEVERITY_RANK = {"info": 0, "warn": 1, "critical": 2}
NTFY_PRIORITY = {"info": "3", "warn": "4", "critical": "5"}
NTFY_TAGS = {"info": "information_source", "warn": "warning", "critical": "rotating_light"}
TOPIC_ENV = "FOCOS_NTFY_TOPIC"
REMIND_AFTER_DAYS = 7
# Standing conditions worth a push. Everything else stays on the dashboard and in the brief.
PUSH_CODES = {
    "sandbox_stop_breached", "sandbox_exit_failed", "sandbox_halted", "robinhood_login_expired",
    "robinhood_not_connected", "claude_login_expiring", "credentials_missing", "feed_auth", "run_failed",
    "drawdown", "app_issue",
}


def log_file():
    return paths.STATE / "notify.jsonl"


def issues_file():
    return paths.STATE / "issues.json"


def cfg() -> dict:
    return (settings.focos().get("notify") or {})


def _sent_keys(today: str) -> set[str]:
    p = log_file()
    if not p.exists():
        return set()
    keys = set()
    for line in p.read_text(encoding="utf-8").splitlines()[-500:]:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("key") and str(e.get("ts", ""))[:10] == today:
            keys.add(e["key"])
    return keys


def _record(entry: dict) -> None:
    p = log_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def send(title: str, body: str, severity: str = "warn", key: str | None = None, force: bool = False) -> dict:
    """Send one notification on every enabled channel. `key` de-duplicates within a day."""
    c = cfg()
    today = _date.today().isoformat()
    result = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "key": key, "severity": severity,
              "title": title, "channels": {}}
    if not c.get("enabled", True) and not force:
        result["skipped"] = "notify.enabled is false"
        return result
    if key and not force and key in _sent_keys(today):
        result["skipped"] = "already sent today"
        return result
    if SEVERITY_RANK.get(severity, 1) < SEVERITY_RANK.get(str(c.get("min_severity") or "info"), 0) and not force:
        result["skipped"] = "below notify.min_severity"
        return result
    if c.get("toast", True):
        result["channels"]["toast"] = _toast(title, body)
    topic = os.environ.get(TOPIC_ENV) or _env_file_value(TOPIC_ENV)
    if topic:
        result["channels"]["ntfy"] = _ntfy(str(c.get("ntfy_server") or "https://ntfy.sh"), topic, title, body, severity,
                                           c.get("click_url"))
    _record(result)
    return result


def _env_file_value(key: str) -> str | None:
    try:
        for line in paths.ENV_FILE.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() == key and v.strip():
                return v.strip().strip('"')
    except OSError:
        pass
    return None


def _ntfy(server: str, topic: str, title: str, body: str, severity: str, click: str | None) -> str:
    headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Priority": NTFY_PRIORITY.get(severity, "3"),
               "Tags": NTFY_TAGS.get(severity, "bell")}
    if click:
        headers["Click"] = click
    try:
        req = urllib.request.Request(f"{server.rstrip('/')}/{topic}", data=body.encode("utf-8"), headers=headers,
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310
            return f"ok ({r.status})"
    except Exception as e:  # noqa: BLE001
        return f"failed: {type(e).__name__}: {str(e)[:120]}"


# Windows PowerShell 5.1 (not pwsh) carries the WinRT projection. The XML travels in an environment variable so
# no quoting of household text can break the command line.
_PS_TOAST = (
    "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
    "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
    "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:FOCOS_TOAST_XML);"
    "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
    "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($t)"
)


def toast_xml(title: str, body: str, launch: str | None = None) -> str:
    launch_attr = f' activationType="protocol" launch="{escape(launch)}"' if launch else ""
    return (f"<toast{launch_attr}><visual><binding template=\"ToastGeneric\"><text>{escape(title)}</text>"
            f"<text>{escape(body[:400])}</text></binding></visual></toast>")


def _toast(title: str, body: str) -> str:
    try:
        if sys.platform == "win32":
            port = (settings.focos().get("dashboard") or {}).get("port") or 3100
            env = {**os.environ, "FOCOS_TOAST_XML": toast_xml(title, body, f"http://localhost:{port}/")}
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command",
                                _PS_TOAST], env=env, capture_output=True, text=True, timeout=20,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "ok" if r.returncode == 0 else f"failed: {(r.stderr or r.stdout).strip()[:160]}"
        if sys.platform == "darwin":
            script = f"display notification {json.dumps(body[:400])} with title {json.dumps(title)}"
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
            return "ok" if r.returncode == 0 else f"failed: {r.stderr.strip()[:160]}"
        r = subprocess.run(["notify-send", title, body[:400]], capture_output=True, text=True, timeout=20)
        return "ok" if r.returncode == 0 else f"failed: {r.stderr.strip()[:160]}"
    except Exception as e:  # noqa: BLE001
        return f"failed: {type(e).__name__}: {str(e)[:120]}"


# ---------------------------------------------------------------- standing issues
def sync_issues(alerts: list[dict], today: str | None = None, push: bool = True) -> dict:
    """Track warn/critical alerts across runs: when each first appeared, and push the ones that matter when they
    first appear and again weekly while they stand. Returns {code: {first_seen, last_seen, days_open, ...}} so the
    brief and the dashboard can say how long something has been waiting."""
    today = today or _date.today().isoformat()
    state = settings.read_json(issues_file(), {}) or {}
    seen_now = {}
    for a in alerts:
        if a.get("severity") not in ("warn", "critical"):
            continue
        code = str(a.get("code") or "alert")
        key = code if code not in ("sandbox_stop_breached",) else f"{code}:{(a.get('data') or {}).get('symbol', '')}"
        prev = state.get(key) or {}
        entry = {"code": code, "text": a.get("text"), "severity": a.get("severity"),
                 "first_seen": prev.get("first_seen") or today, "last_seen": today,
                 "notified_on": prev.get("notified_on")}
        entry["days_open"] = (_date.fromisoformat(today) - _date.fromisoformat(entry["first_seen"])).days
        try:
            from . import needs_you

            handled = needs_you.is_hidden(key, str(a.get("severity")), today)
        except Exception:  # noqa: BLE001
            handled = False
        due = code in PUSH_CODES and not handled and (not entry["notified_on"] or (
            _date.fromisoformat(today) - _date.fromisoformat(entry["notified_on"]) >= timedelta(days=REMIND_AFTER_DAYS)))
        if push and due:
            suffix = f" (open {entry['days_open']} days)" if entry["days_open"] else ""
            send(f"focos: {_title_for(code)}", f"{a.get('text')}{suffix}", str(a.get("severity")), key=f"issue:{key}:{today}")
            entry["notified_on"] = today
        seen_now[key] = entry
    settings.write_json(issues_file(), seen_now)
    return seen_now


def _title_for(code: str) -> str:
    return {
        "sandbox_stop_breached": "stop breached", "sandbox_exit_failed": "exit did not go through",
        "sandbox_halted": "sandbox halted", "robinhood_login_expired": "Robinhood login needed",
        "robinhood_not_connected": "Robinhood not connected", "claude_login_expiring": "Claude login expiring",
        "credentials_missing": "Claude login missing", "feed_auth": "bank feed needs you",
        "run_failed": "a run failed", "drawdown": "portfolio drawdown", "app_issue": "app issue",
    }.get(code, code.replace("_", " "))
