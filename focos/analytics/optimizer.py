"""PyPortfolioOpt what-ifs: current vs min-volatility vs max-Sharpe under a per-name cap."""
from __future__ import annotations

import numpy as np
import pandas as pd


def optimizer_whatifs(px: pd.DataFrame, current_w: pd.Series, max_weight: float) -> dict:
    from pypfopt import EfficientFrontier, expected_returns, risk_models

    tickers = [t for t in current_w.index if t in px.columns]
    prices = px[tickers].dropna()
    mu = expected_returns.capm_return(prices)
    S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()

    def solve(kind: str) -> pd.Series:
        ef = EfficientFrontier(mu, S, weight_bounds=(0, max_weight))
        ef.min_volatility() if kind == "min_vol" else ef.max_sharpe()
        return pd.Series(ef.clean_weights())

    def perf(w: pd.Series) -> tuple[float, float, float]:
        v = w.reindex(tickers).fillna(0).values
        ret = float(v @ mu.values)
        vol = float(np.sqrt(v @ S.values @ v))
        return ret, vol, (ret - 0.02) / vol if vol else float("nan")

    cw = current_w[tickers] / current_w[tickers].sum()
    out = {}
    for label, w in [("current", cw), ("min_vol", solve("min_vol")), ("max_sharpe", solve("max_sharpe"))]:
        er, vol, sh = perf(w)
        out[label] = {
            "expected_return": er,
            "volatility": vol,
            "sharpe": sh,
            "weights": {k: round(float(v), 4) for k, v in w.items() if float(v) > 0.0005},
        }
    out["max_weight"] = max_weight
    return out
