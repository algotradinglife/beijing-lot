"""Stage C: state-dependent expert composition and dynamic funding intensity.

Two learned functions consume issue state plus Stage-B outputs:

- composition: relative expert/cash mixture weights over the four whole-bundle
  experts (identity scores are transparent inputs, not a hidden latent).
- intensity: total expert bankroll fraction in [0, 1].

Weights become non-negative integer copies of complete bundles.  Total stake
never exceeds current bankroll; remaining capital stays in cash.  No fixed
per-issue stake cap is applied (the only bound is bankroll feasibility).

Objectives are compared rather than assumed: mean-P&L, log-wealth, and
downside-aware utilities are each evaluated as a portfolio objective on
earlier expanding OOF folds; the selector never touches 2023 realized
outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue306 import EXPERT_IDS, PREDICTION_YEARS


def composition_from_value(
    scores: pd.DataFrame,
    *,
    objective: str = "log_wealth",
    temperature: float = 1.0,
    calendar: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Composition: softmax over predicted expert utilities, masked by availability.

    identity scores are the per-expert predicted utilities; relative weights
    are a softmax (temperature-controlled) across available experts.  Returns
    one row per issue with weight_<expert> and weight_CASH = 0 at this stage
    (intensity decides how much of the bankroll is deployed).  When a calendar
    is supplied, every calendar issue gets a row; issues absent from scores
    (no available expert) keep zero expert weights.
    """

    if objective not in {"mean", "log_wealth", "downside"}:
        raise ValueError(f"unknown objective: {objective}")
    rows: list[dict[str, object]] = []
    for (issue, year), local in scores.groupby(["issue", "issue_year"], sort=True):
        expert = local[local["action_id"].isin(EXPERT_IDS)].copy()
        available = expert["available"].to_numpy(bool)
        utility = _utility(expert, objective).to_numpy(float)
        utility = np.where(available, utility, -np.inf)
        base = np.max(utility[available]) if available.any() else 0.0
        shifted = utility - base
        exp_values = np.exp(shifted / max(temperature, 1e-9))
        exp_values[~available] = 0.0
        total = float(exp_values.sum())
        weights = exp_values / total if total > 0 else np.zeros(len(expert))
        row: dict[str, object] = {
            "issue": int(issue),
            "issue_year": int(year),
            "objective": objective,
            "temperature": float(temperature),
        }
        for action, weight in zip(expert["action_id"], weights, strict=True):
            row[f"weight_{action}"] = float(weight)
        row["weight_CASH"] = 0.0
        row["n_available"] = int(available.sum())
        rows.append(row)
    frame = pd.DataFrame(rows)
    if calendar is None:
        return frame
    computed = set(zip(frame["issue"], frame["issue_year"]))
    missing = calendar[
        ~calendar.set_index(["issue", "issue_year"]).index.isin(computed)
    ]
    if missing.empty:
        return frame.sort_values(["issue_year", "issue"]).reset_index(drop=True)
    zero_rows = []
    for issue in missing[["issue", "issue_year"]].itertuples(index=False):
        zero_rows.append(
            {
                "issue": int(issue.issue),
                "issue_year": int(issue.issue_year),
                "objective": objective,
                "temperature": float(temperature),
                **{f"weight_{expert}": 0.0 for expert in EXPERT_IDS},
                "weight_CASH": 1.0,
                "n_available": 0,
            }
        )
    frame = pd.concat([frame, pd.DataFrame(zero_rows)], ignore_index=True)
    return frame.sort_values(["issue_year", "issue"]).reset_index(drop=True)


def intensity_from_state(
    issue_state: pd.DataFrame,
    scores: pd.DataFrame,
    *,
    feature_columns: list[str],
    objective: str = "log_wealth",
    condition: str = "DYNAMIC_INTENSITY",
    alpha: float = 5.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Intensity: predict total expert bankroll fraction in [0, 1] from state.

    A small ridge maps pre-event issue state statistics (predicted upside,
    downside, uncertainty, payout/loss probabilities) to a funding fraction
    clipped into [0, 1].  The target for training issues is a relative value
    strength score computed from Stage-B predictions only (never from 2023
    realized outcomes); each target year's model is fit on strictly earlier
    years.
    """

    design = _intensity_design(issue_state, scores, feature_columns, objective)
    frames: list[pd.DataFrame] = []
    receipts: list[dict[str, object]] = []
    for target_year in PREDICTION_YEARS:
        train = design[design["issue_year"].lt(target_year)]
        test = design[design["issue_year"].eq(target_year)]
        if train.empty or test.empty:
            continue
        x_train = train[feature_columns].to_numpy(float)
        y_train = train["intensity_target"].to_numpy(float)
        model = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(x_train, y_train)
        x_test = test[feature_columns].to_numpy(float)
        predicted = np.clip(model.predict(x_test), 0.0, 1.0)
        local = test[["issue", "issue_year"]].assign(
            condition=condition,
            predicted_intensity=predicted,
            objective=objective,
        )
        calibration = pd.DataFrame(
            test[["issue", "issue_year", "intensity_target"]]
        ).rename(columns={"intensity_target": "calibration_target"})
        local = local.merge(calibration, on=["issue", "issue_year"], how="left")
        frames.append(local)
        receipts.append(
            {
                "condition": condition,
                "objective": objective,
                "prediction_year": target_year,
                "train_end_year": target_year - 1,
                "train_issues": int(len(train)),
                "test_issues": int(len(test)),
                "alpha": alpha,
                "mean_predicted_intensity": float(predicted.mean()),
                "zero_intensity_fraction": float((predicted <= 1e-9).mean()),
            }
        )
    if not frames:
        raise AssertionError("no intensity predictions produced")
    combined = pd.concat(frames, ignore_index=True)
    if len(combined) != len(issue_state[issue_state["issue_year"].between(min(PREDICTION_YEARS), max(PREDICTION_YEARS))]):
        raise AssertionError("intensity predictions do not cover the prediction calendar")
    return combined, pd.DataFrame(receipts)


def _intensity_design(
    issue_state: pd.DataFrame,
    scores: pd.DataFrame,
    feature_columns: list[str],
    objective: str,
) -> pd.DataFrame:
    """Pre-event design matrix: issue state plus Stage-B predicted risk stats.

    The intensity target is a value-strength score from predicted expert
    utility relative to predicted downside, standardized within each training
    window, then clipped to [0, 1].  Because it is built exclusively from
    pre-event predictions (Stage-B expanding fits), no realized outcome ever
    selects the funding rule.
    """

    summary = scores.groupby(["issue", "issue_year"], as_index=False).agg(
        predicted_pnl_mean_cny=("predicted_pnl_cny", "mean"),
        predicted_pnl_std_cny=("predicted_pnl_cny", "std"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_payout_probability=("predicted_payout_probability", "mean"),
        predicted_positive_probability=("predicted_positive_probability", "mean"),
    )
    table = issue_state.merge(summary, on=["issue", "issue_year"], how="left")
    table["predicted_pnl_std_cny"] = table["predicted_pnl_std_cny"].fillna(0.0)
    safe_downside = table["predicted_downside_cny"].clip(lower=1.0)
    risk_penalty = (
        table["predicted_loss_probability"].fillna(0.0) * safe_downside
        + table["predicted_pnl_std_cny"].fillna(0.0)
    )
    table["value_strength"] = table["predicted_pnl_mean_cny"].fillna(0.0) / risk_penalty
    for year in PREDICTION_YEARS:
        prior = table[table["issue_year"].lt(year)]
        if prior.empty:
            continue
        prior_values = prior["value_strength"].to_numpy(float)
        positive = prior_values[prior_values > 0]
        denom = float(np.mean(positive)) if len(positive) else float(np.mean(np.abs(prior_values)) + 1e-9)
        denom = max(denom, 1e-9)
        mask = table["issue_year"].eq(year)
        current = table.loc[mask, "value_strength"].to_numpy(float)
        table.loc[mask, "intensity_target"] = np.clip(current / denom, 0.0, 1.0)
    table["intensity_target"] = table["intensity_target"].fillna(0.0)
    return table


def _utility(expert: pd.DataFrame, objective: str) -> pd.Series:
    """Issue-level utility proxy from Stage-B score columns."""

    mean = expert["predicted_pnl_cny"]
    if objective == "mean":
        return mean
    downside = expert["predicted_downside_cny"].fillna(0.0)
    loss_probability = expert["predicted_loss_probability"].fillna(0.0)
    if objective == "downside":
        return mean - 0.5 * loss_probability * downside
    stake = expert["stake_unit_cny"].clip(lower=1.0)
    log_growth = np.log(np.clip(1.0 + mean / stake, 1e-6, None))
    return mean - 0.5 * loss_probability * downside + log_growth


def allocate_integer_bundles(
    issue_row: pd.Series | dict[str, object],
    composition: pd.Series,
    intensity: float,
    *,
    initial_capital_cny: float,
) -> dict[str, object]:
    """Execute one issue: non-negative integer copies of complete bundles.

    Intensity decides the expert bankroll fraction; composition decides the
    relative split among available experts.  Copies are floor-rounded so total
    stake never exceeds intensity x bankroll (and therefore never exceeds
    bankroll).  Remaining capital stays in cash.
    """

    if not isinstance(issue_row, dict):
        if hasattr(issue_row, "_fields"):
            issue_row = {key: getattr(issue_row, key) for key in issue_row._fields}
        else:
            issue_row = dict(issue_row)
    budget = max(float(intensity), 0.0) * float(initial_capital_cny)
    row: dict[str, object] = {"stake_cny": 0.0, "pnl_cny": 0.0, "gross_cny": 0.0}
    remaining = budget
    for expert in EXPERT_IDS:
        weight = float(composition.get(f"weight_{expert}", 0.0))
        available = bool(issue_row.get(f"available_{expert}", False))
        unit_stake = float(issue_row.get(f"stake_{expert}", 0.0))
        if not available or unit_stake <= 0 or weight <= 0:
            row[f"copies_{expert}"] = 0
            row[f"stake_{expert}"] = 0.0
            row[f"pnl_{expert}"] = 0.0
            row[f"gross_{expert}"] = 0.0
            continue
        desired = remaining * weight
        copies = int(np.floor(desired / unit_stake)) if desired >= unit_stake else 0
        local_stake = copies * unit_stake
        local_pnl = copies * float(issue_row.get(f"pnl_{expert}", 0.0))
        local_gross = copies * float(issue_row.get(f"gross_{expert}", 0.0))
        row[f"copies_{expert}"] = copies
        row[f"stake_{expert}"] = local_stake
        row[f"pnl_{expert}"] = local_pnl
        row[f"gross_{expert}"] = local_gross
        row["stake_cny"] += local_stake
        row["pnl_cny"] += local_pnl
        row["gross_cny"] += local_gross
        remaining -= local_stake
    row["stake_cny"] = float(row["stake_cny"])
    row["pnl_cny"] = float(row["pnl_cny"])
    row["gross_cny"] = float(row["gross_cny"])
    if row["stake_cny"] > float(initial_capital_cny) + 1e-6:
        raise AssertionError("allocation exceeded opening bankroll")
    return row