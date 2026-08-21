"""Expanding-window action-conditioned value models for Issue #302."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

SEEDS = (302001, 302002, 302003, 302004, 302005)
PREDICTION_YEARS = (2021, 2022, 2023)


@dataclass
class FittedHeads:
    """One fitted action-value model and train-only transforms."""

    model_kind: str
    seed: int
    condition: str
    target_year: int
    action_ids: tuple[str, ...]
    feature_columns: tuple[str, ...]
    encoder: OneHotEncoder
    mean_model: object
    downside_model: object
    loss_model: object
    payout_model: object
    target_scale: float


def fit_predict_expanding(
    issues: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str = "DYNAMIC_HIERARCHICAL_MLP",
    model_kind: str = "MLP",
    seeds: tuple[int, ...] = SEEDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Generate issue/action predictions using only strictly earlier years."""

    if condition not in {
        "DYNAMIC_HIERARCHICAL_MLP",
        "STATE_SHUFFLED",
        "IDENTITY_SHUFFLED",
    }:
        raise ValueError(f"unknown condition: {condition}")
    if model_kind not in {"MLP", "RIDGE", "HGB"}:
        raise ValueError(f"unknown model kind: {model_kind}")
    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    use_seeds = seeds if model_kind == "MLP" else (seeds[0],)
    fits: list[FittedHeads] = []
    prediction_frames: list[pd.DataFrame] = []
    for target_year in PREDICTION_YEARS:
        train_issues = issues[issues["issue_year"].lt(target_year)].copy()
        test_issues = issues[issues["issue_year"].eq(target_year)].copy()
        if train_issues.empty or test_issues.empty:
            continue
        for seed in use_seeds:
            fit = _fit(
                train_issues,
                actions[actions["issue"].isin(train_issues["issue"])],
                feature_columns,
                condition,
                model_kind,
                seed,
                target_year,
            )
            fits.append(fit)
            prediction_frames.append(
                _predict(
                    fit,
                    test_issues,
                    actions[actions["issue"].isin(test_issues["issue"])],
                )
            )
    seed_predictions = pd.concat(prediction_frames, ignore_index=True)
    average = seed_predictions.groupby(
        ["issue", "issue_year", "condition", "model_kind", "action_id"],
        as_index=False,
    ).agg(
        available=("available", "all"),
        stake_unit_cny=("stake_unit_cny", "mean"),
        predicted_pnl_cny=("predicted_pnl_cny", "mean"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_payout_probability=("predicted_payout_probability", "mean"),
        predicted_pnl_std_cny=("predicted_pnl_cny", "std"),
    )
    average["predicted_pnl_std_cny"] = average["predicted_pnl_std_cny"].fillna(0.0)
    average["utility_cny"] = average["predicted_pnl_cny"] - 0.5 * average[
        "predicted_loss_probability"
    ] * average["predicted_downside_cny"]
    receipts = pd.DataFrame(
        [
            {
                "condition": fit.condition,
                "model_kind": fit.model_kind,
                "seed": fit.seed,
                "prediction_year": fit.target_year,
                "train_end_year": fit.target_year - 1,
                "actions": len(fit.action_ids),
                "features": len(fit.feature_columns),
                "target_scale_cny": fit.target_scale,
                "mean_model": type(fit.mean_model).__name__,
                "downside_model": type(fit.downside_model).__name__,
            }
            for fit in fits
        ]
    )
    return average, seed_predictions, receipts


def _fit(
    issues: pd.DataFrame,
    actions: pd.DataFrame,
    feature_columns: list[str],
    condition: str,
    model_kind: str,
    seed: int,
    target_year: int,
) -> FittedHeads:
    rows = actions[actions["available"]].merge(
        issues[["issue", *feature_columns]], on="issue", validate="many_to_one"
    )
    rng = np.random.default_rng(seed + target_year)
    rows = rows.copy()
    action_ids = tuple(sorted(actions["action_id"].unique()))
    fit_actions = rows["action_id"].copy()
    if condition == "IDENTITY_SHUFFLED":
        mapping = dict(zip(action_ids, rng.permutation(action_ids), strict=True))
        fit_actions = fit_actions.map(mapping)
    feature_values = rows[feature_columns].copy()
    if condition == "STATE_SHUFFLED":
        for _, index in rows.groupby("issue_year").groups.items():
            feature_values.loc[index] = feature_values.loc[
                rng.permutation(index), feature_columns
            ].to_numpy()
    encoder = OneHotEncoder(categories=[list(action_ids)], sparse_output=False)
    action_matrix = encoder.fit_transform(fit_actions.to_frame())
    x = np.column_stack(
        [feature_values.to_numpy(float), np.log1p(rows[["stake_unit_cny"]]), action_matrix]
    )
    y = rows["pnl_unit_cny"].to_numpy(float)
    low, high = np.quantile(y, [0.05, 0.95])
    scale = max(float(np.median(np.abs(y - np.median(y)))), 1.0)
    y_mean = np.clip(y, low, high) / scale
    y_down = rows["downside_cny"].to_numpy(float) / scale
    if model_kind == "MLP":
        mean_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(24,), activation="tanh", solver="lbfgs",
                alpha=5.0, max_iter=700, random_state=seed,
            ),
        ).fit(x, y_mean)
        downside_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(24,), activation="tanh", solver="lbfgs",
                alpha=5.0, max_iter=700, random_state=seed + 10_000,
            ),
        ).fit(x, y_down)
    elif model_kind == "RIDGE":
        mean_model = make_pipeline(StandardScaler(), Ridge(alpha=20.0)).fit(x, y_mean)
        downside_model = make_pipeline(StandardScaler(), Ridge(alpha=20.0)).fit(x, y_down)
    else:
        mean_model = HistGradientBoostingRegressor(
            max_iter=160, max_leaf_nodes=8, l2_regularization=5.0,
            random_state=seed,
        ).fit(x, y_mean)
        downside_model = HistGradientBoostingRegressor(
            max_iter=160, max_leaf_nodes=8, l2_regularization=5.0,
            random_state=seed + 10_000,
        ).fit(x, y_down)
    loss_model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
    ).fit(x, rows["loss"].to_numpy(int))
    payout_model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
    ).fit(x, rows["payout"].to_numpy(int))
    return FittedHeads(
        model_kind=model_kind, seed=seed, condition=condition,
        target_year=target_year, action_ids=action_ids,
        feature_columns=tuple(feature_columns), encoder=encoder,
        mean_model=mean_model, downside_model=downside_model,
        loss_model=loss_model, payout_model=payout_model, target_scale=scale,
    )


def _predict(fit: FittedHeads, issues: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    rows = actions.merge(
        issues[["issue", *fit.feature_columns]], on="issue", validate="many_to_one"
    )
    action_matrix = fit.encoder.transform(rows[["action_id"]])
    x = np.column_stack(
        [rows[list(fit.feature_columns)].to_numpy(float),
         np.log1p(rows[["stake_unit_cny"]]), action_matrix]
    )
    result = rows[["issue", "issue_year", "action_id", "available", "stake_unit_cny"]].copy()
    result["condition"] = fit.condition
    result["model_kind"] = fit.model_kind
    result["seed"] = fit.seed
    result["predicted_pnl_cny"] = fit.mean_model.predict(x) * fit.target_scale
    result["predicted_downside_cny"] = np.maximum(
        fit.downside_model.predict(x) * fit.target_scale, 0.0
    )
    result["predicted_loss_probability"] = fit.loss_model.predict_proba(x)[:, 1]
    result["predicted_payout_probability"] = fit.payout_model.predict_proba(x)[:, 1]
    result.loc[~result["available"], "predicted_pnl_cny"] = -np.inf
    return result
