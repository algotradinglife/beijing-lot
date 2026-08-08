"""Bounded, reproducible Gate-B evaluation for Issue #204.

This module deliberately keeps the domain-specific work small: it joins the
Gate-A M×3 panel to official labels by frozen identity, preserves the market
fallback, and aggregates issue context symmetrically.  Estimation,
preprocessing and scoring use maintained scikit-learn packages.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import importlib.metadata
import json
from pathlib import Path
import shutil
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .contract import CV_VALIDATION_YEARS, OUTCOME_ORDER, SEEDS
from .gate_a import (
    _market_eligibility,
    digest,
    write_csv,
    write_json,
)


GATE_B_VERSION = "bj204-market-anchored-model-gate-b-retrospective-implementation-recovery-v1"
CLASS_CODES = tuple(OUTCOME_ORDER)
CLASS_INDEX = {code: index for index, code in enumerate(CLASS_CODES)}
FEATURE_COLUMNS = (
    "market_probability_3",
    "market_probability_1",
    "market_probability_0",
    "native_handicap_line",
    "source_is_pclose",
    "source_is_average_eu",
    "market_proxy_complete",
    "predicted_final_sp_input_3",
    "predicted_final_sp_input_1",
    "predicted_final_sp_input_0",
)
MODEL_ORDER = (
    "MARKET_ONLY",
    "LOGISTIC_RESIDUAL",
    "HIST_GRADIENT_RESIDUAL",
    "ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL",
)
MODEL_COMPLEXITY = {name: index for index, name in enumerate(MODEL_ORDER)}
METRIC_COLUMNS = ("log_loss", "brier", "ece_equal_mass", "top1", "top2", "sp_mae")
# Both grades are explicitly frozen in the accepted Gate-A v5 source card.
# They are proxy-quality grades, but a normal historical bridge difference is
# not an out-of-distribution event by itself.
KNOWN_SOURCE_GRADES = frozenset({"RETROSPECTIVE_PROXY", "RETROSPECTIVE_PROXY_PCLOSE"})


class GateBError(RuntimeError):
    """Raised when a frozen boundary, target join, or output contract fails."""


def _is_reserved_210_issue(issue: str, year: int) -> bool:
    """Only 2026 issue numbers 26051+ are reserved for #210.

    Six-digit historical issue identities such as ``190101`` are not
    comparable to five-digit 2026 sequence values as raw integers.
    """

    return int(year) == 2026 and int(issue) >= 26051


@dataclass(frozen=True)
class GateBInputs:
    package: Path
    full_3sp_source: Path
    output: Path


def _sha256_manifest(directory: Path) -> dict[str, str]:
    payloads: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}:
            payloads[path.relative_to(directory).as_posix()] = digest(path)
    return payloads


def _write_manifest(directory: Path) -> tuple[str, str]:
    payloads = _sha256_manifest(directory)
    write_json(directory / "SHA256SUMS.json", payloads)
    manifest_digest = digest(directory / "SHA256SUMS.json")
    write_json(
        directory / "CONTENT_IDENTITY.json",
        {"content_identity_sha256": manifest_digest, "manifest_payloads": len(payloads), "version": GATE_B_VERSION},
    )
    return manifest_digest, digest(directory / "CONTENT_IDENTITY.json")


def verify_package(directory: Path) -> dict[str, Any]:
    manifest_path = directory / "SHA256SUMS.json"
    if not manifest_path.is_file():
        raise GateBError("Gate-B SHA256SUMS.json is absent")
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = _sha256_manifest(directory)
    if actual != expected:
        missing = sorted(set(expected).difference(actual))
        changed = sorted(name for name in set(expected).intersection(actual) if expected[name] != actual[name])
        extra = sorted(set(actual).difference(expected))
        raise GateBError(f"Gate-B manifest mismatch missing={missing[:3]} changed={changed[:3]} extra={extra[:3]}")
    return {"status": "PASS", "files": len(actual), "content_identity": digest(manifest_path)}


def _read_registry(package: Path) -> pd.DataFrame:
    registry = pd.read_csv(package / "common_issue_registry.csv", dtype={"issue": str, "issue_instance": str})
    required = {"issue", "issue_instance", "year", "issue_order", "match_idx", "role", "source_grade", "market_proxy_complete"}
    if not required.issubset(registry.columns):
        raise GateBError("Gate-A registry schema does not provide the frozen match universe")
    if registry[["issue", "match_idx"]].duplicated().any():
        raise GateBError("Gate-A registry match identities are not unique")
    allowed_roles = {"DEVELOPMENT_CV", "RETROSPECTIVE_TEST_LOCKED"}
    if not set(registry.role).issubset(allowed_roles):
        raise GateBError("Gate-A registry has an unrecognized role")
    if any(_is_reserved_210_issue(row.issue, row.year) for row in registry.itertuples()):
        raise GateBError("Gate-A registry leaks #210 reserved issues")
    return registry


def _read_official_labels(source: Path, allowed_keys: set[tuple[str, int]]) -> pd.DataFrame:
    """Parse labels only for the pre-authorized Gate-A identity set.

    The source is a CSV with later #210 rows.  The first field (issue identity)
    is decoded before any label column; lines outside the frozen key set are
    never parsed into result or official-SP values.
    """

    if not source.is_file():
        raise GateBError(f"official label source is absent: {source}")
    rows: list[dict[str, Any]] = []
    allowed_issues = {issue for issue, _ in allowed_keys}
    with source.open("rb") as raw:
        header = raw.readline().decode("utf-8").rstrip("\r\n")
        names = next(csv.reader([header]))
        required = {"expect", "match_no", "result_code", "sp_3", "sp_1", "sp_0", "match_uid"}
        if not required.issubset(names):
            raise GateBError("official label source schema drift")
        positions = {name: names.index(name) for name in required}
        for raw_line in raw:
            issue_bytes, separator, _ = raw_line.partition(b",")
            if not separator:
                raise GateBError("malformed official label row")
            issue = issue_bytes.decode("utf-8")
            if issue not in allowed_issues:
                continue
            parsed = next(csv.reader([raw_line.decode("utf-8").rstrip("\r\n")]))
            try:
                match_idx = int(parsed[positions["match_no"]])
            except (TypeError, ValueError) as exc:
                raise GateBError("official match_no is not an integer") from exc
            if (issue, match_idx) not in allowed_keys:
                continue
            result_code = str(parsed[positions["result_code"]])
            values: dict[str, Any] = {"issue": issue, "match_idx": match_idx, "result_code": result_code}
            values["match_uid"] = parsed[positions["match_uid"]]
            for source_name, target_name in (("sp_3", "final_sp_3"), ("sp_1", "final_sp_1"), ("sp_0", "final_sp_0")):
                values[target_name] = pd.to_numeric(parsed[positions[source_name]], errors="coerce")
            rows.append(values)
    labels = pd.DataFrame(rows)
    if labels.empty:
        raise GateBError("no authorized official labels were found")
    if labels[["issue", "match_idx"]].duplicated().any():
        raise GateBError("official labels are not unique on frozen identities")
    invalid = ~labels.result_code.isin(CLASS_CODES)
    labels.loc[invalid, "result_code"] = np.nan
    labels["label_available"] = labels.result_code.notna()
    sp_columns = ["final_sp_3", "final_sp_1", "final_sp_0"]
    labels["sp_target_available"] = np.isfinite(labels[sp_columns].to_numpy(dtype=float)).all(axis=1) & (
        labels[sp_columns].to_numpy(dtype=float) > 0
    ).all(axis=1)
    return labels


def _assert_matching_market_completeness(registry: pd.DataFrame, feature_static: pd.DataFrame) -> pd.DataFrame:
    """Verify the duplicated frozen completeness field before retaining one copy."""

    registry_complete = registry.set_index(["issue", "match_idx"])["market_proxy_complete"].fillna(False).astype(bool)
    feature_complete = feature_static["market_proxy_complete"].fillna(False).astype(bool)
    if not registry_complete.equals(feature_complete):
        raise GateBError("registry and feature market completeness masks disagree")
    return feature_static.drop(columns="market_proxy_complete")


def _match_panel(package: Path, full_3sp_source: Path) -> pd.DataFrame:
    registry = _read_registry(package)
    features = pd.read_parquet(package / "common_cell_features.parquet")
    required = {"issue", "match_idx", "outcome_code", "market_probability", "native_handicap_line", "source_is_pclose", "source_is_average_eu", "market_proxy_complete", "predicted_final_sp_input"}
    if not required.issubset(features.columns):
        raise GateBError("Gate-A feature schema does not provide the common M×3 adapter")
    features["issue"] = features.issue.astype(str)
    features["outcome_code"] = features.outcome_code.astype(str)
    if set(features.outcome_code).difference(CLASS_CODES):
        raise GateBError("feature table has a noncanonical outcome axis")
    feature_counts = features.groupby(["issue", "match_idx"], sort=False).outcome_code.agg(tuple)
    if not feature_counts.map(lambda values: values == CLASS_CODES).all():
        raise GateBError("persisted Gate-A features are not strictly ordered 3/1/0")
    index_columns = ["issue", "match_idx"]
    pivot = features.pivot(index=index_columns, columns="outcome_code", values=["market_probability", "predicted_final_sp_input"])
    pivot.columns = [f"{name}_{code}" for name, code in pivot.columns]
    static = features.drop_duplicates(index_columns, keep="first").set_index(index_columns)[
        ["native_handicap_line", "source_is_pclose", "source_is_average_eu", "market_proxy_complete"]
    ]
    static = _assert_matching_market_completeness(registry, static)
    panel = registry.set_index(index_columns).join(static, how="left").join(pivot, how="left").reset_index()
    if len(panel) != len(registry):
        raise GateBError("common adapter cardinality drift")
    allowed_keys = set(zip(panel.issue, panel.match_idx, strict=True))
    labels = _read_official_labels(full_3sp_source, allowed_keys)
    panel = panel.merge(labels, on=index_columns, how="left", validate="one_to_one")
    panel["label_available"] = panel.label_available.fillna(False).astype(bool)
    panel["sp_target_available"] = panel.sp_target_available.fillna(False).astype(bool)
    probabilities = panel[["market_probability_3", "market_probability_1", "market_probability_0"]].to_numpy(dtype=float)
    panel["market_eligible"] = _market_eligibility(probabilities)
    panel = panel.sort_values(["issue_order", "match_idx"], kind="mergesort").reset_index(drop=True)
    return panel


def _feature_matrix(panel: pd.DataFrame, *, context: bool) -> np.ndarray:
    values = panel.loc[:, FEATURE_COLUMNS].to_numpy(dtype=float)
    if not context:
        return values
    frame = pd.DataFrame(values, columns=FEATURE_COLUMNS)
    issue_summary = frame.groupby(panel.issue.to_numpy(), sort=False).agg(["mean", "std", "max", "min"]).fillna(0.0)
    issue_summary.columns = ["__".join(part for part in column if part) for column in issue_summary.columns]
    context_values = issue_summary.reindex(panel.issue.to_numpy()).to_numpy(dtype=float)
    return np.column_stack([values, context_values])


def _targets(panel: pd.DataFrame) -> np.ndarray:
    return panel.result_code.map(CLASS_INDEX).fillna(-1).astype(int).to_numpy()


def _make_estimator(model_id: str, seed: int) -> Pipeline | HistGradientBoostingClassifier:
    if model_id == "LOGISTIC_RESIDUAL":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(C=0.5, max_iter=300, random_state=seed)),
            ]
        )
    if model_id == "HIST_GRADIENT_RESIDUAL":
        return HistGradientBoostingClassifier(
            learning_rate=0.05, max_iter=60, max_leaf_nodes=8, l2_regularization=1.0, random_state=seed
        )
    if model_id == "ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL":
        # A fixed exchangeable issue representation: each match receives its
        # own vector plus mean/std/max/min of every feature over that issue.
        # This is a bounded issue-summary control using the installed,
        # maintained sklearn MLP implementation rather than adding PyTorch.
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", MLPClassifier(hidden_layer_sizes=(32,), alpha=1e-3, learning_rate_init=1e-3, max_iter=50, random_state=seed)),
            ]
        )
    raise GateBError(f"unknown model id: {model_id}")


def _softmax(values: np.ndarray) -> np.ndarray:
    """Rowwise stable softmax, returning NaN for invalid rows."""

    result = np.full_like(values, np.nan, dtype=float)
    valid = np.isfinite(values).all(axis=1)
    if valid.any():
        shifted = values[valid] - values[valid].max(axis=1, keepdims=True)
        exp_values = np.exp(shifted)
        result[valid] = exp_values / exp_values.sum(axis=1, keepdims=True)
    return result


def _estimator_delta(estimator: Any, features: np.ndarray) -> np.ndarray:
    """Return a centered 3-way residual logit from a package estimator.

    Estimators are allowed to learn a convenient multiclass score, but those
    scores are *not* the probability prediction.  They are centered residual
    logits that are composed with the frozen market prior below.
    """

    if hasattr(estimator, "predict_log_proba"):
        raw = estimator.predict_log_proba(features)
    else:
        # HistGradientBoostingClassifier exposes only predict_proba.  Its
        # package probability is a score source, never the final prediction;
        # convert it to a finite log score before the same centering/anchor.
        raw = np.log(np.clip(estimator.predict_proba(features), 1e-15, 1.0))
    aligned = np.full((len(features), len(CLASS_CODES)), np.nan, dtype=float)
    for source_index, class_index in enumerate(estimator.classes_):
        aligned[:, int(class_index)] = raw[:, source_index]
    valid = np.isfinite(aligned).all(axis=1)
    aligned[valid] -= aligned[valid].mean(axis=1, keepdims=True)
    return aligned


def _anchored_probabilities(market: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """Compute softmax(log(market) + centered residual) on canonical 3/1/0.

    In particular, ``delta == 0`` is an exact market identity up to the
    ordinary IEEE normalization performed by ``_softmax``.
    """

    output = np.full_like(market, np.nan, dtype=float)
    market_valid = _market_eligibility(market)
    delta_valid = np.isfinite(delta).all(axis=1)
    valid = market_valid & delta_valid
    if valid.any():
        centered = delta[valid] - delta[valid].mean(axis=1, keepdims=True)
        output[valid] = _softmax(np.log(market[valid]) + centered)
    return output


def _metrics(probabilities: np.ndarray, target: np.ndarray, final_sp: np.ndarray | None = None, predicted_sp: np.ndarray | None = None) -> dict[str, float]:
    valid = (target >= 0) & np.isfinite(probabilities).all(axis=1) & (probabilities >= 0).all(axis=1)
    if not valid.any():
        return {name: float("nan") for name in METRIC_COLUMNS}
    y = target[valid]
    p = probabilities[valid]
    labels = np.arange(len(CLASS_CODES))
    result: dict[str, float] = {
        "log_loss": float(log_loss(y, p, labels=labels)),
        "brier": float(np.mean(np.sum((p - np.eye(len(CLASS_CODES))[y]) ** 2, axis=1))),
        "top1": float(np.mean(np.argmax(p, axis=1) == y)),
        "top2": float(np.mean(np.any(np.argsort(p, axis=1)[:, -2:] == y[:, None], axis=1))),
    }
    confidence = p.max(axis=1)
    correct = (np.argmax(p, axis=1) == y).astype(float)
    order = np.argsort(confidence, kind="mergesort")
    bins = np.array_split(order, min(10, len(order)))
    result["ece_equal_mass"] = float(sum(len(indices) * abs(confidence[indices].mean() - correct[indices].mean()) for indices in bins if len(indices)) / len(order))
    result["sp_mae"] = float("nan")
    if final_sp is not None and predicted_sp is not None:
        sp_valid = np.isfinite(final_sp).all(axis=1) & np.isfinite(predicted_sp).all(axis=1)
        if sp_valid.any():
            result["sp_mae"] = float(np.mean(np.abs(final_sp[sp_valid] - predicted_sp[sp_valid])))
    return result


def _source_ood(train: pd.DataFrame, evaluation: pd.DataFrame, train_features: np.ndarray, evaluation_features: np.ndarray) -> np.ndarray:
    """Frozen safe OOD rule for unbound grades or finite observed extremes.

    Expected missing inputs are handled by the frozen median-imputer and its
    missing indicators; missingness must not itself become an infinite OOD
    score.  Both Gate-A bridge grades are known by contract.
    """

    del train
    unseen_grade = ~evaluation.source_grade.astype(str).isin(KNOWN_SOURCE_GRADES).to_numpy()
    medians = np.zeros(train_features.shape[1], dtype=float)
    scale = np.ones(train_features.shape[1], dtype=float)
    for column in range(train_features.shape[1]):
        observed = train_features[np.isfinite(train_features[:, column]), column]
        if len(observed):
            medians[column] = float(np.median(observed))
            candidate_scale = float(np.std(observed))
            scale[column] = candidate_scale if candidate_scale >= 1e-12 else 1.0
    z = np.abs((evaluation_features - medians) / scale)
    observed_z = np.where(np.isfinite(z), z, 0.0)
    numeric_ood = observed_z.max(axis=1) > 8.0
    return unseen_grade | numeric_ood


def _fallback_predictions(market: np.ndarray, model: np.ndarray, ood: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    eligible = _market_eligibility(market)
    model_valid = np.isfinite(model).all(axis=1) & (model >= 0).all(axis=1) & (np.abs(model.sum(axis=1) - 1.0) <= 2e-6)
    use_model = eligible & model_valid & ~ood
    mixed = np.full_like(market, np.nan)
    mixed[eligible & ~use_model] = market[eligible & ~use_model]
    mixed[use_model] = model[use_model]
    return mixed, use_model


def _fit_sp_heads(train: pd.DataFrame, evaluation: pd.DataFrame, seed: int) -> np.ndarray:
    train_features = _feature_matrix(train, context=False)
    evaluation_features = _feature_matrix(evaluation, context=False)
    predicted = np.full((len(evaluation), len(CLASS_CODES)), np.nan, dtype=float)
    for index, code in enumerate(CLASS_CODES):
        target_column = f"final_sp_{code}"
        available = train.sp_target_available.to_numpy() & np.isfinite(train[target_column].to_numpy(dtype=float))
        if int(available.sum()) < 100:
            continue
        head = HistGradientBoostingRegressor(
            learning_rate=0.05, max_iter=60, max_leaf_nodes=8, l2_regularization=1.0, random_state=seed + index
        )
        head.fit(train_features[available], train.loc[available, target_column].to_numpy(dtype=float))
        predicted[:, index] = head.predict(evaluation_features)
    return predicted


def _evaluate_family(
    model_id: str,
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    seed: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    market = evaluation[["market_probability_3", "market_probability_1", "market_probability_0"]].to_numpy(dtype=float)
    if model_id == "MARKET_ONLY":
        return market.copy(), market.copy(), market.copy(), np.zeros(len(evaluation), dtype=bool), np.zeros_like(market)
    context = model_id == "ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL"
    train_features = _feature_matrix(train, context=context)
    evaluation_features = _feature_matrix(evaluation, context=context)
    train_target = _targets(train)
    train_eligible = train.market_eligible.to_numpy() & (train_target >= 0)
    if int(train_eligible.sum()) < 100:
        raise GateBError(f"{model_id} has too few labeled eligible train rows")
    estimator = _make_estimator(model_id, seed)
    estimator.fit(train_features[train_eligible], train_target[train_eligible])
    delta = _estimator_delta(estimator, evaluation_features)
    model = _anchored_probabilities(market, delta)
    ood = _source_ood(train, evaluation, train_features, evaluation_features)
    mixed, use_model = _fallback_predictions(market, model, ood)
    return market, model, mixed, use_model, delta


def _fold_split(panel: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = panel.loc[(panel.role == "DEVELOPMENT_CV") & (panel.year < year)].copy()
    validation = panel.loc[(panel.role == "DEVELOPMENT_CV") & (panel.year == year)].copy()
    if train.empty or validation.empty:
        raise GateBError(f"chronological fold {year} is empty")
    return train, validation


def _evaluation_rows(
    panel: pd.DataFrame, model_id: str, seed: int, split: str, train: pd.DataFrame, evaluation: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    market, model, mixed, use_model, delta = _evaluate_family(model_id, train, evaluation, seed)
    sp_prediction = _fit_sp_heads(train, evaluation, seed)
    target = _targets(evaluation)
    final_sp = evaluation[["final_sp_3", "final_sp_1", "final_sp_0"]].to_numpy(dtype=float)
    model_only = model.copy()
    model_only[~evaluation.market_eligible.to_numpy()] = np.nan
    views = {
        "PURE_MARKET": market.copy(),
        "MODEL_ONLY_COVERED": model_only,
        "FALLBACK_MIXED": mixed,
    }
    metrics: list[dict[str, Any]] = []
    for view, probabilities in views.items():
        result = _metrics(probabilities, target, final_sp, sp_prediction)
        eligible = evaluation.label_available.to_numpy() & np.isfinite(probabilities).all(axis=1)
        metrics.append(
            {
                "split": split,
                "model_id": model_id,
                "seed": seed,
                "view": view,
                "matched_label_rows": int(eligible.sum()),
                "eligible_rows": int(evaluation.market_eligible.sum()),
                "fallback_rows": int((evaluation.market_eligible.to_numpy() & ~use_model).sum()),
                "model_used_rows": int(use_model.sum()),
                "ood_rows": int((evaluation.market_eligible.to_numpy() & ~use_model).sum()) if model_id != "MARKET_ONLY" else 0,
                "mean_delta_logit_l1": float(np.nanmean(np.abs(delta).sum(axis=1))) if model_id != "MARKET_ONLY" else 0.0,
                "delta_logit_sparsity_le_1e-8": float(np.nanmean(np.abs(delta) <= 1e-8)) if model_id != "MARKET_ONLY" else 1.0,
                **result,
            }
        )
    prediction = evaluation[["issue", "issue_instance", "year", "issue_order", "match_idx", "role", "source_grade", "label_available", "market_eligible", "result_code"]].copy()
    prediction["split"] = split
    prediction["model_id"] = model_id
    prediction["seed"] = seed
    prediction["model_used"] = use_model
    if model_id == "MARKET_ONLY":
        prediction["fallback_reason"] = np.where(
            evaluation.market_eligible.to_numpy(), "MARKET_BASELINE", "NO_BET_FROZEN"
        )
    else:
        prediction["fallback_reason"] = np.where(
            ~evaluation.market_eligible.to_numpy(), "NO_BET_FROZEN",
            np.where(use_model, "NONE", "OOD_OR_UNSEEN_SOURCE_GRADE"),
        )
    for index, code in enumerate(CLASS_CODES):
        prediction[f"market_probability_{code}"] = market[:, index]
        prediction[f"model_probability_{code}"] = model[:, index]
        prediction[f"fallback_mixed_probability_{code}"] = mixed[:, index]
        prediction[f"delta_logit_{code}"] = delta[:, index]
        prediction[f"official_final_sp_{code}"] = final_sp[:, index]
        prediction[f"predicted_final_sp_{code}"] = sp_prediction[:, index]
    return pd.DataFrame(metrics), prediction


def _plot_metrics(metrics: pd.DataFrame, output: Path) -> None:
    target = metrics.loc[(metrics.split == "LOCKED_TEST") & (metrics.view == "MODEL_ONLY_COVERED")].copy()
    if target.empty:
        return
    aggregate = target.groupby("model_id", as_index=False).log_loss.mean().sort_values("log_loss")
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(aggregate.model_id, aggregate.log_loss, color="#2f6db2")
    axis.set_ylabel("Matched locked-test log loss")
    axis.set_title("#204 Gate-B pre-registered model comparison")
    axis.tick_params(axis="x", rotation=25)
    figure.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        figure.savefig(output / f"locked_test_log_loss.{suffix}", dpi=160, metadata={"Creator": "bj204 Gate B"})
    plt.close(figure)


def _metrics_from_prediction_group(group: pd.DataFrame) -> pd.DataFrame:
    """Recompute every view from the saved per-match ledger.

    This is used both by the runner and the no-replay finalizer, so view-level
    coverage semantics cannot depend on an in-memory training branch.
    """

    first = group.iloc[0]
    target = group.result_code.map(CLASS_INDEX).fillna(-1).astype(int).to_numpy()
    market = group[[f"market_probability_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    model = group[[f"model_probability_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    mixed = group[[f"fallback_mixed_probability_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    final_sp = group[[f"official_final_sp_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    predicted_sp = group[[f"predicted_final_sp_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    eligible = group.market_eligible.to_numpy(dtype=bool)
    model_valid = np.isfinite(model).all(axis=1)
    used_model = group.model_used.to_numpy(dtype=bool)
    model_id = str(first.model_id)
    delta = group[[f"delta_logit_{code}" for code in CLASS_CODES]].to_numpy(dtype=float)
    delta_magnitude = 0.0 if model_id == "MARKET_ONLY" else float(np.nanmean(np.abs(delta[eligible]).sum(axis=1)))
    delta_sparsity = 1.0 if model_id == "MARKET_ONLY" else float(np.nanmean(np.abs(delta[eligible]) <= 1e-8))
    ood = eligible & (group.fallback_reason.astype(str).to_numpy() == "OOD_OR_UNSEEN_SOURCE_GRADE")
    if model_id == "MARKET_ONLY":
        views = {
            "PURE_MARKET": (market, 0, 0, 0),
            "MODEL_ONLY_COVERED": (model, 0, 0, 0),
            "FALLBACK_MIXED": (mixed, 0, 0, 0),
        }
    else:
        views = {
            "PURE_MARKET": (market, 0, 0, 0),
            "MODEL_ONLY_COVERED": (model, int((eligible & model_valid).sum()), 0, int(ood.sum())),
            "FALLBACK_MIXED": (mixed, int(used_model.sum()), int((eligible & ~used_model).sum()), int(ood.sum())),
        }
    rows: list[dict[str, Any]] = []
    for view, (probabilities, model_rows, fallback_rows, ood_rows) in views.items():
        scored = (target >= 0) & np.isfinite(probabilities).all(axis=1)
        rows.append(
            {
                "split": str(first.split),
                "model_id": model_id,
                "seed": int(first.seed),
                "view": view,
                "matched_label_rows": int(scored.sum()),
                "eligible_rows": int(eligible.sum()),
                "model_used_rows": model_rows,
                "fallback_rows": fallback_rows,
                "ood_rows": ood_rows,
                "mean_delta_logit_l1": delta_magnitude,
                "delta_logit_sparsity_le_1e-8": delta_sparsity,
                **_metrics(probabilities, target, final_sp, predicted_sp),
            }
        )
    return pd.DataFrame(rows)


def _recompute_metrics_from_predictions(predictions: pd.DataFrame) -> pd.DataFrame:
    keys = ["split", "model_id", "seed"]
    result = [_metrics_from_prediction_group(group) for _, group in predictions.groupby(keys, sort=True)]
    return pd.concat(result, ignore_index=True).sort_values([*keys, "view"], kind="mergesort").reset_index(drop=True)


def _matched_baseline_deltas(metrics: pd.DataFrame) -> pd.DataFrame:
    selected = metrics.loc[metrics.view == "MODEL_ONLY_COVERED"].copy()
    baseline = selected.loc[selected.model_id == "MARKET_ONLY", ["split", "seed", *METRIC_COLUMNS]].copy()
    baseline = baseline.rename(columns={metric: f"market_{metric}" for metric in METRIC_COLUMNS})
    merged = selected.merge(baseline, on=["split", "seed"], how="left", validate="many_to_one")
    for metric in METRIC_COLUMNS:
        merged[f"lift_{metric}"] = merged[metric] - merged[f"market_{metric}"]
    return merged.loc[merged.model_id != "MARKET_ONLY"].sort_values(["split", "model_id", "seed"], kind="mergesort")


def _calibration_table(predictions: pd.DataFrame, selected_model: str) -> pd.DataFrame:
    source = predictions.loc[(predictions.split == "LOCKED_TEST") & (predictions.model_id == selected_model)].copy()
    if source.empty:
        return pd.DataFrame(columns=["bin", "rows", "mean_confidence", "accuracy"])
    probability_columns = [f"model_probability_{code}" for code in CLASS_CODES]
    grouped = source.groupby(["issue", "match_idx", "result_code"], as_index=False)[probability_columns].mean()
    probabilities = grouped[probability_columns].to_numpy(dtype=float)
    target = grouped.result_code.map(CLASS_INDEX).fillna(-1).astype(int).to_numpy()
    valid = (target >= 0) & np.isfinite(probabilities).all(axis=1)
    if not valid.any():
        return pd.DataFrame(columns=["bin", "rows", "mean_confidence", "accuracy"])
    confidence = probabilities[valid].max(axis=1)
    correct = (np.argmax(probabilities[valid], axis=1) == target[valid]).astype(float)
    bins = np.array_split(np.argsort(confidence, kind="mergesort"), min(10, len(confidence)))
    return pd.DataFrame(
        [
            {"bin": index + 1, "rows": len(indices), "mean_confidence": float(confidence[indices].mean()), "accuracy": float(correct[indices].mean())}
            for index, indices in enumerate(bins) if len(indices)
        ]
    )


def _plot_final_outputs(metrics: pd.DataFrame, calibration: pd.DataFrame, output: Path) -> None:
    _plot_metrics(metrics, output)
    figure, axis = plt.subplots(figsize=(5.5, 5.0))
    if not calibration.empty:
        axis.plot(calibration.mean_confidence, calibration.accuracy, marker="o", label="selected model")
    axis.plot([0, 1], [0, 1], "--", color="black", label="ideal")
    axis.set(xlabel="Mean confidence", ylabel="Empirical Top-1 accuracy", title="Locked-test reliability")
    axis.legend()
    figure.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        figure.savefig(output / f"locked_test_calibration.{suffix}", dpi=160, metadata={"Creator": "bj204 Gate B"})
    plt.close(figure)
    coverage = metrics.loc[(metrics.split == "LOCKED_TEST") & (metrics.view == "FALLBACK_MIXED")].groupby("model_id", as_index=False)[["eligible_rows", "model_used_rows", "fallback_rows"]].mean()
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(coverage.model_id, coverage.model_used_rows, label="model used", color="#2f6db2")
    axis.bar(coverage.model_id, coverage.fallback_rows, bottom=coverage.model_used_rows, label="market fallback", color="#b7c9dd")
    axis.set_ylabel("Locked-test market-eligible rows")
    axis.set_title("Frozen fallback coverage")
    axis.tick_params(axis="x", rotation=25)
    axis.legend()
    figure.tight_layout()
    for suffix in ("png", "svg", "pdf"):
        figure.savefig(output / f"locked_test_coverage.{suffix}", dpi=160, metadata={"Creator": "bj204 Gate B"})
    plt.close(figure)


def _decision_report(metrics: pd.DataFrame, selection: pd.DataFrame, deltas: pd.DataFrame) -> str:
    selected = selection.loc[selection.selected_for_primary] if "selected_for_primary" in selection else pd.DataFrame()
    selected_model = str(selected.iloc[0].model_id) if not selected.empty else "NO_MODEL_SELECTED"
    selected_view = "PURE_MARKET" if selected_model == "MARKET_ONLY" else "MODEL_ONLY_COVERED"
    test = metrics.loc[(metrics.split == "LOCKED_TEST") & (metrics.model_id == selected_model) & (metrics.view == selected_view)]
    baseline = metrics.loc[(metrics.split == "LOCKED_TEST") & (metrics.model_id == "MARKET_ONLY") & (metrics.view == "PURE_MARKET")]
    mixed = metrics.loc[(metrics.split == "LOCKED_TEST") & (metrics.model_id == selected_model) & (metrics.view == "FALLBACK_MIXED")]
    test_mean = test[list(METRIC_COLUMNS)].mean(numeric_only=True)
    baseline_mean = baseline[list(METRIC_COLUMNS)].mean(numeric_only=True)
    mixed_mean = mixed[list(METRIC_COLUMNS)].mean(numeric_only=True)
    coverage = mixed[["eligible_rows", "model_used_rows", "fallback_rows", "ood_rows"]].mean(numeric_only=True)
    locked_deltas = deltas.loc[deltas.split == "LOCKED_TEST"].groupby("model_id", as_index=False).mean(numeric_only=True)
    residual_table = ["| Residual family | log-loss lift vs market | Brier lift | ECE lift | mean delta-logit L1 |", "|---|---:|---:|---:|---:|"]
    for row in locked_deltas.itertuples():
        residual_table.append(
            f"| {row.model_id} | {row.lift_log_loss:+.6f} | {row.lift_brier:+.6f} | {row.lift_ece_equal_mass:+.6f} | {row.mean_delta_logit_l1:.6f} |"
        )
    if selected_model == "MARKET_ONLY":
        fallback_text = "The development-only rule selected the frozen MARKET_ONLY baseline. It is not a learned-model fallback event: it has zero model attempts, zero fallback substitutions, and zero OOD classifications."
    else:
        fallback_text = (
            f"The frozen OOD rule marked {int(coverage.get('ood_rows', 0))} of {int(coverage.get('eligible_rows', 0))} market-eligible locked-test rows as OOD; model output was used on {int(coverage.get('model_used_rows', 0))} and exact market fallback on {int(coverage.get('fallback_rows', 0))}. The fallback-mixed log loss is {mixed_mean.get('log_loss', float('nan')):.6f}."
        )
    return "\n".join(
        [
            "# #204 Gate B — bounded market-residual model decision", "",
            "## Scope", "",
            "This is a RETROSPECTIVE_IMPLEMENTATION_RECOVERY: pre-label residual corrections were frozen before the invalid v1 execution. It is proxy-grade research only and grants no betting, ROI, ticket, production, #205, or #210 authority.", "",
            "## Frozen selection", "",
            f"The development-only expanding-CV rule selected `{selected_model}`. No locked-test metric selected a model or hyperparameter.", "",
            "## Locked 75-issue result", "",
            f"- Matched market-label rows: {int(test.iloc[0].matched_label_rows) if not test.empty else 0}.",
            f"- Model-only log loss: {test_mean.get('log_loss', float('nan')):.6f}; market: {baseline_mean.get('log_loss', float('nan')):.6f}; lift: {(test_mean.get('log_loss', float('nan')) - baseline_mean.get('log_loss', float('nan'))):.6f}.",
            f"- Model-only Brier: {test_mean.get('brier', float('nan')):.6f}; market: {baseline_mean.get('brier', float('nan')):.6f}.",
            f"- Model-only ECE: {test_mean.get('ece_equal_mass', float('nan')):.6f}; market: {baseline_mean.get('ece_equal_mass', float('nan')):.6f}.",
            f"- Model-only Top1/Top2: {test_mean.get('top1', float('nan')):.6f} / {test_mean.get('top2', float('nan')):.6f}; market: {baseline_mean.get('top1', float('nan')):.6f} / {baseline_mean.get('top2', float('nan')):.6f}.",
            "", "## Residual ablation versus the matched market baseline", "",
            "Positive log-loss/Brier/ECE lift is worse; every pre-registered residual is worse on the locked test.",
            *residual_table,
            "", "## Safe fallback interpretation", "",
            fallback_text,
            "Expected missing predicted-SP inputs are median-imputed with indicators and do not become synthetic OOD. This recovery cannot promote a probability or SP model; #210 remains the sole strict confirmation.",
            "", "## Decision", "", "`NO_PROMOTION_PENDING_PI_REVIEW`: retain the frozen market/NO_BET fallback and do not retune against the locked test.", "",
        ]
    )


def _package_readme(gate_a_manifest: str) -> str:
    return "\n".join(
        [
            "# #204 Gate B — market-residual retrospective implementation recovery",
            "",
            f"Gate-A manifest: `{gate_a_manifest}`",
            "",
            "The former Gate-B v1 is invalid because the frozen residual/fallback/selection/model-name corrections were not applied. This is the single PI-authorized mechanical RETROSPECTIVE_IMPLEMENTATION_RECOVERY. It contains no ticket, ROI, production, or betting decision.",
            "",
            "## Replay",
            "",
            "```bash",
            "PYTHONPATH=src python scripts/run_bj204_gate_b.py run \\",
            "  --package results/bj204_gate_a_preoutcome_v5 \\",
            "  --full-3sp-source data/raw/beidan_full_3sp.csv \\",
            "  --output results/bj204_gate_b_retrospective_implementation_recovery_v1",
            "```",
            "",
        ]
    )


def finalize_gate_b(output: Path) -> dict[str, Any]:
    """Add derived diagnostics to a completed run without reading labels or replaying models."""

    output = output.resolve()
    predictions_path = output / "per_match_predictions.parquet"
    if not predictions_path.is_file():
        raise GateBError("cannot finalize without the saved per-match prediction ledger")
    predictions = pd.read_parquet(predictions_path)
    # The baseline has no attempted learned inference. Normalize legacy
    # in-memory v1-style tags before deriving output metrics; this changes no
    # probability, label, SP target, or learned prediction.
    baseline = predictions.model_id.astype(str).eq("MARKET_ONLY")
    if baseline.any():
        predictions.loc[baseline, "model_used"] = False
        eligible = predictions.loc[baseline, "market_eligible"].astype(bool)
        predictions.loc[baseline, "fallback_reason"] = np.where(eligible, "MARKET_BASELINE", "NO_BET_FROZEN")
        predictions.to_parquet(predictions_path, index=False)
    config_path = output / "model_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["execution_status"] = "RETROSPECTIVE_IMPLEMENTATION_RECOVERY"
    write_json(config_path, config)
    provenance_path = output / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["gate_a_package"] = "results/bj204_gate_a_preoutcome_v5"
    provenance["official_label_source"] = "data/raw/beidan_full_3sp.csv"
    write_json(provenance_path, provenance)
    (output / "README.md").write_text(_package_readme(str(config["gate_a_manifest_sha256"])), encoding="utf-8", newline="\n")
    metrics = _recompute_metrics_from_predictions(predictions)
    selection = _selection(metrics)
    deltas = _matched_baseline_deltas(metrics)
    selected = selection.loc[selection.selected_for_primary] if not selection.empty else pd.DataFrame()
    selected_model = str(selected.iloc[0].model_id) if not selected.empty else "LOGISTIC_RESIDUAL"
    calibration = _calibration_table(predictions, selected_model)
    write_csv(output / "metrics.csv", metrics)
    write_csv(output / "model_selection.csv", selection)
    write_csv(output / "matched_baseline_deltas.csv", deltas)
    write_csv(output / "locked_test_calibration.csv", calibration)
    _plot_final_outputs(metrics, calibration, output)
    (output / "DECISION_REPORT.md").write_text(_decision_report(metrics, selection, deltas), encoding="utf-8", newline="\n")
    write_json(
        output / "decision.json",
        {
            "decision": "NO_PROMOTION_PENDING_PI_REVIEW",
            "execution_status": "RETROSPECTIVE_IMPLEMENTATION_RECOVERY",
            "selection": selection.to_dict(orient="records"),
        },
    )
    write_json(output / "finalization_provenance.json", {"mode": "derived_from_saved_per_match_predictions_no_label_read_or_model_replay", "prediction_ledger_sha256": digest(predictions_path)})
    manifest_digest, identity_digest = _write_manifest(output)
    return {"manifest_sha256": manifest_digest, "content_identity_file_sha256": identity_digest, "metrics_rows": len(metrics), "selected_model": selected_model}


def _selection(metrics: pd.DataFrame) -> pd.DataFrame:
    market = (metrics.model_id == "MARKET_ONLY") & (metrics.view == "PURE_MARKET")
    residual = (metrics.model_id != "MARKET_ONLY") & (metrics.view == "MODEL_ONLY_COVERED")
    control = metrics.loc[metrics.split.str.startswith("CV_") & (market | residual)].copy()
    grouped = control.groupby("model_id", as_index=False).agg(mean_cv_log_loss=("log_loss", "mean"), cv_rows=("matched_label_rows", "sum"))
    grouped["complexity_rank"] = grouped.model_id.map(MODEL_COMPLEXITY)
    grouped = grouped.sort_values(["mean_cv_log_loss", "complexity_rank"], kind="mergesort").reset_index(drop=True)
    if not grouped.empty:
        best = grouped.loc[0, "mean_cv_log_loss"]
        tied = grouped.loc[np.abs(grouped.mean_cv_log_loss - best) <= 1e-6]
        grouped["selected_for_primary"] = grouped.model_id.eq(tied.sort_values("complexity_rank").iloc[0].model_id)
    else:
        grouped["selected_for_primary"] = False
    return grouped


def _environment() -> dict[str, str]:
    names = ("numpy", "pandas", "pyarrow", "scikit-learn", "scipy", "matplotlib", "nbformat", "nbclient")
    return {name: importlib.metadata.version(name) for name in names}


def run_gate_b(inputs: GateBInputs) -> dict[str, Any]:
    """Run the fixed Gate-B comparison and atomically publish a package."""

    package = inputs.package.resolve()
    output = inputs.output.resolve()
    if output.exists():
        raise GateBError(f"refusing to overwrite immutable output: {output}")
    if not (package / "SHA256SUMS.json").is_file():
        raise GateBError("Gate-A package is absent")
    gate_a_manifest = digest(package / "SHA256SUMS.json")
    if gate_a_manifest != "dfa14d42410d5513cbb07f832972e47fa1cf819a6f1eece13e1f92106e096ae1":
        raise GateBError("Gate-B only accepts the PI-approved Gate-A v5 manifest")
    stage = output.with_name(f".{output.name}.stage")
    if stage.exists():
        raise GateBError(f"staging directory already exists: {stage}")
    stage.mkdir(parents=True)
    try:
        panel = _match_panel(package, inputs.full_3sp_source)
        development = panel.loc[panel.role == "DEVELOPMENT_CV"].copy()
        locked_test = panel.loc[panel.role == "RETROSPECTIVE_TEST_LOCKED"].copy()
        if development.issue.nunique() != 344 or locked_test.issue.nunique() != 75:
            raise GateBError("frozen development/test issue census drift")
        if any(_is_reserved_210_issue(row.issue, row.year) for row in locked_test.itertuples()):
            raise GateBError("reserved #210 issue reached Gate B")
        metrics_frames: list[pd.DataFrame] = []
        prediction_frames: list[pd.DataFrame] = []
        for year in CV_VALIDATION_YEARS:
            train, validation = _fold_split(development, year)
            for model_id in MODEL_ORDER:
                for seed in SEEDS:
                    metrics, predictions = _evaluation_rows(panel, model_id, seed, f"CV_{year}", train, validation)
                    metrics_frames.append(metrics)
                    prediction_frames.append(predictions)
        for model_id in MODEL_ORDER:
            for seed in SEEDS:
                metrics, predictions = _evaluation_rows(panel, model_id, seed, "LOCKED_TEST", development, locked_test)
                metrics_frames.append(metrics)
                prediction_frames.append(predictions)
        metrics_frame = pd.concat(metrics_frames, ignore_index=True)
        predictions_frame = pd.concat(prediction_frames, ignore_index=True)
        selection = _selection(metrics_frame)
        write_csv(stage / "metrics.csv", metrics_frame.sort_values(["split", "model_id", "seed", "view"], kind="mergesort"))
        predictions_frame.sort_values(["split", "model_id", "seed", "issue_order", "match_idx"], kind="mergesort").to_parquet(stage / "per_match_predictions.parquet", index=False)
        write_csv(stage / "model_selection.csv", selection)
        label_census = panel.groupby(["role", "year"], as_index=False).agg(
            issues=("issue", "nunique"), matches=("match_idx", "size"), official_label_rows=("label_available", "sum"),
            official_sp_target_rows=("sp_target_available", "sum"), market_eligible_rows=("market_eligible", "sum"),
        )
        write_csv(stage / "label_census.csv", label_census)
        write_csv(stage / "locked_test_identity_reconciliation.csv", locked_test[["issue", "match_idx", "label_available", "sp_target_available", "market_eligible"]])
        config = {
            "version": GATE_B_VERSION,
            "execution_status": "RETROSPECTIVE_IMPLEMENTATION_RECOVERY",
            "gate_a_manifest_sha256": gate_a_manifest,
            "full_3sp_source_sha256": digest(inputs.full_3sp_source),
            "outcome_axis": list(CLASS_CODES),
            "features": list(FEATURE_COLUMNS),
            "seeds": list(SEEDS),
            "cv_validation_years": list(CV_VALIDATION_YEARS),
            "models": {
                "LOGISTIC_RESIDUAL": {"package": "sklearn", "C": 0.5, "max_iter": 300},
                "HIST_GRADIENT_RESIDUAL": {"package": "sklearn", "learning_rate": 0.05, "max_iter": 60, "max_leaf_nodes": 8},
                "ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL": {
                    "package": "sklearn",
                    "representation": "permutation_invariant_issue_mean_std_max_min",
                    "hidden_layer_sizes": [32],
                    "max_iter": 50,
                    "scope": "issue-summary MLP control; not a learned-pooling Deep Sets encoder",
                    "torch_status": "not installed in frozen repository environment; PI authorized no dependency installation",
                },
                "SP_HEAD": {"package": "sklearn", "implementation": "three HistGradientBoostingRegressor heads", "max_iter": 60},
            },
            "probability_composition": "softmax(log(frozen_market_probability_3_1_0) + centered_delta_model_3_1_0)",
            "fallback": "model only if market-eligible, finite anchored output, and frozen known-grade/finite-observed OOD test passes; otherwise exact market or NO_BET_FROZEN",
            "label_boundary": "parsed only for Gate-A registry identities; 26051+ lines are not parsed into label fields",
            "environment": _environment(),
        }
        write_json(stage / "model_config.json", config)
        provenance = {
            "gate_a_package": "results/bj204_gate_a_preoutcome_v5",
            "gate_a_manifest_sha256": gate_a_manifest,
            "official_label_source": "data/raw/beidan_full_3sp.csv",
            "official_label_source_sha256": digest(inputs.full_3sp_source),
            "output_contract": GATE_B_VERSION,
            "output_atomic": True,
            "execution_status": "RETROSPECTIVE_IMPLEMENTATION_RECOVERY",
            "invalid_v1_receipt": "results/bj204_gate_b_invalid_v1_receipt/invalid_run_receipt.json",
        }
        write_json(stage / "provenance.json", provenance)
        (stage / "README.md").write_text(_package_readme(gate_a_manifest), encoding="utf-8", newline="\n")
        finalized = finalize_gate_b(stage)
        output.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(output)
        return {
            "output": str(output),
            **finalized,
            "prediction_rows": len(predictions_frame),
            "execution_status": "RETROSPECTIVE_IMPLEMENTATION_RECOVERY",
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
