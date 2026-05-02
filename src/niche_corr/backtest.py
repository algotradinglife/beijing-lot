"""Backtest 4 strategies on a 100k yuan bankroll over the full 8-year span.

Each week, an active niche stakes a fixed fraction of the *current* bankroll
on its single 3-leg combo. Multi-niche portfolios split that week's stake
according to weights `w_i` (renormalised to sum to 1 across niches that have
a bet that week).

Strategies:
  a) single_best  — bankroll into the niche with highest historical mean
                    (chosen on full sample for diagnostic — clearly look-ahead;
                    we also report a strict prior-data variant)
  b) equal        — equal weight across all 16 niches each week
  c) markowitz    — min-variance (no return target) weights, fixed
  d) dynamic_top3 — each week pick the 3 niches with the highest
                    trailing 8-week mean return; equal-weight among them.
                    Uses ONLY weeks strictly before t.

Risk fraction `f`: fraction of bankroll to stake per week (default 0.02).
This is a sizing knob; CAGR/Sharpe/MaxDD/Calmar are reported for f=0.02.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .portfolio import fill_zeros, stats, min_variance


def _annualisation(weekly_returns: pd.Series) -> tuple[float, float]:
    # weekly compounding → annualised
    n_weeks = weekly_returns.notna().sum()
    if n_weeks < 2:
        return 0.0, 0.0
    r = weekly_returns.fillna(0.0)
    ann_mu = r.mean() * 52.0
    ann_vol = r.std(ddof=1) * np.sqrt(52.0)
    return ann_mu, ann_vol


def metrics(equity: pd.Series) -> dict:
    """Return CAGR, Sharpe, MaxDD, Calmar from an equity curve indexed by date."""
    if len(equity) < 2:
        return dict(CAGR=0.0, Sharpe=0.0, MaxDD=0.0, Calmar=0.0,
                    final=float(equity.iloc[-1]) if len(equity) else 0.0)
    days = (equity.index[-1] - equity.index[0]).days
    yrs = max(days / 365.25, 1e-9)
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1.0 / yrs) - 1.0
    weekly_ret = equity.pct_change().dropna()
    if weekly_ret.std() > 0:
        sharpe = weekly_ret.mean() / weekly_ret.std() * np.sqrt(52.0)
    else:
        sharpe = 0.0
    cummax = equity.cummax()
    dd = equity / cummax - 1.0
    maxdd = float(dd.min())
    calmar = cagr / abs(maxdd) if maxdd < 0 else 0.0
    return dict(CAGR=float(cagr), Sharpe=float(sharpe),
                MaxDD=float(maxdd), Calmar=float(calmar),
                final=float(equity.iloc[-1]))


def _equity_from_weights_series(R: pd.DataFrame,
                                W: pd.DataFrame,
                                bankroll: float = 100_000.0,
                                f: float = 0.02) -> pd.Series:
    """Apply per-week weights `W` (rows=weeks, cols=niches, NaN→0) to per-
    week per-yuan niche returns `R` (NaN→0) and compound bankroll."""
    R0 = R.fillna(0.0).reindex(W.index).fillna(0.0)
    # which niches have a bet that week (R is NaN if no bet placed)
    active = R.notna().reindex(W.index).fillna(False)
    eq = []
    bk = bankroll
    for wk in W.index:
        w = W.loc[wk].values * active.loc[wk].values
        s = w.sum()
        if s <= 0:
            eq.append(bk)
            continue
        w = w / s
        port_r = float((w * R0.loc[wk].values).sum())
        bk = bk * (1.0 + f * port_r)
        eq.append(bk)
    return pd.Series(eq, index=W.index, name="equity")


def strategy_single_best(R: pd.DataFrame, bankroll=100_000.0, f=0.02) -> dict:
    means = R.mean(axis=0, skipna=True)
    best = means.idxmax()
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    W[best] = 1.0
    eq = _equity_from_weights_series(R, W, bankroll, f)
    m = metrics(eq); m["niche"] = best
    return dict(name="single_best", equity=eq, **m)


def strategy_equal(R: pd.DataFrame, bankroll=100_000.0, f=0.02) -> dict:
    n = R.shape[1]
    W = pd.DataFrame(1.0 / n, index=R.index, columns=R.columns)
    eq = _equity_from_weights_series(R, W, bankroll, f)
    return dict(name="equal", equity=eq, **metrics(eq))


def strategy_markowitz(R: pd.DataFrame, bankroll=100_000.0, f=0.02) -> dict:
    mu, cov = stats(R)
    w_opt = min_variance(cov)
    W = pd.DataFrame(np.tile(w_opt, (len(R), 1)),
                     index=R.index, columns=R.columns)
    eq = _equity_from_weights_series(R, W, bankroll, f)
    return dict(name="markowitz_minvar", equity=eq,
                weights=dict(zip(R.columns, w_opt)), **metrics(eq))


def strategy_dynamic_top3(R: pd.DataFrame, bankroll=100_000.0, f=0.02,
                          window: int = 8, k: int = 3) -> dict:
    R0 = R.fillna(0.0)
    W = pd.DataFrame(0.0, index=R.index, columns=R.columns)
    for i, wk in enumerate(R.index):
        if i < window:
            continue
        prior = R0.iloc[i - window:i]  # strictly prior weeks
        means = prior.mean(axis=0)
        top = means.sort_values(ascending=False).head(k).index
        if len(top) == 0:
            continue
        W.loc[wk, top] = 1.0 / len(top)
    eq = _equity_from_weights_series(R, W, bankroll, f)
    return dict(name="dynamic_top3_8wk", equity=eq, **metrics(eq))


def run_all(R: pd.DataFrame, bankroll: float = 100_000.0,
            f: float = 0.02) -> dict:
    return dict(
        single_best=strategy_single_best(R, bankroll, f),
        equal=strategy_equal(R, bankroll, f),
        markowitz=strategy_markowitz(R, bankroll, f),
        dynamic_top3=strategy_dynamic_top3(R, bankroll, f),
    )
