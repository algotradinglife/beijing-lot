"""Chronological multitask expert scoring models for Issue #332."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .contract import (
    CURRENT_COLUMNS,
    EXPERT_DESCRIPTOR_COLUMNS,
    STATE_LAG_COLUMNS,
    TARGET_COLUMNS,
)
from .data import expert_lag_columns

DENSE_TARGETS = TARGET_COLUMNS[:-1]


@dataclass
class ModelResult:
    predictions: pd.DataFrame
    receipt: dict[str, object]


def current_feature_columns() -> tuple[str, ...]:
    return (*CURRENT_COLUMNS, *EXPERT_DESCRIPTOR_COLUMNS)


def lagged_feature_columns(panel: pd.DataFrame) -> tuple[str, ...]:
    return (
        *CURRENT_COLUMNS,
        *EXPERT_DESCRIPTOR_COLUMNS,
        *STATE_LAG_COLUMNS,
        *expert_lag_columns(panel),
    )


def chronological_predictions(panel: pd.DataFrame) -> ModelResult:
    """Fit expanding 2022/2023/2024 issue-level expert utility predictions."""

    rows: list[pd.DataFrame] = []
    receipts: list[dict[str, object]] = []
    delayed = delay_lag_state(panel, anchors=7)
    shuffled = shuffle_training_identity(panel)
    specifications = (
        ("CURRENT_ONLY_MOE", "RIDGE", panel, panel, current_feature_columns()),
        (
            "LAGGED_MULTITASK_MOE",
            "RIDGE",
            panel,
            panel,
            lagged_feature_columns(panel),
        ),
        (
            "LAGGED_HGB_MOE",
            "HGB",
            panel,
            panel,
            lagged_feature_columns(panel),
        ),
        (
            "LAG_STATE_SHIFTED",
            "RIDGE",
            delayed,
            delayed,
            lagged_feature_columns(delayed),
        ),
        (
            "EXPERT_IDENTITY_SHUFFLED",
            "RIDGE",
            shuffled,
            panel,
            lagged_feature_columns(panel),
        ),
    )
    for year in (2022, 2023, 2024):
        for condition, family, train_source, eval_source, columns in specifications:
            train = train_source[train_source["issue_year"].lt(year)].copy()
            evaluate = eval_source[eval_source["issue_year"].eq(year)].copy()
            result, receipt = fit_stacked_multitask(
                train,
                evaluate,
                feature_columns=columns,
                family=family,
            )
            result["condition"] = condition
            result["prediction_year"] = year
            rows.append(result)
            receipts.append(
                {
                    "condition": condition,
                    "family": family,
                    "prediction_year": year,
                    "training_issues": int(train["issue"].nunique()),
                    "evaluation_issues": int(evaluate["issue"].nunique()),
                    "training_rows": int(len(train)),
                    "evaluation_rows": int(len(evaluate)),
                    "feature_count": len(columns),
                    **receipt,
                }
            )
    prediction = pd.concat(rows, ignore_index=True).sort_values(
        ["prediction_year", "condition", "issue", "expert"]
    )
    return ModelResult(
        prediction,
        {
            "models": receipts,
            "dense_targets": list(DENSE_TARGETS),
            "utility_target": "clipped_roi",
            "utility_training": "RIDGE_ON_CHRONOLOGICAL_OOF_DENSE_PREDICTIONS",
        },
    )


def fit_stacked_multitask(
    train: pd.DataFrame,
    evaluate: pd.DataFrame,
    *,
    feature_columns: tuple[str, ...],
    family: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Predict dense outcomes first, then map chronological OOF outputs to utility."""

    anchors = np.array(sorted(train["issue_anchor_ts"].unique()))
    if len(anchors) < 25:
        raise AssertionError("insufficient chronological anchors")
    splitter = TimeSeriesSplit(n_splits=4)
    oof = np.full((len(train), len(DENSE_TARGETS)), np.nan)
    fold_receipts: list[dict[str, int]] = []
    for fold, (fit_anchor_index, test_anchor_index) in enumerate(splitter.split(anchors)):
        fit_anchors = set(anchors[fit_anchor_index])
        test_anchors = set(anchors[test_anchor_index])
        fit_mask = train["issue_anchor_ts"].isin(fit_anchors).to_numpy()
        test_mask = train["issue_anchor_ts"].isin(test_anchors).to_numpy()
        dense_model = _dense_estimator(family)
        dense_model.fit(
            train.loc[fit_mask, list(feature_columns)],
            train.loc[fit_mask, list(DENSE_TARGETS)],
        )
        oof[test_mask] = dense_model.predict(
            train.loc[test_mask, list(feature_columns)]
        )
        fold_receipts.append(
            {
                "fold": fold,
                "fit_issues": int(train.loc[fit_mask, "issue"].nunique()),
                "test_issues": int(train.loc[test_mask, "issue"].nunique()),
            }
        )
    valid = np.isfinite(oof).all(axis=1)
    if valid.sum() < 100:
        raise AssertionError("insufficient chronological OOF rows for utility head")
    utility_model = make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=20.0),
    )
    utility_design = np.column_stack(
        [oof[valid], train.loc[valid, list(EXPERT_DESCRIPTOR_COLUMNS)].to_numpy(float)]
    )
    utility_model.fit(utility_design, train.loc[valid, "clipped_roi"])

    dense_model = _dense_estimator(family)
    dense_model.fit(train[list(feature_columns)], train[list(DENSE_TARGETS)])
    dense_prediction = dense_model.predict(evaluate[list(feature_columns)])
    utility_evaluation = np.column_stack(
        [
            dense_prediction,
            evaluate[list(EXPERT_DESCRIPTOR_COLUMNS)].to_numpy(float),
        ]
    )
    score = utility_model.predict(utility_evaluation)
    result = evaluate[
        [
            "issue",
            "issue_year",
            "issue_anchor_ts",
            "expert",
            *TARGET_COLUMNS,
        ]
    ].copy()
    for index, target in enumerate(DENSE_TARGETS):
        result[f"predicted_{target}"] = dense_prediction[:, index]
    result["predicted_utility"] = score
    return result, {
        "chronological_oof_rows": int(valid.sum()),
        "chronological_oof_issues": int(train.loc[valid, "issue"].nunique()),
        "folds": fold_receipts,
    }


def _dense_estimator(family: str):
    if family == "RIDGE":
        estimator = Ridge(alpha=20.0)
    elif family == "HGB":
        estimator = MultiOutputRegressor(
            HistGradientBoostingRegressor(
                max_iter=120,
                max_leaf_nodes=15,
                learning_rate=0.05,
                l2_regularization=5.0,
                random_state=332,
            )
        )
    else:
        raise ValueError(family)
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        clone(estimator),
    )


def delay_lag_state(panel: pd.DataFrame, *, anchors: int) -> pd.DataFrame:
    """Causal negative control: use lag state from seven additional anchors ago."""

    frame = panel.copy()
    lag_columns = [*STATE_LAG_COLUMNS, *expert_lag_columns(panel)]
    blocks = (
        frame[["issue_anchor_ts", "expert", *lag_columns]]
        .drop_duplicates(["issue_anchor_ts", "expert"])
        .sort_values(["expert", "issue_anchor_ts"])
    )
    blocks[lag_columns] = blocks.groupby("expert", sort=False)[lag_columns].shift(
        anchors
    )
    frame = frame.drop(columns=lag_columns).merge(
        blocks,
        on=["issue_anchor_ts", "expert"],
        how="left",
        validate="many_to_one",
    )
    return frame


def shuffle_training_identity(panel: pd.DataFrame) -> pd.DataFrame:
    """Permute expert-specific features while preserving issue and exposure rows."""

    frame = panel.copy()
    expert_specific = [*EXPERT_DESCRIPTOR_COLUMNS, *expert_lag_columns(panel)]
    experts = sorted(frame["expert"].unique())
    source = {expert: experts[(index + 3) % len(experts)] for index, expert in enumerate(experts)}
    feature_lookup = frame.set_index(["issue", "expert"])[expert_specific]
    for index, row in frame[["issue", "expert"]].iterrows():
        frame.loc[index, expert_specific] = feature_lookup.loc[
            (row["issue"], source[row["expert"]])
        ].to_numpy()
    return frame
