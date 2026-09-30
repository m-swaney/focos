"""The one list of things that need the owner, built in code, and the way each one leaves it.

Before 0.3.8 the dashboard's "Needs you" card merged four sources that did not know about each other: every
sandbox proposal ever written (as "Approve", even with approvals switched off), the brief's questions, the
brief's own alerts, and the rule-based alerts. Nothing cleared itself and nothing could be cleared, so the
card only grew. Here the rules are:

- **Only things that need a person.** A login, a decision, an approval, a note focos could not act on. A
  number to keep an eye on is not a task; it goes to `watching`, which does not count.
- **One source per fact.** Rule-based alerts and open decisions are the record. The brief's prose restatements
  of them are not added again.
- **Everything has an exit.** Decisions resolve through the normal update path (acted / keep as is / drop).
  Other items can be marked handled or snoozed for a week; a handled item stays gone until it gets worse
  (its severity rises) or, for a snooze, until the date passes. Handling an item also stops its phone pushes.

Output: `state/derived/latest/needs_you.json`, rewritten whenever something that feeds it changes (a run, a
Done button, a note, a dismissal). State: `state/needs_you_state.json`.
"""
from __future__ import annotations

import hashlib
from datetime import date as _date
from datetime import datetime, timedelta, timezone

from . import paths, settings

FILE_NAME = "needs_you.json"
SEVERITY_RANK = {"info": 0, "warn": 1, "critical": 2}
# Alerts a person has to act on. Anything else with warn/critical severity is still shown, but as something to
# watch rather than a task, because there is nothing for the owner to do about it today.
ACTIONABLE = {
    "sandbox_stop_breached": ("Sandbox stop breached", "/sandbox",
                              "focos sells it on the next trading pass. Sell by hand in Robinhood if you want it out now."),
    "sandbox_exit_failed": ("A stop exit did not go through", "/sandbox",
                            "The next pass retries. Sell by hand in Robinhood if you want it out now."),
    "sandbox_unmanaged": ("Sandbox position with no stop", "/sandbox",
                          "Bought outside focos, so no stop protects it. Sell it or tell focos the stop in a note."),
    "sandbox_halted": ("Sandbox paused by the drawdown halt", "/sandbox",
                       "Buys are off until you run `focos sandbox resume`. Selling still works."),
    "feed_auth": ("Bank connection needs you", "/wealth",
                  "Sign in again at bridge.simplefin.org; until then that account's balance is stale."),
    "robinhood_login_expired": ("Robinhood login needed", "/health", "Run `focos auth robinhood`."),
    "robinhood_not_connected": ("Robinhood not connected", "/health", "Run `focos auth robinhood`."),
    "credentials_missing": ("Claude login missing", "/health", "Open `claude` once and sign in."),
    "claude_login_expiring": ("Claude login expiring", "/health",
                              "Open an interactive `claude` session to renew it; scheduled runs stop if it lapses."),
    "ledger_unavailable": ("Bank data unavailable", "/health", "The bank feed failed this run; see Health."),
    "unmapped_accounts": ("New accounts to assign", "/wealth", "Say which household entity each belongs to."),
    "run_failed": ("A scheduled run failed", "/health", "See Health for the error."),
}


# Alerts that summarise something this list already shows item by item.
LISTED_ELSEWHERE = {"decisions_waiting"}


def state_file():
    return paths.STATE / "needs_you_state.json"


def out_file():
    return paths.LATEST / FILE_NAME


def _today() -> str:
    return _date.today().isoformat()


def _load_state() -> dict:
    return settings.read_json(state_file(), {}) or {}


def _fp(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:10]


def _hidden(item: dict, state: dict, today: str) -> bool:
    """Handled items stay hidden until their severity rises; snoozed ones until the date passes."""
    s = state.get(item["id"])
    if not s:
        return False
    if s.get("action") == "snooze":
        return str(s.get("until") or "") > today
    if s.get("action") == "dismiss":
        return SEVERITY_RANK.get(item.get("severity", "warn"), 1) <= SEVERITY_RANK.get(s.get("severity", "warn"), 1)
    return False


def is_hidden(issue_key: str, severity: str, today: str | None = None) -> bool:
    """For the notifier: has the owner handled or snoozed this issue? Keys match `alert:<issue key>`."""
    return _hidden({"id": f"alert:{issue_key}", "severity": severity}, _load_state(), today or _today())


# ---------------------------------------------------------------- sources
def _alert_items(today: str) -> tuple[list[dict], list[dict]]:
    doc = settings.read_json(paths.LATEST / "alerts.json", {}) or {}
    issues = doc.get("issues") or {}
    do, watch = [], []
    seen = set()
    for a in doc.get("alerts") or []:
        code = str(a.get("code") or "alert")
        sym = (a.get("data") or {}).get("symbol") if isinstance(a.get("data"), dict) else None
        key = f"{code}:{sym}" if sym else code
        if key in seen or code in LISTED_ELSEWHERE:
            continue
        seen.add(key)
        issue = issues.get(key) or issues.get(code) or {}
        sev = str(a.get("severity") or "info")
        base = {"id": f"alert:{key}", "severity": sev, "source": code, "since": issue.get("first_seen"),
                "days_open": issue.get("days_open") or 0}
        if code in ACTIONABLE and sev in ("warn", "critical"):
            title, href, how = ACTIONABLE[code]
            do.append({**base, "kind": "do", "title": title, "detail": a.get("text"), "how": how, "href": href,
                       "actions": ["dismiss", "snooze"]})
        else:
            watch.append({**base, "kind": "watch", "title": a.get("text"), "detail": None, "href": None,
                          "actions": ["dismiss"]})
    return do, watch


def _decision_items(today: str) -> list[dict]:
    from .brief import outputs

    rows = outputs.all_decisions()
    status = outputs.decision_status(rows)
    out = []
    for r in rows:
        if r.get("kind") != "recommendation" or not r.get("id"):
            continue
        if status.get(str(r["id"]), "open") != "open":
            continue
        try:
            age = (_date.fromisoformat(today) - _date.fromisoformat(str(r.get("date"))[:10])).days
        except ValueError:
            age = 0
        text = str(r.get("text") or "").strip()
        title = _first_sentence(text)
        out.append({"id": f"decision:{r['id']}", "kind": "decide", "severity": "warn" if age >= 14 else "info",
                    "source": "decision", "decision_id": r["id"], "title": title, "detail": _rest(text, title),
                    "since": str(r.get("date"))[:10], "days_open": age,
                    "review_on": r.get("review_on"), "href": "/plan", "actions": ["acted", "standing", "retired"]})
    return out


def _approval_items(today: str) -> list[dict]:
    """Proposals that really wait on the owner: approval is required by the rules, the order was not placed,
    and it was written today (a setup from an earlier session is gone; approving it now would be a new trade)."""
    from .sandbox import exits
    from .sandbox import state as sb_state

    rules = settings.sandbox_rules()
    mode = sb_state.load_mode()
    if mode.get("mode") != "live" or int(mode.get("live_orders", 0)) >= int(rules.get("require_approval_first_n", 5)):
        return []
    placed = {str(o.get("ref_id")) for o in exits.accepted_orders()}
    out = []
    for p in sb_state.proposals():
        if p.get("paper") or p.get("approved") or str(p.get("ref_id")) in placed or str(p.get("date")) != today:
            continue
        out.append({"id": f"approve:{p.get('ref_id')}", "kind": "approve", "severity": "warn", "source": "sandbox",
                    "ref_id": p.get("ref_id"), "title": f"{str(p.get('side', '')).upper()} {p.get('symbol')}",
                    "detail": p.get("thesis"), "amount": p.get("dollar_amount"), "since": today, "days_open": 0,
                    "href": "/sandbox", "actions": ["approve"]})
    return out


def _note_items(today: str) -> list[dict]:
    from . import inbox

    out = []
    for n in inbox.unaddressed():
        out.append({"id": f"note:{n.get('id')}", "kind": "do", "severity": "warn", "source": "note",
                    "title": "A note of yours was not acted on", "detail": n.get("text"),
                    "how": "Rephrase it, or dismiss it if it no longer matters.", "since": str(n.get("ts", ""))[:10],
                    "days_open": 0, "href": None, "actions": ["dismiss"], "note_id": n.get("id")})
    return out


def _first_sentence(text: str, limit: int = 110) -> str:
    """The headline of a recommendation: up to the first colon, sentence end, semicolon, or parenthesis, cut at a
    word boundary."""
    cut = text
    for sep in (": ", ". ", "; ", " ("):
        head = cut.split(sep, 1)[0]
        if len(head) >= 12:
            cut = head
    cut = cut.rstrip(".")
    if len(cut) <= limit:
        return cut
    return cut[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."


def _rest(text: str, title: str) -> str | None:
    """What the detail adds beyond the headline, or None when it adds nothing."""
    head = title.removesuffix("...")
    rest = text[len(head):] if text.startswith(head) else text
    rest = rest.lstrip(" .:;,").strip()
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1]
    return rest or None


# ---------------------------------------------------------------- build, write, act
def build(today: str | None = None) -> dict:
    today = today or _today()
    state = _load_state()
    do, watch = [], []
    for fn in (_alert_items,):
        d, w = fn(today)
        do += d
        watch += w
    for fn in (_approval_items, _decision_items, _note_items):
        try:
            do += fn(today)
        except Exception:  # noqa: BLE001 -- one broken source must not blank the whole list
            continue
    order = {"approve": 0, "do": 1, "decide": 2}
    hidden = sum(1 for i in (do + watch) if _hidden(i, state, today))
    do = [i for i in do if not _hidden(i, state, today)]
    do.sort(key=lambda i: (order.get(i["kind"], 3), -SEVERITY_RANK.get(i["severity"], 0), -(i.get("days_open") or 0)))
    watch = [i for i in watch if not _hidden(i, state, today)]
    return {"asof": datetime.now(timezone.utc).isoformat(timespec="seconds"), "date": today, "items": do,
            "watching": watch, "counts": {"items": len(do), "watching": len(watch), "handled": hidden}}


def refresh(today: str | None = None) -> dict:
    doc = build(today)
    settings.write_json(out_file(), doc)
    return doc


def act(item_id: str, action: str, days: int = 7, today: str | None = None) -> dict:
    """dismiss | snooze | restore for non-decision items. Decisions go through updates.apply (see API route)."""
    today = today or _today()
    state = _load_state()
    doc = build(today)
    current = {i["id"]: i for i in doc["items"] + doc["watching"]}
    if action == "restore":
        state.pop(item_id, None)
    elif action in ("dismiss", "snooze"):
        item = current.get(item_id) or {}
        entry = {"action": action, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "severity": item.get("severity", "warn"), "title": item.get("title")}
        if action == "snooze":
            entry["until"] = (_date.fromisoformat(today) + timedelta(days=max(1, int(days)))).isoformat()
        state[item_id] = entry
        if item_id.startswith("note:"):
            from . import inbox

            try:
                inbox.dismiss(item_id.split(":", 1)[1])
            except Exception:  # noqa: BLE001
                pass
    else:
        raise ValueError(f"unknown action {action!r}")
    settings.write_json(state_file(), state)
    return refresh(today)


def start_fresh(today: str | None = None) -> dict:
    """Clear every snooze and dismissal and rebuild, for when the owner wants the list re-derived from scratch."""
    settings.write_json(state_file(), {})
    return refresh(today)
