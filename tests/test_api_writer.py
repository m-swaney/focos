"""API-mode brief writer with a fake provider: report, decisions, proposals, brief_result, budget flag."""
import json
from pathlib import Path

import yaml

from focos import paths, settings
from focos.brief import context, outputs
from focos.brief.api_writer import APIBriefWriter, split_brief
from focos.llm.base import Completion, LLMError, Message, Usage, structured_via_text

BRIEF = """## Headline
Total value not available; cash is fine.

## What changed
Nothing new.

## Actions for Ann
- **Fund the emergency fund** because months_covered is low.

## Needs your input
Nothing new.

```json
{"summary_line": "Quiet day", "alerts": [{"severity": "info", "text": "hi"}], "needs_user": ["birth year"],
 "decisions": [{"kind": "recommendation", "text": "Fund the emergency fund", "evidence": "plan", "review_on": "2026-04-01"}],
 "proposal_specs": [{"symbol": "vti", "side": "buy", "dollar_amount": 100, "thesis": "broad", "entry_reason": "x", "stop_loss": null, "exit_plan": "hold", "horizon_days": 30}]}
```"""


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, system, messages, *, max_tokens, tools=None, tool_choice=None, cache_system=True):
        self.calls.append((system, messages, max_tokens))
        text = self.replies.pop(0)
        return Completion(text=text, usage=Usage(input_tokens=1000, output_tokens=200), cost_usd=0.02, model=self.model, stop_reason="end_turn")

    def structured(self, system, messages, schema, *, max_tokens):
        return structured_via_text(self, system, messages, schema, max_tokens=max_tokens)

    def estimate_cost(self, i, o):
        return 0.0

    def test(self):
        return Completion(text="OK")


def _prep(home: Path):
    (home / "config" / "profile.yml").write_text(yaml.safe_dump({"version": 2, "owner": {"name": "Ann"}}))
    (home / "config" / "focos.yml").write_text(yaml.safe_dump({"ai": {"mode": "api", "provider": "anthropic", "budget_usd": {"daily": 0.01}}}))
    settings.reset()
    settings.write_json(paths.LATEST / "portfolio.json", {"available": False, "reason": "none"})
    settings.write_json(paths.LATEST / "alerts.json", {"alerts": [{"severity": "info", "code": "x", "text": "hello"}]})


def test_split_brief():
    md, payload = split_brief(BRIEF)
    assert md.startswith("## Headline") and md.endswith("Nothing new.")
    assert payload["summary_line"] == "Quiet day"
    assert split_brief("no fence here") == ("no fence here", None)


def test_api_writer_end_to_end(initialized_home: Path):
    _prep(initialized_home)
    fake = FakeProvider([BRIEF])
    out = APIBriefWriter(provider=fake).write("daily", "2026-03-01", "t")
    assert out.ok, out.error
    assert out.report_path == "reports/daily/2026-03-01.md"
    report = (initialized_home / "reports" / "daily" / "2026-03-01.md").read_text()
    assert report.startswith("## Headline") and "```json" not in report
    decisions = outputs.recent_decisions()
    assert len(decisions) == 1 and decisions[0]["text"] == "Fund the emergency fund" and decisions[0]["run"] == "daily"
    props = list((initialized_home / "state" / "sandbox" / "proposals").glob("*.json"))
    assert len(props) == 1
    body = json.loads(props[0].read_text())
    assert body["symbol"] == "VTI" and body["paper"] is True and body["ref_id"] == "2026-03-01-VTI-buy"
    br = settings.read_json(paths.LATEST / "brief_result.json")
    assert br["decisions_logged"] == 1 and br["proposals"] == [props[0].name] and "decisions" not in br
    assert br["_meta"]["over_budget"] is True and br["_meta"]["provider"] == "fake"
    system, messages, max_tokens = fake.calls[0]
    assert "Ann" in system and "api mode" in system and "# Data" in messages[0].content
    assert "### profile" in messages[0].content and "### alerts" in messages[0].content
    assert "Actions for Ann" in system


def test_api_writer_recovers_missing_json(initialized_home: Path):
    _prep(initialized_home)
    md_only = BRIEF.split("```json")[0]
    fake = FakeProvider([md_only, 'here you go\n```json\n{"summary_line": "ok", "alerts": [], "needs_user": []}\n```'])
    out = APIBriefWriter(provider=fake).write("daily", "2026-03-01", "t")
    assert out.ok, out.error
    assert len(fake.calls) == 2 and out.cost_usd == 0.04


def test_api_writer_reports_provider_error(initialized_home: Path):
    _prep(initialized_home)

    class Boom(FakeProvider):
        def complete(self, *a, **k):
            raise LLMError("rejected the API key")

    out = APIBriefWriter(provider=Boom([])).write("daily", "2026-03-01", "t")
    assert not out.ok and "API key" in out.error


def test_context_fit_drops_low_priority_first(initialized_home: Path):
    _prep(initialized_home)
    settings.write_json(paths.LATEST / "catalysts.json", {"date": "x", "earnings": [], "news": [{"title": "n" * 4000, "body": "b" * 9000}] * 5})
    b = context.build("weekly", "2026-03-01")
    names = [s.name for s in b.sections]
    assert {"profile", "goals", "alerts", "portfolio", "risk", "tax_lots", "drift"} <= set(names)
    cat = next(s for s in b.sections if s.name == "catalysts")
    assert all("body" not in n for n in cat.data["news"])
    before = b.tokens()
    fitted = context.fit(b, max_input_tokens=max(50, before // 2))
    assert fitted.tokens() < before and fitted.dropped
    assert fitted.dropped[0] in ("optimizer", "sandbox_rules")
    assert {"profile", "alerts", "portfolio"} <= {s.name for s in fitted.sections}


def test_structured_via_text_retries_once():
    good = '```json\n{"a": 1}\n```'
    fake = FakeProvider(["not json", good])
    data, comp = structured_via_text(fake, "s", [Message(role="user", content="u")], {"type": "object", "required": ["a"]}, max_tokens=100)
    assert data == {"a": 1} and len(fake.calls) == 2
    assert "did not validate" in fake.calls[1][1][-1].content
