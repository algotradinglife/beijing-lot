"""Issue #208: required learning diagnostics.

Chronological train/val loss, calibration of predicted vs realized matched
lift, action-confusion/frequency tables, permutation importance, per-fold
learned-policy lift, ablation vs best fixed action, OOD/fallback census and
an action-variation demonstration (changing only pre-event state can change
the selected action).

REWORK v2 (D3): `chronological_train_val_loss` fits the SAME model class on a
chronological issue-block split of the training folds (last 15% of train
issues by issue id = validation block) and reports train/val loss.  sklearn
row-level early stopping is not used anywhere.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from .contract import Action, all_actions
from .features import STATE_FEATURE_NAMES
from .policy import LearnedPolicy, _feature_columns, build_design, fit_policy, predict_lift


class DiagnosticError(RuntimeError):
    """Raised when a diagnostic cannot be produced."""


def action_frequency(
    decision_rows: pd.DataFrame, *, split: str | None = None
) -> pd.DataFrame:
    frame = decision_rows
    if split is not None:
        frame = frame.loc[frame["split"] == split]
    if frame.empty:
        return pd.DataFrame(
            columns=["action_key", "n", "k", "lane", "capital", "count", "share"]
        )
    counts = (
        frame.groupby(["action_key", "n", "k", "lane", "capital"])
        .size()
        .reset_index(name="count")
    )
    counts["share"] = counts["count"] / counts["count"].sum()
    return counts.sort_values("count", ascending=False)


def action_confusion(
    train_df: pd.DataFrame,
    policy: LearnedPolicy,
    context_states: dict[str, np.ndarray],
    context_issues: list[str],
) -> pd.DataFrame:
    """Cross-table of chosen action by predicted-best action on train folds."""
    actions = all_actions()
    rows: list[dict[str, Any]] = []
    for issue in context_issues:
        state = context_states[issue]
        lifts = predict_lift(policy, [state] * len(actions), actions)
        predicted = actions[int(np.argmax(lifts))]
        rows.append({"issue": issue, "predicted_action": predicted.key})
    predicted_df = pd.DataFrame(rows)
    if train_df.empty:
        return pd.DataFrame(
            columns=["predicted_action", "observed_best_action", "count"]
        )
    observed = (
        train_df.loc[train_df.groupby("issue")["y_lift"].idxmax()][
            ["issue", "action_key"]
        ]
        .rename(columns={"action_key": "observed_best_action"})
    )
    merged = predicted_df.merge(observed, on="issue", how="left")
    return (
        merged.groupby(["predicted_action", "observed_best_action"])
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


def calibration_curve(
    train_df: pd.DataFrame,
    policy: LearnedPolicy,
    context_states: dict[str, np.ndarray],
    *,
    bins: int = 5,
) -> pd.DataFrame:
    """Binned predicted vs realized matched lift on the training folds."""
    actions = all_actions()
    rows: list[dict[str, Any]] = []
    train_issues = set(train_df["issue"].astype(str))
    for key, state in context_states.items():
        issue = key.split(":")[-1]
        if issue not in train_issues:
            continue
        lifts = predict_lift(policy, [state] * len(actions), actions)
        realized = train_df.loc[train_df["issue"].astype(str) == issue]
        if realized.empty:
            continue
        best_realized = float(realized["y_lift"].max())
        best_predicted = float(np.max(lifts))
        rows.append(
            {
                "issue": issue,
                "predicted_best_lift": best_predicted,
                "realized_best_lift": best_realized,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty or len(frame) < bins:
        return frame
    frame["bin"] = pd.qcut(
        frame["predicted_best_lift"], bins, labels=False, duplicates="drop"
    )
    return (
        frame.groupby("bin", as_index=False)
        .agg(
            predicted_best_lift=("predicted_best_lift", "mean"),
            realized_best_lift=("realized_best_lift", "mean"),
            issues=("issue", "count"),
        )
    )


def chronological_train_val_loss(
    train_df: pd.DataFrame,
    *,
    kind: str = "MLP",
    seed: int = 208001,
    validation_fraction: float = 0.15,
) -> pd.DataFrame:
    """Chronological issue-block train/validation loss for the model class.

    REWORK v2 (D3): validation block = last `validation_fraction` of train
    issues by issue id (strictly chronological, never row-random).  Fits the
    same model class on the fit block, scores both blocks, reports RMSE.
    """
    if train_df.empty or "y_lift" not in train_df.columns:
        return pd.DataFrame()
    issues = sorted(train_df["issue"].astype(str).unique())
    if len(issues) < 5:
        return pd.DataFrame()
    cut = max(2, int(len(issues) * (1.0 - validation_fraction)))
    fit_issues = set(issues[:cut])
    val_issues = set(issues[cut:])
    fit_df = train_df.loc[train_df["issue"].astype(str).isin(fit_issues)]
    val_df = train_df.loc[train_df["issue"].astype(str).isin(val_issues)]
    if fit_df.empty or val_df.empty:
        return pd.DataFrame()
    policy = fit_policy(
        fit_df, kind=kind, seed=seed, validation_df=val_df
    )
    return pd.DataFrame(
        [
            {
                "model": kind,
                "fit_issues": len(fit_issues),
                "validation_issues": len(val_issues),
                "fit_rmse": float(policy.residual_rmse),
                "validation_rmse": (
                    float(policy.validation_rmse)
                    if policy.validation_rmse is not None
                    else float("nan")
                ),
            }
        ]
    )


def permutation_importance_table(
    train_df: pd.DataFrame,
    policy: LearnedPolicy,
    *,
    n_repeats: int = 5,
    seed: int = 208601,
) -> pd.DataFrame:
    """Permutation importance of state+action features on train-fold fit."""
    features = _feature_columns()
    x = train_df.loc[:, features].to_numpy(dtype=float)
    y = train_df["y_lift"].to_numpy(dtype=float)
    model = policy.model
    if model is None:
        raise DiagnosticError("permutation importance requires a fitted model")
    result = permutation_importance(
        model, x, y, n_repeats=n_repeats, random_state=seed, scoring="neg_mean_squared_error"
    )
    names = features + ["(action encoding)"]
    return pd.DataFrame(
        {
            "feature": names[: len(features)],
            "importance_mean": result.importances_mean,
            "importance_std": result.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)


def per_fold_lift_summary(path_rows: pd.DataFrame) -> pd.DataFrame:
    if path_rows.empty:
        return pd.DataFrame()
    return (
        path_rows.groupby(["split", "policy"])
        .agg(
            issues=("issue", "count"),
            ending_capital_yuan=("post_issue_bankroll_yuan", "last"),
            max_drawdown_pct=("drawdown_pct", "max"),
            turnover_yuan=("funded_stake_yuan", "sum"),
        )
        .reset_index()
    )


def ood_fallback_census(decision_rows: pd.DataFrame) -> pd.DataFrame:
    if decision_rows.empty:
        return pd.DataFrame(
            columns=["split", "executed", "fallback_incumbent", "no_bet", "issues"]
        )
    decision_rows = decision_rows.copy()
    decision_rows["executed"] = decision_rows["decision_trace_json"].map(
        lambda value: "EXECUTE" in str(value)
    )
    decision_rows["fallback_incumbent"] = decision_rows[
        "decision_trace_json"
    ].map(lambda value: "INCUMBENT" in str(value))
    decision_rows["no_bet"] = decision_rows["decision_trace_json"].map(
        lambda value: "NO_BET" in str(value)
    )
    return (
        decision_rows.groupby("split", as_index=False)
        .agg(
            issues=("issue", "count"),
            executed=("executed", "sum"),
            fallback_incumbent=("fallback_incumbent", "sum"),
            no_bet=("no_bet", "sum"),
        )
    )


def action_variation_demo(
    context_states: dict[str, np.ndarray],
    policy: LearnedPolicy,
    *,
    max_issues: int = 8,
) -> pd.DataFrame:
    """Show that changing only pre-event state can change the selected action."""
    actions = all_actions()
    rows: list[dict[str, Any]] = []
    issues = list(context_states.keys())[:max_issues]
    for issue in issues:
        state = context_states[issue]
        lifts = predict_lift(policy, [state] * len(actions), actions)
        best = actions[int(np.argmax(lifts))]
        rows.append(
            {
                "issue": issue,
                "chosen_action": best.key,
                "chosen_n": best.n,
                "chosen_k": best.k,
                "chosen_lane": best.lane,
                "chosen_capital": best.capital,
                "max_predicted_lift": float(np.max(lifts)),
            }
        )
    return pd.DataFrame(rows)


def ablation_vs_best_fixed(
    summaries: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Ablation table: learned vs ridge vs best-fixed vs incumbent per fold."""
    rows: list[dict[str, Any]] = []
    for fold, summary in summaries.items():
        for name, value in summary.items():
            if name.endswith("_ending_capital_yuan"):
                rows.append(
                    {
                        "fold": fold,
                        "arm": name.removesuffix("_ending_capital_yuan"),
                        "ending_capital_yuan": float(value),
                    }
                )
    return pd.DataFrame(rows)


__all__ = [
    "DiagnosticError", "ablation_vs_best_fixed", "action_confusion",
    "action_frequency", "action_variation_demo", "calibration_curve",
    "chronological_train_val_loss", "ood_fallback_census",
    "per_fold_lift_summary", "permutation_importance_table",
]
