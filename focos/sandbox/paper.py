"""Mark paper proposals to market and build the scorecard (paper and live share the same math).

A proposal file becomes a paper position on the first snapshot dated after the proposal date, filled
at that snapshot's last quote. P&L is measured against SPY over the same window.
"""
from __future__ import annotations

from datetime import date

from .. import paths, settings

def paper_file():
    return paths.SANDBOX / "paper_positions.json"


def scorecard_file():
    return paths.SANDBOX / "scorecard.json"




def _snapshots() -> list[dict]:
    from .. import holdings

    return [settings.read_json(f, {}) for f in holdings.snapshot_files()]


def _quote(snap: dict, symbol: str) -> float | None:
    for q in snap.get("quotes", []):
        if q.get("symbol") == symbol and q.get("last"):
            return float(q["last"])
    return None


def update(today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    snaps = _snapshots()
    if not snaps:
        return {"available": False, "reason": "no snapshots"}
    latest = snaps[-1]
    positions: dict = settings.read_json(paper_file(), {}) or {}

    # open new paper positions
    for f in sorted(paths.PROPOSALS.glob("*.json")):
        p = settings.read_json(f, {}) or {}
        rid = str(p.get("ref_id") or f.stem)
        if not p.get("paper") or rid in positions:
            continue
        fill_snap = next((s for s in snaps if s["date"] > str(p.get("date", "9999"))), None)
        if not fill_snap:
            continue
        px = _quote(fill_snap, str(p.get("symbol", "")).upper())
        spy = _quote(fill_snap, "SPY")
        if px is None:
            continue
        positions[rid] = {"ref_id": rid, "symbol": str(p.get("symbol")).upper(), "side": p.get("side", "buy"),
                          "dollar_amount": float(p.get("dollar_amount") or 0), "proposed": p.get("date"),
                          "fill_date": fill_snap["date"], "fill_price": px, "spy_at_fill": spy,
                          "horizon_days": p.get("horizon_days"), "stop_loss": p.get("stop_loss"),
                          "thesis": p.get("thesis"), "status": "open"}

    # mark to market
    spy_now = _quote(latest, "SPY")
    rows = []
    for rid, pos in positions.items():
        px = _quote(latest, pos["symbol"])
        if px is None or pos.get("status") == "closed":
            rows.append(pos)
            continue
        sign = 1 if pos["side"] == "buy" else -1
        ret = sign * (px / pos["fill_price"] - 1)
        spy_ret = (spy_now / pos["spy_at_fill"] - 1) if (spy_now and pos.get("spy_at_fill")) else None
        pos.update({"current_price": px, "asof": latest["date"], "return_pct": ret,
                    "spy_return_pct": spy_ret, "alpha_pct": (ret - spy_ret) if spy_ret is not None else None,
                    "pnl_usd": ret * pos["dollar_amount"]})
        try:
            days = (date.fromisoformat(latest["date"]) - date.fromisoformat(pos["fill_date"])).days
            pos["days_held"] = days
            if pos.get("horizon_days") and days >= int(pos["horizon_days"]):
                pos["status"] = "horizon_reached"
            if pos.get("stop_loss") and float(pos["stop_loss"]) > 0 and px <= float(pos["stop_loss"]) and pos["side"] == "buy":
                pos["status"] = "stopped"
        except Exception:
            pass
        rows.append(pos)
    settings.write_json(paper_file(), positions)

    scored = [r for r in rows if r.get("return_pct") is not None]
    n = len(scored)
    wins = sum(1 for r in scored if r["return_pct"] > 0)
    beats = sum(1 for r in scored if (r.get("alpha_pct") or 0) > 0)
    sc = {
        "available": True,
        "asof": latest["date"],
        "n_positions": n,
        "hit_rate": (wins / n) if n else None,
        "beat_spy_rate": (beats / n) if n else None,
        "avg_return_pct": (sum(r["return_pct"] for r in scored) / n) if n else None,
        "avg_alpha_pct": (sum(r["alpha_pct"] for r in scored if r.get("alpha_pct") is not None) / n) if n else None,
        "total_pnl_usd": sum(r.get("pnl_usd") or 0 for r in scored),
        "positions": rows,
    }
    settings.write_json(scorecard_file(), sc)
    return sc
