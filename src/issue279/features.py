"""Leakage-safe action-aware features for the staged unified policy.

This thin factory deliberately accepts an external action catalog.  K anchors
are experiment inputs, not a maximum stake rule.  Outcome and settlement
fields are rejected before any feature is constructed.
"""

from __future__ import annotations

from math import lgamma

import numpy as np
import pandas as pd

PAYOUT_COEFFICIENT = 0.65
TICKET_STAKE = 2.0
FORBIDDEN = {
    "Y",
    "realized_outcome",
    "SP_SETTLE",
    "settlement_sp",
    "payout",
    "mean_pnl",
    "utility_bps",
    "seed",
}
REQUIRED_STATE = {
    "issue",
    "issue_year",
    "n_matches",
    "accepted_fraction",
    "prob_entropy_mean",
    "prob_top_mean",
    "value_best_mean",
    "value_margin_mean",
    "value_interval_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
}
REQUIRED_ACTION = {"action_key", "n", "k", "generator"}


def _log_combinations(m: int, n: int) -> float:
    if n <= 0:
        return 0.0
    if n > m:
        return float("nan")
    return float(lgamma(m + 1) - lgamma(n + 1) - lgamma(m - n + 1))


def build_action_features(
    issue_states: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    prior_capital: float = 100_000.0,
) -> pd.DataFrame:
    """Cross issue state with lawful actions and construct ``phi(X, a)``.

    The returned frame is inference-only.  Realized action utilities are joined
    later by the caller for training or diagnostic attribution.
    """

    forbidden = FORBIDDEN.intersection(issue_states.columns) | FORBIDDEN.intersection(
        actions.columns
    )
    if forbidden:
        raise ValueError(f"outcome/seed fields are forbidden in inference features: {sorted(forbidden)}")
    missing_state = REQUIRED_STATE.difference(issue_states.columns)
    missing_action = REQUIRED_ACTION.difference(actions.columns)
    if missing_state or missing_action:
        raise ValueError(
            f"feature contract incomplete: state={sorted(missing_state)}, action={sorted(missing_action)}"
        )
    if prior_capital <= 0:
        raise ValueError("prior_capital must be positive")

    states = issue_states.copy()
    catalog = actions.loc[:, sorted(REQUIRED_ACTION)].drop_duplicates("action_key").copy()
    states["_join"] = 1
    catalog["_join"] = 1
    frame = states.merge(catalog, on="_join", how="inner").drop(columns="_join")
    active = frame["generator"].ne("NO_BET")
    frame = frame.loc[~active | frame["n"].between(1, frame["n_matches"])].copy()

    n = frame["n"].astype(float)
    k = frame["k"].astype(float)
    m = frame["n_matches"].astype(float)
    frame["stage1_candidate_density"] = frame["accepted_fraction"].astype(float)
    frame["stage2_probability_concentration"] = 1.0 - frame[
        "prob_entropy_mean"
    ].astype(float) / np.log(3.0)
    frame["stage2_divergence_confidence"] = frame["divergence_abs_mean"].astype(
        float
    ) / (frame["value_interval_mean"].abs().astype(float) + 1e-9)
    frame["stage3_n_fraction"] = np.divide(n, m, out=np.zeros(len(frame)), where=m > 0)
    frame["stage3_log2_k"] = np.log2(k.clip(lower=1.0))
    frame["stage3_requested_turnover"] = k * TICKET_STAKE
    frame["stage4_requested_capital_fraction"] = (
        frame["stage3_requested_turnover"] / prior_capital
    )
    frame["stage3_effective_coefficient_per_leg"] = np.where(
        n > 0, PAYOUT_COEFFICIENT ** (1.0 / n.clip(lower=1.0)), 1.0
    )
    frame["stage3_log_match_combinations"] = [
        _log_combinations(int(matches), int(legs))
        for matches, legs in zip(frame["n_matches"], frame["n"])
    ]
    entropy_support = np.exp(
        np.clip(n * frame["prob_entropy_mean"].astype(float), 0.0, 30.0)
    )
    frame["stage3_repeat_pressure_proxy"] = np.where(
        active, k / np.maximum(entropy_support, 1.0), 0.0
    )
    frame["stage3_n_x_value"] = n * frame["value_best_mean"].astype(float)
    frame["stage3_n_x_divergence"] = n * frame["divergence_abs_mean"].astype(float)
    for generator in ("NO_BET", "TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR"):
        frame[f"stage3_generator_{generator}"] = frame["generator"].eq(generator).astype(int)
    return frame.sort_values(["issue_year", "issue", "action_key"]).reset_index(drop=True)


def feature_dictionary() -> pd.DataFrame:
    """Machine-readable dictionary for implemented first-slice features."""

    rows = [
        ("stage1_candidate_density", "selection", "accepted_fraction", "decision_epoch", "SAFE"),
        ("stage2_probability_concentration", "outcome", "1-entropy/log(3)", "decision_epoch", "SAFE"),
        ("stage2_divergence_confidence", "outcome", "mean_abs_divergence/(value_interval+eps)", "decision_epoch", "SAFE"),
        ("stage3_n_fraction", "ticket", "N/M", "decision_epoch", "SAFE"),
        ("stage3_log2_k", "ticket", "log2(K)", "action", "SAFE"),
        ("stage3_requested_turnover", "ticket", "2*K CNY", "action", "SAFE"),
        ("stage4_requested_capital_fraction", "capital", "2*K/prior_capital", "decision_epoch", "SAFE"),
        ("stage3_effective_coefficient_per_leg", "ticket", "0.65^(1/N), comparison only", "action", "SAFE"),
        ("stage3_log_match_combinations", "ticket", "log choose(M,N)", "decision_epoch", "SAFE"),
        ("stage3_repeat_pressure_proxy", "ticket", "K/exp(N*mean_entropy)", "decision_epoch", "SAFE_PROXY"),
        ("stage3_n_x_value", "ticket", "N*mean_best_value", "decision_epoch", "SAFE"),
        ("stage3_n_x_divergence", "ticket", "N*mean_abs_divergence", "decision_epoch", "SAFE"),
    ]
    return pd.DataFrame(
        rows,
        columns=["feature", "stage", "formula", "earliest_availability", "leakage_class"],
    )
