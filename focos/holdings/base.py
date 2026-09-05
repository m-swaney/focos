"""Snapshot shape shared by every holdings source (this is what analytics, diff, and the dashboard read)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class SourceError(RuntimeError):
    """A source that is configured but could not capture (auth expired, CLI missing, bad data)."""


class HoldingsSource(Protocol):
    name: str

    def available(self) -> tuple[bool, str | None]:
        """(configured and reachable, reason when not)."""

    def capture(self, asof: str, mode: str, run_id: str) -> dict | None:
        """Return the normalized snapshot for `asof` (also written to state/snapshots/holdings), or None."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_snapshot(date: str, mode: str, source: str) -> dict:
    return {"date": date, "mode": mode, "captured_at": now_iso(), "source": source, "accounts": [], "quotes": [],
            "earnings": [], "news": [], "tax_lots": [], "notes": "", "total_value": None}


def account_entry(key: str, *, label: str | None = None, role: str | None = None, positions: list[dict] | None = None,
                  cash: float = 0.0, last4: str | None = None, extra_portfolio: dict | None = None) -> dict:
    positions = sorted(positions or [], key=lambda r: -(r.get("value") or 0))
    equity = float(sum((p.get("value") or 0.0) for p in positions))
    portfolio = {"total_value": equity + float(cash), "equity_value": equity, "cash": float(cash),
                 "buying_power": float(cash), **(extra_portfolio or {})}
    return {"key": key, "last4": last4, "nickname": label, "brokerage_account_type": role, "type": role,
            "agentic_allowed": role == "sandbox", "option_level": None, "portfolio": portfolio,
            "positions": positions, "option_positions": [], "crypto_positions": [], "recent_orders": []}


def position_entry(symbol: str, quantity: float, avg_cost: float | None, price: float | None,
                   prev_close: float | None = None) -> dict:
    value = (quantity * price) if price is not None else None
    return {"symbol": symbol.upper(), "quantity": float(quantity), "avg_cost": avg_cost, "price": price, "value": value,
            "day_change_pct": ((price / prev_close - 1) if (price and prev_close) else None), "sellable": float(quantity)}


def finish_snapshot(snap: dict) -> dict:
    snap["total_value"] = float(sum((a.get("portfolio") or {}).get("total_value") or 0.0 for a in snap["accounts"])) \
        if snap["accounts"] else None
    return snap
