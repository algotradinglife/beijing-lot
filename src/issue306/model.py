"""Expanding neural action-value heads for Issue #306."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue209.dynamic_policy import STATE_FEATURES, action_features

MODEL_SEEDS = (306101, 306102, 306103, 306104, 306105)
PREDICTION_YEARS = (2021, 2022, 2023)
TARGET_COLUMNS = (
    "mean_roi",
    "positive_probability",
    "tail_5x_probability",
    "mean_downside_roi",
    "conditional_log_gross",
)


def fit_predict_expanding(
    states: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    condition: str = "LEARNED",
    seeds: tuple[int, ...] = MODEL_SEEDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fit shared neural heads with strict earlier-year issue blocks."""

    if condition not in {"LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED"}:
        raise ValueError(f"unknown condition: {condition}")
    if states["issue_year"].ge(2024).any() or labels["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    joined = labels.merge(
        states.drop(columns=["issue_year", "temporal_role"]),
        on="issue",
        how="left",
        validate="many_to_one",
    )
    # Reuse the accepted Issue #209 feature interface without changing its
    # semantics: an action's exposure is the physical ticket stake used to
    # produce its label, not the later fixed 512-ticket portfolio budget.
    joined["stake_total"] = joined["stake_cny"]
    seed_frames: list[pd.DataFrame] = []
    receipt_rows: list[dict[str, object]] = []
    for year in PREDICTION_YEARS:
        train = joined[joined["issue_year"].lt(year)].copy()
        test = joined[joined["issue_year"].eq(year)].copy()
        if train.empty or test.empty:
            continue
        for seed in seeds:
            fit_train = _condition_training(train, condition, seed, year)
            x_train = action_features(fit_train)
            x_test = action_features(test)
            quantiles = {
                column: np.quantile(fit_train[column], [0.01, 0.99])
                for column in TARGET_COLUMNS
            }
            y_raw = np.column_stack(
                [
                    np.clip(
                        fit_train[column].to_numpy(float),
                        quantiles[column][0],
                        quantiles[column][1],
                    )
                    for column in TARGET_COLUMNS
                ]
            )
            target_center = y_raw.mean(axis=0)
            target_scale = y_raw.std(axis=0)
            target_scale = np.where(target_scale > 1e-8, target_scale, 1.0)
            y = (y_raw - target_center) / target_scale
            model = make_pipeline(
                StandardScaler(),
                MLPRegressor(
                    hidden_layer_sizes=(32, 16),
                    activation="tanh",
                    solver="adam",
                    alpha=0.05,
                    batch_size=256,
                    learning_rate_init=0.001,
                    max_iter=500,
                    early_stopping=True,
                    validation_fraction=0.15,
                    n_iter_no_change=25,
                    random_state=seed,
                ),
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConvergenceWarning)
                model.fit(x_train, y)
            predicted = model.predict(x_test) * target_scale + target_center
            local = test[
                ["issue", "issue_year", "action_key", "n", "k", "generator", "effective_k"]
            ].copy()
            local["condition"] = condition
            local["model_seed"] = seed
            for index, column in enumerate(TARGET_COLUMNS):
                local[f"predicted_{column}"] = predicted[:, index]
            local["predicted_positive_probability"] = local[
                "predicted_positive_probability"
            ].clip(0.0, 1.0)
            local["predicted_tail_5x_probability"] = local[
                "predicted_tail_5x_probability"
            ].clip(0.0, 1.0)
            local["predicted_mean_downside_roi"] = local[
                "predicted_mean_downside_roi"
            ].clip(lower=0.0)
            local["predicted_conditional_log_gross"] = local[
                "predicted_conditional_log_gross"
            ].clip(lower=0.0)
            seed_frames.append(local)
            estimator = model[-1]
            receipt_rows.append(
                {
                    "condition": condition,
                    "model_seed": seed,
                    "prediction_year": year,
                    "train_start_year": int(train["issue_year"].min()),
                    "train_end_year": year - 1,
                    "train_issues": int(train["issue"].nunique()),
                    "test_issues": int(test["issue"].nunique()),
                    "train_rows": int(len(train)),
                    "features": int(x_train.shape[1]),
                    "iterations": int(estimator.n_iter_),
                    "converged": not any(
                        isinstance(item.message, ConvergenceWarning) for item in caught
                    ),
                    "final_loss": float(estimator.loss_),
                    "target_scale_min": float(target_scale.min()),
                    "target_scale_max": float(target_scale.max()),
                }
            )
    seed_predictions = pd.concat(seed_frames, ignore_index=True)
    value_columns = [f"predicted_{column}" for column in TARGET_COLUMNS]
    scores = seed_predictions.groupby(
        ["issue", "issue_year", "condition", "action_key", "n", "k", "generator", "effective_k"],
        as_index=False,
    )[value_columns].mean()
    uncertainty = seed_predictions.groupby(
        ["issue", "condition", "action_key"], as_index=False
    )["predicted_mean_roi"].std().rename(
        columns={"predicted_mean_roi": "predicted_mean_roi_std"}
    )
    scores = scores.merge(
        uncertainty, on=["issue", "condition", "action_key"], validate="one_to_one"
    )
    scores["predicted_mean_roi_std"] = scores["predicted_mean_roi_std"].fillna(0.0)
    return scores, seed_predictions, pd.DataFrame(receipt_rows)


def add_policy_scores(frame: pd.DataFrame) -> pd.DataFrame:
    """Add within-issue comparable mean and tail-aware action scores."""

    result = frame.copy()

    def zscore(column: str) -> pd.Series:
        centered = result[column] - result.groupby("issue")[column].transform("mean")
        scale = result.groupby("issue")[column].transform("std").replace(0.0, 1.0)
        return centered / scale.fillna(1.0)

    result["mean_score"] = (
        zscore("predicted_mean_roi")
        - 0.40 * zscore("predicted_mean_downside_roi")
        - 0.25 * zscore("predicted_mean_roi_std")
    )
    result["tail_score"] = (
        0.45 * zscore("predicted_mean_roi")
        + 0.85 * zscore("predicted_tail_5x_probability")
        + 0.25 * zscore("predicted_conditional_log_gross")
        + 0.20 * zscore("predicted_positive_probability")
        - 0.45 * zscore("predicted_mean_downside_roi")
        - 0.25 * zscore("predicted_mean_roi_std")
    )
    return result


def _condition_training(
    train: pd.DataFrame, condition: str, seed: int, year: int
) -> pd.DataFrame:
    result = train.copy()
    rng = np.random.default_rng(seed + year)
    if condition == "ISSUE_BLOCK_SHUFFLED":
        issue_state = result[["issue", "issue_year", *STATE_FEATURES]].drop_duplicates("issue")
        donor_frames = []
        for _, group in issue_state.groupby("issue_year", sort=True):
            donor = group.copy()
            donor[list(STATE_FEATURES)] = group.iloc[
                rng.permutation(len(group))
            ][list(STATE_FEATURES)].to_numpy()
            donor_frames.append(donor)
        replacement = pd.concat(donor_frames, ignore_index=True).set_index("issue")
        for column in STATE_FEATURES:
            result[column] = result["issue"].map(replacement[column])
    elif condition == "IDENTITY_SHUFFLED":
        action_keys = sorted(result["action_key"].unique())
        mapping = dict(zip(action_keys, rng.permutation(action_keys), strict=True))
        targets = result[["issue", "action_key", *TARGET_COLUMNS]].rename(
            columns={column: f"donor_{column}" for column in TARGET_COLUMNS}
        )
        result["donor_action_key"] = result["action_key"].map(mapping)
        result = result.merge(
            targets,
            left_on=["issue", "donor_action_key"],
            right_on=["issue", "action_key"],
            suffixes=("", "_donor"),
            validate="one_to_one",
        )
        for column in TARGET_COLUMNS:
            result[column] = result[f"donor_{column}"]
    return result
