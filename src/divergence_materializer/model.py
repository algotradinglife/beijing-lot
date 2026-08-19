"""Chronological controls and European-plus-line translator for #238."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    EXPERIMENTAL_FEATURES,
    HORIZONS,
    MODEL_VERSION,
    OUTCOMES,
)


class ModelContractError(ValueError):
    """Raised when a chronological model cannot satisfy the frozen design."""


@dataclass
class HorizonModel:
    horizon: str
    control: Pipeline
    experimental: Pipeline
    accepted: bool
    metrics: pd.DataFrame
    bootstrap: pd.DataFrame


def _pipeline(*, experimental: bool) -> Pipeline:
    numeric = list(EXPERIMENTAL_FEATURES[1:]) if experimental else []
    transformers: list[tuple[str, Any, list[str]]] = [
        (
            "line",
            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            ["native_handicap_line"],
        )
    ]
    if numeric:
        transformers.append(("numeric", StandardScaler(), numeric))
    return Pipeline(
        [
            (
                "features",
                ColumnTransformer(transformers, remainder="drop"),
            ),
            (
                "model",
                LogisticRegression(
                    solver="lbfgs",
                    max_iter=1_000,
                    random_state=BOOTSTRAP_SEED,
                ),
            ),
        ]
    )


def _ordered_probability(model: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(frame)
    classes = [str(value) for value in model.named_steps["model"].classes_]
    missing = set(OUTCOMES) - set(classes)
    if missing:
        raise ModelContractError(
            f"fitted model lacks outcome classes: {sorted(missing)}"
        )
    return raw[:, [classes.index(code) for code in OUTCOMES]]


def multiclass_brier(target: pd.Series, probability: np.ndarray) -> float:
    index = {code: position for position, code in enumerate(OUTCOMES)}
    observed = np.zeros_like(probability)
    observed[np.arange(len(target)), [index[str(value)] for value in target]] = 1.0
    return float(np.mean(np.sum((probability - observed) ** 2, axis=1)))


def multiclass_ece(
    target: pd.Series, probability: np.ndarray, *, bins: int = 10
) -> float:
    """Classwise equal-width ECE, averaged across all three outcomes."""

    target_values = target.astype(str).to_numpy()
    edges = np.linspace(0.0, 1.0, bins + 1)
    errors: list[float] = []
    for position, code in enumerate(OUTCOMES):
        predicted = probability[:, position]
        observed = (target_values == code).astype(float)
        bucket = np.minimum(np.digitize(predicted, edges[1:-1]), bins - 1)
        error = 0.0
        for value in range(bins):
            mask = bucket == value
            if mask.any():
                error += float(mask.mean()) * abs(
                    float(predicted[mask].mean()) - float(observed[mask].mean())
                )
        errors.append(error)
    return float(np.mean(errors))


def _metric_row(
    frame: pd.DataFrame,
    probability: np.ndarray,
    *,
    horizon: str,
    role: str,
    model_name: str,
    line_scope: str,
) -> dict[str, object]:
    target = frame["target_outcome"].astype(str)
    target_index = np.array([OUTCOMES.index(value) for value in target])
    ordered_log_loss = float(
        -np.log(
            np.clip(probability[np.arange(len(target)), target_index], 1e-15, 1.0)
        ).mean()
    )
    return {
        "horizon": horizon,
        "temporal_role": role,
        "model": model_name,
        "line_scope": line_scope,
        "issues": int(frame["issue_code"].nunique()),
        "fixtures": int(len(frame)),
        "log_loss": ordered_log_loss,
        "brier": multiclass_brier(target, probability),
        "ece": multiclass_ece(target, probability),
    }


def _per_issue_loss(
    frame: pd.DataFrame,
    control_probability: np.ndarray,
    experimental_probability: np.ndarray,
) -> pd.DataFrame:
    target = frame["target_outcome"].astype(str).to_numpy()
    target_index = np.array([OUTCOMES.index(value) for value in target])
    row = pd.DataFrame(
        {
            "issue_code": frame["issue_code"].astype(str).to_numpy(),
            "control_log_loss": -np.log(
                np.clip(
                    control_probability[np.arange(len(frame)), target_index], 1e-15, 1.0
                )
            ),
            "experimental_log_loss": -np.log(
                np.clip(
                    experimental_probability[np.arange(len(frame)), target_index],
                    1e-15,
                    1.0,
                )
            ),
        }
    )
    observed = np.zeros_like(control_probability)
    observed[np.arange(len(frame)), target_index] = 1.0
    row["control_brier"] = np.sum((control_probability - observed) ** 2, axis=1)
    row["experimental_brier"] = np.sum(
        (experimental_probability - observed) ** 2, axis=1
    )
    return row.groupby("issue_code", sort=True).mean().reset_index()


def _issue_bootstrap(
    per_issue: pd.DataFrame,
    *,
    horizon: str,
    role: str,
) -> pd.DataFrame:
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    rows: list[dict[str, object]] = []
    for metric in ("log_loss", "brier"):
        delta = (
            per_issue[f"experimental_{metric}"] - per_issue[f"control_{metric}"]
        ).to_numpy(dtype=float)
        draws = rng.choice(
            delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True
        ).mean(axis=1)
        rows.append(
            {
                "horizon": horizon,
                "temporal_role": role,
                "metric": metric,
                "issues": int(len(delta)),
                "experimental_minus_control": float(delta.mean()),
                "ci_low": float(np.quantile(draws, 0.025)),
                "ci_high": float(np.quantile(draws, 0.975)),
                "bootstrap_unit": "issue",
                "bootstrap_draws": BOOTSTRAP_DRAWS,
            }
        )
    return pd.DataFrame(rows)


def fit_horizon_models(development: pd.DataFrame) -> list[HorizonModel]:
    """Fit fixed models through 2021 and freeze acceptance on 2022/2023."""

    fitted: list[HorizonModel] = []
    for horizon in HORIZONS:
        horizon_frame = development.loc[
            development["snapshot_kind"].eq(horizon)
            & development["target_outcome"].notna()
            & development["native_line_supported"]
        ].copy()
        train = horizon_frame.loc[horizon_frame["temporal_role"].eq("fit")]
        if train.empty or set(train["target_outcome"].astype(str)) != set(OUTCOMES):
            raise ModelContractError(
                f"{horizon}: fit partition lacks three-class support"
            )
        control = _pipeline(experimental=False)
        experimental = _pipeline(experimental=True)
        control.fit(train, train["target_outcome"].astype(str))
        experimental.fit(train, train["target_outcome"].astype(str))

        metric_rows: list[dict[str, object]] = []
        bootstrap_frames: list[pd.DataFrame] = []
        role_deltas: dict[str, dict[str, float]] = {}
        for role in ("tune", "calibration"):
            evaluation = horizon_frame.loc[
                horizon_frame["temporal_role"].eq(role)
                & horizon_frame["native_handicap_line"].ne(0)
            ].copy()
            if evaluation.empty:
                raise ModelContractError(f"{horizon}: {role} has no non-zero-line rows")
            control_probability = _ordered_probability(control, evaluation)
            experimental_probability = _ordered_probability(experimental, evaluation)
            for name, probability in (
                ("LINE_ONLY_CONTROL", control_probability),
                ("EU_PLUS_LINE_LOGIT", experimental_probability),
            ):
                metric_rows.append(
                    _metric_row(
                        evaluation,
                        probability,
                        horizon=horizon,
                        role=role,
                        model_name=name,
                        line_scope="NONZERO",
                    )
                )
            per_issue = _per_issue_loss(
                evaluation, control_probability, experimental_probability
            )
            bootstrap = _issue_bootstrap(per_issue, horizon=horizon, role=role)
            bootstrap_frames.append(bootstrap)
            role_deltas[role] = {
                str(row.metric): float(row.experimental_minus_control)
                for row in bootstrap.itertuples(index=False)
            }

        zero = horizon_frame.loc[
            horizon_frame["temporal_role"].isin(["tune", "calibration"])
            & horizon_frame["native_handicap_line"].eq(0)
        ].copy()
        if not zero.empty:
            identity = zero[[f"q_eu_{code}" for code in OUTCOMES]].to_numpy(dtype=float)
            for role, group in zero.groupby("temporal_role", sort=True):
                positions = group.index.map(
                    {index: offset for offset, index in enumerate(zero.index)}
                )
                metric_rows.append(
                    _metric_row(
                        group,
                        identity[np.asarray(positions, dtype=int)],
                        horizon=horizon,
                        role=str(role),
                        model_name="ZERO_LINE_IDENTITY",
                        line_scope="ZERO",
                    )
                )

        tune = role_deltas["tune"]
        calibration = role_deltas["calibration"]
        accepted = bool(
            tune["log_loss"] < 0
            and tune["brier"] < 0
            and calibration["log_loss"] <= 0
            and calibration["brier"] <= 0
        )
        fitted.append(
            HorizonModel(
                horizon=horizon,
                control=control,
                experimental=experimental,
                accepted=accepted,
                metrics=pd.DataFrame(metric_rows),
                bootstrap=pd.concat(bootstrap_frames, ignore_index=True),
            )
        )
    return fitted


def predict_panel(panel: pd.DataFrame, models: list[HorizonModel]) -> pd.DataFrame:
    """Apply frozen controls and accepted translators without opening labels."""

    rows: list[pd.DataFrame] = []
    for fitted in models:
        frame = panel.loc[
            panel["snapshot_kind"].eq(fitted.horizon) & panel["native_line_supported"]
        ].copy()
        control = _ordered_probability(fitted.control, frame)
        experimental = _ordered_probability(fitted.experimental, frame)
        for position, code in enumerate(OUTCOMES):
            frame[f"q_line_control_{code}"] = control[:, position]
            frame[f"q_eu_bjline_candidate_{code}"] = experimental[:, position]
            identity = frame["native_handicap_line"].eq(0)
            accepted = identity | fitted.accepted
            frame[f"q_eu_bjline_{code}"] = np.where(
                identity,
                frame[f"q_eu_{code}"],
                np.where(fitted.accepted, experimental[:, position], np.nan),
            )
            frame[f"divergence_{code}"] = np.where(
                accepted,
                frame[f"q_eu_bjline_{code}"] - frame[f"q_line_control_{code}"],
                np.nan,
            )
        frame["mapping_accepted"] = (
            frame["native_handicap_line"].eq(0) | fitted.accepted
        )
        frame["mapping_status"] = np.select(
            [
                frame["native_handicap_line"].eq(0),
                pd.Series(fitted.accepted, index=frame.index),
            ],
            ["AVAILABLE_ZERO_LINE_IDENTITY", "AVAILABLE_ACCEPTED_EU_PLUS_LINE"],
            default="DIAGNOSTIC_REJECTED_NONZERO_TRANSLATOR",
        )
        frame["model_version"] = MODEL_VERSION
        rows.append(frame)
    predicted = pd.concat(rows, ignore_index=True)
    unavailable = panel.loc[~panel["native_line_supported"]].copy()
    if not unavailable.empty:
        for code in OUTCOMES:
            for prefix in (
                "q_line_control",
                "q_eu_bjline_candidate",
                "q_eu_bjline",
                "divergence",
            ):
                unavailable[f"{prefix}_{code}"] = np.nan
        unavailable["mapping_accepted"] = False
        unavailable["mapping_status"] = np.where(
            unavailable["native_handicap_line"].isna(),
            "UNAVAILABLE_MISSING_NATIVE_LINE",
            "UNAVAILABLE_UNSUPPORTED_NATIVE_LINE",
        )
        unavailable["model_version"] = MODEL_VERSION
        predicted = pd.concat([predicted, unavailable], ignore_index=True)
    return predicted.sort_values(
        ["issue_code", "match_idx", "snapshot_kind"], kind="mergesort"
    ).reset_index(drop=True)
