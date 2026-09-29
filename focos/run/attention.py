"""Alerts for the things that were piling up unseen in 0.3.6: a breached stop still held, a bank feed that needs a
login, decisions nobody has answered, problems in focos itself. Deterministic, built in Stage B, and fed to the
issue tracker (notify.sync_issues) so each carries how long it has been open and the important ones are pushed.
"""
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta

from ..brief import outputs


def _a(sev: str, code: str, text: str, **data) -> dict:
    return {"severity": sev, "code": code, "text": text, **({"data": data} if data else {})}


def sandbox_alerts(snapshot: dict | None, today: str) -> list[dict]:
    from ..sandbox import exits
    from ..sandbox import state as sb_state

    if sb_state.load_mode().get("mode") != "live":
        return []
    plan = exits.build(exits.view_from_snapshot(snapshot), today=today, write_proposals=False, persist=False)
    out = []
    for e in plan.get("required_exits") or []:
        out.append(_a("critical", "sandbox_stop_breached",
                      f"Sandbox {e['symbol']} is below its stop ({e['reason']}); the next trading pass sells it",
                      symbol=e["symbol"]))
    unmanaged = plan.get("unmanaged") or []
    if unmanaged:
        out.append(_a("warn", "sandbox_unmanaged", f"Sandbox holds {', '.join(unmanaged)} with no opening proposal, "
                      "so no stop protects it", symbols=unmanaged))
    return out


def feed_alerts(consolidated: dict | None) -> list[dict]:
    pull = (consolidated or {}).get("pull") or {}
    out = []
    for err in pull.get("errors") or []:
        text = str(err)
        if any(k in text.lower() for k in ("auth", "attention", "reconnect", "credential")):
            name = text.split("Connection to ", 1)[-1].split(" may", 1)[0] if "Connection to " in text else "a bank"
            out.append(_a("warn", "feed_auth", f"{name} needs you to sign in again in SimpleFIN Bridge "
                          f"(https://bridge.simplefin.org); until then its balances are stale", feed=name))
    return out


def decision_alerts(today: str, min_days: int = 7) -> list[dict]:
    rows = outputs.all_decisions()
    status = outputs.decision_status(rows)
    t = _date.fromisoformat(today)
    waiting = []
    for r in rows:
        if r.get("kind") != "recommendation" or not r.get("id"):
            continue
        if status.get(str(r["id"]), "open") != "open":
            continue
        try:
            age = (t - _date.fromisoformat(str(r.get("date"))[:10])).days
        except ValueError:
            continue
        if age >= min_days:
            waiting.append((age, r))
    if not waiting:
        return []
    waiting.sort(key=lambda x: -x[0])
    ids = ", ".join(f"{r['id']} ({age}d)" for age, r in waiting[:6])
    return [_a("info", "decisions_waiting", f"{len(waiting)} recommendation(s) waiting on you for a week or more: {ids}. "
               "Mark them done, standing, or retired on the Plan page", ids=[r["id"] for _, r in waiting])]


def app_issue_alerts(today: str, days: int = 7) -> list[dict]:
    cutoff = (_date.fromisoformat(today) - timedelta(days=days)).isoformat()
    issues = [r for r in outputs.all_decisions() if r.get("kind") == "app_issue" and str(r.get("date", "")) >= cutoff]
    if not issues:
        return []
    latest = issues[-1]
    return [_a("warn", "app_issue", f"focos logged {len(issues)} app issue(s) this week; latest: {str(latest.get('text'))[:200]}",
               n=len(issues))]


def build(snapshot: dict | None, consolidated: dict | None, today: str) -> list[dict]:
    out: list[dict] = []
    for fn in (lambda: sandbox_alerts(snapshot, today), lambda: feed_alerts(consolidated),
               lambda: decision_alerts(today), lambda: app_issue_alerts(today)):
        try:
            out += fn()
        except Exception as e:  # noqa: BLE001 -- an alert builder must never fail the pipeline
            out.append(_a("info", "attention_error", f"an attention check failed: {type(e).__name__}: {str(e)[:120]}"))
    return out
