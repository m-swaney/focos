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


class RobinhoodAdapter:
    name = "robinhood"
    mcp_server_name = SERVER
    market_tz = "America/New_York"

    def mcp_config(self) -> dict:
        return {"mcpServers": {SERVER: {"type": "http", "url": URL}}}

    def guarded_tools(self) -> dict[str, Literal["place", "review"]]:
        return {PLACE: "place", REVIEW: "review"}

    def readonly_tools_stage_a(self) -> list[str]:
        return [PREFIX + "get_*", PREFIX + "search"]

    def readonly_tools_stage_c(self) -> list[str]:
        return list(STAGE_C_READ)

    def denied_tools(self) -> list[str]:
        return list(ALWAYS_DENY)

    def trade_tools(self) -> list[str]:
        return [REVIEW, PLACE]

    def hook_matcher(self) -> str:
        return f"{PLACE}|{REVIEW}"

    def sandbox_account_number(self, raw_snapshot: dict | None) -> str | None:
        for a in (raw_snapshot or {}).get("accounts", []):
            if a.get("agentic_allowed"):
                return str(a.get("account_number"))
        return None

    def order_from_tool_input(self, tool_input: dict) -> Order:
        return Order.model_validate(tool_input or {})

    def response_failed(self, tool_response: Any) -> bool:
        text = json.dumps(tool_response, default=str) if not isinstance(tool_response, str) else tool_response
        return any(k in text.lower() for k in ('"error"', "rejected", "failed", "not allowed", "invalid"))
