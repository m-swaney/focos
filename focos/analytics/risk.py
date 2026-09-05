"""Risk statistics, correlation, and QuantStats tear sheets."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def portfolio_returns(px: pd.DataFrame, weights: pd.Series) -> pd.Series:
    cols = [c for c in weights.index if c in px.columns]
    rets = px[cols].pct_change().dropna(how="all")
    w = weights[cols] / weights[cols].sum()
    return (rets.fillna(0) * w).sum(axis=1)


def risk_stats(r: pd.Series, bench: pd.Series) -> dict:
    import quantstats as qs

    aligned = pd.concat([r, bench], axis=1, join="inner").dropna()
    r, bench = aligned.iloc[:, 0], aligned.iloc[:, 1]
    return {
        "cagr": float(qs.stats.cagr(r)),
        "benchmark_cagr": float(qs.stats.cagr(bench)),
        "volatility": float(qs.stats.volatility(r)),
        "sharpe": float(qs.stats.sharpe(r)),
        "sortino": float(qs.stats.sortino(r)),
        "max_drawdown": float(qs.stats.max_drawdown(r)),
        "benchmark_max_drawdown": float(qs.stats.max_drawdown(bench)),
        "beta": float(qs.stats.greeks(r, bench)["beta"]),
        "worst_day": float(r.min()),
        "worst_month": float(qs.stats.worst(r, aggregate="M")),
        "days": int(len(r)),
        "start": str(r.index[0].date()),
        "end": str(r.index[-1].date()),
    }


def correlation(px: pd.DataFrame, symbols: list[str]) -> tuple[pd.DataFrame, float]:
    cols = [s for s in symbols if s in px.columns]
    corr = px[cols].pct_change().dropna().corr()
    vals = corr.values[np.triu_indices_from(corr.values, 1)]
    return corr, float(vals.mean()) if len(vals) else float("nan")


def heatmap(corr: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)), corr.columns, rotation=90)
    ax.set_yticks(range(len(corr)), corr.index)
    fig.colorbar(im, ax=ax, fraction=0.03)
    ax.set_title("Daily return correlation")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)


def tearsheet(port_r: pd.Series, bench_r: pd.Series, out: Path, title: str) -> None:
    import quantstats as qs

    out.parent.mkdir(parents=True, exist_ok=True)
    qs.reports.html(port_r, benchmark=bench_r, output=str(out), title=title, download_filename=out.name)
