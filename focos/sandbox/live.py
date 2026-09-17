"""The agentic account as it stands right now, read fresh at the start of an intraday trading pass.

The daily snapshot is captured once, after the close, and the sandbox rules are sized against it. That is
fine for a brief and wrong for a trade: by 15:00 the cash figure is a day stale, and a buy sized against a
stale price can breach `max_position_weight` without the gate noticing. So a trading pass opens with one
cheap broker read scoped to the agentic account alone and publishes it here.

Two things this deliberately does not do: it never writes `state/snapshots/holdings/<date>.json`, so the
daily diff baseline and the dashboard's day-over-day numbers stay exactly as the daily run left them, and it
never bumps the sandbox warmup counter. Full account numbers stay in `state/raw/`; what lands in
`state/sandbox/live.json` is masked to the last four, like every other committed file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .. import paths, settings

FILE_NAME = "live.json"
# How old a live read may be and still be trusted for sizing. A pass takes a couple of minutes end to end;
# beyond this the run has stalled and the gate should fall back to the snapshot rather than size on stale cash.
MAX_AGE_MINUTES = 30


def path():
    return paths.SANDBOX / FILE_NAME


def read() -> dict | None:
    """The last live read, or None. Never raises: missing or corrupt just means "no live view", and the gate
    falls back to the snapshot. This runs inside the PreToolUse hook, where an exception would fail an order
    closed on a technicality rather than on the rules."""
    try:
        got = settings.read_json(path(), None)
    except (OSError, ValueError):
        return None
    return got if isinstance(got, dict) else None


def age_minutes(view: dict | None, now: datetime | None = None) -> float | None:
    view = view if view is not None else read()
    if not view or not view.get("asof"):
        return None
    try:
        asof = datetime.fromisoformat(str(view["asof"]))
    except ValueError:
        return None
    now = now or datetime.now(asof.tzinfo or timezone.utc)
    return (now - asof).total_seconds() / 60.0


def fresh(view: dict | None = None, now: datetime | None = None) -> bool:
    age = age_minutes(view, now)
    return age is not None and 0 <= age <= MAX_AGE_MINUTES


def normalize(payload: dict, now: datetime | None = None) -> dict:
    """Coerce the model's JSON into the shape the gate reads, and mask the account number.

    Accepts the shapes the model drifts into: positions under `positions` or `equity_positions`, a quote's
    price as `last`, `last_trade_price` or `price`.
    """
    now = now or datetime.now(timezone.utc)
    portfolio = payload.get("portfolio") or {}
    positions = payload.get("positions") or payload.get("equity_positions") or []
    quotes = payload.get("quotes") or []

    out_positions = []
    for p in positions:
        if not isinstance(p, dict) or not p.get("symbol"):
            continue
        qty = _f(p.get("quantity")) or 0.0
        price = _f(p.get("price")) or _f(p.get("last_trade_price")) or _f(p.get("last"))
        out_positions.append({
            "symbol": str(p["symbol"]).upper(),
            "quantity": qty,
            "sellable": _f(p.get("sellable")) or _f(p.get("shares_available_for_sells")) or qty,
            "price": price,
            "avg_cost": _f(p.get("avg_cost")) or _f(p.get("average_buy_price")),
            "value": (qty * price) if price is not None else _f(p.get("value")),
        })

    out_quotes = {}
    for q in quotes:
        if not isinstance(q, dict) or not q.get("symbol"):
            continue
        last = _f(q.get("last")) or _f(q.get("last_trade_price")) or _f(q.get("price"))
        if last is not None:
            out_quotes[str(q["symbol"]).upper()] = last
    for p in out_positions:  # a position's own price is a quote for sizing purposes
        if p["symbol"] not in out_quotes and p.get("price") is not None:
            out_quotes[p["symbol"]] = p["price"]

    number = str(payload.get("account_number") or "")
    return {
        "asof": now.isoformat(timespec="seconds"),
        "last4": number[-4:] or None,
        "portfolio": {
            "total_value": _f(portfolio.get("total_value")) or _f(payload.get("total_value")) or 0.0,
            "cash": _f(portfolio.get("cash")) or _f(payload.get("cash")) or 0.0,
            "buying_power": _f(portfolio.get("buying_power")) or _f(payload.get("buying_power")) or 0.0,
        },
        "positions": out_positions,
        "quotes": out_quotes,
        "open_orders": payload.get("open_orders") or [],
    }


def write(view: dict) -> dict:
    settings.write_json(path(), view)
    return view


def _f(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None
