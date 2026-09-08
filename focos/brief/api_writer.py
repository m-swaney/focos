"""API mode: assemble a context bundle from the derived JSON, call the configured LLM provider once, and write
the brief, decisions, and proposal files ourselves. Works with any provider in focos.llm."""
from __future__ import annotations

import json
import re

from .. import paths, settings
from ..llm import LLMError, Message, provider_for
from ..llm.base import structured_via_text
from ..run.claude_io import FENCE
from . import context, outputs, prompts
from .base import BriefOutcome, apply_updates, prepare_inbox, record_result, validate_result

BRIEF_SCHEMA_PATH = "schemas/brief_result.schema.json"


def split_brief(text: str) -> tuple[str, dict | None]:
    """Markdown before the final fenced JSON block, plus that block parsed (None when absent/invalid)."""
    matches = list(FENCE.finditer(text))
    if not matches:
        return text.strip(), None
    last = matches[-1]
    markdown = text[:last.start()].strip()
    try:
        return markdown, json.loads(last.group(1))
    except json.JSONDecodeError:
        return markdown, None


def _schema() -> dict:
    return json.loads((paths.AGENT / BRIEF_SCHEMA_PATH).read_text(encoding="utf-8"))


class APIBriefWriter:
    mode_name = "api"

    def __init__(self, provider=None):
        self._provider = provider

    def write(self, mode: str, date: str, run_id: str) -> BriefOutcome:
        cfg = settings.focos()
        ai = cfg.get("ai") or {}
        try:
            provider = self._provider or provider_for(ai, heavy=(mode != "daily"))
        except LLMError as e:
            return BriefOutcome(ok=False, error=str(e))
        prepare_inbox(run_id, mode)
        bundle = context.fit(context.build(mode, date), int(ai.get("max_input_tokens") or 60000))
        system = prompts.system_prompt() + "\n\n" + prompts.addendum("api")
        user = prompts.render(mode, date, run_id, variant="api") + "\n\n# Data\n\n" + bundle.render()
        max_out = int(ai.get("max_output_tokens") or 8192)
        meta = {"provider": provider.name, "model": provider.model, "context_tokens_est": bundle.tokens(), "dropped": bundle.dropped}
        try:
            comp = provider.complete(system, [Message(role="user", content=user)], max_tokens=max_out)
        except LLMError as e:
            return BriefOutcome(ok=False, error=str(e), meta=meta)
        cost = comp.cost_usd  # internal only: budget enforcement, never surfaced
        markdown, payload = split_brief(comp.text)
        if payload is None or validate_result(payload):
            # second, cheap pass: ask for just the result JSON for the brief we already have
            try:
                payload, comp2 = structured_via_text(
                    provider, system,
                    [Message(role="user", content=user), Message(role="assistant", content=comp.text),
                     Message(role="user", content="Now produce only the brief_result JSON object for the brief above.")],
                    _schema(), max_tokens=2048)
                cost = (cost or 0) + (comp2.cost_usd or 0)
            except LLMError as e:
                (paths.LOGS / f"{date}-{mode}-C-result.txt").write_text(comp.text, encoding="utf-8")
                return BriefOutcome(ok=False, error=f"no valid brief_result JSON: {e}", meta=meta)
        if not markdown or not re.search(r"^##\s+", markdown, re.M):
            return BriefOutcome(ok=False, error="model returned no markdown brief sections", meta=meta, result=payload)
        rel = outputs.write_report(mode, date, markdown)
        payload["report_path"] = rel
        n_dec = outputs.append_decisions(payload.get("decisions") or [], date, mode)
        payload["decisions_logged"] = n_dec
        files = outputs.write_proposals(payload.get("proposal_specs") or [], date)
        payload["proposals"] = files or payload.get("proposals") or []
        payload.setdefault("trades_placed", [])
        payload.pop("decisions", None)
        payload.pop("proposal_specs", None)
        apply_updates(payload, run_id=run_id, date=date)
        budget = (ai.get("budget_usd") or {}).get(mode)
        meta.update({"usage": comp.usage.model_dump(), "stop_reason": comp.stop_reason})
        if cost is not None and budget and cost > float(budget):
            meta["over_budget"] = True
        record_result(payload, meta, date, mode)
        return BriefOutcome(ok=True, result=payload, report_path=rel, meta=meta)
