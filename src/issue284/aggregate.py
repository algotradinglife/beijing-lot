"""Issue×N distribution tables for reliable parameter learning."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES

AGGREGATE_FEATURES = (
    *ISSUE_STATE_FEATURES,
    "n",
    "n_fraction_of_issue",
    "n_log_support",
    "expected_mean",
    "expected_std",
    "expected_q10",
    "expected_q50",
    "expected_q90",
    "expected_family_range",
    "expected_margin_to_n7",
    "subset_count",
)


def build_issue_n_table(
    labels: pd.DataFrame, issue_state: pd.DataFrame
) -> pd.DataFrame:
    """Aggregate nested subsets without leaking realized outcomes into features."""

    required = {
        "issue",
        "issue_year",
        "issue_match_count",
        "n",
        "proposal_family",
        "subset_id",
        "normalized_pnl_cny100",
        "model_expected_pnl_cny100",
    }
    missing = required - set(labels)
    if missing:
        raise ValueError(f"subset labels missing columns: {sorted(missing)}")
    frame = labels.copy()
    frame["issue"] = frame["issue"].astype(str)
    grouped = frame.groupby(
        ["issue", "issue_year", "issue_match_count", "n"], as_index=False
    ).agg(
        subset_count=("subset_id", "nunique"),
        expected_mean=("model_expected_pnl_cny100", "mean"),
        expected_std=("model_expected_pnl_cny100", "std"),
        expected_q10=("model_expected_pnl_cny100", lambda values: values.quantile(0.10)),
        expected_q50=("model_expected_pnl_cny100", "median"),
        expected_q90=("model_expected_pnl_cny100", lambda values: values.quantile(0.90)),
        realized_mean=("normalized_pnl_cny100", "mean"),
        realized_std=("normalized_pnl_cny100", "std"),
        realized_q10=("normalized_pnl_cny100", lambda values: values.quantile(0.10)),
        realized_q50=("normalized_pnl_cny100", "median"),
        realized_q90=("normalized_pnl_cny100", lambda values: values.quantile(0.90)),
    )
    family = (
        frame.groupby(["issue", "n", "proposal_family"])[
            "model_expected_pnl_cny100"
        ]
        .mean()
        .groupby(["issue", "n"])
        .agg(lambda values: float(values.max() - values.min()))
        .rename("expected_family_range")
        .reset_index()
    )
    grouped = grouped.merge(family, on=["issue", "n"], validate="one_to_one")
    n7 = grouped.loc[grouped["n"].eq(7), ["issue", "expected_mean", "realized_mean"]].rename(
        columns={
            "expected_mean": "n7_expected_mean",
            "realized_mean": "n7_realized_mean",
        }
    )
    if n7["issue"].duplicated().any():
        raise ValueError("N7 aggregate baseline is not unique")
    grouped = grouped.merge(n7, on="issue", how="left", validate="many_to_one")
    grouped["expected_margin_to_n7"] = (
        grouped["expected_mean"] - grouped["n7_expected_mean"]
    )
    grouped["realized_lift_to_n7"] = (
        grouped["realized_mean"] - grouped["n7_realized_mean"]
    )
    grouped["residual_to_expected"] = (
        grouped["realized_mean"] - grouped["expected_mean"]
    )
    grouped["n_fraction_of_issue"] = grouped["n"] / grouped[
        "issue_match_count"
    ].clip(lower=1)
    grouped["n_log_support"] = grouped["n"] * np.log(3.0)

    state = issue_state.copy()
    state["issue"] = state["issue"].astype(str)
    state = state[["issue", *ISSUE_STATE_FEATURES]].drop_duplicates("issue")
    result = grouped.merge(state, on="issue", how="left", validate="many_to_one")
    if result[list(ISSUE_STATE_FEATURES)].isna().all(axis=1).any():
        raise ValueError("an issue is missing all pre-event state features")
    return result.sort_values(["issue_year", "issue", "n"]).reset_index(drop=True)
