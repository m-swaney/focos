"""The Needs you list: only what needs a person, one source per fact, and a way out for every item."""
import json
from pathlib import Path

from focos import needs_you, notify, paths, settings
from focos.sandbox import journal
from focos.sandbox import state as sb_state


def _alerts(alerts, issues=None):
    paths.LATEST.mkdir(parents=True, exist_ok=True)
    (paths.LATEST / "alerts.json").write_text(json.dumps({"date": "2026-09-30", "alerts": alerts, "issues": issues or {}}),
                                               encoding="utf-8")


def _decisions(rows):
    paths.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    paths.DECISIONS.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_only_actionable_alerts_are_tasks(initialized_home: Path):
    _alerts([
        {"severity": "warn", "code": "feed_auth", "text": "Example Bank needs you to sign in again"},
        {"severity": "warn", "code": "concentration", "text": "ABC is 31% of the taxable account"},
        {"severity": "info", "code": "emergency_fund", "text": "Personal cash covers 0.5 months"},
        {"severity": "info", "code": "decisions_waiting", "text": "2 recommendation(s) waiting on you"},
    ], issues={"feed_auth": {"first_seen": "2026-09-14", "days_open": 16}})
    doc = needs_you.build("2026-09-30")
    assert [i["source"] for i in doc["items"]] == ["feed_auth"]
    assert doc["items"][0]["days_open"] == 16 and doc["items"][0]["how"]
    assert {i["source"] for i in doc["watching"]} == {"concentration", "emergency_fund"}


def test_open_decisions_are_listed_and_resolved_ones_are_not(initialized_home: Path):
    _alerts([])
    _decisions([
        {"id": "decision_6", "date": "2026-09-13", "kind": "recommendation", "text": "Choose a solo 401(k) or SEP IRA."},
        {"id": "decision_4", "date": "2026-09-13", "kind": "recommendation", "text": "Redirect DCA."},
        {"date": "2026-09-20", "kind": "resolution", "ref": "decision_4", "status": "standing"},
    ])
    items = needs_you.build("2026-09-30")["items"]
    assert [i["decision_id"] for i in items] == ["decision_6"]
    assert items[0]["kind"] == "decide" and items[0]["severity"] == "warn"   # waiting more than two weeks
    from focos.updates import apply as upd

    upd.apply([{"target": "decision", "op": "resolve", "id": "decision_6", "set": {"status": "acted"}}], actor="user", run="t")
    assert json.loads(needs_you.out_file().read_text(encoding="utf-8"))["items"] == []


def test_old_or_placed_proposals_never_ask_for_approval(initialized_home: Path):
    _alerts([])
    sb_state.save_mode({"mode": "live", "run_count": 20, "live_orders": 0})
    rules = paths.CONFIG / "sandbox_rules.yml"
    rules.write_text(rules.read_text(encoding="utf-8") + "\nrequire_approval_first_n: 5\n", encoding="utf-8")
    settings.reset()
    paths.PROPOSALS.mkdir(parents=True, exist_ok=True)
    for name, p in {"old": {"ref_id": "old", "date": "2026-09-21", "symbol": "AAA", "side": "buy"},
                    "placed": {"ref_id": "placed", "date": "2026-09-30", "symbol": "BBB", "side": "buy"},
                    "fresh": {"ref_id": "fresh", "date": "2026-09-30", "symbol": "CCC", "side": "buy", "dollar_amount": 200}}.items():
        (paths.PROPOSALS / f"{name}.json").write_text(json.dumps({**p, "paper": False}), encoding="utf-8")
    journal.orders_file().write_text(json.dumps({"ts": "2026-09-30T10:31:00-04:00", "ok": True,
                                                 "order": {"symbol": "BBB", "side": "buy", "ref_id": "placed"}}) + "\n",
                                     encoding="utf-8")
    items = needs_you.build("2026-09-30")["items"]
    assert [i["ref_id"] for i in items if i["kind"] == "approve"] == ["fresh"]
    # with approvals switched off (the aggressive sandbox), nothing asks at all
    rules.write_text(rules.read_text(encoding="utf-8") + "\nrequire_approval_first_n: 0\n", encoding="utf-8")
    settings.reset()
    assert not [i for i in needs_you.build("2026-09-30")["items"] if i["kind"] == "approve"]


def test_handled_stays_gone_until_it_gets_worse_and_snooze_expires(initialized_home: Path):
    _alerts([{"severity": "warn", "code": "feed_auth", "text": "Example Bank needs you"}])
    needs_you.act("alert:feed_auth", "dismiss", today="2026-09-30")
    assert needs_you.build("2026-10-05")["items"] == []
    assert needs_you.build("2026-10-05")["counts"]["handled"] == 1
    _alerts([{"severity": "critical", "code": "feed_auth", "text": "Example Bank has been down a month"}])
    assert [i["id"] for i in needs_you.build("2026-10-30")["items"]] == ["alert:feed_auth"]

    needs_you.start_fresh("2026-09-30")
    _alerts([{"severity": "warn", "code": "feed_auth", "text": "Example Bank needs you"}])
    needs_you.act("alert:feed_auth", "snooze", days=7, today="2026-09-30")
    assert needs_you.build("2026-10-06")["items"] == []
    assert needs_you.build("2026-10-07")["items"]


def test_handled_issues_stop_pushing(initialized_home: Path, _no_real_notifications):
    alert = {"severity": "warn", "code": "feed_auth", "text": "Example Bank needs you"}
    _alerts([alert])
    needs_you.act("alert:feed_auth", "dismiss", today="2026-09-14")
    notify.sync_issues([alert], "2026-09-14")
    notify.sync_issues([alert], "2026-09-28")
    assert _no_real_notifications == []


def test_policy_reserve_turns_the_emergency_fund_into_a_fact(initialized_home: Path):
    from focos.run import alerts

    profile = {"cash_policy": {"emergency_fund_months": 3}}
    cons = {"available": True, "personal_runway_months": 0.5}
    plan = {"emergency_fund": {"business_cash_is_reserve": True, "months_covered_incl_business": 5.4}}
    snap = {"date": "2026-09-30", "accounts": []}
    got = [a for a in alerts.build(snap, {}, profile, {}, [], consolidated=cons, plan=plan) if a["code"] == "emergency_fund"]
    assert got[0]["severity"] == "info" and "reserve" in got[0]["text"]
    plan["emergency_fund"]["months_covered_incl_business"] = 2.0
    got = [a for a in alerts.build(snap, {}, profile, {}, [], consolidated=cons, plan=plan) if a["code"] == "emergency_fund"]
    assert got[0]["severity"] == "warn"
