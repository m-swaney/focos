"""Stage C: turning derived JSON into a written brief, either through the Claude Code CLI with file tools
(agent mode) or through a plain LLM API with the context inlined (api mode)."""
from __future__ import annotations

from .base import BriefOutcome, BriefWriter  # noqa: F401


def writer_for(ai_cfg: dict | None = None) -> BriefWriter:
    from .. import settings

    ai = ai_cfg if ai_cfg is not None else (settings.focos().get("ai") or {})
    if ai.get("mode") == "agent":
        from .agent_writer import AgentBriefWriter
        return AgentBriefWriter()
    from .api_writer import APIBriefWriter
    return APIBriefWriter()
