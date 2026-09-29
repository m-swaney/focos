"""The exit plan: which positions must be sold and which lack a resting stop, decided in code, not by the model.

0.3.6 left every stop to the trading pass's judgement. When the gate refused an exit the model logged it,
decided not to retry, and the position sat below its stop for days. A stop is arithmetic: price against a
number written down at entry. So this module does the arithmetic, writes the exit order out in full, and the
trading pass is told to send it. Afterwards `verify` checks the order journal, and a missing exit fails the pass
loudly instead of passing as "no action".

It also keeps a resting stop under every position. A stop at the broker works between passes, overnight and
through a gap; a stop that only exists in a proposal file works three times a day at best.

Inputs are all on disk: the live view of the account (`live.json`), the proposal files, and the order journal.
Nothing here calls the broker.
"""
from __future__ import annotations

import uuid
from datetime import date as _date
from datetime import datetime, timedelta

from .. import paths, settings
from . import journal, live

PLAN_FILE = "exits.json"
STOP_TYPES = ("stop_market", "stop_limit")


def plan_file():
    return paths.SANDBOX / PLAN_FILE


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("$", "")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def accepted_orders() -> list[dict]:
    """Orders the broker accepted, from the PostToolUse journal, oldest first."""
    import json

    path = journal.orders_file()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("ok"):
            out.append({**(e.get("order") or {}), "_ts": e.get("ts")})
    return out


def _proposals() -> list[dict]:
    out = []
    for f in sorted(paths.PROPOSALS.glob("*.json")):
        p = settings.read_json(f, {}) or {}
        if isinstance(p, dict) and p.get("symbol"):
            p["_file"] = f.name
            out.append(p)
    return out


def opening_proposal(symbol: str, proposals: list[dict], placed_refs: set[str]) -> dict | None:
    """The buy proposal behind a held position: the newest one that actually reached the broker, else the
    newest one for the symbol at all (a position bought before the journal existed still has a plan)."""
    buys = [p for p in proposals if str(p.get("symbol", "")).upper() == symbol and str(p.get("side", "")).lower() == "buy"
            and not p.get("paper")]
    placed = [p for p in buys if str(p.get("ref_id")) in placed_refs]
    pool = placed or buys
    return sorted(pool, key=lambda p: (str(p.get("date", "")), p["_file"]))[-1] if pool else None


def business_days_between(start: _date, end: _date) -> int:
    days, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def resting_stops(view: dict) -> dict[str, list[dict]]:
    """Open sell stop orders by symbol, from the live read."""
    out: dict[str, list[dict]] = {}
    for o in view.get("open_orders") or []:
        if not isinstance(o, dict):
            continue
        otype = str(o.get("type") or o.get("order_type") or "").lower()
        trigger = str(o.get("trigger") or "").lower()
        is_stop = otype in STOP_TYPES or trigger == "stop" or _f(o.get("stop_price")) is not None
        if is_stop and str(o.get("side", "")).lower() == "sell":
            out.setdefault(str(o.get("symbol", "")).upper(), []).append(o)
    return out


def _existing_exit(symbol: str, today: str, proposals: list[dict], used: set[str]) -> dict | None:
    """Today's harness-written exit for this symbol, if its ref_id has not been spent: a second pass re-sends
    the same order rather than inventing a new one."""
    for p in reversed(proposals):
        if (p.get("kind") == "stop_exit" and str(p.get("symbol", "")).upper() == symbol
                and str(p.get("date")) == today and str(p.get("ref_id")) not in used):
            return p
    return None


def build(view: dict | None = None, today: str | None = None, write_proposals: bool = True,
          persist: bool = True) -> dict:
    """Compute the plan for the account as `view` shows it, and (when asked) write an exit proposal for every
    breached stop so the order the pass sends has a file behind it."""
    view = view if view is not None else (live.read() or {})
    today = today or _date.today().isoformat()
    proposals = _proposals()
    orders = accepted_orders()
    used = {str(o.get("ref_id")) for o in orders if o.get("ref_id")}
    placed_buys = {str(o.get("ref_id")) for o in orders if str(o.get("side", "")).lower() == "buy" and o.get("ref_id")}
    stops_by_symbol = resting_stops(view)

    rows, required, missing, unmanaged = [], [], [], []
    for pos in view.get("positions") or []:
        symbol = str(pos.get("symbol", "")).upper()
        qty = _f(pos.get("quantity")) or 0.0
        if qty <= 0:
            continue
        sellable = _f(pos.get("sellable"))
        price = _f(pos.get("price")) or _f((view.get("quotes") or {}).get(symbol))
        prop = opening_proposal(symbol, proposals, placed_buys)
        resting = stops_by_symbol.get(symbol, [])
        row = {"symbol": symbol, "quantity": qty, "sellable": sellable, "price": price,
               "avg_cost": _f(pos.get("avg_cost")), "resting_stops": resting}
        if prop is None:
            row["status"] = "unmanaged"
            unmanaged.append(symbol)
            rows.append(row)
            continue
        stop = _f(prop.get("stop_loss"))
        target = _f(prop.get("target"))
        horizon = int(_f(prop.get("horizon_days")) or 0)
        opened = str(prop.get("date") or today)[:10]
        try:
            held_days = business_days_between(_date.fromisoformat(opened), _date.fromisoformat(today))
        except ValueError:
            held_days = None
        row.update({"opened": opened, "opening_ref_id": prop.get("ref_id"), "proposal_file": prop["_file"],
                    "stop_loss": stop, "target": target, "horizon_days": horizon or None, "days_held": held_days})

        if stop is not None and price is not None and price <= stop:
            row["status"] = "stop_breached"
            existing = _existing_exit(symbol, today, proposals, used)
            ref_id = str(existing["ref_id"]) if existing else str(uuid.uuid4())
            # All of it. Shares a resting stop holds are not sellable until that stop is cancelled.
            order = {"symbol": symbol, "side": "sell", "type": "market", "quantity": _qty(qty),
                     "time_in_force": "gfd", "market_hours": "regular_hours", "ref_id": ref_id}
            exit_row = {"symbol": symbol, "reason": f"price {price:.2f} is at or below the {stop:.2f} stop",
                        "order": order, "cancel_first": [o.get("id") or o.get("order_id") for o in resting
                                                          if o.get("id") or o.get("order_id")],
                        "proposal_file": f"{today}-{symbol}-sell-stop.json"}
            required.append(exit_row)
            if write_proposals and not existing:
                settings.write_json(paths.PROPOSALS / exit_row["proposal_file"], {
                    "ref_id": ref_id, "date": today, "symbol": symbol, "side": "sell", "kind": "stop_exit",
                    "quantity": qty, "exit_of": prop.get("ref_id"),
                    "thesis": f"Stop exit written by focos: {exit_row['reason']} (from {prop['_file']}).",
                    "entry_reason": "stop breached", "exit_plan": "Full exit. No re-entry for 30 days.",
                    "stop_loss": None, "target": None, "horizon_days": 0, "paper": False, "created_by": "focos",
                })
        elif target is not None and price is not None and price >= target:
            row["status"] = "target_hit"
        elif horizon and held_days is not None and held_days >= horizon:
            row["status"] = "horizon_due"
        else:
            row["status"] = "ok"

        if row["status"] != "stop_breached" and stop is not None and not resting:
            missing.append({"symbol": symbol, "reason": f"no resting stop at the broker for the {stop:.2f} stop",
                            "order": {"symbol": symbol, "side": "sell", "type": "stop_market",
                                      "quantity": _qty(sellable if sellable is not None else qty),
                                      "stop_price": f"{stop:.2f}", "time_in_force": "gtc",
                                      "market_hours": "regular_hours", "ref_id": str(uuid.uuid4())}})
        rows.append(row)

    plan = {"asof": view.get("asof"), "date": today, "positions": rows, "required_exits": required,
            "missing_stops": missing, "unmanaged": unmanaged}
    if persist:
        settings.write_json(plan_file(), plan)
    return plan


def view_from_snapshot(snapshot: dict | None) -> dict:
    """The agentic account from a holdings snapshot, in the live-view shape `build` reads. Used after the close,
    where the snapshot's quotes are fresher than the last trading pass's live read."""
    from ..sources import robinhood_snapshot as rh

    try:
        acct = rh.agentic_account(snapshot or {}) or {}
    except (KeyError, TypeError):
        acct = {}
    quotes = {q.get("symbol"): q.get("last") for q in (snapshot or {}).get("quotes", []) if q.get("last")}
    positions = []
    for p in acct.get("positions") or []:
        sym = str(p.get("symbol", "")).upper()
        qty = _f(p.get("quantity")) or 0.0
        price = _f(quotes.get(sym)) or _f(p.get("price")) or _f(p.get("last_trade_price"))
        positions.append({"symbol": sym, "quantity": qty, "sellable": _f(p.get("sellable")) or qty, "price": price,
                          "avg_cost": _f(p.get("average_buy_price")) or _f(p.get("avg_cost"))})
    return {"asof": (snapshot or {}).get("captured_at"), "positions": positions, "quotes": quotes, "open_orders": []}


def _qty(q: float | None) -> str:
    q = float(q or 0)
    return str(int(q)) if abs(q - round(q)) < 1e-9 else f"{q:.6f}".rstrip("0").rstrip(".")


def verify(plan: dict, since: datetime | None = None) -> dict:
    """After a pass: which required exits and protective stops reached the broker. Checked against the journal
    by ref_id, so the model's own summary of what it did does not count."""
    accepted = {str(o.get("ref_id")) for o in accepted_orders() if o.get("ref_id")}
    missed_exits = [e["symbol"] for e in plan.get("required_exits", []) if str(e["order"]["ref_id"]) not in accepted]
    done_exits = [e["symbol"] for e in plan.get("required_exits", []) if str(e["order"]["ref_id"]) in accepted]
    missed_stops = [s["symbol"] for s in plan.get("missing_stops", []) if str(s["order"]["ref_id"]) not in accepted]
    return {"exits_done": done_exits, "exits_missed": missed_exits, "stops_missed": missed_stops}


def prompt_block(plan: dict) -> str:
    """The plan as the trading pass reads it: short, exact, and first."""
    import json

    lines = []
    if plan.get("required_exits"):
        lines.append("### Required exits: send these first, exactly as written")
        lines.append("focos checked each position against the stop in its proposal. These are breached. Each order "
                     "below is complete except `account_number` (the full number from `get_accounts`). Its proposal "
                     "file is already written. If `cancel_first` lists order ids, cancel those resting stops first "
                     "(`cancel_equity_order`) so the shares become sellable. Do not second-guess a breached stop, "
                     "do not swap in a limit price, and do not wait for a bounce.")
        for e in plan["required_exits"]:
            lines.append(f"- **{e['symbol']}**: {e['reason']}. cancel_first={e['cancel_first'] or []} "
                         f"order=`{json.dumps(e['order'])}`")
    if plan.get("missing_stops"):
        lines.append("### Protective stops to place")
        lines.append("These positions have a stop in their proposal but no stop order resting at the broker. "
                     "Place each one (after the required exits), exactly as written plus `account_number`. If a "
                     "position's sellable quantity is lower than shown because something already holds the shares, "
                     "check `get_equity_orders` and log what you find instead of forcing it.")
        for s in plan["missing_stops"]:
            lines.append(f"- **{s['symbol']}**: {s['reason']}. order=`{json.dumps(s['order'])}`")
    status = [f"{r['symbol']} {r['status']}" + (f" (stop {r['stop_loss']}, price {r['price']})"
                                                 if r.get("stop_loss") is not None else "")
              for r in plan.get("positions", [])]
    lines.append("### Position check")
    lines.append("; ".join(status) if status else "No open positions.")
    if plan.get("unmanaged"):
        lines.append(f"Unmanaged (no opening proposal on file, leave them alone and log it): {', '.join(plan['unmanaged'])}")
    return "\n".join(lines)
