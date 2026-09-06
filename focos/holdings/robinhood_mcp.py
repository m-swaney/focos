"""Robinhood via the Claude Code CLI acting as an MCP client (Stage A of the original design)."""
from __future__ import annotations

from .. import paths, settings
from ..agent_runtime import claude_cli, settings_render
from ..run import claude_io, tokens
from ..sandbox import brokers
from ..sources import robinhood_snapshot as rh
from . import write_snapshot
from .base import SourceError


class RobinhoodMCPSource:
    name = "robinhood_mcp"

    def __init__(self):
        self.last_meta: dict = {}

    def available(self) -> tuple[bool, str | None]:
        cfg = settings.focos()
        if not claude_cli.find_claude((cfg.get("agent") or {}).get("claude_cli") or "auto"):
            return False, "Claude Code CLI not found; install it and run `claude` once to log in"
        e = tokens.expiries()
        if not e.get("available"):
            return False, "Claude credentials not found; run `claude` once to log in"
        if not e.get("robinhood_has_refresh") and not e.get("robinhood_access_expires"):
            return False, "Robinhood MCP is not connected; run `claude`, then `/mcp` to authorize robinhood-trading"
        return True, None

    def capture(self, asof: str, mode: str, run_id: str) -> dict | None:
        from ..brief import prompts

        ok, why = self.available()
        if not ok:
            raise SourceError(why or "unavailable")
        cfg = settings.focos()
        agent = cfg.get("agent") or {}
        adapter = brokers.current()
        files = settings_render.render()
        prompt = prompts.render("snapshot", asof, run_id, run_mode=mode)
        args = claude_cli.stage_a_args(adapter, model=agent.get("model_snapshot") or "sonnet",
                                       budget_usd=float((agent.get("budget_usd") or {}).get("snapshot") or 3.0),
                                       mcp_config=files["mcp"])
        log = paths.LOGS / f"{asof}-{mode}-A.json"
        result = claude_cli.run(prompt, args, log_path=log, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto")
        meta = claude_io.summarize(result)
        self.last_meta = meta
        if meta["is_error"]:
            raise SourceError(str(result.get("result") or result.get("error") or meta.get("subtype") or "claude error")[:500])
        payload = claude_io.extract_json(result.get("result") or "")
        normalize_crypto_keys(payload)
        ensure_quotes(payload)
        errors = rh.validate(payload)
        if errors:
            raise SourceError("schema: " + "; ".join(errors[:5]))
        settings.write_json(paths.RAW / f"{asof}-{mode}.json", payload)  # full account numbers, gitignored
        snap = rh.normalize(payload, asof, mode)
        snap["source"] = self.name
        write_snapshot(snap)
        return snap


CRYPTO_CODE_ALIASES = ("code", "asset", "symbol", "currency", "ticker")


def ensure_quotes(payload) -> None:
    """A snapshot without quotes still has positions and portfolio totals; downstream valuation falls back to
    Yahoo closes. Keep the run alive and say so in notes instead of failing the whole day."""
    if not isinstance(payload, dict):
        return
    if not isinstance(payload.get("quotes"), list):
        payload["quotes"] = []
        note = "quotes missing from the snapshot; positions valued at Yahoo closes this run"
        notes = payload.get("notes")
        if isinstance(notes, list):
            notes.append(note)
        else:
            payload["notes"] = (f"{notes}; " if notes else "") + note


def normalize_crypto_keys(payload) -> None:
    """The model sometimes labels a crypto position's code as asset/symbol/currency; the schema wants code."""
    for acct in (payload.get("accounts") or []) if isinstance(payload, dict) else []:
        for pos in acct.get("crypto_positions") or []:
            if isinstance(pos, dict) and not pos.get("code"):
                for k in CRYPTO_CODE_ALIASES[1:]:
                    if pos.get(k):
                        pos["code"] = str(pos[k]).upper()
                        break
