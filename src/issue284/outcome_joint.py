"""Matched outcome-mode interaction tables for the #284 subset screen."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ACTION_COLUMNS = [
    "n",
    "proposal_family",
    "outcome_weight_mode",
    "generator",
    "requested_k",
]


def build_issue_action_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Average stream and subset nuisance while retaining all action dimensions."""
    required = {
        "issue",
        "issue_year",
        "subset_id",
        "stream_replica",
        "normalized_pnl_cny100",
        "model_expected_pnl_cny100",
        *ACTION_COLUMNS,
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"outcome joint grid missing columns: {sorted(missing)}")
    if raw["issue_year"].ge(2024).any():
        raise ValueError("2024+ outcome row entered the joint mode table")
    subset_keys = ["issue", "issue_year", *ACTION_COLUMNS, "subset_id"]
    subset = raw.groupby(subset_keys, as_index=False).agg(
        realized_roi_pct=("normalized_pnl_cny100", "mean"),
        expected_roi_pct=("model_expected_pnl_cny100", "mean"),
        stream_replicas=("stream_replica", "nunique"),
    )
    family = _collapse(subset, ["issue", "issue_year", *ACTION_COLUMNS])
    ensemble_keys = [
        "issue",
        "issue_year",
        "n",
        "outcome_weight_mode",
        "generator",
        "requested_k",
    ]
    ensemble = _collapse(subset, ensemble_keys)
    ensemble["proposal_family"] = "ENSEMBLE"
    table = pd.concat([family, ensemble], ignore_index=True)
    table["action_key"] = (
        table["outcome_weight_mode"]
        + "_N"
        + table["n"].astype(str)
        + "_"
        + table["generator"]
        + "_K"
        + table["requested_k"].astype(str)
        + "_F"
        + table["proposal_family"]
    )
    cell = table.loc[
        table["outcome_weight_mode"].eq("CELL_VALUE"),
        [
            "issue",
            "n",
            "proposal_family",
            "generator",
            "requested_k",
            "realized_roi_pct",
        ],
    ].rename(columns={"realized_roi_pct": "matched_cell_roi_pct"})
    match_keys = [
        "issue",
        "n",
        "proposal_family",
        "generator",
        "requested_k",
    ]
    table = table.merge(cell, on=match_keys, how="left", validate="many_to_one")
    if table["matched_cell_roi_pct"].isna().any():
        raise ValueError("an outcome action is missing its matched CELL_VALUE control")
    table["lift_to_cell_pct"] = (
        table["realized_roi_pct"] - table["matched_cell_roi_pct"]
    )
    return table.sort_values(["issue_year", "issue", "action_key"]).reset_index(
        drop=True
    )


def summarize_actions(table: pd.DataFrame) -> pd.DataFrame:
    """Summarize every fixed action and its matched lift to CELL_VALUE."""
    rows: list[dict[str, float | int | str]] = []
    for action, group in table.groupby(ACTION_COLUMNS, sort=True):
        realized = group["realized_roi_pct"].to_numpy(float)
        lift = group["lift_to_cell_pct"].to_numpy(float)
        annual = group.groupby("issue_year")["realized_roi_pct"].mean()
        development = group.loc[group["issue_year"].le(2022), "realized_roi_pct"]
        holdout = group.loc[group["issue_year"].eq(2023), "realized_roi_pct"]
        row = dict(zip(ACTION_COLUMNS, action, strict=True))
        row.update(
            {
                "issues": len(group),
                "mean_roi_pct": realized.mean(),
                "ex_largest_roi_pct": _ex_largest(realized),
                "median_issue_roi_pct": np.median(realized),
                "mean_lift_to_cell_pct": lift.mean(),
                "ex_largest_lift_to_cell_pct": _ex_largest(lift),
                "positive_lift_fraction": np.mean(lift > 0),
                "positive_years": int((annual > 0).sum()),
                "development_roi_pct": development.mean(),
                "holdout_roi_pct": holdout.mean(),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["development_roi_pct", "holdout_roi_pct"], ascending=False
    )


def annual_actions(table: pd.DataFrame) -> pd.DataFrame:
    return (
        table.groupby([*ACTION_COLUMNS, "issue_year"], as_index=False)
        .agg(
            roi_pct=("realized_roi_pct", "mean"),
            lift_to_cell_pct=("lift_to_cell_pct", "mean"),
            issues=("issue", "nunique"),
        )
        .sort_values([*ACTION_COLUMNS, "issue_year"])
    )


def development_holdout_rank_spearman(summary: pd.DataFrame) -> float:
    statistic = spearmanr(
        summary["development_roi_pct"], summary["holdout_roi_pct"]
    ).statistic
    return float(statistic)


def _collapse(subset: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return subset.groupby(keys, as_index=False).agg(
        realized_roi_pct=("realized_roi_pct", "mean"),
        expected_roi_pct=("expected_roi_pct", "mean"),
        subsets=("subset_id", "nunique"),
        stream_replicas_max=("stream_replicas", "max"),
    )


def _ex_largest(values: np.ndarray) -> float:
    if len(values) < 2:
        return float("nan")
    return float((values.sum() - values.max()) / (len(values) - 1))
