"""Stage A: frozen expert-label-invariant BEST_FULL keep/skip (Issue #305).

The Issue #306 contract freezes Stage A to the independent BEST_FULL keep/skip
head produced by Issue #305.  This module is the contract layer:

- If Issue #305 has delivered its frozen output under results/issue-305, load
  and use it verbatim (source=FROM_305_OUTPUT).
- Until then (Issue #305 is a PI-owned in-flight correction), a local reference
  fit with identical semantics is used and tagged
  LOCAL_REFERENCE_FIT_PENDING_305.  It is trained on issue features plus
  BEST_FULL labels only; expert identities, returns, and labels are never
  inputs, so mutating any expert label cannot alter Stage A (the byte-invariant
  property demanded by #305).  The tag forces the decision report to state the
  substitution explicitly rather than pretending #305 has delivered.

No module in Issue #306 back-propagates into Stage A decisions: keep/skip is
computed once from the frozen model and consumed as a constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue306 import PREDICTION_YEARS, SEEDS

STAGE_A_OUTPUT_PATH = Path("results/issue-305/policy_decisions.csv")
SOURCE_TAG_LOCAL = "LOCAL_REFERENCE_FIT_PENDING_305"
SOURCE_TAG_FROZEN = "FROM_305_OUTPUT"

# Decision frame columns shared with #305's corrected dedicated head.
DECISION_COLUMNS = [
    "issue",
    "issue_year",
    "condition",
    "keep_baseline",
    "predicted_baseline_utility_cny",
]


@dataclass
class StageAFit:
    """One frozen Stage A fit (all seeds averaged)."""

    source: str
    condition: str
    feature_columns: tuple[str, ...]
    seed_predictions: pd.DataFrame
    scores: pd.DataFrame
    receipts: pd.DataFrame


def load_frozen_stage_a(root: str | Path) -> pd.DataFrame | None:
    """Return the Issue #305 frozen keep/skip frame if it exists, else None."""

    path = Path(root) / STAGE_A_OUTPUT_PATH
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    required = {"issue", "issue_year", "keep_baseline"}
    if not required.issubset(frame.columns):
        raise AssertionError(f"#305 output missing columns: {required - set(frame.columns)}")
    return frame


def fit_local_reference(
    issues: pd.DataFrame,
    *,
    feature_columns: list[str],
    condition: str = "DEDICATED_MLP",
    seeds: tuple[int, ...] = SEEDS,
) -> StageAFit:
    """Fit the dedicated Stage A head on issue features + BEST_FULL labels only.

    The function has no expert-action argument anywhere, which makes expert
    labels structurally unable to influence the fit.  Expanding chronology:
    2021 <- 2019-20, 2022 <- 2019-21, 2023 <- 2019-22.
    """

    if issues["issue_year"].ge(2024).any():
        raise AssertionError("2024+ is sealed")
    if condition not in {"DEDICATED_MLP"}:
        raise ValueError(f"unknown condition: {condition}")
    active = issues[issues["baseline_active"].eq(1)].copy()
    predictions: list[pd.DataFrame] = []
    receipts: list[dict[str, object]] = []
    for target_year in PREDICTION_YEARS:
        train = active[active["issue_year"].lt(target_year)].copy()
        test = active[active["issue_year"].eq(target_year)].copy()
        if train.empty or test.empty:
            continue
        for seed in seeds:
            frame, receipt = _fit_seed(
                train, test, feature_columns, seed, target_year
            )
            predictions.append(frame)
            receipts.append(receipt)
    seed_predictions = pd.concat(predictions, ignore_index=True)
    scores = seed_predictions.groupby(
        ["issue", "issue_year", "condition"], as_index=False
    ).agg(
        predicted_pnl_cny=("predicted_pnl_cny", "mean"),
        predicted_downside_cny=("predicted_downside_cny", "mean"),
        predicted_loss_probability=("predicted_loss_probability", "mean"),
        predicted_utility_cny=("predicted_utility_cny", "mean"),
        predicted_utility_std_cny=("predicted_utility_cny", "std"),
        positive_seed_count=("predicted_utility_cny", lambda value: int((value > 0).sum())),
    )
    scores["predicted_utility_std_cny"] = scores["predicted_utility_std_cny"].fillna(0.0)
    return StageAFit(
        source=SOURCE_TAG_LOCAL,
        condition=condition,
        feature_columns=tuple(feature_columns),
        seed_predictions=seed_predictions,
        scores=scores,
        receipts=pd.DataFrame(receipts),
    )


def _fit_seed(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    seed: int,
    target_year: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    x = train[feature_columns].to_numpy(float)
    pnl = train["baseline_pnl_cny"].to_numpy(float)
    scale = max(float(np.median(np.abs(pnl - np.median(pnl)))), 1.0)
    y_mean = pnl / scale
    y_downside = np.maximum(-pnl, 0.0) / scale
    with warnings.catch_warnings(record=True) as mean_warnings:
        warnings.simplefilter("always", ConvergenceWarning)
        mean_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(8,), activation="tanh", solver="lbfgs",
                alpha=20.0, max_iter=5_000, tol=1e-7, random_state=seed,
            ),
        ).fit(x, y_mean)
    with warnings.catch_warnings(record=True) as downside_warnings:
        warnings.simplefilter("always", ConvergenceWarning)
        downside_model = make_pipeline(
            StandardScaler(),
            MLPRegressor(
                hidden_layer_sizes=(8,), activation="tanh", solver="lbfgs",
                alpha=20.0, max_iter=5_000, tol=1e-7, random_state=seed + 10_000,
            ),
        ).fit(x, y_downside)
    loss_model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.2, max_iter=5_000, class_weight="balanced"),
    ).fit(x, pnl < 0)
    xt = test[feature_columns].to_numpy(float)
    predicted_pnl = mean_model.predict(xt) * scale
    predicted_downside = np.maximum(downside_model.predict(xt) * scale, 0.0)
    predicted_loss_probability = loss_model.predict_proba(xt)[:, 1]
    predicted_utility = predicted_pnl - 0.5 * predicted_loss_probability * predicted_downside
    frame = test[["issue", "issue_year"]].assign(
        condition="DEDICATED_MLP",
        seed=seed,
        predicted_pnl_cny=predicted_pnl,
        predicted_downside_cny=predicted_downside,
        predicted_loss_probability=predicted_loss_probability,
        predicted_utility_cny=predicted_utility,
    )
    receipt = {
        "seed": seed,
        "prediction_year": target_year,
        "train_end_year": target_year - 1,
        "active_train_issues": int(len(train)),
        "active_test_issues": int(len(test)),
        "features": len(feature_columns),
        "mean_iterations": int(getattr(mean_model[-1], "n_iter_", 1)),
        "downside_iterations": int(getattr(downside_model[-1], "n_iter_", 1)),
        "mean_converged": not any(isinstance(item.message, ConvergenceWarning) for item in mean_warnings),
        "downside_converged": not any(isinstance(item.message, ConvergenceWarning) for item in downside_warnings),
        "expert_label_inputs": 0,
    }
    return frame, receipt


def stage_a_decisions(
    issues: pd.DataFrame,
    stage_a: StageAFit | pd.DataFrame,
) -> pd.DataFrame:
    """Keep an active atomic BEST_FULL only when ensemble utility is positive."""

    if isinstance(stage_a, StageAFit):
        scores = stage_a.scores
        condition = "STAGE_A_REFERENCE"
        source = stage_a.source
    else:
        scores = stage_a
        condition = "STAGE_A_305"
        source = SOURCE_TAG_FROZEN
    result = issues[["issue", "issue_year", "baseline_active"]].merge(
        scores[["issue", "issue_year", "predicted_utility_cny", "keep_baseline"]],
        on=["issue", "issue_year"],
        how="left",
        validate="one_to_one",
    )
    result["condition"] = condition
    # A frozen #305 row carries its own keep_baseline; a local reference has
    # utility only and recomputes the decision from the positive-utility rule.
    if "keep_baseline" in result.columns and result["keep_baseline"].notna().any():
        result["keep_baseline"] = result["keep_baseline"].fillna(False).astype(bool)
        result["keep_baseline"] = result["keep_baseline"] & result["baseline_active"].eq(1)
    else:
        result["keep_baseline"] = (
            result["baseline_active"].eq(1)
            & result["predicted_utility_cny"].fillna(-np.inf).gt(0)
        )
    result["stage_a_source"] = source
    return result.drop(columns="baseline_active")