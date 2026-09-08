"""The categorizer: seeds first, one model batch for the rest, confidence gate, once-a-day gate, provider choice."""
import json
from pathlib import Path

import yaml

from focos import paths, settings
from focos.ledger import categorize
from focos.ledger.providers.base import LedgerAccount
from focos.ledger.providers.sqlite_store import SQLiteStore
from focos.llm.base import Completion, LLMError, Message, structured_via_text


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, labels, fail=False):
        self.labels, self.fail, self.calls = labels, fail, []

    def complete(self, system, messages, *, max_tokens, tools=None, tool_choice=None, cache_system=True):
        self.calls.append("\n".join(m.content for m in messages))
        if self.fail:
            raise LLMError("down")
        return Completion(text="```json\n" + json.dumps({"labels": self.labels}) + "\n```")

    def structured(self, system, messages, schema, *, max_tokens):
        return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)


def _store(home: Path) -> SQLiteStore:
    store = SQLiteStore(home / "state" / "ledger.sqlite")
    store.upsert_account(LedgerAccount(id="simplefin:A", provider="simplefin", name="Checking", account_type="depository", subtype="checking"))
    store.upsert_transactions("simplefin:A", [
        {"id": "t1", "posted_date": "2026-09-01", "amount": -12.5, "description": "STARBUCKS STORE 10023"},
        {"id": "t2", "posted_date": "2026-09-02", "amount": -80.0, "description": "ALDI 77166 VERO BEACH"},
        {"id": "t3", "posted_date": "2026-09-03", "amount": -45.0, "description": "LOCAL ROASTERS"},
        {"id": "t4", "posted_date": "2026-09-03", "amount": -300.0, "description": "MYSTERY VENDOR"},
        {"id": "t5", "posted_date": "2026-09-04", "amount": -500.0, "description": "ROBINHOOD ACH"},
        {"id": "t6", "posted_date": "2026-09-04", "amount": 3000.0, "description": "PAYROLL"},
    ])
    return store


def test_seeds_then_model_then_rules(initialized_home: Path):
    store = _store(initialized_home)
    fake = FakeProvider([{"merchant_key": "LOCAL ROASTERS", "category": "dining", "confidence": 0.9},
                         {"merchant_key": "MYSTERY VENDOR", "category": "shopping", "confidence": 0.3},
                         {"merchant_key": "NOT ASKED", "category": "travel", "confidence": 0.9}])
    out = categorize.run(store, "2026-09-05", provider=fake)
    assert out["seeded"] == 2 and out["asked"] == 2 and out["labeled"] == 1 and out["low_confidence"] == 1 and out["provider"] == "fake"
    assert "ROBINHOOD" not in fake.calls[0] and "LOCAL ROASTERS" in fake.calls[0] and "MYSTERY VENDOR" in fake.calls[0]
    rules = store.merchant_rules()
    assert rules["STARBUCKS"]["category"] == "dining" and rules["STARBUCKS"]["source"] == "seed"
    assert rules["ALDI"]["category"] == "groceries"
    assert rules["LOCAL ROASTERS"] == {**rules["LOCAL ROASTERS"], "category": "dining", "source": "model"}
    assert rules["MYSTERY VENDOR"]["category"] == "uncategorized" and "NOT ASKED" not in rules
    cats = {r["id"]: r["category"] for r in store.conn.execute("SELECT id, category FROM transactions")}
    assert cats == {"t1": "dining", "t2": "groceries", "t3": "dining", "t4": "uncategorized", "t5": None, "t6": None}
    assert settings.read_json(paths.LATEST / "categorize.json")["labeled"] == 1
    changes = [json.loads(l) for l in paths.CHANGES.read_text().splitlines()]
    assert changes[-1]["target"] == "merchant_rule" and changes[-1]["actor"] == "system" and changes[-1]["after"]["n"] == 1
    # same day: no second model call
    again = categorize.run(store, "2026-09-05", provider=fake)
    assert again["skipped"] == "already labeled today" and len(fake.calls) == 1
    # next day with nothing new: no call either
    nxt = categorize.run(store, "2026-09-06", provider=fake)
    assert nxt["skipped"] == "no new merchants" and len(fake.calls) == 1
    store.close()


def test_dry_run_writes_nothing(initialized_home: Path):
    store = _store(initialized_home)
    out = categorize.run(store, "2026-09-05", provider=FakeProvider([]), dry_run=True)
    assert out["seeded"] == 2 and out["skipped"] == "dry run" and store.merchant_rules() == {}
    assert not (paths.LATEST / "categorize.json").exists()
    store.close()


def test_model_failure_is_recorded_not_raised(initialized_home: Path):
    store = _store(initialized_home)
    out = categorize.run(store, "2026-09-05", provider=FakeProvider([], fail=True))
    assert out["error"].startswith("model call failed") and out["seeded"] == 2
    assert store.get_meta(categorize.META_KEY) is None  # will try again next run
    store.close()


def test_pick_provider(initialized_home: Path, monkeypatch):
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "api", "provider": "anthropic"}}))
    settings.reset()
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p, why = categorize.pick_provider()
    assert p is None and "ANTHROPIC_API_KEY" in why
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "api", "provider": "ollama"}}))
    settings.reset()
    p, why = categorize.pick_provider()
    assert p is not None and p.name == "ollama"
    (initialized_home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "agent", "provider": "anthropic"}, "agent": {"model_keepalive": "haiku"}}))
    settings.reset()
    monkeypatch.setattr("focos.agent_runtime.claude_cli.find_claude", lambda explicit="auto": "claude")
    p, why = categorize.pick_provider()
    assert p is not None and p.name == "claude_cli" and p.model == "haiku"


def test_claude_cli_provider_shape(initialized_home: Path, monkeypatch):
    from focos.llm.claude_cli_provider import ClaudeCLIProvider, NO_TOOLS

    seen = {}

    def fake_run(prompt, args, *, log_path, cwd, claude="auto", timeout_s=0):
        seen.update(prompt=prompt, args=args)
        return {"is_error": False, "result": "```json\n{\"labels\": []}\n```", "subtype": "success"}

    monkeypatch.setattr("focos.agent_runtime.claude_cli.find_claude", lambda explicit="auto": "claude")
    monkeypatch.setattr("focos.agent_runtime.claude_cli.run", fake_run)
    p = ClaudeCLIProvider(model="haiku", budget_usd=0.2)
    data, comp = p.structured("sys", [Message(role="user", content="label these")], {"type": "object", "required": ["labels"],
                                                                                        "properties": {"labels": {"type": "array"}}}, max_tokens=100)
    assert data == {"labels": []} and comp.model == "haiku"
    a = seen["args"]
    assert a[a.index("--disallowedTools") + 1] == ",".join(NO_TOOLS) and "--strict-mcp-config" in a and a[a.index("--model") + 1] == "haiku"
    assert "label these" in seen["prompt"] and "Respond with ONLY" in seen["prompt"]
