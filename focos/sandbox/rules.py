"""Pure order validation for the Agentic sandbox. No I/O; the gate builds the context.

order: tool_input of place_equity_order / review_equity_order (strings as sent by the model).
ctx: {
  "tool": "place"|"review", "now": datetime (ET-aware), "killed": bool, "mode": "paper"|"live",
  "run_count": int, "live_orders": int,
  "agentic_account_number": str | None, "equity": float, "cash": float,
  "positions": {symbol: {"value": float, "quantity": float, "sellable": float}},
  "prices": {symbol: float}, "orders_this_run": int, "orders_this_week": int, "buy_notional_this_week": float,
  "proposal": dict | None (matched by ref_id), "approved": bool,
}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

SYMBOL_RE = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    notional: float | None = None
    price: float | None = None
    side: str | None = None
    symbol: str | None = None


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except ValueError:
        return None


def is_regular_hours(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.timetz().replace(tzinfo=None)
    return time(9, 30) <= t <= time(16, 0)


def validate(order: dict, ctx: dict, rules: dict) -> Verdict:
    r: list[str] = []
    tool = ctx.get("tool", "place")
    side = str(order.get("side", "")).lower()
    symbol = str(order.get("symbol", "")).upper().strip()
    otype = str(order.get("type", "")).lower()
    hours = str(order.get("market_hours") or "regular_hours").lower()
    qty = _f(order.get("quantity"))
    dollars = _f(order.get("dollar_amount"))
    limit_price = _f(order.get("limit_price"))

    # --- kill switch, mode, warmup
    if ctx.get("killed"):
        r.append("KILL switch is set (state/sandbox/KILL)")
    if ctx.get("mode") != "live":
        r.append(f"sandbox mode is '{ctx.get('mode')}', not live")
    warm = int(rules.get("warmup_runs", 10))
    if int(ctx.get("run_count", 0)) < warm:
        r.append(f"warmup incomplete: {ctx.get('run_count', 0)}/{warm} runs")

    # --- account
    acct = str(order.get("account_number", ""))
    if not ctx.get("agentic_account_number") or acct != str(ctx["agentic_account_number"]):
        r.append("order account is not the Agentic account")

    # --- shape
    if side not in ("buy", "sell"):
        r.append(f"side must be buy or sell, got '{side}'")
    if otype not in ("market", "limit"):
        r.append(f"order type must be market or limit, got '{otype}'")
    if hours != "regular_hours":
        r.append("only regular_hours orders are allowed")
    if otype == "market" and not is_regular_hours(ctx["now"]) and rules.get("market_orders_only_during_rth", True):
        r.append("market orders only between 09:30 and 16:00 ET on weekdays")
    if (qty is None) == (dollars is None):
        r.append("provide exactly one of quantity or dollar_amount")
    if dollars is not None and otype != "market":
        r.append("dollar_amount requires type=market")
    if otype == "limit" and limit_price is None:
        r.append("limit orders need limit_price")
    if order.get("tax_lots") and side != "sell":
        r.append("tax_lots only on sells")
    if str(order.get("time_in_force") or "gfd").lower() == "gtc":
        r.append("gtc orders are not allowed; use gfd")

    # --- symbol / universe
    if not SYMBOL_RE.match(symbol):
        r.append(f"symbol '{symbol}' is not a plain US ticker")
    for pat in rules.get("blocklist_patterns", []) or []:
        if re.search(pat, symbol, re.I):
            r.append(f"symbol {symbol} matches blocklist pattern {pat}")
            break
    price = ctx.get("prices", {}).get(symbol)
    if price is None and limit_price is not None:
        price = limit_price
    if price is None:
        r.append(f"no quote available for {symbol}; cannot size the order")
    elif price < float(rules.get("min_price", 5.0)):
        r.append(f"{symbol} price {price:.2f} is below the {rules.get('min_price', 5.0)} minimum")

    # --- sizing
    notional = None
    if price is not None:
        notional = dollars if dollars is not None else (qty or 0) * (limit_price or price)
    equity = float(ctx.get("equity") or 0)
    cash = float(ctx.get("cash") or 0)
    positions = ctx.get("positions", {})
    if side == "buy" and notional is not None:
        if equity <= 0:
            r.append("Agentic account is unfunded")
        cap_order = float(rules.get("max_order_usd", 250))
        if notional > cap_order + 0.005:
            r.append(f"notional {notional:.2f} exceeds max_order_usd {cap_order:.2f}")
        max_w = float(rules.get("max_position_weight", 0.25))
        if equity > 0:
            post = (positions.get(symbol, {}).get("value", 0.0) + notional) / equity
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
        budget = float(rules.get("budget_usd", 1000))
        growth = float(rules.get("budget_growth_per_week_usd", 0) or 0)
        funded_on = rules.get("funded_on")
        if growth and funded_on:
            try:
                weeks = max(0, (ctx["now"].date() - datetime.fromisoformat(str(funded_on)).date()).days // 7)
                budget += growth * weeks
            except Exception:
                pass
        if equity > budget * 1.5:
            r.append(f"account equity {equity:.2f} is far above the {budget:.2f} sandbox budget; withdraw excess first")
    if side == "sell":
        pos = positions.get(symbol)
        if not pos:
            r.append(f"no {symbol} position to sell")
        elif qty is not None and qty > float(pos.get("sellable") or pos.get("quantity") or 0) + 1e-9:
            r.append(f"sell quantity {qty} exceeds sellable {pos.get('sellable')}")

    # --- frequency
    if tool == "place":
        if int(ctx.get("orders_this_run", 0)) >= int(rules.get("max_orders_per_run", 2)):
            r.append("max orders per run reached")
        if int(ctx.get("orders_this_week", 0)) >= int(rules.get("max_orders_per_week", 4)):
            r.append("max orders per week reached")

    # --- proposal + approval
    prop = ctx.get("proposal")
    if not order.get("ref_id"):
        r.append("ref_id is required and must match a proposal file")
    elif not prop:
        r.append(f"no proposal file with ref_id {order.get('ref_id')}")
    else:
        if str(prop.get("symbol", "")).upper() != symbol or str(prop.get("side", "")).lower() != side:
            r.append("proposal symbol/side do not match the order")
        for k in ("thesis", "exit_plan", "stop_loss", "horizon_days"):
            if not prop.get(k):
                r.append(f"proposal is missing '{k}'")
        if prop.get("paper"):
            r.append("proposal is marked paper: true")
    if tool == "place":
        need_approval = int(ctx.get("live_orders", 0)) < int(rules.get("require_approval_first_n", 5))
        if need_approval and not ctx.get("approved"):
            r.append("approval required: create state/sandbox/approvals/<ref_id>.approved (dashboard Approve)")

    return Verdict(ok=not r, reasons=r, notional=notional, price=price, side=side, symbol=symbol)
