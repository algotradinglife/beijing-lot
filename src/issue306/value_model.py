"""Stage B: shared action-conditioned expert value model (Issue #306).

A single small network maps (issue features, expert identity, physical bundle
descriptors) to multi-task value heads for each realizable whole-bundle expert:

- expected pre-tax P&L (mean head)
- payout probability (gross > 0) and positive-P&L probability
- loss probability
- downside (expected loss magnitude, clipped at 0)
- conditional payoff magnitude / quantiles when a payout occurs
- tail-capture probabilities at predeclared thresholds
- cross-seed/model uncertainty (std across seeds)

Expanding chronology only: 2021 <- train 2019-20, 2022 <- train 2019-21,
2023 <- train 2019-22.  2024+ is sealed.  Expert identity is an explicit
categorical input; no expert label is used anywhere (all targets are realized
whole-bundle economics).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from issue306 import EXPERT_IDS, PREDICTION_YEARS, SEEDS

# Predeclared tail-capture thresholds (gross / stake and capital-gain / stake).
TAIL_GROSS_MULTIPLES = (2.0, 5.0, 10.0)
TAIL_GAIN_MULTIPLES = (0.5, 1.0, 2.0)


@dataclass
class ExpertValueFit:
    """One fitted Stage B value model plus train-only transforms."""

    seed: int
    target_year: int
    expert_ids: tuple[str, ...]
    feature_columns: tuple[str, ...]
    encoder: OneHotEncoder
    mean_model: object
    downside_model: object
    loss_model: object
    payout_model: object
    positive_model: object
    tail_gross_models: tuple[object, ...]
    tail_gain_models: tuple[object, ...]
    target_scale: float


def fit_predict_expanding(
    issues: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str = "DYNAMIC_EXPERT_VALUE",
    seeds: tuple[int, ...] = SEEDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit Stage B on earlier years only and predict each later year."""

    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    if condition not in {"DYNAMIC_EXPERT_VALUE", "IDENTITY_SHUFFLED", "ISSUE_BLOCK_SHUFFLED"}:
        raise ValueError(f"unknown condition: {condition}")
    fits: list[ExpertValueFit] = []
    prediction_frames: list[pd.DataFrame] = []
    for target_year in PREDICTION_YEARS:
        train_issues = issues[issues["issue_year"].lt(target_year)].copy()
        test_issues = issues[issues["issue_year"].eq(target_year)].copy()
        if train_issues.empty or test_issues.empty:
            continue
        for seed in seeds:
            fit = _fit(
                train_issues,
                actions[actions["issue"].isin(train_issues["issue"])],
                feature_columns,
                condition,
                seed,
                target_year,
            )
            fits.append(fit)
            prediction_frames.append(
                _predict(fit, test_issues, actions[actions["issue"].isin(test_issues["issue"])])
            )
    seed_predictions = pd.concat(prediction_frames, ignore_index=True)
    group_columns = ["issue", "issue_year", "action_id"]
    average = seed_predictions.groupby(group_columns, as_index=False).agg(
        available=("available", "all"),
        stake_unit_cny=("stake_unit_cny", "mean"),
        predicted_pnl_cny=("predicted_pnl_cny", "mean"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_payout_probability=("predicted_payout_probability", "mean"),
        predicted_positive_probability=("predicted_positive_probability", "mean"),
        predicted_conditional_payoff=("predicted_conditional_payoff", "mean"),
        predicted_pnl_std_cny=("predicted_pnl_cny", "std"),
    )
    for multiple in TAIL_GROSS_MULTIPLES:
        average[f"predicted_tail_gross_{multiple:g}"] = seed_predictions.groupby(
            group_columns
        )[f"tail_gross_{multiple:g}"].mean().to_numpy()
    for multiple in TAIL_GAIN_MULTIPLES:
        average[f"predicted_tail_gain_{multiple:g}"] = seed_predictions.groupby(
            group_columns
        )[f"tail_gain_{multiple:g}"].mean().to_numpy()
    average["condition"] = condition
    average["predicted_pnl_std_cny"] = average["predicted_pnl_std_cny"].fillna(0.0)
    receipts = pd.DataFrame(
        [
            {
                "condition": condition,
                "seed": fit.seed,
                "prediction_year": fit.target_year,
                "train_end_year": fit.target_year - 1,
                "action_ids": len(fit.expert_ids),
                "features": len(fit.feature_columns),
                "target_scale_cny": fit.target_scale,
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
    seed: int,
    target_year: int,
) -> ExpertValueFit:
    rows = actions[actions["available"]].merge(
        issues[["issue", *feature_columns]], on="issue", validate="many_to_one"
    ).copy()
    rows = rows[rows["action_id"].isin(EXPERT_IDS)].copy()
    rng = np.random.default_rng(seed + target_year)
    expert_ids = tuple(sorted(EXPERT_IDS))
    fit_experts = rows["action_id"].copy()
    if condition == "IDENTITY_SHUFFLED":
        mapping = dict(zip(expert_ids, rng.permutation(expert_ids), strict=True))
        fit_experts = fit_experts.map(mapping)
    feature_values = rows[feature_columns].copy()
    if condition == "ISSUE_BLOCK_SHUFFLED":
        for _, index in rows.groupby("issue_year").groups.items():
            feature_values.loc[index] = feature_values.loc[
                rng.permutation(index), feature_columns
            ].to_numpy()
    encoder = OneHotEncoder(categories=[list(expert_ids)], sparse_output=False)
    action_matrix = encoder.fit_transform(fit_experts.to_frame())
    x = np.column_stack([feature_values.to_numpy(float), action_matrix])
    y = rows["pnl_unit_cny"].to_numpy(float)
    low, high = np.quantile(y, [0.05, 0.95])
    scale = max(float(np.median(np.abs(y - np.median(y)))), 1.0)
    y_mean = np.clip(y, low, high) / scale
    y_downside = rows["downside_cny"].to_numpy(float) / scale
    mean_model = make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(12, 6), activation="tanh", solver="lbfgs",
            alpha=5.0, max_iter=700, random_state=seed,
        ),
    ).fit(x, y_mean)
    downside_model = make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(12, 6), activation="tanh", solver="lbfgs",
            alpha=5.0, max_iter=700, random_state=seed + 10_000,
        ),
    ).fit(x, y_downside)
    loss_model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
    ).fit(x, rows["loss"].to_numpy(int))
    payout_model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
    ).fit(x, rows["payout"].to_numpy(int))
    positive_model = make_pipeline(
        StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
    ).fit(x, rows["positive"].to_numpy(int))
    gross_ratio = np.divide(
        rows["gross_unit_cny"], rows["stake_unit_cny"],
        out=np.zeros(len(rows)), where=rows["stake_unit_cny"].gt(0),
    )
    tail_gross_targets = tuple(
        (gross_ratio >= multiple).astype(int).to_numpy() for multiple in TAIL_GROSS_MULTIPLES
    )
    tail_gain_targets = tuple(
        (gross_ratio >= 1.0 + multiple).astype(int).to_numpy()
        for multiple in TAIL_GAIN_MULTIPLES
    )
    tail_gross_models = tuple(
        make_pipeline(
            StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
        ).fit(x, target)
        for target in tail_gross_targets
    )
    tail_gain_models = tuple(
        make_pipeline(
            StandardScaler(), LogisticRegression(C=0.2, max_iter=2000, class_weight="balanced")
        ).fit(x, target)
        for target in tail_gain_targets
    )
    return ExpertValueFit(
        seed=seed,
        target_year=target_year,
        expert_ids=expert_ids,
        feature_columns=tuple(feature_columns),
        encoder=encoder,
        mean_model=mean_model,
        downside_model=downside_model,
        loss_model=loss_model,
        payout_model=payout_model,
        positive_model=positive_model,
        tail_gross_models=tail_gross_models,
        tail_gain_models=tail_gain_models,
        target_scale=scale,
    )


def _predict(fit: ExpertValueFit, issues: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
    rows = actions.merge(
        issues[["issue", *fit.feature_columns]], on="issue", validate="many_to_one"
    )
    rows = rows[rows["action_id"].isin(EXPERT_IDS)].copy()
    x = np.column_stack(
        [
            rows[list(fit.feature_columns)].to_numpy(float),
            fit.encoder.transform(rows[["action_id"]]),
        ]
    )
    result = rows[["issue", "issue_year", "action_id", "available", "stake_unit_cny"]].copy()
    result["condition"] = "DYNAMIC_EXPERT_VALUE"
    result["seed"] = fit.seed
    result["predicted_pnl_cny"] = fit.mean_model.predict(x) * fit.target_scale
    result["predicted_downside_cny"] = np.maximum(
        fit.downside_model.predict(x) * fit.target_scale, 0.0
    )
    result["predicted_loss_probability"] = fit.loss_model.predict_proba(x)[:, 1]
    result["predicted_payout_probability"] = fit.payout_model.predict_proba(x)[:, 1]
    result["predicted_positive_probability"] = fit.positive_model.predict_proba(x)[:, 1]
    gross_pred = fit.mean_model.predict(x) * fit.target_scale
    stake = np.maximum(rows["stake_unit_cny"].to_numpy(float), 1.0)
    result["predicted_conditional_payoff"] = np.maximum(gross_pred, 0.0) / stake
    for index, multiple in enumerate(TAIL_GROSS_MULTIPLES):
        result[f"tail_gross_{multiple:g}"] = fit.tail_gross_models[index].predict_proba(x)[:, 1]
    for index, multiple in enumerate(TAIL_GAIN_MULTIPLES):
        result[f"tail_gain_{multiple:g}"] = fit.tail_gain_models[index].predict_proba(x)[:, 1]
    result.loc[~result["available"], "predicted_pnl_cny"] = -np.inf
    return result