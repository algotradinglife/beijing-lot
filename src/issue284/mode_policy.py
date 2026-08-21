"""Leakage-safe tables for learning CELL versus DIVERGENCE outcome mode."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES


def build_mode_learning_table(
    issue_actions: pd.DataFrame, issue_states: pd.DataFrame
) -> pd.DataFrame:
    """Create one independent row per issue for matched outcome-mode learning."""
    action = issue_actions.loc[
        issue_actions["proposal_family"].eq("DIVERGENCE_WEIGHTED")
    ].copy()
    duplicate = action.duplicated(["issue", "outcome_weight_mode"], keep=False)
    if duplicate.any():
        raise ValueError("mode confirmation contains duplicate issue×mode rows")
    pivot = action.pivot(
        index=["issue", "issue_year"],
        columns="outcome_weight_mode",
        values="realized_roi_pct",
    ).reset_index()
    required_modes = {"CELL_VALUE", "DIVERGENCE_VALUE"}
    if not required_modes.issubset(pivot.columns):
        raise ValueError("both CELL_VALUE and DIVERGENCE_VALUE are required")
    pivot["realized_lift_pct"] = (
        pivot["DIVERGENCE_VALUE"] - pivot["CELL_VALUE"]
    )
    state = issue_states[["issue", *ISSUE_STATE_FEATURES]].copy()
    state["issue"] = state["issue"].astype(str)
    state = state.drop_duplicates("issue")
    pivot["issue"] = pivot["issue"].astype(str)
    table = pivot.merge(state, on="issue", how="left", validate="one_to_one")
    if table[list(ISSUE_STATE_FEATURES)].isna().all(axis=1).any():
        raise ValueError("mode table contains an issue without pre-event state")
    return table.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def apply_mode_policy(
    validation: pd.DataFrame, predicted_lift_pct: np.ndarray, *, policy: str
) -> pd.DataFrame:
    """Use divergence only when its pre-event predicted lift is positive."""
    prediction = np.asarray(predicted_lift_pct, dtype=float)
    if prediction.shape != (len(validation),):
        raise ValueError("one mode prediction is required per issue")
    result = validation[
        [
            "issue",
            "issue_year",
            "CELL_VALUE",
            "DIVERGENCE_VALUE",
            "realized_lift_pct",
        ]
    ].copy()
    result["predicted_lift_pct"] = prediction
    use_divergence = prediction > 0.0
    result["selected_mode"] = np.where(
        use_divergence, "DIVERGENCE_VALUE", "CELL_VALUE"
    )
    result["realized_roi_pct"] = np.where(
        use_divergence, result["DIVERGENCE_VALUE"], result["CELL_VALUE"]
    )
    result["matched_lift_to_cell_pct"] = (
        result["realized_roi_pct"] - result["CELL_VALUE"]
    )
    result["policy"] = policy
    return result
