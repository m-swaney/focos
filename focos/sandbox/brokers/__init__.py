"""Broker adapters: every broker-specific string (MCP server name, tool names, account identity) lives here."""
from __future__ import annotations

from ... import settings
from .base import BrokerAdapter, Order  # noqa: F401


def current(name: str | None = None) -> BrokerAdapter:
    name = name or (settings.sandbox_rules().get("broker") or "robinhood")
    if name == "robinhood":
        from .robinhood import RobinhoodAdapter
        return RobinhoodAdapter()
    raise ValueError(f"unknown broker adapter {name!r}")
