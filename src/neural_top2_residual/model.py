"""Anchored linear and neural residual models for Issue #334."""

from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .contract import FEATURE_COLUMNS, MLP_CONFIGS, MODEL_SEEDS, OUTCOMES, TRAIN_YEARS


@dataclass
class ResidualPreprocessor:
    imputer: SimpleImputer
    x_scaler: StandardScaler
    y_scaler: StandardScaler

    def transform_x(self, frame: pd.DataFrame) -> np.ndarray:
        values = frame.loc[:, FEATURE_COLUMNS].to_numpy(float)
        return self.x_scaler.transform(self.imputer.transform(values))


def prepare_training(cells: pd.DataFrame) -> tuple[pd.DataFrame, ResidualPreprocessor, np.ndarray, np.ndarray]:
    train = cells[
        cells["issue_year"].isin(TRAIN_YEARS) & cells["settlement_available"]
    ].copy()
    x_raw = train.loc[:, FEATURE_COLUMNS].to_numpy(float)
    imputer = SimpleImputer(strategy="median")
    x_imputed = imputer.fit_transform(x_raw)
    x_scaler = StandardScaler()
    x = x_scaler.fit_transform(x_imputed)
    targets = np.column_stack(
        [
            train["target_probability"].to_numpy(float) - train["q_eu"].to_numpy(float),
            train["target_value"].to_numpy(float) - train["market_value_anchor"].to_numpy(float),
        ]
    )
    y_scaler = StandardScaler()
    y = y_scaler.fit_transform(targets)
    return train, ResidualPreprocessor(imputer, x_scaler, y_scaler), x, y


def fit_linear_predictions(cells: pd.DataFrame) -> pd.DataFrame:
    train, prep, x, y = prepare_training(cells)
    del train
    model = Ridge(alpha=10.0)
    model.fit(x, y)
    evaluation = cells[cells["issue_year"].ge(2023)].copy()
    return _prediction_frame(
        evaluation, "LINEAR", -1, model.predict(prep.transform_x(evaluation)), prep
    )


def fit_mlp_predictions(
    cells: pd.DataFrame,
    config: dict[str, object],
    seed: int,
    *,
    shuffle_labels: bool = False,
) -> pd.DataFrame:
    train, prep, x, y = prepare_training(cells)
    if shuffle_labels:
        rng = np.random.default_rng(seed + 991)
        shuffled = y.copy()
        for outcome in OUTCOMES:
            positions = np.flatnonzero(train["outcome"].eq(outcome).to_numpy())
            shuffled[positions] = shuffled[rng.permutation(positions)]
        y = shuffled
    model = MLPRegressor(
        hidden_layer_sizes=tuple(config["hidden_layer_sizes"]),
        alpha=float(config["alpha"]),
        random_state=seed,
        max_iter=100,
        batch_size=512,
        learning_rate_init=0.001,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=8,
        tol=1e-4,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        model.fit(x, y)
    name = f"{config['name']}{'_LABEL_SHUFFLED' if shuffle_labels else ''}"
    evaluation = cells[cells["issue_year"].ge(2023)].copy()
    result = _prediction_frame(
        evaluation, name, seed, model.predict(prep.transform_x(evaluation)), prep
    )
    result["fit_iterations"] = int(model.n_iter_)
    return result


def fit_candidate_surface(cells: pd.DataFrame) -> pd.DataFrame:
    frames = [fit_linear_predictions(cells)]
    for config in MLP_CONFIGS:
        for seed in MODEL_SEEDS:
            frames.append(fit_mlp_predictions(cells, config, seed))
    return pd.concat(frames, ignore_index=True)


def fit_shuffled_surface(cells: pd.DataFrame, selected_config: str) -> pd.DataFrame:
    config = next(item for item in MLP_CONFIGS if item["name"] == selected_config)
    return pd.concat(
        [fit_mlp_predictions(cells, config, seed, shuffle_labels=True) for seed in MODEL_SEEDS],
        ignore_index=True,
    )


def _prediction_frame(
    cells: pd.DataFrame,
    model_name: str,
    seed: int,
    scaled_residual: np.ndarray,
    prep: ResidualPreprocessor,
) -> pd.DataFrame:
    residual = prep.y_scaler.inverse_transform(np.asarray(scaled_residual))
    result = cells[
        ["issue", "issue_year", "issue_anchor_ts", "match_idx", "outcome", "q_eu", "q_line", "market_value_anchor"]
    ].copy()
    result["model"] = model_name
    result["seed"] = int(seed)
    result["raw_probability"] = result["q_eu"].to_numpy(float) + residual[:, 0]
    result["predicted_value"] = np.clip(
        result["market_value_anchor"].to_numpy(float) + residual[:, 1], 1e-6, 25.0
    )
    result["predicted_probability"] = result["raw_probability"].clip(1e-6, 1.0)
    denominator = result.groupby(["issue", "match_idx", "model", "seed"])[
        "predicted_probability"
    ].transform("sum")
    result["predicted_probability"] = result["predicted_probability"] / denominator
    result["probability_residual"] = result["predicted_probability"] - result["q_eu"]
    result["value_residual"] = result["predicted_value"] - result["market_value_anchor"]
    return result


def prediction_diagnostics(predictions: pd.DataFrame, labelled: pd.DataFrame) -> pd.DataFrame:
    observed = labelled[
        ["issue", "match_idx", "outcome", "target_probability", "target_value", "settlement_available"]
    ]
    frame = predictions.merge(observed, on=["issue", "match_idx", "outcome"], validate="many_to_one")
    frame = frame[frame["settlement_available"]].copy()
    rows: list[dict[str, object]] = []
    for (model, seed, year), group in frame.groupby(["model", "seed", "issue_year"], sort=True):
        p = group["predicted_probability"].clip(1e-9, 1 - 1e-9)
        y = group["target_probability"]
        value = group["predicted_value"]
        target_value = group["target_value"]
        rows.append(
            {
                "model": model,
                "seed": int(seed),
                "issue_year": int(year),
                "cells": int(len(group)),
                "brier": float(np.mean((p - y) ** 2)),
                "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))),
                "value_mae": float(np.mean(np.abs(value - target_value))),
                "value_rank_correlation": float(value.corr(target_value, method="spearman")),
                "mean_abs_probability_residual": float(group["probability_residual"].abs().mean()),
            }
        )
    return pd.DataFrame(rows)
