"""Local API with a temp home: auth, setup status, AI configure, ledger assign + rule seeding, holdings manual,
interview with a fake provider, config get/put, run start/poll, doctor."""
import json
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from focos import paths, settings
from focos.api.app import create_app
from focos.llm.base import Completion, Usage

TOKEN = "t0k3n"


@pytest.fixture
def client(initialized_home: Path, monkeypatch):
    monkeypatch.setenv("FOCOS_DASH_TOKEN", TOKEN)
    app = create_app(token=TOKEN)
    c = TestClient(app)
    c.headers.update({"x-focos-token": TOKEN})
    return c


def test_inbox_updates_and_changes_routes(client, initialized_home: Path):
    (initialized_home / "config" / "goals.yml").write_text(yaml.safe_dump({"version": 2, "goals": [{"id": "roof", "kind": "custom", "name": "Roof"}]}))
    settings.reset()
    r = client.post("/inbox", json={"text": "Roof is done.", "about": {"type": "goal", "id": "roof"}}).json()
    assert r["ok"] and r["note"]["status"] == "pending"
    assert client.post("/inbox", json={"text": "  "}).json()["ok"] is False
    lst = client.get("/inbox").json()
    assert len(lst["pending"]) == 1 and lst["unaddressed"] == []
    u = client.post("/updates", json={"updates": [{"target": "goal", "id": "roof", "set": {"status": "done"}}]}).json()
    assert u["ok"] and u["changes"][0]["actor"] == "user" and u["changes"][0]["summary"].startswith("goal roof: status = done")
    assert yaml.safe_load((initialized_home / "config" / "goals.yml").read_text())["goals"][0]["status"] == "done"
    bad = client.post("/updates", json={"updates": [{"target": "goal", "id": "nope", "set": {"status": "done"}}]}).json()
    assert not bad["ok"] and "unknown goal" in bad["changes"][0]["error"]
    ch = client.get("/changes").json()["changes"]
    assert len(ch) == 2 and ch[0]["ok"] is False and ch[1]["ok"] is True  # newest first
    d = client.post(f"/inbox/{r['note']['id']}/dismiss").json()
    assert d["ok"] and d["note"]["status"] == "dismissed"
    assert client.post("/inbox/n_nothing/dismiss").json()["ok"] is False


def test_ledger_category_routes(client, initialized_home: Path):
    from focos.ledger.providers.sqlite_store import SQLiteStore
    from focos.ledger.providers.base import LedgerAccount

    assert client.get("/ledger/merchants").json() == {"merchants": []}  # no ledger yet
    cats = client.get("/ledger/categories").json()
    assert "groceries" in cats["categories"] and "dining" in cats["discretionary"] and cats["counts"] == {}
    store = SQLiteStore(paths.LEDGER_DB)
    store.upsert_account(LedgerAccount(id="simplefin:A", provider="simplefin", name="Checking", account_type="depository", subtype="checking"))
    store.upsert_transactions("simplefin:A", [{"id": "t1", "posted_date": "2026-09-01", "amount": -50, "description": "SOME LOCAL PLACE 12", "payee": None},
                                              {"id": "t2", "posted_date": "2026-09-02", "amount": -30, "description": "SOME LOCAL PLACE 12", "payee": None}])
    store.close()
    import focos.api.routes.ledger as lr
    monkeypatch_today = lr._date.today().isoformat()
    rows = client.get("/ledger/merchants", params={"days": 3650}).json()["merchants"]
    assert rows and rows[0]["merchant_key"] == "SOME LOCAL PLACE" and rows[0]["n"] == 2, (rows, monkeypatch_today)
    bad = client.post("/ledger/categories/rule", json={"merchant_key": "SOME LOCAL PLACE", "category": "snacks"}).json()
    assert not bad["ok"] and "unknown category" in bad["error"]
    ok = client.post("/ledger/categories/rule", json={"merchant_key": "some local place", "category": "dining"}).json()
    assert ok["ok"] and ok["change"]["after"] == {"category": "dining", "transactions": 2} and ok["change"]["actor"] == "user"
    assert client.get("/ledger/merchants", params={"days": 3650}).json()["merchants"] == []
    counts = client.get("/ledger/categories", params={"days": 3650}).json()["counts"]
    assert counts["dining"] == {"n": 2, "spend": 80.0}
    ch = client.get("/changes").json()["changes"][0]
    assert ch["target"] == "merchant_rule" and ch["id"] == "SOME LOCAL PLACE"


def test_auth_required(initialized_home: Path):
    c = TestClient(create_app(token=TOKEN))
    assert c.get("/health").status_code == 200
    assert c.get("/setup/status").status_code == 401
    assert c.get("/setup/status", headers={"x-focos-token": "nope"}).status_code == 401
    assert c.get("/setup/status", headers={"x-focos-token": TOKEN}).status_code == 200


def test_setup_status_and_label(client):
    r = client.get("/setup/status").json()
    assert r["steps"]["ai"] == "todo" and r["steps"]["profile"] == "todo" and r["config_ok"] is True
    assert client.post("/setup/label", json={"home_label": "The Smiths"}).json()["home_label"] == "The Smiths"
    assert client.post("/setup/complete").json()["ok"]
    assert client.get("/setup/status").json()["setup_completed_at"]


def test_welcome_step_tracks_the_household_name(client):
    """The rail draws a check per step key, so Welcome needs one or it can never look done."""
    assert client.get("/setup/status").json()["steps"]["welcome"] == "todo"
    client.post("/setup/label", json={"home_label": "My household"})  # the seeded placeholder does not count
    assert client.get("/setup/status").json()["steps"]["welcome"] == "todo"
    client.post("/setup/label", json={"home_label": "The Smiths"})
    assert client.get("/setup/status").json()["steps"]["welcome"] == "done"


def test_setup_complete_does_not_need_the_wizard_button(client, monkeypatch):
    """A household that configured focos by hand should not be nagged forever by the setup banner."""
    from focos.api.routes import setup as setup_routes

    assert client.get("/setup/status").json()["setup_complete"] is False
    monkeypatch.setattr(setup_routes, "step_status", lambda: {"welcome": "done", "ai": "done", "ledger": "done",
                                                              "accounts": "done", "holdings": "skipped",
                                                              "profile": "done", "schedule": "done",
                                                              "first_run": "done"})
    assert client.get("/setup/status").json()["setup_complete"] is True


def test_ai_configure_writes_env_and_config(client, initialized_home: Path):
    r = client.post("/ai/configure", json={"provider": "openai", "model": "gpt-5.6-luna", "api_key": "sk-test-1234567890abcdefghij", "mode": "api"}).json()
    assert r["ok"] and r["key_ok"] and r["ai"]["provider"] == "openai" and r["ai"]["model"] == "gpt-5.6-luna"
    env = (initialized_home / ".env").read_text()
    assert "OPENAI_API_KEY=sk-test-1234567890abcdefghij" in env and "FOCOS_DASH_TOKEN=" in env
    assert yaml.safe_load((initialized_home / "config" / "focos.yml").read_text())["ai"]["provider"] == "openai"
    assert client.get("/setup/status").json()["steps"]["ai"] == "done"
    assert client.get("/ai/models").json()["defaults"]["openai"]


def test_ledger_assign_seeds_rules(client, initialized_home: Path, monkeypatch):
    from tests.test_simplefin import _provider

    p = _provider(initialized_home)
    p.refresh(__import__("datetime").date(2026, 3, 2), force=True)
    monkeypatch.setattr("focos.ledger.providers.current", lambda name=None: p)
    monkeypatch.setattr("focos.ledger.providers.configured_name", lambda: "simplefin")
    accts = client.get("/ledger/accounts").json()
    assert accts["provider"] == "simplefin" and len(accts["accounts"]) == 3
    ids = {a["name"]: a["id"] for a in accts["accounts"]}
    body = {"entities": [{"key": "shop", "label": "Corner Shop", "kind": "business"}],
            "accounts": [{"id": ids["Everyday Checking"], "entity": "personal"},
                         {"id": ids["Rewards Visa"], "entity": "personal", "type": "credit_card"},
                         {"id": ids["Individual Brokerage"], "entity": "shop", "brokerage_key": "brk", "brokerage_label": "Shop brokerage", "brokerage_role": "taxable"}]}
    r = client.post("/ledger/assign", json=body).json()
    assert r["ok"], r
    ents = yaml.safe_load((initialized_home / "config" / "entities.yml").read_text())
    assert ents["entities"]["shop"]["kind"] == "business" and ids["Individual Brokerage"] in ents["entities"]["shop"]["account_ids"]
    assert ents["account_types"][ids["Rewards Visa"]]["type"] == "credit_card"
    acc = yaml.safe_load((initialized_home / "config" / "accounts.yml").read_text())
    assert acc["brokerage"][0]["key"] == "brk" and acc["brokerage"][0]["entity"] == "shop"
    rules = yaml.safe_load((initialized_home / "config" / "transfer_rules.yml").read_text())
    assert any(rl["classify_as"] == "investment_contribution" and rl["entity"] == "shop" for rl in rules["rules"])
    assert any(rl["classify_as"] == "debt_payment" for rl in rules["rules"])
    assert "shop" in rules["income_labels"]
    assert settings.focos()["holdings"]["source"] == "simplefin_holdings"
    assert client.get("/config/validate").json()["ok"]
    m = client.post("/ledger/manual-accounts", json=[{"key": "cabin", "name": "Lake cabin", "account_type": "property", "balance": 100000}]).json()
    assert m["ok"] and m["created"][0]["id"] == "manual:cabin"
    assert "manual:cabin" in yaml.safe_load((initialized_home / "config" / "entities.yml").read_text())["entities"]["personal"]["account_ids"]


def test_holdings_manual_and_capture(client, initialized_home: Path, monkeypatch):
    r = client.post("/holdings/manual", json={"rows": [{"account_key": "brk", "symbol": "vti", "quantity": 3, "avg_cost": 200, "price": 250}],
                                              "accounts": [{"key": "brk", "label": "Brokerage", "role": "taxable"}]}).json()
    assert r["ok"] and r["rows"] == 1
    assert (initialized_home / "data" / "holdings.csv").read_text().splitlines()[1].startswith("brk,VTI,3")
    assert settings.focos()["holdings"]["source"] == "csv"
    monkeypatch.setattr("focos.holdings.csv_source.yahoo_prices", lambda symbols: {})
    cap = client.post("/holdings/capture", json={}).json()
    assert cap["ok"] and cap["source"] == "csv" and cap["total_value"] == 750.0
    srcs = client.get("/holdings/sources").json()
    assert srcs["configured"] == "csv" and srcs["sources"]["csv"]["available"] is True and srcs["latest"]["accounts"] == 1


class FakeInterviewProvider:
    name = "fake"
    model = "fake"

    def __init__(self):
        self.n = 0

    def complete(self, system, messages, *, max_tokens, tools=None, tool_choice=None, cache_system=True):
        self.n += 1
        if self.n == 1:
            return Completion(text="Hi! What's your first name and birth year?", usage=Usage(input_tokens=10, output_tokens=5), cost_usd=0.001)
        if self.n == 2:
            return Completion(text="Got it. Where do you live?", cost_usd=0.001,
                              tool_calls=[{"name": "propose_section", "input": {"section": "owner", "data": {"name": "Ann", "birth_year": 1990}, "confidence": "high"}}])
        if self.n == 3:
            return Completion(text="", cost_usd=0.001,
                              tool_calls=[{"name": "propose_section", "input": {"section": "goals", "data": {"goals": [{"kind": "custom", "name": "Boat"}]}, "confidence": "low", "assumptions": ["no amount yet"]}}])
        return Completion(text="", cost_usd=0.001, tool_calls=[{"name": "finish", "input": {"summary": "All done."}}])

    def structured(self, *a, **k):
        raise NotImplementedError

    def estimate_cost(self, i, o):
        return 0.0

    def test(self):
        return Completion(text="OK")


def test_interview_flow(client, initialized_home: Path, monkeypatch):
    fake = FakeInterviewProvider()
    monkeypatch.setattr("focos.interview.engine.provider_for", lambda cfg=None, heavy=False: fake)
    t = client.post("/interview/start", json={}).json()
    sid = t["session_id"]
    assert "first name" in t["assistant_text"] and t["proposal"] is None and "owner" in t["remaining"]
    t = client.post("/interview/reply", json={"session_id": sid, "text": "Ann, 1990"}).json()
    assert t["proposal"]["section"] == "owner" and t["proposal"]["data"]["birth_year"] == 1990 and not t["proposal"]["errors"]
    assert "name: Ann" in t["proposal"]["yaml"]
    c = client.post("/interview/confirm", json={"session_id": sid, "section": "owner", "data": {"name": "Ann", "birth_year": 1990}}).json()
    assert c["ok"], c
    assert yaml.safe_load((initialized_home / "config" / "profile.yml").read_text())["owner"]["name"] == "Ann"
    t = client.post("/interview/reply", json={"session_id": sid, "text": "Texas"}).json()
    assert t["proposal"]["section"] == "goals" and t["proposal"]["data"][0]["name"] == "Boat" and t["proposal"]["assumptions"]
    c = client.post("/interview/confirm", json={"session_id": sid, "section": "goals", "data": t["proposal"]["data"]}).json()
    assert c["ok"] and yaml.safe_load((initialized_home / "config" / "goals.yml").read_text())["goals"][0]["id"] == "boat"
    t = client.post("/interview/reply", json={"session_id": sid, "text": "ok"}).json()
    assert t["finished"] and "owner" in t["confirmed"] and "goals" in t["confirmed"]
    assert "cost_usd" not in t and not t["over_budget"]
    bad = client.post("/interview/confirm", json={"section": "household", "data": {"timezone": "Mars/Olympus"}}).json()
    assert not bad["ok"] and "timezone" in bad["errors"][0]
    assert client.get("/setup/status").json()["steps"]["profile"] == "done"
    sch = client.get("/interview/schema").json()
    assert "goals" in sch["sections"] and sch["schemas"]["owner"]["type"] == "object" and "$ref" not in json.dumps(sch["schemas"])


def test_config_get_put(client, initialized_home: Path):
    assert client.get("/config/focos").json()["ai"]["mode"] == "api"
    r = client.put("/config/analytics", json={"benchmark": "VTI", "max_weight": 0.2}).json()
    assert r["ok"] and settings.analytics()["benchmark"] == "VTI"
    bad = client.put("/config/accounts", json={"version": 2, "brokerage": [{"key": "Bad Key", "label": "x"}]}).json()
    assert not bad["ok"] and bad["issues"]
    assert client.get("/config/nope").status_code == 404
    assert client.patch("/config/profile/spending", json={"monthly_core_expenses": 3000}).json()["ok"]
    assert settings.profile_v2()["spending"]["monthly_core_expenses"] == 3000
    assert "properties" in client.get("/config/schema/profile").json()


def test_schedule_endpoint_writes_config_without_installing(client, initialized_home: Path):
    r = client.post("/schedule/install", json={"schedule": {"daily": {"days": "daily", "time": "08:00"}}, "timezone": "America/Chicago", "install": False}).json()
    assert r["ok"] and r["schedule"]["daily"]["time"] == "08:00" and settings.timezone_name() == "America/Chicago"
    bad = client.post("/schedule/install", json={"schedule": {"daily": {"time": "25:00"}}, "install": False}).json()
    assert not bad["ok"]


def test_run_start_and_poll(client, initialized_home: Path, monkeypatch):
    from focos.orchestrator import run as orch

    def fake_run(opts):
        (paths.LOGS).mkdir(parents=True, exist_ok=True)
        log = paths.LOGS / "2026-03-01-daily-run.log"
        log.write_text("hello\nworld\n")
        return orch.RunResult(run_id="x", mode=opts.mode, date="2026-03-01", ok=True, stages={"A": "ok"}, log_file=str(log))

    monkeypatch.setattr("focos.api.routes.run.orch.run", fake_run)
    r = client.post("/run", json={"mode": "daily", "no_git": True}).json()
    rid = r["id"]
    for _ in range(50):
        g = client.get(f"/run/{rid}").json()
        if g.get("finished"):
            break
        time.sleep(0.05)
    assert g["ok"] is True and g["stages"] == {"A": "ok"} and g["log"] == ["hello", "world"]
    assert client.post("/run", json={"mode": "yearly"}).status_code == 400
    assert client.get("/run/latest").json()["runs"][-1]["id"] == rid


def test_doctor_and_diagnostics(client, initialized_home: Path):
    d = client.get("/doctor").json()["checks"]
    ids = {c["id"]: c for c in d}
    assert ids["home"]["ok"] and ids["config_valid"]["ok"] and ids["env_not_tracked"]["ok"]
    assert ids["ai_key"]["ok"] is False and "Setup" in ids["ai_key"]["fix"]
    assert ids["last_daily_run"]["ok"] is None
    (initialized_home / "config" / "profile.yml").write_text("version: 2\nowner: {name: Ann}\n")
    (initialized_home / ".env").write_text("FOCOS_DASH_TOKEN=abc\nANTHROPIC_API_KEY=sk-ant-secretsecretsecret123\n")  # private-scan: allow (fake test value)
    p = client.post("/doctor/diagnostics").json()["path"]
    import zipfile

    with zipfile.ZipFile(p) as z:
        names = z.namelist()
        assert "doctor.json" in names and "config/profile.yml" in names and not any(n.endswith(".env") for n in names)
        prof = z.read("config/profile.yml").decode()
        assert "Ann" not in prof and "[OWNER]" in prof
