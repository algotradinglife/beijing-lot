"""Markowitz min-variance portfolio + efficient frontier.

Constraints:  w >= 0,  sum(w) = 1,  optionally w · mu >= target.

Sparse weekly returns (many NaNs). We treat NaN as "no bet placed that week
in that niche", which contributes 0 to the portfolio P&L for the week. So:
  - mu_i = mean over weeks where the niche placed a bet
  - The effective P&L in week t = Σ_i w_i * r_i(t)  with NaN→0
  - Cov is computed on the NaN→0 series
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def fill_zeros(R: pd.DataFrame) -> pd.DataFrame:
    return R.fillna(0.0)


def stats(R: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """mu, cov on NaN→0 weekly returns (per-bet-yuan units)."""
    R0 = fill_zeros(R)
    mu = R0.mean(axis=0).values
    cov = R0.cov().values
    return mu, cov


def min_variance(cov: np.ndarray, mu: np.ndarray | None = None,
                 target: float | None = None) -> np.ndarray:
    n = cov.shape[0]
    x0 = np.ones(n) / n
    cons = [dict(type="eq", fun=lambda w: np.sum(w) - 1.0)]
    if target is not None and mu is not None:
        cons.append(dict(type="ineq", fun=lambda w: w @ mu - target))
    bnds = [(0.0, 1.0)] * n
    res = minimize(lambda w: w @ cov @ w, x0,
                   method="SLSQP", bounds=bnds, constraints=cons,
                   options=dict(maxiter=500, ftol=1e-10))
    if not res.success:
        # fall back to equal weight
        return x0
    w = np.clip(res.x, 0.0, None)
    s = w.sum()
    return w / s if s > 0 else x0


def efficient_frontier(mu: np.ndarray, cov: np.ndarray,
                       n_points: int = 25) -> pd.DataFrame:
    targets = np.linspace(mu.min(), mu.max(), n_points)
    rows = []
    for t in targets:
        w = min_variance(cov, mu=mu, target=t)
        port_mu = float(w @ mu)
        port_var = float(w @ cov @ w)
        rows.append(dict(target=float(t), mu=port_mu,
                         vol=float(np.sqrt(max(port_var, 0.0))),
                         w=w))
    return pd.DataFrame(rows)


def bootstrap_min_var(R: pd.DataFrame, n_boot: int = 200,
                      seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    R0 = fill_zeros(R)
    n_rows = len(R0)
    weights = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_rows, size=n_rows)
        sub = R0.iloc[idx]
        cov = sub.cov().values
        try:
            w = min_variance(cov)
        except Exception:
            w = np.ones(R0.shape[1]) / R0.shape[1]
        weights.append(w)
    W = np.array(weights)
    out = pd.DataFrame(dict(
        niche=R0.columns,
        mean_w=W.mean(axis=0),
        std_w=W.std(axis=0),
        p05=np.quantile(W, 0.05, axis=0),
        p95=np.quantile(W, 0.95, axis=0),
    ))
    return out
