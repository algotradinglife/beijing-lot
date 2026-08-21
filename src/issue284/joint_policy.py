"""Leakage-safe issue×joint-action learning tables for #284."""

from __future__ import annotations

import numpy as np
import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES

BASELINE_ACTION = (7, "WEIGHTED_WR", 128, "ENSEMBLE")
JOINT_N = (7, 8, 9, 10)
JOINT_GENERATORS = ("TOP_VALUE", "WEIGHTED_WR")
JOINT_K = (8, 16, 32, 64, 128, 256, 512)

JOINT_FEATURES = (
    *ISSUE_STATE_FEATURES,
    "action_n",
    "action_n_fraction",
    "action_log2_k",
    "action_generator_top",
    "action_generator_weighted",
    "action_family_uniform",
    "action_family_value",
    "action_family_divergence",
    "action_family_shape",
    "action_family_ensemble",
    "expected_mean_asinh",
    "expected_std_log1p",
    "expected_q10_asinh",
    "expected_q50_asinh",
    "expected_q90_asinh",
    "expected_subset_range_log1p",
    "expected_lift_to_baseline_asinh",
    "action_n_x_value",
    "action_n_x_divergence",
    "action_k_x_probability_concentration",
)


def build_joint_action_table(
    raw: pd.DataFrame, issue_state: pd.DataFrame
) -> pd.DataFrame:
    """Average nuisance replicas and attach only pre-event issue/action features."""

    required = {
        "issue",
        "issue_year",
        "n",
        "proposal_family",
        "subset_id",
        "generator",
        "requested_k",
        "stream_replica",
        "normalized_pnl_cny100",
        "model_expected_pnl_cny100",
    }
    missing = required - set(raw)
    if missing:
        raise ValueError(f"joint grid missing columns: {sorted(missing)}")
    frame = raw.loc[
        raw["n"].isin(JOINT_N)
        & raw["generator"].isin(JOINT_GENERATORS)
        & raw["requested_k"].isin(JOINT_K)
    ].copy()
    if frame["issue_year"].ge(2024).any():
        raise ValueError("2024+ outcome row entered joint policy table")
    frame["issue"] = frame["issue"].astype(str)
    subset_keys = [
        "issue",
        "issue_year",
        "n",
        "proposal_family",
        "subset_id",
        "generator",
        "requested_k",
    ]
    subset = frame.groupby(subset_keys, as_index=False).agg(
        realized_roi_pct=("normalized_pnl_cny100", "mean"),
        expected_roi_pct=("model_expected_pnl_cny100", "mean"),
        stream_replicas=("stream_replica", "nunique"),
    )
    action_keys = [
        "issue",
        "issue_year",
        "n",
        "proposal_family",
        "generator",
        "requested_k",
    ]
    family_actions = _aggregate_action_replicas(subset, action_keys)
    ensemble_keys = ["issue", "issue_year", "n", "generator", "requested_k"]
    ensemble = _aggregate_action_replicas(subset, ensemble_keys)
    ensemble["proposal_family"] = "ENSEMBLE"
    table = pd.concat([family_actions, ensemble], ignore_index=True)
    baseline = table.loc[
        table["n"].eq(BASELINE_ACTION[0])
        & table["generator"].eq(BASELINE_ACTION[1])
        & table["requested_k"].eq(BASELINE_ACTION[2])
        & table["proposal_family"].eq(BASELINE_ACTION[3]),
        ["issue", "realized_roi_pct", "expected_mean"],
    ].rename(
        columns={
            "realized_roi_pct": "baseline_realized_roi_pct",
            "expected_mean": "baseline_expected_mean",
        }
    )
    if baseline["issue"].duplicated().any():
        raise ValueError("joint matched baseline is not unique")
    table = table.merge(baseline, on="issue", how="left", validate="many_to_one")
    if table["baseline_realized_roi_pct"].isna().any():
        raise ValueError("an issue is missing the fixed N7 weighted-K128 baseline")
    table["realized_lift_pct"] = (
        table["realized_roi_pct"] - table["baseline_realized_roi_pct"]
    )
    table["expected_lift_to_baseline"] = (
        table["expected_mean"] - table["baseline_expected_mean"]
    )
    table["action_key"] = (
        "N"
        + table["n"].astype(str)
        + "_"
        + table["generator"]
        + "_K"
        + table["requested_k"].astype(str)
        + "_F"
        + table["proposal_family"]
    )
    table["issue_training_weight"] = 1.0 / table.groupby("issue")[
        "issue"
    ].transform("size")

    state = issue_state.copy()
    state["issue"] = state["issue"].astype(str)
    state = state[["issue", *ISSUE_STATE_FEATURES]].drop_duplicates("issue")
    table = table.merge(state, on="issue", how="left", validate="many_to_one")
    if table[list(ISSUE_STATE_FEATURES)].isna().all(axis=1).any():
        raise ValueError("an issue is missing all pre-event state features")
    return _add_joint_features(table).sort_values(
        ["issue_year", "issue", "n", "generator", "requested_k"]
    ).reset_index(drop=True)


def _add_joint_features(table: pd.DataFrame) -> pd.DataFrame:
    result = table.copy()
    result["action_n"] = result["n"].astype(float)
    result["action_n_fraction"] = result["action_n"] / result["n_matches"].clip(
        lower=1.0
    )
    result["action_log2_k"] = np.log2(result["requested_k"].clip(lower=1.0))
    result["action_generator_top"] = result["generator"].eq("TOP_VALUE").astype(float)
    result["action_generator_weighted"] = result["generator"].eq(
        "WEIGHTED_WR"
    ).astype(float)
    for family, suffix in (
        ("UNIFORM", "uniform"),
        ("VALUE_WEIGHTED", "value"),
        ("DIVERGENCE_WEIGHTED", "divergence"),
        ("SHAPE_STRATIFIED", "shape"),
        ("ENSEMBLE", "ensemble"),
    ):
        result[f"action_family_{suffix}"] = result["proposal_family"].eq(
            family
        ).astype(float)
    for source, target in (
        ("expected_mean", "expected_mean_asinh"),
        ("expected_q10", "expected_q10_asinh"),
        ("expected_q50", "expected_q50_asinh"),
        ("expected_q90", "expected_q90_asinh"),
        ("expected_lift_to_baseline", "expected_lift_to_baseline_asinh"),
    ):
        result[target] = np.arcsinh(result[source] / 100.0)
    result["expected_std_log1p"] = np.log1p(result["expected_std"].clip(lower=0.0))
    result["expected_subset_range_log1p"] = np.log1p(
        result["expected_subset_range"].clip(lower=0.0)
    )
    result["action_n_x_value"] = result["action_n"] * result["value_best_mean"]
    result["action_n_x_divergence"] = (
        result["action_n"] * result["divergence_abs_mean"]
    )
    result["action_k_x_probability_concentration"] = (
        result["action_log2_k"] * result["prob_top_mean"]
    )
    return result.replace([np.inf, -np.inf], np.nan)


def select_policy(
    prediction: pd.DataFrame,
    *,
    score_column: str,
    policy: str,
    fallback_column: str | None = None,
) -> pd.DataFrame:
    """Select one available action per issue, optionally falling back to baseline."""

    selected = (
        prediction.sort_values(
            ["issue", score_column, "action_key"],
            ascending=[True, False, True],
        )
        .groupby("issue", as_index=False)
        .head(1)
        .copy()
    )
    prediction_columns = list(prediction.columns)
    fallback_mask = pd.Series(False, index=selected.index)
    if fallback_column is not None:
        needs_fallback = selected[fallback_column].le(0.0)
        fallback_mask = needs_fallback.copy()
        baseline = prediction.loc[
            prediction["action_key"].eq("N7_WEIGHTED_WR_K128_FENSEMBLE")
        ].set_index("issue")
        replacement = baseline.reindex(selected.loc[needs_fallback, "issue"])
        if replacement.isna().all(axis=1).any():
            raise ValueError("fallback baseline missing for a selected issue")
        replacement = replacement.reset_index()
        replacement.index = selected.index[needs_fallback]
        selected.loc[needs_fallback, prediction_columns] = replacement[
            prediction_columns
        ]
    selected["used_fallback"] = fallback_mask
    selected["policy"] = policy
    return selected.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def _aggregate_action_replicas(
    subset: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    result = subset.groupby(keys, as_index=False).agg(
        realized_roi_pct=("realized_roi_pct", "mean"),
        realized_std=("realized_roi_pct", "std"),
        expected_mean=("expected_roi_pct", "mean"),
        expected_std=("expected_roi_pct", "std"),
        expected_q10=("expected_roi_pct", lambda value: value.quantile(0.10)),
        expected_q50=("expected_roi_pct", "median"),
        expected_q90=("expected_roi_pct", lambda value: value.quantile(0.90)),
        subsets=("subset_id", "nunique"),
        families=("proposal_family", "nunique"),
        stream_replicas_max=("stream_replicas", "max"),
    )
    result["expected_subset_range"] = result["expected_q90"] - result["expected_q10"]
    return result
