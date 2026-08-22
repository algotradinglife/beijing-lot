"""Chronological predictive and persistence diagnostics for the regime ledger."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .contract import MARKET_FEATURES, MODEL_SEED, PREDICTION_YEARS, TARGETS, WINDOWS


def _spearman(left: np.ndarray | pd.Series, right: np.ndarray | pd.Series) -> float:
    left_series, right_series = pd.Series(left), pd.Series(right)
    if left_series.nunique(dropna=True) < 2 or right_series.nunique(dropna=True) < 2:
        return np.nan
    return float(left_series.corr(right_series, method="spearman"))


def model_lag_columns(all_lag_columns: list[str]) -> list[str]:
    sources = (
        "eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual",
        "allocator_delta", "pnl_l000", "pnl_l100",
    )
    return [
        column for column in all_lag_columns
        if any(column.startswith(f"lag_{source}_") for source in sources)
        and not column.endswith("_std")
    ]


def _model(family: str):
    if family == "RIDGE":
        return make_pipeline(
            SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=10.0)
        )
    return make_pipeline(
        SimpleImputer(strategy="median"),
        HistGradientBoostingRegressor(
            learning_rate=0.05, max_iter=160, max_leaf_nodes=7,
            min_samples_leaf=12, l2_regularization=10.0, random_state=MODEL_SEED,
        ),
    )


def _usable_columns(train: pd.DataFrame, columns: list[str]) -> list[str]:
    return [column for column in columns if train[column].notna().sum() >= 10]


def _block_shift(frame: pd.DataFrame, columns: list[str], block_size: int = 5) -> pd.DataFrame:
    output = frame.copy()
    if len(frame) <= block_size:
        return output
    blocks = [np.arange(start, min(start + block_size, len(frame))) for start in range(0, len(frame), block_size)]
    shifted = blocks[1:] + blocks[:1]
    order = np.concatenate(shifted)
    output.loc[:, columns] = frame.iloc[order][columns].to_numpy()
    return output


def chronological_predictions(
    state: pd.DataFrame, lag_columns: list[str]
) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    lag_columns = model_lag_columns(lag_columns)
    rows: list[pd.DataFrame] = []
    receipts: dict[str, list[dict]] = {"folds": [], "models": []}
    feature_sets = {
        "CURRENT_RIDGE": ("RIDGE", list(MARKET_FEATURES)),
        "LAG_RIDGE": ("RIDGE", lag_columns),
        "COMBINED_RIDGE": ("RIDGE", [*MARKET_FEATURES, *lag_columns]),
        "COMBINED_HGBR": ("HGBR", [*MARKET_FEATURES, *lag_columns]),
    }
    for target in TARGETS:
        for year in PREDICTION_YEARS:
            train = state[state.issue_year.lt(year) & state[target].notna()].copy()
            test = state[state.issue_year.eq(year) & state[target].notna()].copy()
            if len(train) < 30 or test.empty:
                continue
            receipts["folds"].append({
                "target": target, "prediction_year": year,
                "training_year_max": year - 1,
                "training_issue_codes": train.issue_code.astype(str).tolist(),
                "test_issue_codes": test.issue_code.astype(str).tolist(),
            })
            baseline = float(train[target].mean())
            rows.append(pd.DataFrame({
                "issue_code": test.issue_code.astype(str), "issue_year": year,
                "issue_anchor_ts": test.issue_anchor_ts.astype(str), "target": target,
                "condition": "PRIOR_MEAN", "actual": test[target].to_numpy(float),
                "prediction": baseline,
            }))
            for condition, (family, declared_columns) in feature_sets.items():
                columns = _usable_columns(train, declared_columns)
                estimator = _model(family).fit(train[columns], train[target])
                prediction = estimator.predict(test[columns])
                rows.append(pd.DataFrame({
                    "issue_code": test.issue_code.astype(str), "issue_year": year,
                    "issue_anchor_ts": test.issue_anchor_ts.astype(str), "target": target,
                    "condition": condition, "actual": test[target].to_numpy(float),
                    "prediction": prediction,
                }))
                if condition == "COMBINED_HGBR":
                    shifted = _block_shift(test, [column for column in columns if column in lag_columns])
                    rows.append(pd.DataFrame({
                        "issue_code": test.issue_code.astype(str), "issue_year": year,
                        "issue_anchor_ts": test.issue_anchor_ts.astype(str), "target": target,
                        "condition": "COMBINED_HGBR_STATE_SHIFT",
                        "actual": test[target].to_numpy(float),
                        "prediction": estimator.predict(shifted[columns]),
                    }))
                receipts["models"].append({
                    "target": target, "prediction_year": year, "condition": condition,
                    "family": family, "training_issue_count": len(train),
                    "test_issue_count": len(test), "training_year_max": year - 1,
                    "features": columns,
                })
    return pd.concat(rows, ignore_index=True), receipts


def prediction_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in predictions.groupby(["target", "issue_year", "condition"], sort=True):
        actual = group.actual.to_numpy(float)
        predicted = group.prediction.to_numpy(float)
        nonzero = actual != 0
        rows.append({
            "target": key[0], "issue_year": int(key[1]), "condition": key[2],
            "issues": len(group), "mse": float(mean_squared_error(actual, predicted)),
            "mae": float(mean_absolute_error(actual, predicted)),
            "spearman": _spearman(actual, predicted),
            "direction_accuracy_nonzero": (
                float((np.sign(actual[nonzero]) == np.sign(predicted[nonzero])).mean())
                if nonzero.any() else np.nan
            ),
        })
    output = pd.DataFrame(rows)
    prior = output[output.condition.eq("PRIOR_MEAN")][
        ["target", "issue_year", "mse"]
    ].rename(columns={"mse": "prior_mse"})
    output = output.merge(prior, on=["target", "issue_year"], validate="many_to_one")
    output["mse_lift_vs_prior"] = output.prior_mse - output.mse
    return output


def block_bootstrap_increment(predictions: pd.DataFrame, draws: int = 2000) -> pd.DataFrame:
    pivot = predictions[predictions.condition.isin(["CURRENT_RIDGE", "COMBINED_HGBR"])].pivot(
        index=["issue_code", "issue_year", "issue_anchor_ts", "target"],
        columns="condition", values=["actual", "prediction"],
    )
    rows = []
    rng = np.random.default_rng(MODEL_SEED)
    for (target, year), group in pivot.reset_index().groupby(["target", "issue_year"]):
        actual = group[("actual", "CURRENT_RIDGE")].to_numpy(float)
        current = group[("prediction", "CURRENT_RIDGE")].to_numpy(float)
        combined = group[("prediction", "COMBINED_HGBR")].to_numpy(float)
        improvement = np.square(actual - current) - np.square(actual - combined)
        block = 5
        blocks_per_draw = math.ceil(len(improvement) / block)
        samples = np.empty(draws)
        for draw in range(draws):
            starts = rng.integers(0, len(improvement), size=blocks_per_draw)
            index = ((starts[:, None] + np.arange(block)) % len(improvement)).ravel()[:len(improvement)]
            samples[draw] = improvement[index].mean()
        rows.append({
            "target": target, "issue_year": int(year), "issues": len(improvement),
            "mean_mse_improvement": float(improvement.mean()),
            "ci95_low": float(np.quantile(samples, 0.025)),
            "ci95_high": float(np.quantile(samples, 0.975)),
            "block_size": block, "draws": draws,
        })
    return pd.DataFrame(rows)


def persistence_diagnostics(state: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    autocorrelation_rows = []
    for target in TARGETS:
        values = state[target].dropna().reset_index(drop=True)
        for lag in range(1, 11):
            autocorrelation_rows.append({
                "target": target, "lag_issues": lag, "observations": len(values),
                "autocorrelation": float(values.autocorr(lag=lag)),
            })
    sensitivity_rows = []
    for target in TARGETS:
        for year in (2023, 2024):
            group = state[state.issue_year.eq(year)]
            for window in WINDOWS:
                feature = f"lag_{target}_roll{window}_mean"
                usable = group[[target, feature]].dropna()
                sensitivity_rows.append({
                    "target": target, "issue_year": year, "window": window,
                    "issues": len(usable),
                    "spearman": _spearman(usable[target], usable[feature]),
                })
    return pd.DataFrame(autocorrelation_rows), pd.DataFrame(sensitivity_rows)


def decide(
    state: pd.DataFrame,
    metrics: pd.DataFrame,
    autocorrelation: pd.DataFrame,
    bootstrap: pd.DataFrame,
) -> dict:
    comparison = metrics[metrics.condition.isin(["CURRENT_RIDGE", "COMBINED_HGBR"])].pivot(
        index=["target", "issue_year"], columns="condition", values="mse"
    ).reset_index()
    comparison["combined_better"] = comparison.COMBINED_HGBR < comparison.CURRENT_RIDGE
    calibration_targets = ["eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual"]
    consistent = 0
    for target in calibration_targets:
        rows = comparison[comparison.target.eq(target) & comparison.issue_year.isin([2023, 2024])]
        consistent += int(len(rows) == 2 and rows.combined_better.all())
    robust = bootstrap[
        bootstrap.target.isin(calibration_targets)
        & bootstrap.issue_year.isin([2023, 2024])
    ].ci95_low.gt(0).sum()
    allocator = state.allocator_delta.dropna()
    positive_allocator_issues = int(allocator.gt(0).sum())
    nonzero_allocator_issues = int(allocator.ne(0).sum())
    lag1 = autocorrelation[
        autocorrelation.target.isin(calibration_targets) & autocorrelation.lag_issues.eq(1)
    ].autocorrelation.abs().max()
    calibration_state = consistent >= 2 or robust >= 2
    if calibration_state and positive_allocator_issues >= 10:
        disposition = "REGIME_STATE_OBSERVABLE"
    elif positive_allocator_issues < 10:
        disposition = "SPARSE_RESPONSE_REDESIGN"
    elif lag1 >= 0.1:
        disposition = "SLOW_DRIFT_ONLY"
    else:
        disposition = "NO_REGIME_SIGNAL"
    return {
        "issue": 330, "disposition": disposition,
        "consistent_calibration_targets": consistent,
        "bootstrap_positive_calibration_slices": int(robust),
        "max_abs_calibration_lag1": float(lag1),
        "allocator_observable_issues": len(allocator),
        "allocator_nonzero_issues": nonzero_allocator_issues,
        "allocator_positive_issues": positive_allocator_issues,
        "next_moe_interface": (
            "MULTITASK_LAGGED_CALIBRATION_STATE"
            if disposition == "SPARSE_RESPONSE_REDESIGN" else disposition
        ),
        "promotion": False, "unlock_210": False,
        "claim_boundary": "HISTORICAL_WALK_FORWARD_DIAGNOSTIC",
    }
