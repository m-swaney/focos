"""Robinhood via the Claude Code CLI acting as an MCP client (Stage A of the original design)."""
from __future__ import annotations

import re

from .. import paths, settings
from ..agent_runtime import claude_cli, settings_render
from ..run import claude_io, tokens
from ..sandbox import brokers
from ..sources import robinhood_snapshot as rh
from . import write_snapshot
from .base import SourceError

AUTH_ERROR = re.compile(
    r"unauthori[sz]ed|\b401\b|\b403\b|needs?[ -]auth|authentication (?:required|failed)|not authenticated|"
    r"please (?:re-?)?authenticate|invalid_grant|invalid_token|token (?:has )?expired|login (?:has )?expired", re.I)


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
        st = tokens.robinhood_status(e)
        if not st["present"]:
            return False, f"Robinhood is not connected; {tokens.AUTH_FIX}"
        if st["expired"] and not st["has_refresh"]:
            return False, f"Robinhood login expired and cannot refresh; {tokens.AUTH_FIX}"
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
        if agent.get("debug_claude"):
            args += claude_cli.debug_args(paths.LOGS / f"{asof}-{mode}-A.debug.log")
        before = tokens.robinhood_status()
        try:
            result = claude_cli.run(prompt, args, log_path=log, cwd=paths.HOME, claude=agent.get("claude_cli") or "auto")
        except RuntimeError as e:  # no result object at all; the message carries the stderr tail
            self.last_meta = {"is_error": True, "token_before": before, "token_after": tokens.robinhood_status()}
            raise SourceError(_auth_message(str(e)) or str(e)[:500]) from e
        meta = claude_io.summarize(result)
        after = tokens.robinhood_status()
        meta.update({"token_before": before, "token_after": after,
                     "token_refreshed": bool(after.get("expires_at") and after.get("expires_at") != before.get("expires_at"))})
        self.last_meta = meta
        if meta["is_error"]:
            text = str(result.get("result") or result.get("error") or meta.get("subtype") or "claude error")
            evidence = "\n".join(str(x) for x in (text, result.get("_stderr_tail"), result.get("api_error_status")) if x)
            raise SourceError(_auth_message(evidence) or text[:500])
        payload = claude_io.extract_json(result.get("result") or "")
        normalize_snapshot(payload)
        errors = rh.validate(payload)
        if errors:
            raise SourceError("schema: " + "; ".join(errors[:5]))
        settings.write_json(paths.RAW / f"{asof}-{mode}.json", payload)  # full account numbers, gitignored
        snap = rh.normalize(payload, asof, mode)
        snap["source"] = self.name
        write_snapshot(snap)
        return snap


def _auth_message(evidence: str) -> str | None:
    """A clear, actionable error when the CLI output looks like an MCP auth failure; None otherwise."""
    if AUTH_ERROR.search(evidence or ""):
        return f"Robinhood login expired or refresh failed; {tokens.AUTH_FIX} (detail: {evidence.strip()[:200]})"
    return None


CRYPTO_CODE_ALIASES = ("code", "asset", "symbol", "currency", "ticker")
NEWS_SOURCE_ALIASES = ("source", "publisher", "provider")


def normalize_snapshot(payload) -> None:
    """Coerce the shapes the model drifts into back to the schema before validating: crypto code aliases,
    missing quotes, notes as a list, news/earnings keyed by symbol instead of flat arrays."""
    if not isinstance(payload, dict):
        return
    normalize_crypto_keys(payload)
    ensure_quotes(payload)
    for key in ("news", "earnings"):
        val = payload.get(key)
        if isinstance(val, dict):  # {"NVDA": [{...}, ...]} -> [{"symbol": "NVDA", ...}, ...]
            flat = []
            for sym, items in val.items():
                for it in (items if isinstance(items, list) else [items]):
                    if isinstance(it, dict):
                        flat.append({"symbol": str(sym), **it})
            payload[key] = flat
        elif val is None:
            payload[key] = []
    for it in payload.get("news") or []:
        if isinstance(it, dict) and "source" not in it:
            for k in NEWS_SOURCE_ALIASES[1:]:
                if k in it:
                    it["source"] = it.pop(k)
                    break


def ensure_quotes(payload) -> None:
    """A snapshot without quotes still has positions and portfolio totals; downstream valuation falls back to
    Yahoo closes. Keep the run alive and say so in notes instead of failing the whole day."""
    if not isinstance(payload, dict):
        return
    if isinstance(payload.get("notes"), list):  # the schema wants one string; the model often writes a list
        payload["notes"] = "; ".join(str(n) for n in payload["notes"] if n)
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
