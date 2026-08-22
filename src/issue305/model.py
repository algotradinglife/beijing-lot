"""Expert-label-invariant BEST_FULL keep/skip models for Issue #305."""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEEDS = (305001, 305002, 305003, 305004, 305005)
PREDICTION_YEARS = (2021, 2022, 2023)


@dataclass
class BaselineFit:
    """One dedicated baseline-only fitted value model."""

    condition: str
    model_kind: str
    seed: int
    target_year: int
    feature_columns: tuple[str, ...]
    mean_model: object
    downside_model: object
    loss_model: object
    mean_iterations: int
    downside_iterations: int
    mean_converged: bool
    downside_converged: bool


def fit_predict_expanding(
    issues: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str = "DEDICATED_MLP",
    model_kind: str = "MLP",
    alpha: float = 20.0,
    seeds: tuple[int, ...] = SEEDS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Predict atomic BEST_FULL value from issue state and baseline labels only.

    This function deliberately has no expert-action argument.  It is therefore
    impossible for expert identities, returns, or labels to affect this fit.
    """

    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    if condition not in {
        "DEDICATED_MLP",
        "DEDICATED_MLP_ALPHA5",
        "DEDICATED_MLP_ALPHA50",
        "ISSUE_BLOCK_SHUFFLED",
        "RIDGE_CONTROL",
    }:
        raise ValueError(f"unknown condition: {condition}")
    if model_kind not in {"MLP", "RIDGE"}:
        raise ValueError(f"unknown model kind: {model_kind}")
    use_seeds = seeds if model_kind == "MLP" else (seeds[0],)
    fits: list[BaselineFit] = []
    predictions: list[pd.DataFrame] = []
    active = issues[issues["baseline_active"].eq(1)].copy()
    for target_year in PREDICTION_YEARS:
        train = active[active["issue_year"].lt(target_year)].copy()
        test = active[active["issue_year"].eq(target_year)].copy()
        if train.empty or test.empty:
            continue
        for seed in use_seeds:
            fit = _fit(
                train,
                feature_columns=feature_columns,
                condition=condition,
                model_kind=model_kind,
                alpha=alpha,
                seed=seed,
                target_year=target_year,
            )
            fits.append(fit)
            predictions.append(_predict(fit, test))
    seed_predictions = pd.concat(predictions, ignore_index=True)
    scores = seed_predictions.groupby(
        ["issue", "issue_year", "condition", "model_kind"], as_index=False
    ).agg(
        predicted_pnl_cny=("predicted_pnl_cny", "mean"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_utility_cny=("predicted_utility_cny", "mean"),
        predicted_utility_std_cny=("predicted_utility_cny", "std"),
        positive_seed_count=("predicted_utility_cny", lambda value: int((value > 0).sum())),
    )
    scores["predicted_utility_std_cny"] = scores["predicted_utility_std_cny"].fillna(0.0)
    receipts = pd.DataFrame(
        [
            {
                "condition": fit.condition,
                "model_kind": fit.model_kind,
                "seed": fit.seed,
                "prediction_year": fit.target_year,
                "train_end_year": fit.target_year - 1,
                "active_train_issues": int(
                    active["issue_year"].lt(fit.target_year).sum()
                ),
                "active_test_issues": int(
                    active["issue_year"].eq(fit.target_year).sum()
                ),
                "features": len(fit.feature_columns),
                "mean_iterations": fit.mean_iterations,
                "downside_iterations": fit.downside_iterations,
                "mean_converged": fit.mean_converged,
                "downside_converged": fit.downside_converged,
                "expert_label_inputs": 0,
            }
            for fit in fits
        ]
    )
    return scores, seed_predictions, receipts


def _fit(
    train: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str,
    model_kind: str,
    alpha: float,
    seed: int,
    target_year: int,
) -> BaselineFit:
    feature_values = train[feature_columns].copy()
    if condition == "ISSUE_BLOCK_SHUFFLED":
        rng = np.random.default_rng(seed + target_year)
        for _, index in train.groupby("issue_year").groups.items():
            feature_values.loc[index] = feature_values.loc[
                rng.permutation(index), feature_columns
            ].to_numpy()
    x = feature_values.to_numpy(float)
    pnl = train["baseline_pnl_cny"].to_numpy(float)
    y_mean = pnl / 4_374.0
    y_downside = np.maximum(-pnl, 0.0) / 4_374.0
    if model_kind == "MLP":
        mean_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(8,),
                activation="tanh",
                solver="lbfgs",
                alpha=alpha,
                max_iter=5_000,
                tol=1e-7,
                random_state=seed,
            ),
        )
        downside_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(8,),
                activation="tanh",
                solver="lbfgs",
                alpha=alpha,
                max_iter=5_000,
                tol=1e-7,
                random_state=seed + 10_000,
            ),
        )
    else:
        mean_model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
        downside_model = make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    with warnings.catch_warnings(record=True) as mean_warnings:
        warnings.simplefilter("always", ConvergenceWarning)
        mean_model.fit(x, y_mean)
    with warnings.catch_warnings(record=True) as downside_warnings:
        warnings.simplefilter("always", ConvergenceWarning)
        downside_model.fit(x, y_downside)
    loss_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.2, max_iter=5_000, class_weight="balanced"),
    ).fit(x, pnl < 0)
    mean_estimator = mean_model[-1]
    downside_estimator = downside_model[-1]
    return BaselineFit(
        condition=condition,
        model_kind=model_kind,
        seed=seed,
        target_year=target_year,
        feature_columns=tuple(feature_columns),
        mean_model=mean_model,
        downside_model=downside_model,
        loss_model=loss_model,
        mean_iterations=int(getattr(mean_estimator, "n_iter_", None) or 1),
        downside_iterations=int(getattr(downside_estimator, "n_iter_", None) or 1),
        mean_converged=not any(isinstance(item.message, ConvergenceWarning) for item in mean_warnings),
        downside_converged=not any(
            isinstance(item.message, ConvergenceWarning) for item in downside_warnings
        ),
    )


def _predict(fit: BaselineFit, test: pd.DataFrame) -> pd.DataFrame:
    x = test[list(fit.feature_columns)].to_numpy(float)
    pnl = fit.mean_model.predict(x) * 4_374.0
    downside = np.maximum(fit.downside_model.predict(x) * 4_374.0, 0.0)
    loss_probability = fit.loss_model.predict_proba(x)[:, 1]
    utility = pnl - 0.5 * loss_probability * downside
    return test[["issue", "issue_year"]].assign(
        condition=fit.condition,
        model_kind=fit.model_kind,
        seed=fit.seed,
        predicted_pnl_cny=pnl,
        predicted_downside_cny=downside,
        predicted_loss_probability=loss_probability,
        predicted_utility_cny=utility,
    )
