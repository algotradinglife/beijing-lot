"""Rare-event sampling, calibration, and evaluation helpers for Issue #291."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss


@dataclass(frozen=True)
class CalibrationResult:
    """One-dimensional chronological Platt calibration result."""

    intercept: float
    coefficient: float
    fitted: bool


def deterministic_rare_event_sample(
    frame: pd.DataFrame,
    *,
    negative_per_action: int = 24,
) -> pd.DataFrame:
    """Keep all positives and a weighted deterministic negative sample.

    The returned ``issue_weight`` sums to one within every Beijing issue, so
    ticket and candidate multiplicity cannot create artificial history.
    """

    required = {"issue", "action_key", "candidate_identity", "hit"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"rare-event sample missing columns: {missing}")
    if negative_per_action <= 0:
        raise ValueError("negative_per_action must be positive")
    work = frame.copy()
    work["issue"] = work["issue"].astype(str)
    positive = work.loc[work["hit"].eq(1)].copy()
    negative = work.loc[work["hit"].eq(0)].copy()
    population = negative.groupby(["issue", "action_key"])["issue"].transform("size")
    negative["_population"] = population
    negative["_hash"] = pd.util.hash_pandas_object(
        negative[["issue", "action_key", "candidate_identity"]], index=False
    ).to_numpy()
    negative = (
        negative.sort_values(["issue", "action_key", "_hash"])
        .groupby(["issue", "action_key"], as_index=False)
        .head(negative_per_action)
    )
    sampled = negative.groupby(["issue", "action_key"])["issue"].transform("size")
    negative["sampling_weight"] = negative["_population"] / sampled
    positive["sampling_weight"] = 1.0
    result = pd.concat(
        [positive, negative.drop(columns=["_hash", "_population"])],
        ignore_index=True,
    )
    result["issue_weight"] = result["sampling_weight"] / result.groupby("issue")[
        "sampling_weight"
    ].transform("sum")
    error = float((result.groupby("issue")["issue_weight"].sum() - 1.0).abs().max())
    if error > 1e-10:
        raise AssertionError("issue-normalized sample weights do not sum to one")
    return result


def fit_platt_calibrator(
    raw_probability: np.ndarray,
    target: np.ndarray,
    sample_weight: np.ndarray,
) -> CalibrationResult:
    """Fit a chronological Platt map without refitting the upstream model."""

    probability = np.clip(np.asarray(raw_probability, dtype=float), 1e-8, 1 - 1e-8)
    y = np.asarray(target, dtype=int)
    weight = np.asarray(sample_weight, dtype=float)
    if len(np.unique(y)) < 2:
        return CalibrationResult(0.0, 1.0, False)
    logit = np.log(probability / (1.0 - probability)).reshape(-1, 1)
    model = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
    model.fit(logit, y, sample_weight=weight)
    return CalibrationResult(
        intercept=float(model.intercept_[0]),
        coefficient=float(model.coef_[0, 0]),
        fitted=True,
    )


def apply_platt_calibrator(
    raw_probability: np.ndarray,
    calibration: CalibrationResult,
) -> np.ndarray:
    """Apply a frozen Platt map and return bounded probabilities."""

    probability = np.clip(np.asarray(raw_probability, dtype=float), 1e-8, 1 - 1e-8)
    if not calibration.fitted:
        return probability
    logit = np.log(probability / (1.0 - probability))
    linear = calibration.intercept + calibration.coefficient * logit
    return 1.0 / (1.0 + np.exp(-np.clip(linear, -40.0, 40.0)))


def derived_ticket_ev(
    probability: np.ndarray,
    conditional_gross: np.ndarray,
    *,
    stake_cny: float = 2.0,
) -> np.ndarray:
    """Convert decomposed heads into expected net ticket value."""

    if stake_cny <= 0:
        raise ValueError("stake_cny must be positive")
    probability = np.clip(np.asarray(probability, dtype=float), 0.0, 1.0)
    gross = np.clip(np.asarray(conditional_gross, dtype=float), 0.0, None)
    return probability * gross - stake_cny


def weighted_probability_metrics(
    target: np.ndarray,
    probability: np.ndarray,
    sample_weight: np.ndarray,
) -> dict[str, float]:
    """Return issue-weighted proper scoring rules."""

    y = np.asarray(target, dtype=int)
    p = np.clip(np.asarray(probability, dtype=float), 1e-12, 1 - 1e-12)
    weight = np.asarray(sample_weight, dtype=float)
    return {
        "brier": float(brier_score_loss(y, p, sample_weight=weight)),
        "log_loss": float(log_loss(y, p, sample_weight=weight, labels=[0, 1])),
        "average_precision": float(average_precision_score(y, p, sample_weight=weight)),
        "weighted_event_rate": float(np.average(y, weights=weight)),
        "weighted_predicted_rate": float(np.average(p, weights=weight)),
    }


def reliability_table(
    frame: pd.DataFrame,
    *,
    probability_column: str,
    bins: int = 10,
) -> pd.DataFrame:
    """Build weighted equal-frequency reliability bins."""

    required = {"hit", "issue_weight", probability_column}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"reliability table missing columns: {missing}")
    work = frame.copy()
    rank = work[probability_column].rank(method="first", pct=True)
    work["probability_bin"] = np.minimum((rank * bins).astype(int), bins - 1)
    rows = []
    for value, group in work.groupby("probability_bin", sort=True):
        weight = group["issue_weight"].to_numpy(float)
        rows.append(
            {
                "probability_bin": int(value),
                "rows": len(group),
                "predicted_probability": float(
                    np.average(group[probability_column], weights=weight)
                ),
                "observed_rate": float(np.average(group["hit"], weights=weight)),
                "weight": float(weight.sum()),
            }
        )
    return pd.DataFrame(rows)


def stable_random_score(issue: str, identity: str) -> float:
    """Return a deterministic pseudo-random score in [0, 1)."""

    digest = hashlib.sha256(f"291|{issue}|{identity}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64
