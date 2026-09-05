"""Prompt templates under agent/prompts with placeholders filled from the data dir.

Layout: system.md (shared core) + system.agent.md / system.api.md (mode addenda); daily|weekly|monthly.md for
agent mode (the model reads files itself) and api/daily|weekly|monthly.md for api mode (data is inlined).
"""
from __future__ import annotations

from datetime import date as _date

from .. import paths, settings
from . import outputs

RESULT_CONTRACT = ("\n\nWhen finished, end your chat response (NOT the report file) with a fenced ```json block containing exactly: "
                   '{"summary_line": str, "report_path": str, "alerts": [{"severity": "info|warn|critical", "text": str}], '
                   '"needs_user": [str], "decisions_logged": int, "proposals": [str], "trades_placed": [str]}. '
                   "The report file itself must contain only the markdown brief.")
API_RESULT_CONTRACT = ("\n\nOutput format: first the complete markdown brief (H2 sections per the contract), then ONE fenced ```json "
                       "block containing exactly: "
                       '{"summary_line": str, "alerts": [{"severity": "info|warn|critical", "text": str}], "needs_user": [str], '
                       '"decisions": [{"kind": "recommendation|proposal", "text": str, "evidence": str, "review_on": "YYYY-MM-DD"}], '
                       '"proposal_specs": [{"symbol": str, "side": "buy|sell", "dollar_amount": number, "thesis": str, '
                       '"entry_reason": str, "stop_loss": number|null, "exit_plan": str, "horizon_days": int}]}. '
                       "Nothing after the JSON block.")
SNAPSHOT_SUFFIX = "\n\nReturn ONLY the JSON object. No prose, no markdown fences, no commentary before or after."


def account_names() -> str:
    return ", ".join(f"{a['key']} ({a.get('label') or a['key']}, {a.get('role')})" for a in settings.brokerage()) or "(none configured)"


def render_placeholders(text: str, *, date: str, run_id: str = "manual", prev_brief: str = "(none yet)",
                        week: str = "", run_mode: str = "daily") -> str:
    """Fill {{DATE}} {{RUN_ID}} {{PREV_BRIEF}} {{WEEK}} {{MONTH}} {{MODE}} {{OWNER}} {{ACCOUNT_NAMES}}."""
    return (text.replace("{{DATE}}", date).replace("{{RUN_ID}}", run_id).replace("{{PREV_BRIEF}}", prev_brief)
                .replace("{{WEEK}}", week).replace("{{MONTH}}", date[:7]).replace("{{MODE}}", run_mode)
                .replace("{{OWNER}}", settings.owner_name()).replace("{{ACCOUNT_NAMES}}", account_names()))


def previous_brief(run_mode: str, date: str) -> str:
    return outputs.previous_brief_path(run_mode, date) or "(none yet)"


def week_label(date: str) -> str:
    return outputs.week_label(date)


def render(template: str, date: str, run_id: str = "manual", run_mode: str | None = None, variant: str = "agent") -> str:
    """template: snapshot | daily | weekly | monthly. variant: agent (files) | api (inline data)."""
    run_mode = run_mode or (template if template != "snapshot" else "daily")
    if template == "snapshot":
        path = paths.AGENT / "prompts" / "snapshot.md"
    elif variant == "api":
        path = paths.AGENT / "prompts" / "api" / f"{template}.md"
    else:
        path = paths.AGENT / "prompts" / f"{template}.md"
    text = path.read_text(encoding="utf-8")
    text = render_placeholders(text, date=date, run_id=run_id, prev_brief=previous_brief(run_mode, date),
                               week=week_label(date), run_mode=run_mode)
    if template == "snapshot":
        return text + SNAPSHOT_SUFFIX
    return text + (API_RESULT_CONTRACT if variant == "api" else RESULT_CONTRACT)


def system_prompt() -> str:
    return render_placeholders((paths.AGENT / "prompts" / "system.md").read_text(encoding="utf-8"), date=_date.today().isoformat())


def addendum(variant: str) -> str:
    p = paths.AGENT / "prompts" / f"system.{variant}.md"
    return render_placeholders(p.read_text(encoding="utf-8"), date=_date.today().isoformat()) if p.exists() else ""
