"""Robinhood's official MCP server (agent.robinhood.com) as seen through Claude Code tool names."""
from __future__ import annotations

import json
from typing import Any, Literal

from .base import Order

SERVER = "robinhood-trading"
URL = "https://agent.robinhood.com/mcp/trading"
PREFIX = f"mcp__{SERVER}__"

PLACE = PREFIX + "place_equity_order"
REVIEW = PREFIX + "review_equity_order"
ALWAYS_DENY = [PREFIX + t for t in (
    "place_option_order", "place_crypto_order", "review_option_order", "preview_crypto_order",
    "cancel_equity_order", "cancel_option_order", "cancel_crypto_order", "exercise_option", "cancel_option_exercise",
)]
STAGE_C_READ = [PREFIX + t for t in (
    "get_equity_quotes", "get_equity_news", "get_equity_fundamentals", "get_earnings_calendar",
    "get_equity_historicals", "search",
)]
# A trading pass has to find candidates, not just describe what is already held, so it gets the screening and
# indicator reads the brief does not need. All read-only: `create_scan` and the scan-mutation tools write to
# the broker account and the gate does not cover them, so they stay off.
TRADE_READ = STAGE_C_READ + [PREFIX + t for t in (
    "get_scans", "run_scan", "get_equity_technical_indicators", "get_equity_analyst_ratings",
    "get_earnings_results", "get_equity_price_book", "get_equity_tradability", "get_watchlists",
    "get_watchlist_items", "get_popular_watchlists", "get_realized_pnl", "get_pnl_trade_history",
    "get_index_quotes",
)]


class RobinhoodAdapter:
    name = "robinhood"
    mcp_server_name = SERVER
    mcp_server_url = URL
    market_tz = "America/New_York"

    def mcp_config(self) -> dict:
        return {"mcpServers": {SERVER: {"type": "http", "url": URL}}}

    def guarded_tools(self) -> dict[str, Literal["place", "review"]]:
        return {PLACE: "place", REVIEW: "review"}

    def readonly_tools_stage_a(self) -> list[str]:
        return [PREFIX + "get_*", PREFIX + "search"]

    def readonly_tools_stage_c(self) -> list[str]:
        return list(STAGE_C_READ)

    def readonly_tools_trade(self) -> list[str]:
        return list(TRADE_READ)

    def denied_tools(self) -> list[str]:
        return list(ALWAYS_DENY)

    def trade_tools(self) -> list[str]:
        return [REVIEW, PLACE]

    def hook_matcher(self) -> str:
        return f"{PLACE}|{REVIEW}"

    def sandbox_account_number(self, raw_snapshot: dict | None) -> str | None:
        """The full account number the gate checks orders against.

        Two shapes reach here. The daily holdings snapshot carries every account, and the agentic one is the
        flagged member. A trading pass's own raw read is scoped to that account alone and states its number
        at the top level -- and since it is the newest file in state/raw while a pass runs, missing this case
        meant every order during a pass was refused as "not the Agentic account"."""
        for a in (raw_snapshot or {}).get("accounts", []):
            if a.get("agentic_allowed"):
                return str(a.get("account_number"))
        scoped = (raw_snapshot or {}).get("account_number")
        return str(scoped) if scoped else None

    def order_from_tool_input(self, tool_input: dict) -> Order:
        return Order.model_validate(tool_input or {})

    def response_failed(self, tool_response: Any) -> bool:
        text = json.dumps(tool_response, default=str) if not isinstance(tool_response, str) else tool_response
        return any(k in text.lower() for k in ('"error"', "rejected", "failed", "not allowed", "invalid"))
