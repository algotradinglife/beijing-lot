"""Reusable cutoff-bound mapping API with replayable model and gate receipts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.temporal_learning import (
    AvailabilityFilter,
    Cutoff,
    PartitionPolicy,
    TemporalContractError,
    WalkForwardRunner,
    WeightingPolicy,
    prepare_learning_context,
)
from src.temporal_learning.core import stable_frame_hash, stable_json_hash, utc

from .contract import (
    CONTRACT_ID,
    MODEL_RANDOM_STATE,
    NUMERIC_FEATURES,
    OUTCOMES,
    PROBABILITY_ATOL,
)


CutoffContractError = TemporalContractError


@dataclass
class MappingResult:
    cutoff: Cutoff
    accepted: bool
    experimental: Pipeline
    control: Pipeline
    mapped: pd.DataFrame
    weights: pd.DataFrame
    receipt: dict[str, Any]


def _implementation_hash() -> str:
    return stable_json_hash({
        path.name: path.read_text(encoding="utf-8")
        for path in [Path(__file__), Path(__file__).with_name("contract.py")]
    })


def _pipeline(*, experimental: bool) -> Pipeline:
    transformers: list[tuple[str, Any, list[str]]] = [
        ("line", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["native_handicap_line"])
    ]
    if experimental:
        transformers.append(("numeric", StandardScaler(), list(NUMERIC_FEATURES)))
    return Pipeline([
        ("features", ColumnTransformer(transformers, remainder="drop")),
        ("model", LogisticRegression(solver="lbfgs", max_iter=1_000, random_state=MODEL_RANDOM_STATE)),
    ])


def _ordered_probability(model: Pipeline, frame: pd.DataFrame) -> np.ndarray:
    raw = model.predict_proba(frame)
    classes = [str(value) for value in model.named_steps["model"].classes_]
    if set(classes) != set(OUTCOMES):
        raise CutoffContractError("fitted model lacks exact 3/1/0 classes")
    probability = raw[:, [classes.index(code) for code in OUTCOMES]]
    if not np.isfinite(probability).all() or (probability <= 0).any():
        raise CutoffContractError("mapping emitted invalid probabilities")
    if not np.allclose(probability.sum(axis=1), 1.0, rtol=0, atol=PROBABILITY_ATOL):
        raise CutoffContractError("mapping probabilities do not sum to one")
    return probability


def _losses(frame: pd.DataFrame, probability: np.ndarray) -> tuple[float, float]:
    target = frame["target_outcome"].astype(str).to_numpy()
    positions = np.asarray([OUTCOMES.index(value) for value in target])
    log_loss = float(-np.log(np.clip(probability[np.arange(len(frame)), positions], 1e-15, 1)).mean())
    observed = np.zeros_like(probability)
    observed[np.arange(len(frame)), positions] = 1.0
    brier = float(np.mean(np.sum(np.square(probability - observed), axis=1)))
    return log_loss, brier


def _model_state(model: Pipeline, *, experimental: bool) -> dict[str, Any]:
    transform = model.named_steps["features"]
    line = transform.named_transformers_["line"]
    estimator = model.named_steps["model"]
    state: dict[str, Any] = {
        "experimental": experimental,
        "line_categories": [float(value) for value in line.categories_[0]],
        "numeric_features": list(NUMERIC_FEATURES) if experimental else [],
        "classes": [str(value) for value in estimator.classes_],
        "coef": estimator.coef_.tolist(),
        "intercept": estimator.intercept_.tolist(),
        "n_iter": estimator.n_iter_.tolist(),
    }
    if experimental:
        scaler = transform.named_transformers_["numeric"]
        state["numeric_mean"] = scaler.mean_.tolist()
        state["numeric_scale"] = scaler.scale_.tolist()
    state["state_sha256"] = stable_json_hash(state)
    return state


def _validate_inputs(development: pd.DataFrame, target: pd.DataFrame, cutoff: Cutoff) -> None:
    required_development = {
        "issue_code", "issue_year", "fixture_decision_ts", "label_available_ts", "target_outcome",
        "native_line_supported", "native_handicap_line", *NUMERIC_FEATURES,
    }
    required_target = {
        "issue_code", "issue_year", "fixture_decision_ts", "native_line_supported",
        "native_handicap_line", "q_eu_3", "q_eu_1", "q_eu_0", *NUMERIC_FEATURES,
    }
    if not required_development.issubset(development) or not required_target.issubset(target):
        raise CutoffContractError("mapping input lacks chronology, label, or feature columns")
    if development["label_available_ts"].isna().any() or target["fixture_decision_ts"].isna().any():
        raise CutoffContractError("mapping input has missing chronology receipts")
    if utc(target["fixture_decision_ts"].min()) < cutoff.cutoff_ts:
        raise CutoffContractError("target decision precedes explicit cutoff")


def fit_cutoff_mapping(
    development: pd.DataFrame,
    target: pd.DataFrame,
    cutoff: Cutoff,
    *,
    source_hashes: Mapping[str, str],
    weighting_policy: WeightingPolicy | None = None,
    helper_hashes: Mapping[str, str] | None = None,
) -> MappingResult:
    """Fit, gate, refit and map using labels strictly available before cutoff."""

    development, target = development.copy(), target.copy()
    _validate_inputs(development, target, cutoff)
    development["label_available_ts"] = pd.to_datetime(development["label_available_ts"], utc=True)
    target["fixture_decision_ts"] = pd.to_datetime(target["fixture_decision_ts"], utc=True)
    admissible_history = development[
        development["target_outcome"].astype(str).isin(OUTCOMES)
        & development["native_line_supported"].eq(True)
    ].copy()
    weighting_policy = weighting_policy or WeightingPolicy.expanding_equal()
    helper_hashes = dict(sorted((helper_hashes or {}).items()))
    implementation_hashes = {
        "cutoff_mapping.client": _implementation_hash(),
        "temporal_learning.core": stable_json_hash(
            (Path(__file__).parents[1] / "temporal_learning/core.py").read_text(encoding="utf-8")
        ),
        **helper_hashes,
    }
    context = prepare_learning_context(
        admissible_history,
        cutoff,
        source_hashes=source_hashes,
        implementation_hashes=implementation_hashes,
        availability=AvailabilityFilter(data_available_column="fixture_decision_ts"),
        partition_policy=PartitionPolicy(),
        weighting_policy=weighting_policy,
    )
    eligible, weights = context.eligible, context.weights
    fit = context.partitions["fit"]
    tune = context.partitions["tune"][context.partitions["tune"]["native_handicap_line"].ne(0)]
    calibration = context.partitions["calibration"][
        context.partitions["calibration"]["native_handicap_line"].ne(0)
    ]
    for name, frame in [("fit", fit), ("tune", tune), ("calibration", calibration)]:
        if frame.empty or set(frame["target_outcome"].astype(str)) != set(OUTCOMES):
            raise CutoffContractError(f"{name} partition lacks exact three-class history")
        if not frame["label_available_ts"].lt(cutoff.cutoff_ts).all():
            raise CutoffContractError(f"{name} partition crosses cutoff")

    gate_control, gate_experimental = _pipeline(experimental=False), _pipeline(experimental=True)
    gate_control.fit(fit, fit["target_outcome"].astype(str), model__sample_weight=weights.loc[fit.index])
    gate_experimental.fit(fit, fit["target_outcome"].astype(str), model__sample_weight=weights.loc[fit.index])
    metrics: dict[str, dict[str, float]] = {}
    predicates: dict[str, bool] = {}
    for role, frame in [("tune", tune), ("calibration", calibration)]:
        control_loss = _losses(frame, _ordered_probability(gate_control, frame))
        experimental_loss = _losses(frame, _ordered_probability(gate_experimental, frame))
        delta = {
            "log_loss": experimental_loss[0] - control_loss[0],
            "brier": experimental_loss[1] - control_loss[1],
        }
        metrics[role] = {
            "control_log_loss": control_loss[0], "experimental_log_loss": experimental_loss[0],
            "experimental_minus_control_log_loss": delta["log_loss"],
            "control_brier": control_loss[1], "experimental_brier": experimental_loss[1],
            "experimental_minus_control_brier": delta["brier"],
        }
        predicates[f"{role}_log_loss_nonworse"] = bool(delta["log_loss"] < 0 if role == "tune" else delta["log_loss"] <= 0)
        predicates[f"{role}_brier_nonworse"] = bool(delta["brier"] < 0 if role == "tune" else delta["brier"] <= 0)
    accepted = bool(all(predicates.values()))

    control, experimental = _pipeline(experimental=False), _pipeline(experimental=True)
    control.fit(eligible, eligible["target_outcome"].astype(str), model__sample_weight=weights)
    experimental.fit(eligible, eligible["target_outcome"].astype(str), model__sample_weight=weights)
    control_probability = _ordered_probability(control, target)
    candidate_probability = _ordered_probability(experimental, target)
    zero_line = target["native_handicap_line"].eq(0).to_numpy()
    mapped = target[["issue_code", "issue_year", "match_idx", "fixture_decision_ts", "native_handicap_line"]].copy()
    for position, outcome in enumerate(OUTCOMES):
        mapped[f"q_line_{outcome}"] = control_probability[:, position]
        mapped[f"q_candidate_{outcome}"] = np.where(
            zero_line, target[f"q_eu_{outcome}"].to_numpy(float), candidate_probability[:, position]
        )
        mapped[f"q_mapped_{outcome}"] = np.where(
            zero_line | accepted, mapped[f"q_candidate_{outcome}"], np.nan
        )
    mapped["mapping_accepted"] = zero_line | accepted
    mapped["mapping_status"] = np.select(
        [zero_line, pd.Series(accepted, index=target.index)],
        ["ZERO_LINE_IDENTITY", "CUTOFF_GATE_ACCEPTED"],
        default="CUTOFF_GATE_REJECTED",
    )
    gate_states = {
        "control": _model_state(gate_control, experimental=False),
        "experimental": _model_state(gate_experimental, experimental=True),
    }
    final_states = {
        "control": _model_state(control, experimental=False),
        "experimental": _model_state(experimental, experimental=True),
    }
    receipt: dict[str, Any] = dict(context.receipt.payload)
    receipt.update({
        "contract": CONTRACT_ID,
        "partition": {
            **receipt["partition"],
            "tune_rows_nonzero_line": len(tune),
            "calibration_rows_nonzero_line": len(calibration),
        },
        "selected_parameters": {
            "estimator": "sklearn.linear_model.LogisticRegression",
            "solver": "lbfgs", "max_iter": 1_000, "random_state": MODEL_RANDOM_STATE,
            "weighting_policy": receipt["weight_receipt"]["policy"],
        },
        "metrics": metrics, "gate_predicates": predicates, "mapping_accepted": accepted,
        "gate_model_states": gate_states, "final_model_states": final_states,
        "model_identity": stable_json_hash(final_states),
        "scientific_output_sha256": stable_json_hash({
            "accepted": accepted,
            "model_identity": stable_json_hash(final_states),
            "mapped_frame": stable_frame_hash(mapped),
        }),
    })
    return MappingResult(
        cutoff, accepted, experimental, control, mapped.reset_index(drop=True),
        context.weight_ledger.reset_index(drop=True), receipt,
    )


def fit_issue_walk_forward(
    history: pd.DataFrame,
    targets: pd.DataFrame,
    *,
    source_hashes: Mapping[str, str],
    weighting_policy: WeightingPolicy,
    helper_hashes: Mapping[str, str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.DataFrame]:
    """Fit one immutable artifact per target issue at its decision epoch."""

    mapped_parts: list[pd.DataFrame] = []
    receipts: list[dict[str, Any]] = []
    weight_parts: list[pd.DataFrame] = []

    def fit_one(cutoff: Cutoff, issue_target: pd.DataFrame) -> MappingResult:
        result = fit_cutoff_mapping(
            history,
            issue_target,
            cutoff,
            source_hashes=source_hashes,
            weighting_policy=weighting_policy,
            helper_hashes=helper_hashes,
        )
        return result

    runner: WalkForwardRunner[MappingResult] = WalkForwardRunner()
    for result in runner.run(targets, fit_one):
        issue = result.cutoff.identity.removeprefix("DECISION_EPOCH_")
        mapped_parts.append(
            result.mapped.assign(artifact_cutoff_identity=result.cutoff.identity)
        )
        receipts.append(result.receipt)
        weight_parts.append(result.weights.assign(target_issue=issue))
    return (
        pd.concat(mapped_parts, ignore_index=True),
        receipts,
        pd.concat(weight_parts, ignore_index=True),
    )


def _predict_state(frame: pd.DataFrame, state: Mapping[str, Any]) -> np.ndarray:
    categories = np.asarray(state["line_categories"], dtype=float)
    line = frame["native_handicap_line"].to_numpy(float)
    onehot = (line[:, None] == categories[None, :]).astype(float)
    unknown = ~np.isin(line, categories)
    if unknown.any():
        onehot[unknown] = 0.0
    matrix = onehot
    numeric = list(state["numeric_features"])
    if numeric:
        values = frame[numeric].to_numpy(float)
        scaled = (values - np.asarray(state["numeric_mean"], float)) / np.asarray(state["numeric_scale"], float)
        matrix = np.column_stack([matrix, scaled])
    logits = matrix @ np.asarray(state["coef"], float).T + np.asarray(state["intercept"], float)
    logits -= logits.max(axis=1, keepdims=True)
    probability = np.exp(logits)
    probability /= probability.sum(axis=1, keepdims=True)
    classes = [str(value) for value in state["classes"]]
    return probability[:, [classes.index(code) for code in OUTCOMES]]


def replay_mapped(target: pd.DataFrame, receipt: Mapping[str, Any]) -> pd.DataFrame:
    """Rebuild mapped probabilities from receipt states without sklearn objects."""

    states = receipt["final_model_states"]
    control = _predict_state(target, states["control"])
    candidate = _predict_state(target, states["experimental"])
    zero_line = target["native_handicap_line"].eq(0).to_numpy()
    accepted = bool(receipt["mapping_accepted"])
    mapped = target[["issue_code", "issue_year", "match_idx", "fixture_decision_ts", "native_handicap_line"]].copy()
    for position, outcome in enumerate(OUTCOMES):
        mapped[f"q_line_{outcome}"] = control[:, position]
        mapped[f"q_candidate_{outcome}"] = np.where(zero_line, target[f"q_eu_{outcome}"], candidate[:, position])
        mapped[f"q_mapped_{outcome}"] = np.where(zero_line | accepted, mapped[f"q_candidate_{outcome}"], np.nan)
    mapped["mapping_accepted"] = zero_line | accepted
    mapped["mapping_status"] = np.select(
        [zero_line, pd.Series(accepted, index=target.index)],
        ["ZERO_LINE_IDENTITY", "CUTOFF_GATE_ACCEPTED"], default="CUTOFF_GATE_REJECTED",
    )
    return mapped.reset_index(drop=True)


def replay_gate(development: pd.DataFrame, receipt: Mapping[str, Any]) -> dict[str, bool]:
    """Independently reconstruct gate predicates from model states and receipt partitions."""

    development = development.copy()
    development["label_available_ts"] = pd.to_datetime(development["label_available_ts"], utc=True)
    cutoff = utc(receipt["cutoff_ts"])
    predicates: dict[str, bool] = {}
    for role in ["tune", "calibration"]:
        years = receipt["partition"][f"{role}_years"]
        frame = development[
            development["issue_year"].isin(years)
            & development["label_available_ts"].lt(cutoff)
            & development["native_line_supported"].eq(True)
            & development["native_handicap_line"].ne(0)
            & development["target_outcome"].astype(str).isin(OUTCOMES)
        ]
        control_loss = _losses(frame, _predict_state(frame, receipt["gate_model_states"]["control"]))
        experimental_loss = _losses(frame, _predict_state(frame, receipt["gate_model_states"]["experimental"]))
        log_delta, brier_delta = experimental_loss[0] - control_loss[0], experimental_loss[1] - control_loss[1]
        predicates[f"{role}_log_loss_nonworse"] = bool(log_delta < 0 if role == "tune" else log_delta <= 0)
        predicates[f"{role}_brier_nonworse"] = bool(brier_delta < 0 if role == "tune" else brier_delta <= 0)
    return predicates
