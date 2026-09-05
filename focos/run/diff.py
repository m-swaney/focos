"""Diff two normalized Robinhood snapshots."""
from __future__ import annotations


def _acct_map(snap: dict | None) -> dict:
    return {a["key"]: a for a in (snap or {}).get("accounts", [])}


def _pos_map(acct: dict | None) -> dict:
    return {p["symbol"]: p for p in (acct or {}).get("positions", [])}


def diff(cur: dict, prev: dict | None, big_move_pct: float = 5.0) -> dict:
    out: dict = {
        "date": cur["date"],
        "previous_date": prev["date"] if prev else None,
        "total_value": cur.get("total_value"),
        "total_change": (cur.get("total_value") - prev.get("total_value")) if prev else None,
        "accounts": [],
        "new_positions": [],
        "closed_positions": [],
        "quantity_changes": [],
        "movers": [],
        "orders": [],
    }
    ca, pa = _acct_map(cur), _acct_map(prev)
    for key, a in ca.items():
        p = pa.get(key)
        cv = (a.get("portfolio") or {}).get("total_value")
        pv = (p.get("portfolio") or {}).get("total_value") if p else None
        out["accounts"].append({
            "account": key,
            "value": cv,
            "previous_value": pv,
            "change": (cv - pv) if (cv is not None and pv is not None) else None,
            "change_pct": ((cv / pv - 1) if (cv is not None and pv) else None),
            "cash": (a.get("portfolio") or {}).get("cash"),
            "cash_change": ((a.get("portfolio") or {}).get("cash", 0) - (p.get("portfolio") or {}).get("cash", 0)) if p else None,
        })
        cp, pp = _pos_map(a), _pos_map(p)
        for sym, pos in cp.items():
            if sym not in pp:
                out["new_positions"].append({"account": key, "symbol": sym, "quantity": pos["quantity"], "value": pos.get("value")})
            elif abs(pos["quantity"] - pp[sym]["quantity"]) > 1e-6:
                out["quantity_changes"].append({"account": key, "symbol": sym, "from": pp[sym]["quantity"], "to": pos["quantity"]})
            dc = pos.get("day_change_pct")
            if dc is not None and abs(dc) * 100 >= big_move_pct:
                out["movers"].append({"account": key, "symbol": sym, "day_change_pct": dc, "value": pos.get("value"),
                                      "value_change": (pos.get("value") or 0) * (1 - 1 / (1 + dc)) if dc > -1 else None})
        for sym, pos in pp.items():
            if sym not in cp:
                out["closed_positions"].append({"account": key, "symbol": sym, "quantity": pos["quantity"]})
        for o in a.get("recent_orders", []) or []:
            out["orders"].append({"account": key, **o})
    out["movers"].sort(key=lambda m: -abs(m["day_change_pct"]))
    return out
