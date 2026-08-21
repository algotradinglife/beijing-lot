"""Cross-year diagnostics for the #282 outcome-value action surface."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ACTION_COLUMNS = ["selector", "outcome_weight_mode", "n", "generator", "k"]
REQUIRED_COLUMNS = [
    "issue",
    "issue_year",
    "return_per_cny_mean",
    *ACTION_COLUMNS,
]


def load_counterfactual_labels(paths: Iterable[Path]) -> pd.DataFrame:
    """Load and validate one row per issue and fixed outcome-surface action."""
    resolved = sorted(Path(path) for path in paths)
    if not resolved:
        raise FileNotFoundError("no counterfactual label parquet files found")
    panel = pd.concat((pd.read_parquet(path) for path in resolved), ignore_index=True)
    missing = sorted(set(REQUIRED_COLUMNS) - set(panel.columns))
    if missing:
        raise ValueError(f"counterfactual labels missing columns: {missing}")
    if panel["issue_year"].ge(2024).any():
        raise ValueError("2024+ outcome seal violated")
    duplicate = panel.duplicated(["issue", *ACTION_COLUMNS], keep=False)
    if duplicate.any():
        raise ValueError("duplicate issue×action counterfactual labels")
    return panel.sort_values(["issue_year", "issue", *ACTION_COLUMNS]).reset_index(
        drop=True
    )


def summarize_actions(
    panel: pd.DataFrame, *, development_end: int = 2022, holdout_year: int = 2023
) -> pd.DataFrame:
    """Summarize the fixed action surface without selecting on holdout outcomes."""
    rows: list[dict[str, float | int | str]] = []
    for action, group in panel.groupby(ACTION_COLUMNS, sort=True):
        values = group["return_per_cny_mean"].to_numpy(float) * 100.0
        annual = group.groupby("issue_year")["return_per_cny_mean"].mean() * 100.0
        development = group.loc[
            group["issue_year"].le(development_end), "return_per_cny_mean"
        ]
        holdout = group.loc[
            group["issue_year"].eq(holdout_year), "return_per_cny_mean"
        ]
        row = dict(zip(ACTION_COLUMNS, action, strict=True))
        row.update(
            {
                "issues": len(group),
                "mean_roi_pct": values.mean(),
                "median_issue_roi_pct": np.median(values),
                "ex_largest_roi_pct": _ex_largest(values),
                "positive_issue_fraction": np.mean(values > 0),
                "positive_years": int((annual > 0).sum()),
                "development_roi_pct": development.mean() * 100.0,
                "holdout_roi_pct": holdout.mean() * 100.0,
                "development_to_holdout_delta_pct": (
                    holdout.mean() - development.mean()
                )
                * 100.0,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["development_roi_pct", "holdout_roi_pct"], ascending=False
    )


def summarize_focus_modes(
    panel: pd.DataFrame,
    *,
    selector: str = "ALL",
    n: int = 7,
    generator: str = "TOP_VALUE",
    k: int = 8,
    draws: int = 5_000,
    seed: int = 284_991,
) -> pd.DataFrame:
    """Issue-block bootstrap for the fixed N7/TOP/K8 value-mode comparison."""
    focus = panel.loc[
        panel["selector"].eq(selector)
        & panel["n"].eq(n)
        & panel["generator"].eq(generator)
        & panel["k"].eq(k)
    ]
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []
    for mode, group in focus.groupby("outcome_weight_mode", sort=True):
        values = group.sort_values("issue")["return_per_cny_mean"].to_numpy(float)
        bootstrap = np.empty(draws, dtype=float)
        for draw in range(draws):
            bootstrap[draw] = rng.choice(values, len(values), replace=True).mean()
        annual = group.groupby("issue_year")["return_per_cny_mean"].mean()
        development = group.loc[group["issue_year"].le(2022), "return_per_cny_mean"]
        holdout = group.loc[group["issue_year"].eq(2023), "return_per_cny_mean"]
        rows.append(
            {
                "outcome_weight_mode": mode,
                "issues": len(group),
                "mean_roi_pct": values.mean() * 100.0,
                "median_issue_roi_pct": np.median(values) * 100.0,
                "ex_largest_roi_pct": _ex_largest(values) * 100.0,
                "bootstrap_low_pct": np.quantile(bootstrap, 0.025) * 100.0,
                "bootstrap_high_pct": np.quantile(bootstrap, 0.975) * 100.0,
                "bootstrap_probability_positive": np.mean(bootstrap > 0),
                "positive_years": int((annual > 0).sum()),
                "development_roi_pct": development.mean() * 100.0,
                "holdout_roi_pct": holdout.mean() * 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values("development_roi_pct", ascending=False)


def annual_action_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Return the issue-weighted annual ROI of every fixed action."""
    return (
        panel.groupby([*ACTION_COLUMNS, "issue_year"], as_index=False)
        .agg(
            roi_pct=("return_per_cny_mean", lambda values: values.mean() * 100.0),
            issues=("issue", "nunique"),
        )
        .sort_values([*ACTION_COLUMNS, "issue_year"])
    )


def development_holdout_rank_spearman(action_summary: pd.DataFrame) -> float:
    """Measure whether development action ordering transfers to the holdout year."""
    result = spearmanr(
        action_summary["development_roi_pct"], action_summary["holdout_roi_pct"]
    ).statistic
    return float(result)


def _ex_largest(values: np.ndarray) -> float:
    if len(values) < 2:
        return float("nan")
    return float((values.sum() - values.max()) / (len(values) - 1))
