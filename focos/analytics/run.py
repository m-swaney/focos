"""Compute portfolio analytics from a positions frame and return plain dicts (JSON-ready)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .. import paths, settings
from . import exposure, metadata, optimizer, prices, risk, tax, valuation


def compute(pos: pd.DataFrame, cfg: dict | None = None, mode: str = "daily", lots: list[dict] | None = None,
            live_prices: dict[str, float] | None = None, tearsheet_dir: Path | None = None,
            heavy: bool = True) -> dict:
    """pos columns: account, symbol, quantity, avg_cost.

    live_prices: symbol->price from Robinhood quotes; when given they override Yahoo's last close for
    valuation so daily numbers match the broker. heavy=False skips optimizer/tear sheet/heatmap.
    """
    cfg = cfg or settings.analytics()
    years = int(cfg.get(f"{mode}_years", cfg.get("years", 3)))
    bench = cfg["benchmark"]
    symbols = sorted(pos["symbol"].unique())
    px, stale = prices.fetch_prices(sorted(set(symbols) | {bench}), years)
    last = px.ffill().iloc[-1].copy()
    if live_prices:
        for s, p in live_prices.items():
            if s in last.index and p:
                last[s] = p
    asof = str(px.index[-1].date()) if not live_prices else str(date.today())

    meta = metadata.fetch_metadata(symbols, cfg.get("etf_labels", {}))
    df = valuation.value_positions(pos, last)
    total = float(df["value"].sum())
    acct = valuation.account_summary(df)

    res: dict = {
        "meta": {"asof": asof, "years": years, "mode": mode, "prices_stale": stale, "benchmark": bench,
                 "total_value": total, "total_cost": float(df["cost"].sum())},
        "accounts": [{"account": a, **{k: (None if pd.isna(v) else float(v)) for k, v in r.items()}}
                     for a, r in acct.iterrows()],
        "positions": [{k: (None if (isinstance(v, float) and pd.isna(v)) else (float(v) if isinstance(v, (int, float)) and k not in ("account", "symbol") else v))
                       for k, v in r.items()} for r in df.to_dict("records")],
        "concentration": valuation.concentration(df),
    }

    lt = exposure.look_through(df, meta)
    res["look_through"] = {k: {"value": float(v), "weight": float(v / total)} for k, v in lt.items()}
    sec = exposure.sector_exposure(df, meta)
    res["sectors"] = {k: {"value": float(v), "weight": float(v / total)} for k, v in sec.items()}

    cw = exposure.class_weights(df, cfg.get("classes", {}))
    res["class_weights"] = {a: {r.asset_class: float(r.weight) for r in g.itertuples()} for a, g in cw.groupby("account")}
    res["drift"] = _drift(res["class_weights"], settings.profile().get("targets") or {},
                          {a["account"]: a.get("value") or 0.0 for a in res["accounts"]})

    combined = df.groupby("symbol")["value"].sum()
    port_r = risk.portfolio_returns(px, combined)
    bench_r = px[bench].pct_change().dropna()
    try:
        r = risk.risk_stats(port_r, bench_r)
        corr, avg = risk.correlation(px, symbols)
        r["avg_pairwise_correlation"] = avg
        res["risk"] = r
        if heavy:
            out_dir = tearsheet_dir or paths.TEARSHEETS
            risk.heatmap(corr, out_dir / "correlation.png")
            risk.tearsheet(port_r, bench_r, out_dir / "tearsheet.html", "Portfolio (current weights) vs SPY")
            res["risk"]["artifacts"] = {"heatmap": str(out_dir / "correlation.png"), "tearsheet": str(out_dir / "tearsheet.html")}
    except Exception as e:  # keep the pipeline alive if quantstats misbehaves
        res["risk"] = None
        res["meta"]["risk_error"] = str(e)

    if heavy:
        try:
            res["optimizer"] = optimizer.optimizer_whatifs(px, combined, float(cfg["max_weight"]))
        except Exception as e:
            res["optimizer"] = None
            res["meta"]["optimizer_error"] = str(e)
    else:
        res["optimizer"] = None

    taxable = pos[pos["account"].isin(settings.accounts_by_role("taxable"))]
    if lots:
        res["tax_split"] = tax.from_lots(lots, last)
    elif (paths.ROOT / "data" / "tax_lot_summary.csv").exists() and not taxable.empty:
        res["tax_split"] = tax.from_summary_csv(paths.ROOT / "data" / "tax_lot_summary.csv", last)
    else:
        res["tax_split"] = {"available": False}
    return res


def _drift(class_weights: dict, targets: dict, account_values: dict | None = None,
           role_to_accounts: dict[str, list[str]] | None = None) -> dict:
    """targets: {taxable: {class: pct}, roth_ira: {class: pct}} keyed by role. Accounts sharing a role are
    combined, weighted by account value. Output is keyed by role."""
    if role_to_accounts is None:
        role_to_accounts = {}
        for a in settings.brokerage():
            role_to_accounts.setdefault(a.get("role") or "other", []).append(a["key"])
    account_values = account_values or {}
    out = {}
    for role, tgt in (targets or {}).items():
        keys = [k for k in role_to_accounts.get(role, [role]) if class_weights.get(k)]
        if not keys:
            continue
        acct = role
        cur = _combine_weights({k: class_weights[k] for k in keys}, account_values)
        rows = []
        for cls, t in tgt.items():
            c = cur.get(cls, 0.0)
            rows.append({"asset_class": cls, "target": float(t) / 100.0, "current": c, "drift": c - float(t) / 100.0})
        for cls, c in cur.items():
            if cls not in tgt:
                rows.append({"asset_class": cls, "target": 0.0, "current": c, "drift": c})
        out[acct] = sorted(rows, key=lambda r: -abs(r["drift"]))
    return out


def _combine_weights(per_account: dict[str, dict[str, float]], values: dict[str, float]) -> dict[str, float]:
    if len(per_account) == 1:
        return dict(next(iter(per_account.values())))
    weights = {k: float(values.get(k) or 0.0) for k in per_account}
    total = sum(weights.values())
    if total <= 0:
        weights = {k: 1.0 for k in per_account}
        total = float(len(per_account))
    out: dict[str, float] = {}
    for k, cw in per_account.items():
        for cls, w in cw.items():
            out[cls] = out.get(cls, 0.0) + float(w) * weights[k] / total
    return out


def split_outputs(res: dict) -> dict[str, dict]:
    """Split the big result into the files Stage C reads."""
    portfolio = {k: v for k, v in res.items() if k not in ("risk", "optimizer", "tax_split", "drift")}
    return {
        "portfolio.json": portfolio,
        "risk.json": res.get("risk") or {"available": False, "error": res["meta"].get("risk_error")},
        "optimizer.json": res.get("optimizer") or {"available": False},
        "tax_lots.json": res.get("tax_split") or {"available": False},
        "drift.json": res.get("drift") or {},
    }
