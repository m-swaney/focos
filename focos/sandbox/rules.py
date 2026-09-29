"""Pure order validation for the Agentic sandbox. No I/O; the gate builds the context.

order: tool_input of place_equity_order / review_equity_order / cancel_equity_order (strings as sent by the
model).
ctx: {
  "tool": "place"|"review"|"cancel", "now": datetime (ET-aware), "killed": bool, "mode": "paper"|"live",
  "run_count": int, "live_orders": int,
  "agentic_account_number": str | None, "equity": float, "cash": float,
  "positions": {symbol: {"value": float, "quantity": float, "sellable": float}},
  "prices": {symbol: float}, "orders_this_run": int, "orders_this_week": int, "buy_notional_this_week": float,
  "proposal": dict | None (matched by ref_id), "approved": bool,
  "used_ref_ids": {ref_id: "what it was used for"} (orders the broker already accepted),
}

The asymmetry is the design. A buy adds risk, so it has to clear every limit and carry a written plan. A sell
of something the account holds removes risk, so it clears only what keeps it honest -- the right account, a
real position, a quantity the broker will accept, a fresh idempotency key -- and nothing else. Frequency caps,
approvals, proposals, the price floor and the drawdown halt are all entry controls; none of them may stand
between the account and its own stop. 0.3.6 got this wrong and held a breached stop for days.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import market_calendar

SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")
ORDER_TYPES = ("market", "limit", "stop_market", "stop_limit")
STOP_TYPES = ("stop_market", "stop_limit")
# Reasons the model can fix by correcting the order itself (a field, a key, the account number). Anything else
# is a limit, and a limit is not something to work around.
CORRECTABLE_MARKERS = ("ref_id", "account", "limit_price", "stop_price", "quantity or dollar_amount",
                       "dollar_amount requires", "use a limit order", "order type", "side must", "regular_hours",
                       "proposal is missing", "proposal symbol", "no proposal file", "exceeds sellable",
                       "gtc", "stop_loss", "time_in_force")


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    notional: float | None = None
    price: float | None = None
    side: str | None = None
    symbol: str | None = None
    exit: bool = False            # a sell of a held position: the risk-reducing path

    @property
    def correctable(self) -> bool:
        """True when every reason is a shape problem the model can fix without changing the trade."""
        return bool(self.reasons) and all(any(m in r for m in CORRECTABLE_MARKERS) for r in self.reasons)


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return None


def capital_basis(rules: dict, now: datetime) -> float:
    """What the household has put into the sandbox: the initial funding plus the recurring weekly deposits
    that have landed since. Gains are not capital, so the drawdown halt measures against this, not the peak."""
    basis = float(rules.get("budget_usd", 1000))
    growth = float(rules.get("budget_growth_per_week_usd", 0) or 0)
    funded_on = rules.get("funded_on")
    if growth and funded_on:
        try:
            weeks = max(0, (now.date() - datetime.fromisoformat(str(funded_on)).date()).days // 7)
            basis += growth * weeks
        except Exception:
            pass
    return basis


def _is_time_of_day_reason(reason: str) -> bool:
    """Distinguish "the market is shut today" from "it is shut right now". The first blocks any order type;
    the second only blocks market orders, since a limit or stop order can legitimately rest until the next
    session."""
    return reason.startswith("before the") or reason.startswith("after the")


def is_regular_hours(now: datetime, no_trading_days: list[str] | None = None) -> bool:
    """Market holidays and 13:00 half-day closes count, not just the weekend and the clock."""
    return market_calendar.is_open(now, no_trading_days)


def validate_cancel(order: dict, ctx: dict) -> Verdict:
    """cancel_equity_order: only in the Agentic account, only in live mode, and only with an order id. Cancelling
    is how a resting stop is moved up or cleared before a planned exit; the next pass re-places any stop that
    goes missing, so a cancel can never leave a position unprotected for longer than one pass."""
    r: list[str] = []
    if ctx.get("killed"):
        r.append("KILL switch is set (state/sandbox/KILL)")
    if ctx.get("mode") != "live":
        r.append(f"sandbox mode is '{ctx.get('mode')}', not live")
    acct = str(order.get("account_number", ""))
    if not ctx.get("agentic_account_number") or acct != str(ctx["agentic_account_number"]):
        r.append("order account is not the Agentic account (use the full number from get_accounts)")
    if not order.get("order_id"):
        r.append("order_id is required")
    return Verdict(ok=not r, reasons=r, symbol=str(order.get("symbol") or "").upper() or None)


def validate(order: dict, ctx: dict, rules: dict) -> Verdict:
    tool = ctx.get("tool", "place")
    if tool == "cancel":
        return validate_cancel(order, ctx)
    r: list[str] = []
    side = str(order.get("side", "")).lower()
    symbol = str(order.get("symbol", "")).upper().strip()
    otype = str(order.get("type", "")).lower()
    hours = str(order.get("market_hours") or "regular_hours").lower()
    tif = str(order.get("time_in_force") or "gfd").lower()
    qty = _f(order.get("quantity"))
    dollars = _f(order.get("dollar_amount"))
    limit_price = _f(order.get("limit_price"))
    stop_price = _f(order.get("stop_price"))
    positions = ctx.get("positions", {}) or {}
    pos = positions.get(symbol)
    is_exit = side == "sell" and bool(pos)

    # --- kill switch, mode, warmup: these stop everything, exits included, because the owner set them
    if ctx.get("killed"):
        r.append("KILL switch is set (state/sandbox/KILL)")
    if ctx.get("mode") != "live":
        r.append(f"sandbox mode is '{ctx.get('mode')}', not live")
    warm = int(rules.get("warmup_runs", 10))
    if int(ctx.get("run_count", 0)) < warm:
        r.append(f"warmup incomplete: {ctx.get('run_count', 0)}/{warm} runs")
    # The 12:45 pass exists to honour stops, not to add risk. The gate enforces that, not the prompt, so the
    # model cannot reinterpret its way into a new position.
    if ctx.get("pass_kind") == "exits" and side == "buy":
        r.append("this is an exits-only pass; no new positions")

    # --- account
    acct = str(order.get("account_number", ""))
    if not ctx.get("agentic_account_number") or acct != str(ctx["agentic_account_number"]):
        r.append("order account is not the Agentic account (use the full number from get_accounts)")

    # --- shape
    if side not in ("buy", "sell"):
        r.append(f"side must be buy or sell, got '{side}'")
    if otype not in ORDER_TYPES:
        r.append(f"order type must be one of {', '.join(ORDER_TYPES)}, got '{otype}'")
    if otype in STOP_TYPES and side != "sell":
        r.append("stop orders are for protective sells only; enter with a market or limit order")
    if hours != "regular_hours":
        r.append("only regular_hours orders are allowed")
    closed = market_calendar.why_closed(ctx["now"], rules.get("no_trading_days") or [])
    if closed and not _is_time_of_day_reason(closed):
        r.append(f"no trading today: {closed}")   # holiday or an explicit no_trading_days date, whatever the order type
    elif otype == "market" and closed and rules.get("market_orders_only_during_rth", True):
        r.append(f"market orders only during regular hours ({closed})")
    if (qty is None) == (dollars is None):
        r.append("provide exactly one of quantity or dollar_amount")
    if dollars is not None and otype != "market":
        r.append("dollar_amount requires type=market")
    if otype in ("limit", "stop_limit") and limit_price is None:
        r.append("limit orders need limit_price")
    if otype in STOP_TYPES and stop_price is None:
        r.append("stop orders need stop_price")
    if order.get("tax_lots") and side != "sell":
        r.append("tax_lots only on sells")
    # A resting stop is only a stop if it outlives the day, so a protective sell may be good-till-cancelled.
    # Buys stay day orders: an entry that fills tomorrow was sized against today.
    if tif == "gtc" and side != "sell":
        r.append("gtc is for resting sell orders only; buys use gfd")
    elif tif not in ("gfd", "gtc"):
        r.append(f"time_in_force must be gfd or gtc, got '{tif}'")

    # --- symbol / universe
    if not SYMBOL_RE.match(symbol):
        r.append(f"symbol '{symbol}' is not a plain US ticker")
    if side == "buy":
        for pat in rules.get("blocklist_patterns", []) or []:
            if re.search(pat, symbol, re.I):
                r.append(f"symbol {symbol} matches blocklist pattern {pat}")
                break
    price = ctx.get("prices", {}).get(symbol)
    if price is None and pos and pos.get("quantity"):
        price = (pos.get("value") or 0) / float(pos["quantity"]) or None
    if price is None and limit_price is not None:
        price = limit_price
    if side == "buy":
        if price is None:
            # The gate only knows the prices in the snapshot and the pass's own live read, which cover held
            # names. A new name has to price itself, and a limit order does: its limit_price is the size.
            r.append(f"no quote available for {symbol}; use a limit order so limit_price can size it")
        elif price < float(rules.get("min_price", 5.0)):
            r.append(f"{symbol} price {price:.2f} is below the {rules.get('min_price', 5.0)} minimum")

    # --- sizing
    notional = None
    if price is not None:
        notional = dollars if dollars is not None else (qty or 0) * (limit_price or price)
    equity = float(ctx.get("equity") or 0)
    cash = float(ctx.get("cash") or 0)
    if side == "buy" and notional is not None:
        if equity <= 0:
            r.append("Agentic account is unfunded")
        cap_order = float(rules.get("max_order_usd", 250))
        if notional > cap_order + 0.005:
            r.append(f"notional {notional:.2f} exceeds max_order_usd {cap_order:.2f}")
        max_w = float(rules.get("max_position_weight", 0.25))
        if equity > 0:
            post = ((pos or {}).get("value", 0.0) + notional) / equity
            if post > max_w + 1e-9:
                r.append(f"post-trade weight {post*100:.1f}% exceeds {max_w*100:.0f}% cap")
            floor = float(rules.get("cash_floor_pct", 0.05)) * equity
            if cash - notional < floor - 0.005:
                r.append(f"cash after trade {cash - notional:.2f} would breach the {floor:.2f} cash floor")
        if notional > cash + 0.005:
            r.append("notional exceeds available cash (no margin)")
        wk_budget = float(rules.get("weekly_budget_usd", 500))
        if float(ctx.get("buy_notional_this_week", 0)) + notional > wk_budget + 0.005:
            r.append(f"weekly buy budget {wk_budget:.2f} would be exceeded")
        basis = float(ctx.get("drawdown_basis") or 0) or capital_basis(rules, ctx["now"])
        # Opt-in deposit check. Off by default: an account that is winning should not have its own gains
        # read as an unexpected deposit and be barred from buying.
        ceiling = rules.get("equity_ceiling_multiple")
        if ceiling and equity > basis * float(ceiling):
            r.append(f"account equity {equity:.2f} is above {float(ceiling):.1f}x the {basis:.2f} sandbox "
                     f"capital; withdraw the excess or raise equity_ceiling_multiple")
        # Account-level stop. Buys only -- a halted account must still be able to sell its way out.
        dd = float(rules.get("max_drawdown_pct") or 0)
        if dd and basis > 0 and equity < basis * (1 - dd):
            r.append(f"drawdown halt: equity {equity:.2f} is below {(1 - dd) * 100:.0f}% of the {basis:.2f} "
                     f"contributed capital; new positions are paused until `focos sandbox resume`")
    if side == "sell":
        if not pos:
            r.append(f"no {symbol} position to sell (the sandbox never sells short)")
        elif qty is not None and qty > float(pos.get("sellable") or pos.get("quantity") or 0) + 1e-9:
            r.append(f"sell quantity {qty} exceeds sellable {pos.get('sellable')}; if a resting stop holds the "
                     f"shares, cancel it first (get_equity_orders for its id, then cancel_equity_order)")

    # --- frequency: an entry control, so buys only. A stop that waits for next week's quota is not a stop.
    if tool == "place" and side == "buy":
        if int(ctx.get("orders_this_run", 0)) >= int(rules.get("max_orders_per_run", 2)):
            r.append("max orders per run reached")
        if int(ctx.get("orders_this_week", 0)) >= int(rules.get("max_orders_per_week", 4)):
            r.append("max orders per week reached")

    # --- ref_id and proposal (place only: review_equity_order has no ref_id field to carry one)
    prop = ctx.get("proposal")
    ref_id = order.get("ref_id")
    if tool == "place":
        used = (ctx.get("used_ref_ids") or {}).get(str(ref_id)) if ref_id else None
        if not ref_id:
            r.append("ref_id is required: a fresh UUID for every new order, written in its proposal file")
        elif used:
            # The broker de-duplicates on ref_id, so re-sending one that already went through returns the old
            # order instead of placing this one. That is what an exit reusing its entry's ref_id would do.
            r.append(f"ref_id {ref_id} was already used by an accepted order ({used}); the broker would treat "
                     f"this as a duplicate. Use a fresh UUID and put it in this order's own proposal file")
        if side == "buy":
            if ref_id and not prop:
                r.append(f"no proposal file with ref_id {ref_id}")
            elif prop:
                if str(prop.get("symbol", "")).upper() != symbol or str(prop.get("side", "")).lower() != "buy":
                    r.append("proposal symbol/side do not match the order")
                for k in ("thesis", "exit_plan", "stop_loss", "horizon_days"):
                    if not prop.get(k):
                        r.append(f"proposal is missing '{k}'")
                stop = _f(prop.get("stop_loss"))
                entry = limit_price or price
                if stop is not None and entry and stop >= entry:
                    r.append(f"proposal stop_loss {stop:.2f} is not below the entry price {entry:.2f}")
                if prop.get("paper"):
                    r.append("proposal is marked paper: true")
        elif prop is not None:
            # An exit needs no proposal, but if it names one, that file has to be about this exit.
            if str(prop.get("symbol", "")).upper() != symbol:
                r.append("proposal symbol/side do not match the order")
            elif str(prop.get("side", "")).lower() != "sell":
                r.append("proposal symbol/side do not match the order: that ref_id belongs to the entry; an "
                         "exit takes its own fresh ref_id")
        if side == "buy":
            need_approval = int(ctx.get("live_orders", 0)) < int(rules.get("require_approval_first_n", 5))
            if need_approval and not ctx.get("approved"):
                r.append("approval required: create state/sandbox/approvals/<ref_id>.approved (dashboard Approve)")

    return Verdict(ok=not r, reasons=r, notional=notional, price=price, side=side, symbol=symbol, exit=is_exit)
