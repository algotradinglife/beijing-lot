"""Leakage-safe issue/action features for conditional policy learning."""

from __future__ import annotations

import numpy as np
import pandas as pd

FORBIDDEN = {
    "pnl_cny_mean",
    "pnl_cny_q10",
    "pnl_cny_std",
    "return_per_cny_mean",
    "normalized_pnl_cny100",
    "positive_stream_fraction",
    "hit_rate_mean",
}

ISSUE_STATE_FEATURES = (
    "n_matches",
    "n_accepted",
    "accepted_fraction",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "prob_entropy_mean",
    "prob_top_mean",
    "prob_top_q90",
    "value_best_mean",
    "value_best_std",
    "value_best_q50",
    "value_best_q90",
    "value_margin_mean",
    "value_interval_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
)


def build_action_feature_frame(
    labels: pd.DataFrame, issue_states: pd.DataFrame
) -> pd.DataFrame:
    """Construct explicit ``phi(X,a)`` without reading settlement columns."""

    missing_label = {
        "issue",
        "selector",
        "outcome_weight_mode",
        "n",
        "generator",
        "k",
        "selected_match_count",
        "stake_cny_mean",
    }.difference(labels.columns)
    missing_state = {"issue", *ISSUE_STATE_FEATURES}.difference(issue_states.columns)
    if missing_label or missing_state:
        raise ValueError(
            f"feature inputs incomplete: labels={sorted(missing_label)} "
            f"states={sorted(missing_state)}"
        )
    states = issue_states[["issue", *ISSUE_STATE_FEATURES]].copy()
    states["issue"] = states["issue"].astype(str)
    states = states.drop_duplicates("issue")
    action = labels[
        [
            "issue",
            "selector",
            "outcome_weight_mode",
            "n",
            "generator",
            "k",
            "selected_match_count",
            "stake_cny_mean",
            "proposal_count_mean",
            "effective_k_mean",
        ]
    ].copy()
    action["issue"] = action["issue"].astype(str)
    frame = action.merge(states, on="issue", how="left", validate="many_to_one")
    if frame[list(ISSUE_STATE_FEATURES)].isna().all(axis=None):
        raise ValueError("issue states failed to join action rows")

    result = frame[list(ISSUE_STATE_FEATURES)].astype(float).copy()
    n_matches = result["n_matches"].clip(lower=1.0)
    result["action_n"] = frame["n"].astype(float)
    result["action_n_fraction"] = result["action_n"] / n_matches
    result["action_log2_k"] = np.log2(frame["k"].astype(float).clip(lower=1.0))
    result["action_selected_fraction"] = (
        frame["selected_match_count"].astype(float) / n_matches
    )
    result["action_stake_fraction_cny100k"] = (
        frame["stake_cny_mean"].astype(float) / 100_000.0
    )
    result["action_proposal_pressure"] = np.divide(
        frame["proposal_count_mean"].astype(float),
        frame["effective_k_mean"].astype(float).clip(lower=1.0),
    )
    result["action_n_x_value"] = result["action_n"] * result["value_best_mean"]
    result["action_n_x_divergence"] = (
        result["action_n"] * result["divergence_abs_mean"]
    )
    for selector in ("ALL", "TOP_HALF_VALUE"):
        result[f"selector_{selector}"] = frame["selector"].eq(selector).astype(float)
    for outcome_mode in (
        "CELL_VALUE",
        "MARKET_PROBABILITY",
        "DIVERGENCE_VALUE",
    ):
        result[f"outcome_{outcome_mode}"] = (
            frame["outcome_weight_mode"].eq(outcome_mode).astype(float)
        )
    for generator in ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR"):
        result[f"generator_{generator}"] = frame["generator"].eq(generator).astype(float)
    leaked = FORBIDDEN.intersection(result.columns)
    if leaked:
        raise AssertionError(f"settlement targets leaked into features: {sorted(leaked)}")
    return result.replace([np.inf, -np.inf], np.nan)
