from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict


class Order(BaseModel):
    """What sandbox.rules.validate consumes (kept as a plain-dict contract via model_dump)."""
    model_config = ConfigDict(extra="allow")
    account_number: str | None = None
    symbol: str
    side: str
    type: str | None = None
    quantity: str | float | None = None
    dollar_amount: str | float | None = None
    limit_price: str | float | None = None
    time_in_force: str | None = None
    market_hours: str | None = None
    ref_id: str | None = None
    tax_lots: Any = None


class BrokerAdapter(Protocol):
    name: str
    mcp_server_name: str
    mcp_server_url: str
    market_tz: str

    def mcp_config(self) -> dict: ...
    def guarded_tools(self) -> dict[str, Literal["place", "review"]]: ...
    def readonly_tools_stage_a(self) -> list[str]: ...
    def readonly_tools_stage_c(self) -> list[str]: ...
    def denied_tools(self) -> list[str]: ...
    def trade_tools(self) -> list[str]: ...
    def hook_matcher(self) -> str: ...
    def sandbox_account_number(self, raw_snapshot: dict | None) -> str | None: ...
    def order_from_tool_input(self, tool_input: dict) -> Order: ...
    def response_failed(self, tool_response: Any) -> bool: ...
