"""Budget-matched development targets for action-conditioned learning.

The raw counterfactual PnL surface confounds action quality with requested
turnover: a K512 action risks 64 times as much cash as K8.  These helpers
express every active action at one common reference stake before any ranking or
conditional profiling.  They are outcome-aware training/diagnostic targets and
must never be passed to inference feature construction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

INITIAL_CAPITAL = 100_000.0
REFERENCE_STAKE = 16.0
REQUIRED = {
    "issue",
    "issue_year",
    "action_key",
    "n",
    "k",
    "generator",
    "stake_total",
    "mean_pnl",
}


def add_budget_matched_targets(
    counterfactuals: pd.DataFrame,
    *,
    reference_stake: float = REFERENCE_STAKE,
    initial_capital: float = INITIAL_CAPITAL,
) -> pd.DataFrame:
    """Return matched-risk labels plus within-family marginal-K diagnostics.

    ``budget_matched_pnl`` linearly rescales the observed action return to the
    reference stake.  It is a comparison label, not a claim that fractional or
    resampled tickets were actually funded.  Marginal K columns retain the raw
    nested-grid diagnostic and are explicitly noisy because ticket draws at
    adjacent K anchors are not guaranteed to be nested.
    """

    missing = REQUIRED.difference(counterfactuals.columns)
    if missing:
        raise ValueError(f"counterfactual target fields missing: {sorted(missing)}")
    if reference_stake <= 0 or initial_capital <= 0:
        raise ValueError("reference_stake and initial_capital must be positive")

    frame = counterfactuals.copy()
    active = frame["generator"].ne("NO_BET")
    invalid = active & frame["stake_total"].le(0)
    if invalid.any():
        raise ValueError("active action has non-positive stake_total")

    frame["return_per_cny"] = 0.0
    frame.loc[active, "return_per_cny"] = (
        frame.loc[active, "mean_pnl"] / frame.loc[active, "stake_total"]
    )
    frame["budget_matched_stake"] = np.where(active, reference_stake, 0.0)
    frame["budget_matched_pnl"] = (
        frame["return_per_cny"] * frame["budget_matched_stake"]
    )
    frame["budget_matched_utility_bps"] = 10_000.0 * np.log1p(
        frame["budget_matched_pnl"] / initial_capital
    )

    frame["marginal_k_stake"] = np.nan
    frame["marginal_k_pnl"] = np.nan
    frame["marginal_k_pnl_per_cny"] = np.nan
    frame["marginal_k_continue_observed"] = False
    active_index = frame.index[active]
    ordered = frame.loc[active_index].sort_values(
        ["issue", "n", "generator", "k", "action_key"]
    )
    groups = ordered.groupby(["issue", "n", "generator"], sort=False)
    delta_stake = groups["stake_total"].diff()
    delta_pnl = groups["mean_pnl"].diff()
    first = groups.cumcount().eq(0)
    delta_stake.loc[first] = ordered.loc[first, "stake_total"]
    delta_pnl.loc[first] = ordered.loc[first, "mean_pnl"]
    marginal = delta_pnl / delta_stake.replace(0, np.nan)
    frame.loc[ordered.index, "marginal_k_stake"] = delta_stake
    frame.loc[ordered.index, "marginal_k_pnl"] = delta_pnl
    frame.loc[ordered.index, "marginal_k_pnl_per_cny"] = marginal
    frame.loc[ordered.index, "marginal_k_continue_observed"] = marginal.gt(0)

    # Distributional labels avoid turning a hindsight argmax into a hard class.
    frame["budget_matched_rank_pct"] = frame.groupby("issue")[
        "budget_matched_utility_bps"
    ].rank(method="average", pct=True)
    best = frame.groupby("issue")["budget_matched_utility_bps"].transform("max")
    frame["budget_matched_regret_bps"] = best - frame["budget_matched_utility_bps"]
    return frame.sort_values(["issue_year", "issue", "action_key"]).reset_index(drop=True)


def conditional_budget_profile(
    joined: pd.DataFrame,
    *,
    bins: int = 4,
) -> pd.DataFrame:
    """Summarize budget-matched target distributions by pre-event state bins."""

    required = {
        "issue",
        "n",
        "k",
        "generator",
        "n_matches",
        "divergence_abs_mean",
        "budget_matched_pnl",
    }
    missing = required.difference(joined.columns)
    if missing:
        raise ValueError(f"conditional profile fields missing: {sorted(missing)}")
    frame = joined.copy()
    frame["breadth_bin"] = pd.qcut(frame["n_matches"], bins, duplicates="drop")
    frame["divergence_bin"] = pd.qcut(
        frame["divergence_abs_mean"], bins, duplicates="drop"
    )
    return (
        frame.groupby(
            ["breadth_bin", "divergence_bin", "n", "k", "generator"],
            observed=True,
        )
        .agg(
            issues=("issue", "nunique"),
            mean_budget_pnl=("budget_matched_pnl", "mean"),
            median_budget_pnl=("budget_matched_pnl", "median"),
            positive_issue_fraction=(
                "budget_matched_pnl",
                lambda x: float((x > 0).mean()),
            ),
        )
        .reset_index()
        .sort_values(
            ["breadth_bin", "divergence_bin", "mean_budget_pnl"],
            ascending=[True, True, False],
        )
        .reset_index(drop=True)
    )
