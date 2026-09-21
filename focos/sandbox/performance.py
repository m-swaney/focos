"""Score the live sandbox: what the real orders actually earned, against SPY over the same window.

`paper.py` only marks proposals that were never sent to the broker. Once the sandbox goes live that answers
the wrong question -- the proposal is an intention, and the fill is what happened. This module reads the
order journal instead, matches sells to buys FIFO, and marks what is still open, so "how much has it made"
has one answer that does not depend on the model's own account of itself.

Fill prices come from the broker response when it carries one and from the next snapshot quote when it does
not; a market order's response is written before the fill is reported, so the quote fallback is the normal
path rather than the exception.
"""
from __future__ import annotations

from datetime import date

from .. import paths, settings
from . import journal, live, rules as rules_mod, state as sb_state


def live_file():
    return paths.SANDBOX / "live_positions.json"


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _snapshots() -> list[dict]:
    from .. import holdings

    return [settings.read_json(f, {}) for f in holdings.snapshot_files()]


def _quote(snap: dict, symbol: str) -> float | None:
    for q in snap.get("quotes", []):
        if q.get("symbol") == symbol and q.get("last"):
            return float(q["last"])
    return None


def _response_price(resp) -> float | None:
    """The average fill price, if the broker already knew it when it answered."""
    if isinstance(resp, str):
        try:
            import json

            resp = json.loads(resp)
        except ValueError:
            return None
    if not isinstance(resp, dict):
        return None
    for key in ("average_price", "executed_price", "price", "last_trade_price"):
        px = _f(resp.get(key))
        if px:
            return px
    return None


def _fills(snaps: list[dict]) -> list[dict]:
    """Every order that the broker accepted, oldest first, priced as well as we can price it."""
    path = journal.orders_file()
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            import json

            entry = json.loads(line)
        except ValueError:
            continue
        if not entry.get("ok"):
            continue
        order = entry.get("order") or {}
        symbol = str(order.get("symbol", "")).upper()
        side = str(order.get("side", "")).lower()
        if not symbol or side not in ("buy", "sell"):
            continue
        day = str(entry.get("ts", ""))[:10]
        px = _response_price(entry.get("response")) or _f(order.get("limit_price"))
        if px is None:
            fill_snap = next((s for s in snaps if s.get("date", "") >= day), None)
            px = _quote(fill_snap or {}, symbol)
        if not px:
            continue
        qty = _f(order.get("quantity"))
        if qty is None:
            dollars = _f(order.get("dollar_amount"))
            qty = (dollars / px) if dollars else None
        if not qty:
            continue
        out.append({"date": day, "symbol": symbol, "side": side, "quantity": qty, "price": px,
                    "ref_id": order.get("ref_id"),
                    "spy": _quote(next((s for s in snaps if s.get("date", "") >= day), {}) or {}, "SPY")})
    return sorted(out, key=lambda f: f["date"])


def _match(fills: list[dict]) -> tuple[list[dict], list[dict]]:
    """FIFO: each sell closes the oldest open lot of that symbol. Returns (closed trades, open lots)."""
    open_lots: dict[str, list[dict]] = {}
    closed: list[dict] = []
    for f in fills:
        lots = open_lots.setdefault(f["symbol"], [])
        if f["side"] == "buy":
            lots.append(dict(f, remaining=f["quantity"]))
            continue
        to_close = f["quantity"]
        while to_close > 1e-9 and lots:
            lot = lots[0]
            take = min(lot["remaining"], to_close)
            closed.append({
                "symbol": f["symbol"], "quantity": take, "opened": lot["date"], "closed": f["date"],
                "entry_price": lot["price"], "exit_price": f["price"],
                "pnl_usd": (f["price"] - lot["price"]) * take,
                "return_pct": (f["price"] / lot["price"] - 1) if lot["price"] else None,
                "spy_return_pct": (f["spy"] / lot["spy"] - 1) if (f.get("spy") and lot.get("spy")) else None,
                "ref_id": lot.get("ref_id"),
            })
            lot["remaining"] -= take
            to_close -= take
            if lot["remaining"] <= 1e-9:
                lots.pop(0)
    for t in closed:
        if t["return_pct"] is not None and t["spy_return_pct"] is not None:
            t["alpha_pct"] = t["return_pct"] - t["spy_return_pct"]
    return closed, [lot for lots in open_lots.values() for lot in lots if lot["remaining"] > 1e-9]


def _account(snaps: list[dict], view: dict | None) -> dict:
    """The account against the money put into it: total return, and where it sits versus the drawdown halt."""
    rules = settings.sandbox_rules()
    mode = sb_state.load_mode()
    from datetime import datetime

    now = datetime.now(settings.tz())
    basis = float(mode.get("drawdown_basis") or 0) or rules_mod.capital_basis(rules, now)
    equity = _f(((view or {}).get("portfolio") or {}).get("total_value"))
    if equity is None and snaps:
        from ..sources import robinhood_snapshot as rh

        try:
            agentic = rh.agentic_account(snaps[-1]) or {}
        except (KeyError, TypeError):   # a snapshot from before the agentic account existed
            agentic = {}
        equity = _f((agentic.get("portfolio") or {}).get("total_value"))
    dd = float(rules.get("max_drawdown_pct") or 0)
    return {
        "equity": equity,
        "capital_basis": basis,
        "pnl_usd": (equity - basis) if equity is not None else None,
        "return_pct": (equity / basis - 1) if (equity is not None and basis) else None,
        "drawdown_pct": (1 - equity / basis) if (equity is not None and basis and equity < basis) else 0.0,
        "halt_at_pct": dd or None,
        "halted": bool(dd and equity is not None and basis and equity < basis * (1 - dd)),
    }


def update(today: str | None = None) -> dict:
    """Recompute the live scorecard. Safe to call when nothing has ever traded: it reports unavailable."""
    today = today or date.today().isoformat()
    snaps = _snapshots()
    view = live.read()
    fills = _fills(snaps)
    if not fills:
        return {"available": False, "reason": "no live fills yet", "account": _account(snaps, view)}

    closed, open_lots = _match(fills)
    latest = snaps[-1] if snaps else {}
    spy_now = _quote(latest, "SPY")
    prices = {p.get("symbol"): p.get("price") for p in ((view or {}).get("positions") or [])}
    open_rows = []
    for lot in open_lots:
        px = _f(prices.get(lot["symbol"])) or _quote(latest, lot["symbol"])
        row = {"symbol": lot["symbol"], "quantity": lot["remaining"], "opened": lot["date"],
               "entry_price": lot["price"], "current_price": px, "ref_id": lot.get("ref_id")}
        if px:
            row["pnl_usd"] = (px - lot["price"]) * lot["remaining"]
            row["return_pct"] = px / lot["price"] - 1
            if spy_now and lot.get("spy"):
                row["spy_return_pct"] = spy_now / lot["spy"] - 1
                row["alpha_pct"] = row["return_pct"] - row["spy_return_pct"]
        open_rows.append(row)

    scored = [t for t in closed if t.get("return_pct") is not None]
    n = len(scored)
    realized = sum(t["pnl_usd"] for t in closed)
    unrealized = sum(r.get("pnl_usd") or 0 for r in open_rows)
    alphas = [t["alpha_pct"] for t in scored if t.get("alpha_pct") is not None]
    out = {
        "available": True,
        "asof": today,
        "n_closed": n,
        "n_open": len(open_rows),
        "hit_rate": (sum(1 for t in scored if t["return_pct"] > 0) / n) if n else None,
        "beat_spy_rate": (sum(1 for a in alphas if a > 0) / len(alphas)) if alphas else None,
        "avg_return_pct": (sum(t["return_pct"] for t in scored) / n) if n else None,
        "avg_alpha_pct": (sum(alphas) / len(alphas)) if alphas else None,
        "realized_pnl_usd": realized,
        "unrealized_pnl_usd": unrealized,
        "total_pnl_usd": realized + unrealized,
        "closed": closed,
        "open": open_rows,
        "account": _account(snaps, view),
    }
    settings.write_json(live_file(), out)
    return out


def merge_into_scorecard(paper_card: dict, live_card: dict) -> dict:
    """One file the dashboard and the prompts already read. The paper keys stay where they were so older
    readers keep working; live and account hang off it."""
    from . import paper

    merged = {**(paper_card or {}), "paper": paper_card, "live": live_card,
              "account": (live_card or {}).get("account")}
    settings.write_json(paper.scorecard_file(), merged)
    return merged
