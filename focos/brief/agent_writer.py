"""Agent mode: Claude Code reads the derived JSON itself and writes the brief with scoped file tools."""
from __future__ import annotations

from .. import paths, settings
from ..agent_runtime import claude_cli, settings_render
from ..run import claude_io
from ..sandbox import brokers
from ..sandbox import state as sandbox_state
from . import prompts
from .base import BriefOutcome, record_result, validate_result


def trade_tools_enabled() -> bool:
    agent = settings.focos().get("agent") or {}
    return bool(agent.get("sandbox_enabled")) and sandbox_state.trading_enabled()


class AgentBriefWriter:
    mode_name = "agent"

    def write(self, mode: str, date: str, run_id: str) -> BriefOutcome:
        cfg = settings.focos()
        agent = cfg.get("agent") or {}
        adapter = brokers.current()
        files = settings_render.render(adapter)
        # the system prompt carries {{OWNER}} etc.; render it into the home so the CLI reads a filled file
        rendered_system = paths.HOME_AGENT / "system.rendered.md"
        rendered_system.write_text(prompts.system_prompt() + "\n\n" + prompts.addendum("agent"), encoding="utf-8")
        model = agent.get("model_daily" if mode == "daily" else "model_heavy") or ("sonnet" if mode == "daily" else "opus")
        budget = float((agent.get("budget_usd") or {}).get(mode) or {"daily": 5, "weekly": 10, "monthly": 12}[mode])
        trade = trade_tools_enabled()
        args = claude_cli.stage_c_args(adapter, model=model, budget_usd=budget, mcp_config=files["mcp"],
                                       settings_file=files["settings"], system_prompt=rendered_system, trade_enabled=trade)
        prompt = prompts.render(mode, date, run_id)
        log = paths.LOGS / f"{date}-{mode}-C.json"
        try:
            result = claude_cli.run(prompt, args, log_path=log, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto")
        except Exception as e:  # CLI missing, timeout, unreadable output
            return BriefOutcome(ok=False, error=f"{type(e).__name__}: {str(e)[:300]}", meta={"trade_tools": trade})
        meta = {**claude_io.summarize(result), "trade_tools": trade, "model": model}
        if meta["is_error"]:
            return BriefOutcome(ok=False, error=str(result.get("result") or result.get("error") or meta.get("subtype"))[:500],
                                cost_usd=meta.get("cost_usd"), meta=meta)
        text = result.get("result") or ""
        try:
            payload = claude_io.extract_json(text)
        except Exception as e:
            (paths.LOGS / f"{date}-{mode}-C-result.txt").write_text(text, encoding="utf-8")
            return BriefOutcome(ok=False, error=f"no JSON in result: {e}", cost_usd=meta.get("cost_usd"), meta=meta)
        errors = validate_result(payload)
        if errors:
            return BriefOutcome(ok=False, error="brief_result schema: " + "; ".join(errors[:5]), result=payload,
                                cost_usd=meta.get("cost_usd"), meta=meta)
        record_result(payload, meta, date, mode)
        return BriefOutcome(ok=True, result=payload, report_path=payload.get("report_path"), cost_usd=meta.get("cost_usd"), meta=meta)
