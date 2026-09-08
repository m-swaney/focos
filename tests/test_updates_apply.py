"""The apply engine: goals, tax agenda, profile notes, spending policy, decision resolution, the changes log."""
import json
from pathlib import Path

import yaml

from focos import inbox, paths, settings
from focos.brief import outputs
from focos.updates import apply as apply_mod
from focos.updates.models import validate_update

PROFILE = """# Household profile (v2). No account numbers here.
version: 2
owner:
  name: Ann          # first name only
spending:
  monthly_core_expenses: 4000
income:
  notes: Salary is steady.
tax_agenda:
- Fix payroll over-withholding and size the refund
- Choose solo 401(k) vs SEP IRA
"""

GOALS = """# Goals the monthly review measures progress against. Order = priority.
version: 2
goals:
- id: roof
  kind: purchase
  name: New roof     # the big one
  target_amount: 12000
  params:
    funded_amount: 3000
- id: someday
  kind: custom
  name: Someday
"""


def _seed(home: Path) -> None:
    (home / "config" / "profile.yml").write_text(PROFILE, encoding="utf-8")
    (home / "config" / "goals.yml").write_text(GOALS, encoding="utf-8")
    settings.reset()


def _changes() -> list[dict]:
    return [json.loads(l) for l in paths.CHANGES.read_text().splitlines()]


def test_goal_done_preserves_comments_and_other_goals(initialized_home: Path):
    _seed(initialized_home)
    note = inbox.add("Roof is paid for.")
    recs = apply_mod.apply([{"target": "goal", "id": "roof", "set": {"status": "done"}, "reason": "owner said so",
                             "source_note_id": note["id"]}], actor="model", run="daily-x", date="2026-09-08")
    assert len(recs) == 1 and recs[0]["ok"], recs
    assert recs[0]["before"] == {"status": None} and recs[0]["after"] == {"status": "done", "completed_on": "2026-09-08"}
    text = (initialized_home / "config" / "goals.yml").read_text(encoding="utf-8")
    assert "# the big one" in text and "Order = priority" in text
    data = yaml.safe_load(text)
    roof, someday = data["goals"]
    assert roof["status"] == "done" and str(roof["completed_on"]) == "2026-09-08" and roof["params"]["funded_amount"] == 3000
    assert "status" not in someday and someday["name"] == "Someday"
    assert inbox.get(note["id"])["status"] == "applied"
    log = _changes()
    assert log[0]["actor"] == "model" and log[0]["target"] == "goal" and log[0]["id"] == "roof" and log[0]["source_note_id"] == note["id"]
    assert apply_mod.describe(log[0]) == "goal roof: status = done, completed_on = 2026-09-08"
    # reopening clears the completion date
    apply_mod.apply([{"target": "goal", "id": "roof", "set": {"status": "active"}}], actor="user", run="cli")
    roof = yaml.safe_load((initialized_home / "config" / "goals.yml").read_text())["goals"][0]
    assert roof["status"] == "active" and roof["completed_on"] is None


def test_plan_json_follows_edits(initialized_home: Path):
    _seed(initialized_home)
    settings.write_json(paths.LATEST / "plan.json", {"available": True, "tax_agenda": ["Fix payroll over-withholding and size the refund"],
                                                    "goals": [{"id": "roof", "name": "New roof", "status": "active"}, {"id": "someday", "name": "Someday"}],
                                                    "goals_summary": {"active": 2, "done": 0, "paused": 0}})
    apply_mod.apply([{"target": "goal", "id": "roof", "set": {"status": "done"}},
                     {"target": "tax_agenda", "id": "fix_payroll_over_withholding_and_size_the_refund", "set": {"status": "done"}}],
                    actor="user", run="cli", date="2026-09-08")
    plan = settings.read_json(paths.LATEST / "plan.json")
    assert plan["goals"][0]["status"] == "done" and plan["goals"][0]["completed_on"] == "2026-09-08" and plan["goals"][1]["status"] == "active"
    assert plan["goals_summary"] == {"active": 1, "done": 1, "paused": 0}
    assert plan["tax_agenda"][0]["status"] == "done" and plan["tax_agenda"][1]["status"] == "open" and plan["tax_agenda"][1]["id"]


def test_goal_fields_and_unknown_id(initialized_home: Path):
    _seed(initialized_home)
    recs = apply_mod.apply([{"target": "goal", "id": "someday", "set": {"target_amount": 5000, "deadline": "2027-01-01", "funded_amount": 100}},
                            {"target": "goal", "id": "nope", "set": {"status": "done"}},
                            {"target": "goal", "id": "roof", "set": {"budget": 1}}], actor="user", run="cli")
    assert [r["ok"] for r in recs] == [True, False, False]
    assert "unknown goal id" in recs[1]["error"] and "invalid update" in recs[2]["error"]
    g = yaml.safe_load((initialized_home / "config" / "goals.yml").read_text())["goals"][1]
    assert g["target_amount"] == 5000 and str(g["deadline"]) == "2027-01-01" and g["params"]["funded_amount"] == 100
    assert len(_changes()) == 3  # rejected updates are logged too


def test_tax_agenda_string_list_is_coerced_and_marked_done(initialized_home: Path):
    _seed(initialized_home)
    items = settings.profile_v2()["tax_agenda"]
    assert items[0]["id"] == "fix_payroll_over_withholding_and_size_the_refund" and items[0]["status"] == "open"
    recs = apply_mod.apply([{"target": "tax_agenda", "id": items[0]["id"], "set": {"status": "done", "notes": "fixed in September"}}],
                           actor="user", run="cli", date="2026-09-08")
    assert recs[0]["ok"], recs
    text = (initialized_home / "config" / "profile.yml").read_text(encoding="utf-8")
    assert "# first name only" in text
    ta = yaml.safe_load(text)["tax_agenda"]
    assert ta[0]["status"] == "done" and str(ta[0]["done_on"]) == "2026-09-08" and ta[0]["notes"] == "fixed in September"
    assert ta[1] == {"id": "choose_solo_401_k_vs_sep_ira", "text": "Choose solo 401(k) vs SEP IRA", "status": "open"}
    add = apply_mod.apply([{"target": "tax_agenda", "op": "add", "text": "Ask about the home office deduction"}], actor="model", run="r")
    assert add[0]["ok"] and add[0]["id"] == "ask_about_the_home_office_deduction"
    ta = yaml.safe_load((initialized_home / "config" / "profile.yml").read_text())["tax_agenda"]
    assert len(ta) == 3 and ta[2]["status"] == "open" and ta[2]["added_on"]
    # the v2 view now hands consumers items, and open/done filter correctly
    view = settings.profile_v2()["tax_agenda"]
    assert [i["status"] for i in view] == ["done", "open", "open"]


def test_profile_note_append(initialized_home: Path):
    _seed(initialized_home)
    recs = apply_mod.apply([{"target": "profile", "op": "append", "path": "income.notes", "text": "Withholding fixed."}],
                           actor="model", run="r", date="2026-09-08")
    assert recs[0]["ok"] and recs[0]["id"] == "income.notes"
    notes = yaml.safe_load((initialized_home / "config" / "profile.yml").read_text())["income"]["notes"]
    assert notes == "Salary is steady.\n[2026-09-08] Withholding fixed."
    bad = apply_mod.apply([{"target": "profile", "op": "append", "path": "owner.name", "text": "x"}], actor="model", run="r")
    assert not bad[0]["ok"]


def test_spending_policy(initialized_home: Path):
    _seed(initialized_home)
    upd = {"target": "spending", "set": {"monthly_core_expenses": 4600}}
    no_note = apply_mod.apply([upd], actor="model", run="r")
    assert not no_note[0]["ok"] and "owner" in no_note[0]["error"]
    with_note = apply_mod.apply([{**upd, "source_note_id": "n_abc"}], actor="model", run="r")
    assert with_note[0]["ok"] and with_note[0]["before"] == {"monthly_core_expenses": 4000}
    system = apply_mod.apply([{"target": "spending", "set": {"monthly_discretionary": 900}}], actor="system", run="pipeline")
    assert system[0]["ok"]
    sp = yaml.safe_load((initialized_home / "config" / "profile.yml").read_text())["spending"]
    assert sp["monthly_core_expenses"] == 4600 and sp["monthly_discretionary"] == 900
    assert sp["monthly_core_source"] == "observed" and str(sp["observed_asof"])  # the system set it last
    apply_mod.apply([{"target": "spending", "set": {"monthly_core_expenses": 4700}}], actor="user", run="cli")
    assert yaml.safe_load((initialized_home / "config" / "profile.yml").read_text())["spending"]["monthly_core_source"] == "user"


def test_decision_resolution_appends_only(initialized_home: Path):
    _seed(initialized_home)
    outputs.append_decisions([{"kind": "recommendation", "text": "Fund the emergency fund", "evidence": "plan"}], "2026-09-01", "daily")
    paths.DECISIONS.open("a", encoding="utf-8").write('{"date":"2026-09-02","run":"manual","kind":"resolution","text":"legacy hand-written line"}\n')
    rows = outputs.recent_decisions()
    dec = rows[0]
    assert dec["id"] == outputs.decision_id("2026-09-01", "Fund the emergency fund") and dec["status"] == "open"
    recs = apply_mod.apply([{"target": "decision", "id": dec["id"], "set": {"status": "acted", "note": "funded it"}}],
                           actor="user", run="cli", date="2026-09-08")
    assert recs[0]["ok"] and recs[0]["before"] == {"status": "open"} and recs[0]["after"]["status"] == "acted"
    lines = paths.DECISIONS.read_text().splitlines()
    assert len(lines) == 3 and json.loads(lines[0])["text"] == "Fund the emergency fund"  # earlier lines untouched
    last = json.loads(lines[-1])
    assert last["kind"] == "resolution" and last["ref"] == dec["id"] and last["status"] == "acted" and last["by"] == "user"
    assert outputs.recent_decisions()[0]["status"] == "acted"
    assert not apply_mod.apply([{"target": "decision", "id": "deadbeef", "set": {"status": "acted"}}], actor="user", run="cli")[0]["ok"]


def test_legacy_decision_lines_get_stable_ids(initialized_home: Path):
    paths.DECISIONS.parent.mkdir(parents=True, exist_ok=True)
    paths.DECISIONS.write_text('{"date":"2026-09-02","run":"daily","kind":"recommendation","text":"Confirm NVDA weight","evidence":"x","review_on":null}\n')
    a, b = outputs.recent_decisions()[0], outputs.all_decisions()[0]
    assert a["id"] == b["id"] == outputs.decision_id("2026-09-02", "Confirm NVDA weight")


def test_validate_update_messages():
    m, err = validate_update({"target": "goal", "id": "x", "set": {"status": "finished"}})
    assert m is None and "status" in err
    m, err = validate_update({"target": "unicorn"})
    assert m is None and err
    m, err = validate_update({"target": "tax_agenda", "op": "add", "text": "hi"})
    assert m is not None and err is None


def test_recent_changes_and_replies(initialized_home: Path):
    _seed(initialized_home)
    q = inbox.add("Should I pay the HELOC faster?", about={"type": "question"})
    assert apply_mod.apply_replies([{"note_id": q["id"], "reply": "Yes, it is your highest-rate debt."}, {"note_id": "n_missing", "reply": "x"}], "r") == 1
    assert inbox.get(q["id"])["status"] == "answered"
    apply_mod.apply([{"target": "goal", "id": "roof", "set": {"status": "paused"}}], actor="user", run="cli")
    rc = apply_mod.recent_changes(5, days=14)
    assert len(rc) == 1 and rc[0]["summary"].startswith("goal roof: status")
    assert apply_mod.recent_changes(5, days=0) == [] or all(r["date"] >= rc[0]["date"] for r in apply_mod.recent_changes(5, days=0))
