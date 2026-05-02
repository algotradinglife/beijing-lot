"""Forward Monte Carlo for time-to-converge & ruin analysis.

Methodology:
  - Empirical distribution of (weekly_stake, week_pnl) is bootstrapped to
    project a 1-year (52-week) forward path.
  - For each path we compute final ROI, max drawdown, # hits.
  - 1000 paths per N.

Caveat: this assumes weeks are exchangeable. We inherit the variance and
mean from the test-period combo simulator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def forward_simulate(
    weekly: pd.DataFrame,
    *,
    initial_bankroll: float = 100_000.0,
    horizon_weeks: int = 52,
    n_paths: int = 1000,
    rng_seed: int = 11,
) -> dict:
    """Return summary stats over n_paths forward simulations.

    Each path: 52 weekly PnL draws (with replacement) from the empirical
    weekly PnL series. Bankroll evolves additively (not compounded — at
    52 weeks compounding effect is approximated by the empirical week_roi
    distribution; we use additive dollar PnL for stability)."""
    if weekly.empty:
        return dict(
            P_pos_ROI_1y=float("nan"),
            P_ROI_gt_20pct_1y=float("nan"),
            P_drawdown_lt_20pct=float("nan"),
            E_hits_1y=float("nan"),
            paths_final_ROI=np.array([]),
            paths=np.array([]),
        )
    pnl = weekly["week_pnl"].to_numpy()
    hits = weekly["n_hits"].to_numpy()
    rng = np.random.default_rng(rng_seed)
    n = len(pnl)
    idx = rng.integers(0, n, size=(n_paths, horizon_weeks))
    pnl_paths = pnl[idx]                       # (n_paths, horizon)
    hit_paths = hits[idx]
    cum = np.cumsum(pnl_paths, axis=1)
    bankroll = initial_bankroll + cum          # (n_paths, horizon)

    final_pnl = cum[:, -1]
    final_roi = final_pnl / initial_bankroll
    # Drawdown per path
    paths_with_init = np.concatenate(
        [np.full((n_paths, 1), initial_bankroll), bankroll], axis=1
    )
    peaks = np.maximum.accumulate(paths_with_init, axis=1)
    dd = (paths_with_init - peaks) / peaks
    max_dd = dd.min(axis=1)

    p_pos = float((final_roi > 0).mean())
    p_20 = float((final_roi > 0.20).mean())
    p_dd_safe = float((max_dd > -0.20).mean())
    e_hits = float(hit_paths.sum(axis=1).mean())

    return dict(
        P_pos_ROI_1y=p_pos,
        P_ROI_gt_20pct_1y=p_20,
        P_drawdown_lt_20pct=p_dd_safe,
        E_hits_1y=e_hits,
        median_final_ROI=float(np.median(final_roi)),
        p5_final_ROI=float(np.quantile(final_roi, 0.05)),
        p95_final_ROI=float(np.quantile(final_roi, 0.95)),
        paths_final_ROI=final_roi,
        paths=paths_with_init,
    )


def estimate_ruin_bankroll(
    weekly: pd.DataFrame,
    *,
    horizon_weeks: int = 52,
    n_paths: int = 2000,
    target_ruin: float = 0.05,
    rng_seed: int = 13,
    bankroll_grid: tuple = (10_000, 25_000, 50_000, 100_000, 250_000, 500_000),
) -> dict:
    """For a grid of starting bankrolls, estimate P(ruin within horizon) by
    scaling weekly_pnl proportionally to bankroll changes (assuming
    fractional Kelly maintains stake ∝ bankroll). We use the empirical
    weekly_roi distribution applied multiplicatively."""
    if weekly.empty or "week_roi" not in weekly.columns:
        return dict(min_bankroll_for_safe=None, ruin_table={})
    # Use weekly *PnL fraction of bankroll* as the scale-invariant measure.
    # Approximate from week_pnl / preceding bankroll.
    bb = np.concatenate(([weekly.iloc[0]["bankroll_end"] - weekly.iloc[0]["week_pnl"]],
                          weekly["bankroll_end"].to_numpy()[:-1]))
    bb = np.where(bb <= 0, 1.0, bb)
    growth = 1.0 + weekly["week_pnl"].to_numpy() / bb

    rng = np.random.default_rng(rng_seed)
    n = len(growth)
    idx = rng.integers(0, n, size=(n_paths, horizon_weeks))
    paths = growth[idx]
    cum_growth = np.cumprod(paths, axis=1)
    min_growth = cum_growth.min(axis=1)

    table: dict[int, float] = {}
    safe_bankroll: int | None = None
    for B in bankroll_grid:
        # ruin if min equity <= 0; but we are multiplicative, so equity = B*cum.
        # "Ruin" here = drawdown beyond -90% (essentially busted given practical floor).
        ruin_rate = float((min_growth < 0.10).mean())
        table[int(B)] = ruin_rate
        if safe_bankroll is None and ruin_rate < target_ruin:
            safe_bankroll = int(B)

    return dict(min_bankroll_for_safe=safe_bankroll, ruin_table=table)
