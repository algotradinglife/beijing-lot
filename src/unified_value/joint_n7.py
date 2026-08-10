"""Issue #205: auditable M×3 value matrix and fixed-N7 joint payoff calibration.

The module consumes the accepted #204 out-of-fold/locked prediction ledger.  It
uses exhaustive 3**7 outcome configurations for one deterministic seven-match
panel per issue; it does not sample or optimize tickets.  Generic estimation is
package-backed (scikit-learn/SciPy).  Custom code is limited to the N7 identity,
settlement, fallback and provenance adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import itertools
import json
from pathlib import Path
import shutil
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.ensemble import HistGradientBoostingClassifier

OUTCOMES = ("3", "1", "0")
OUTCOME_INDEX = {code: i for i, code in enumerate(OUTCOMES)}
N = 7
TAX_FACTOR = 0.65
CONFIGS = np.asarray(list(itertools.product(range(3), repeat=N)), dtype=np.int8)
VERSION = "bj205-joint-n7-value-matrix-v1"
SOURCE_LEDGER_ID = (
    "bj204-market-anchored-model-gate-b-retrospective-method-correction-v1"
)
PRIMARY_METRIC = "joint_log_loss"
FEATURE_NAMES = (
    "share_3",
    "share_1",
    "share_0",
    "same_outcome_pair_share",
    "selected_residual_mean",
    "selected_residual_std",
    "selected_logp_mean",
    "selected_logsp_mean",
    "issue_mean_abs_residual",
    "issue_mean_entropy",
    "issue_sp_cv",
)


class JointN7Error(RuntimeError):
    pass


@dataclass(frozen=True)
class Inputs:
    ledger: Path
    gate_a_cells: Path
    output: Path


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )


def _environment() -> dict[str, str]:
    names = (
        "numpy",
        "pandas",
        "pyarrow",
        "scikit-learn",
        "scipy",
        "matplotlib",
        "nbformat",
        "nbclient",
    )
    return {name: importlib.metadata.version(name) for name in names}


def _normalize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    total = float(values.sum())
    if not np.isfinite(values).all() or (values < 0).any() or total <= 0:
        raise JointN7Error("invalid joint probability vector")
    return values / total


def _config_products(matrix: np.ndarray) -> np.ndarray:
    return np.prod(matrix[np.arange(N)[None, :], CONFIGS], axis=1)


def _result_config(result_codes: np.ndarray) -> int:
    target = np.asarray(
        [OUTCOME_INDEX[str(code)] for code in result_codes], dtype=np.int8
    )
    hits = np.flatnonzero(np.all(CONFIGS == target[None, :], axis=1))
    if len(hits) != 1:
        raise JointN7Error("realized N7 configuration is not unique")
    return int(hits[0])


def load_match_panel(ledger_path: Path, gate_a_cells_path: Path) -> pd.DataFrame:
    ledger = pd.read_parquet(ledger_path)
    required = {
        "issue",
        "year",
        "issue_order",
        "match_idx",
        "split",
        "model_id",
        "seed",
        "result_code",
        "label_available",
        "market_eligible",
        "model_used",
        "fallback_reason",
        *[f"market_probability_{c}" for c in OUTCOMES],
        *[f"fallback_mixed_probability_{c}" for c in OUTCOMES],
        *[f"delta_logit_{c}" for c in OUTCOMES],
        *[f"predicted_final_sp_{c}" for c in OUTCOMES],
        *[f"official_final_sp_{c}" for c in OUTCOMES],
    }
    if not required.issubset(ledger.columns):
        raise JointN7Error(
            f"#204 ledger schema missing {sorted(required.difference(ledger.columns))}"
        )
    source = ledger.loc[ledger.model_id.astype(str).eq("LOGISTIC_RESIDUAL")].copy()
    if source.empty:
        raise JointN7Error("accepted #204 LOGISTIC_RESIDUAL rows are absent")
    keys = ["issue", "year", "issue_order", "match_idx", "split", "result_code"]
    numeric = [
        *[f"market_probability_{c}" for c in OUTCOMES],
        *[f"fallback_mixed_probability_{c}" for c in OUTCOMES],
        *[f"delta_logit_{c}" for c in OUTCOMES],
        *[f"predicted_final_sp_{c}" for c in OUTCOMES],
        *[f"official_final_sp_{c}" for c in OUTCOMES],
    ]
    means = source.groupby(keys, as_index=False, dropna=False)[numeric].mean()
    stds = source.groupby(keys, as_index=False, dropna=False)[
        [f"fallback_mixed_probability_{c}" for c in OUTCOMES]
        + [f"predicted_final_sp_{c}" for c in OUTCOMES]
    ].std(ddof=0)
    stds = stds.rename(
        columns={c: f"seed_std__{c}" for c in stds.columns if c not in keys}
    )
    flags = source.groupby(keys, as_index=False, dropna=False).agg(
        label_available=("label_available", "all"),
        market_eligible=("market_eligible", "all"),
        model_used=("model_used", "all"),
        fallback_reason=(
            "fallback_reason",
            lambda x: "|".join(sorted(set(map(str, x)))),
        ),
        seed_count=("seed", "nunique"),
    )
    panel = means.merge(stds, on=keys, validate="one_to_one").merge(
        flags, on=keys, validate="one_to_one"
    )
    cells = pd.read_parquet(gate_a_cells_path)
    cells["issue"] = cells.issue.astype(str)
    cells["outcome_code"] = cells.outcome_code.astype(str)
    sp_input = cells.pivot(
        index=["issue", "match_idx"],
        columns="outcome_code",
        values="predicted_final_sp_input",
    )
    sp_input.columns = [f"frozen_sp_input_{c}" for c in sp_input.columns]
    panel["issue"] = panel.issue.astype(str)
    panel = panel.merge(
        sp_input.reset_index(),
        on=["issue", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    if (panel.seed_count != 3).any():
        raise JointN7Error("#204 nuisance-seed coverage is not exactly three")
    return panel.sort_values(
        ["issue_order", "match_idx"], kind="mergesort"
    ).reset_index(drop=True)


def build_value_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in panel.itertuples(index=False):
        market = np.asarray(
            [getattr(row, f"market_probability_{c}") for c in OUTCOMES], dtype=float
        )
        model = np.asarray(
            [getattr(row, f"fallback_mixed_probability_{c}") for c in OUTCOMES],
            dtype=float,
        )
        sp = np.asarray(
            [getattr(row, f"predicted_final_sp_{c}") for c in OUTCOMES], dtype=float
        )
        valid = (
            bool(row.market_eligible)
            and np.isfinite(market).all()
            and np.isfinite(sp).all()
            and (sp > 0).all()
        )
        use_model = valid and bool(row.model_used) and np.isfinite(model).all()
        effective = model if use_model else market
        reason = (
            "NONE"
            if use_model
            else (
                "BASELINE_SP_OR_PROBABILITY_UNSUPPORTED"
                if not valid
                else "DEPENDENCE_BASELINE_FALLBACK"
            )
        )
        for i, code in enumerate(OUTCOMES):
            p = effective[i] if valid else np.nan
            rows.append(
                {
                    "issue": row.issue,
                    "year": int(row.year),
                    "split": row.split,
                    "match_idx": int(row.match_idx),
                    "outcome_code": code,
                    "market_probability": market[i],
                    "calibrated_true_probability": p,
                    "predicted_final_sp": sp[i],
                    "probability_seed_std": getattr(
                        row, f"seed_std__fallback_mixed_probability_{code}"
                    ),
                    "sp_seed_std": getattr(row, f"seed_std__predicted_final_sp_{code}"),
                    "predictive_entropy": float(
                        -np.sum(effective * np.log(np.clip(effective, 1e-15, 1)))
                    )
                    if valid
                    else np.nan,
                    "model_market_residual": p - market[i] if valid else np.nan,
                    "expected_gross": p * sp[i] if valid else np.nan,
                    "expected_pre_tax_net": TAX_FACTOR * p * sp[i] - 1
                    if valid
                    else np.nan,
                    "displayed_scalar_utility": TAX_FACTOR * p * sp[i] - 1
                    if valid
                    else np.nan,
                    "fallback_applied": not use_model,
                    "fallback_reason": reason,
                    "official_final_sp_label": getattr(
                        row, f"official_final_sp_{code}"
                    ),
                    "realized_outcome": str(row.result_code) == code,
                }
            )
    return pd.DataFrame(rows)


def _ticket_features(
    prob: np.ndarray, residual: np.ndarray, sp: np.ndarray
) -> np.ndarray:
    selected_p = prob[np.arange(N)[None, :], CONFIGS]
    selected_r = residual[np.arange(N)[None, :], CONFIGS]
    selected_sp = sp[np.arange(N)[None, :], CONFIGS]
    counts = np.column_stack([(CONFIGS == k).mean(axis=1) for k in range(3)])
    pair_share = (
        np.sum(
            np.column_stack(
                [
                    np.sum(CONFIGS == k, axis=1)
                    * (np.sum(CONFIGS == k, axis=1) - 1)
                    / 2
                    for k in range(3)
                ]
            ),
            axis=1,
        )
        / 21.0
    )
    entropy = -np.sum(prob * np.log(np.clip(prob, 1e-15, 1)), axis=1)
    context = np.column_stack(
        [
            np.full(len(CONFIGS), np.mean(np.abs(residual))),
            np.full(len(CONFIGS), np.mean(entropy)),
            np.full(len(CONFIGS), np.std(sp) / max(np.mean(sp), 1e-12)),
        ]
    )
    return np.column_stack(
        [
            counts,
            pair_share,
            selected_r.mean(axis=1),
            selected_r.std(axis=1),
            np.log(np.clip(selected_p, 1e-15, 1)).mean(axis=1),
            np.log(np.clip(selected_sp, 1e-15, None)).mean(axis=1),
            context,
        ]
    )


def build_issue_tickets(
    panel: pd.DataFrame,
) -> tuple[dict[str, list[dict[str, Any]]], pd.DataFrame]:
    by_split: dict[str, list[dict[str, Any]]] = {}
    census: list[dict[str, Any]] = []
    for (split, issue), group in panel.groupby(["split", "issue"], sort=False):
        group = group.sort_values("match_idx", kind="mergesort")
        prob_cols = [f"fallback_mixed_probability_{c}" for c in OUTCOMES]
        market_cols = [f"market_probability_{c}" for c in OUTCOMES]
        sp_cols = [f"predicted_final_sp_{c}" for c in OUTCOMES]
        eligible = group.label_available.astype(bool) & group.market_eligible.astype(
            bool
        )
        eligible &= np.isfinite(
            group[market_cols + prob_cols + sp_cols].to_numpy(dtype=float)
        ).all(axis=1)
        eligible &= (group[sp_cols].to_numpy(dtype=float) > 0).all(axis=1)
        chosen = group.loc[eligible].head(N)
        if len(chosen) < N:
            census.append(
                {
                    "split": split,
                    "issue": issue,
                    "eligible_matches": len(chosen),
                    "ticket_status": "NO_BET_LT7",
                }
            )
            continue
        market = chosen[market_cols].to_numpy(dtype=float)
        prob = chosen[prob_cols].to_numpy(dtype=float)
        residual = prob - market
        sp = chosen[sp_cols].to_numpy(dtype=float)
        record = {
            "split": split,
            "issue": issue,
            "year": int(chosen.year.iloc[0]),
            "issue_order": float(chosen.issue_order.iloc[0]),
            "match_indices": chosen.match_idx.astype(int).tolist(),
            "market_joint": _normalize(_config_products(market)),
            "model_independent_joint": _normalize(_config_products(prob)),
            "sp_product": _config_products(sp),
            "features": _ticket_features(prob, residual, sp),
            "realized_index": _result_config(chosen.result_code.astype(str).to_numpy()),
            "context": np.asarray(
                [
                    np.mean(np.abs(residual)),
                    np.mean(-np.sum(prob * np.log(np.clip(prob, 1e-15, 1)), axis=1)),
                    np.std(sp) / max(np.mean(sp), 1e-12),
                ]
            ),
        }
        by_split.setdefault(str(split), []).append(record)
        census.append(
            {
                "split": split,
                "issue": issue,
                "eligible_matches": int(eligible.sum()),
                "ticket_status": "EXHAUSTIVE_3POW7",
                "match_indices": "|".join(map(str, record["match_indices"])),
            }
        )
    return by_split, pd.DataFrame(census)


def _nll(records: list[dict[str, Any]], probabilities: list[np.ndarray]) -> float:
    return float(
        np.mean(
            [
                -np.log(np.clip(p[r["realized_index"]], 1e-15, 1))
                for r, p in zip(records, probabilities, strict=True)
            ]
        )
    )


def _simple_fit(records: list[dict[str, Any]]) -> np.ndarray:
    indices = np.asarray([3, 4, 5], dtype=int)

    def objective(theta: np.ndarray) -> float:
        probs = []
        for r in records:
            f = r["features"][:, indices]
            score = (f - f.mean(axis=0)) @ theta
            probs.append(
                _normalize(
                    r["model_independent_joint"] * np.exp(np.clip(score, -20, 20))
                )
            )
        return _nll(records, probs) + 1e-3 * float(theta @ theta)

    result = minimize(
        objective,
        np.zeros(len(indices)),
        method="L-BFGS-B",
        bounds=[(-1.0, 1.0)] * len(indices),
    )
    if not result.success:
        raise JointN7Error(f"simple dependence optimizer failed: {result.message}")
    return np.asarray(result.x)


def _simple_predict(
    records: list[dict[str, Any]], theta: np.ndarray
) -> list[np.ndarray]:
    indices = np.asarray([3, 4, 5], dtype=int)
    output = []
    for r in records:
        f = r["features"][:, indices]
        score = (f - f.mean(axis=0)) @ theta
        output.append(
            _normalize(r["model_independent_joint"] * np.exp(np.clip(score, -20, 20)))
        )
    return output


def _latent_fit(
    records: list[dict[str, Any]],
) -> tuple[HistGradientBoostingClassifier, float]:
    x = np.vstack([r["features"] for r in records])
    y = np.zeros(len(x), dtype=np.int8)
    for i, r in enumerate(records):
        y[i * len(CONFIGS) + r["realized_index"]] = 1
    model = HistGradientBoostingClassifier(
        max_iter=30,
        max_leaf_nodes=8,
        learning_rate=0.05,
        l2_regularization=2.0,
        class_weight="balanced",
        random_state=205001,
    ).fit(x, y)
    raw = model.predict_proba(x)[:, 1]
    logits = np.log(np.clip(raw, 1e-12, 1 - 1e-12)) - np.log(np.clip(1 - raw, 1e-12, 1))
    directions = [
        logits[i * len(CONFIGS) : (i + 1) * len(CONFIGS)] for i in range(len(records))
    ]

    def objective(alpha_arr: np.ndarray) -> float:
        alpha = float(alpha_arr[0])
        probs = [
            _normalize(
                r["model_independent_joint"]
                * np.exp(np.clip(alpha * (d - d.mean()), -20, 20))
            )
            for r, d in zip(records, directions, strict=True)
        ]
        return _nll(records, probs)

    result = minimize(
        objective, np.asarray([0.0]), method="L-BFGS-B", bounds=[(0.0, 1.0)]
    )
    if not result.success:
        raise JointN7Error(f"latent anchor optimizer failed: {result.message}")
    return model, float(result.x[0])


def _latent_predict(
    records: list[dict[str, Any]], model: HistGradientBoostingClassifier, alpha: float
) -> list[np.ndarray]:
    output = []
    for r in records:
        raw = model.predict_proba(r["features"])[:, 1]
        direction = np.log(np.clip(raw, 1e-12, 1 - 1e-12)) - np.log(
            np.clip(1 - raw, 1e-12, 1)
        )
        output.append(
            _normalize(
                r["model_independent_joint"]
                * np.exp(np.clip(alpha * (direction - direction.mean()), -20, 20))
            )
        )
    return output


def _support_bounds(records: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    x = np.vstack([r["context"] for r in records])
    lo, hi = np.quantile(x, [0.01, 0.99], axis=0)
    margin = np.maximum(hi - lo, 1e-9) * 0.20
    return lo - margin, hi + margin


def _fallback_mix(
    records: list[dict[str, Any]],
    candidate: list[np.ndarray],
    bounds: tuple[np.ndarray, np.ndarray],
) -> tuple[list[np.ndarray], np.ndarray]:
    lo, hi = bounds
    supported = np.asarray(
        [
            np.isfinite(r["context"]).all()
            and (r["context"] >= lo).all()
            and (r["context"] <= hi).all()
            and np.isfinite(p).all()
            for r, p in zip(records, candidate, strict=True)
        ]
    )
    mixed = [
        p if ok else r["market_joint"].copy()
        for r, p, ok in zip(records, candidate, supported, strict=True)
    ]
    return mixed, supported


def _metric_rows(
    split: str,
    model: str,
    records: list[dict[str, Any]],
    probabilities: list[np.ndarray],
    supported: np.ndarray | None = None,
) -> dict[str, Any]:
    n = len(records)
    true_p = np.asarray(
        [p[r["realized_index"]] for r, p in zip(records, probabilities, strict=True)]
    )
    brier = []
    payout_mae = []
    predicted_mean = []
    realized_mean = []
    for r, p in zip(records, probabilities, strict=True):
        one = np.zeros(len(CONFIGS))
        one[r["realized_index"]] = 1
        brier.append(np.sum((p - one) ** 2))
        pred = TAX_FACTOR * p * r["sp_product"] - 1
        real = np.where(one > 0, TAX_FACTOR * r["sp_product"] - 1, -1.0)
        payout_mae.append(np.mean(np.abs(pred - real)))
        predicted_mean.append(np.mean(pred))
        realized_mean.append(np.mean(real))
    return {
        "split": split,
        "model": model,
        "issues": n,
        "ticket_candidates": n * len(CONFIGS),
        "realized_hits": n,
        "joint_log_loss": float(np.mean(-np.log(np.clip(true_p, 1e-15, 1)))),
        "joint_brier": float(np.mean(brier)),
        "mean_realized_configuration_probability": float(true_p.mean()),
        "payout_mae": float(np.mean(payout_mae)),
        "mean_predicted_net": float(np.mean(predicted_mean)),
        "mean_realized_net": float(np.mean(realized_mean)),
        "model_covered_issues": int(supported.sum()) if supported is not None else n,
        "fallback_issues": int((~supported).sum()) if supported is not None else 0,
    }


def _fit_predict(
    train: list[dict[str, Any]], evaluation: list[dict[str, Any]], family: str
) -> tuple[list[np.ndarray], np.ndarray, dict[str, Any]]:
    bounds = _support_bounds(train)
    if family == "SIMPLE_REGIME_DEPENDENCE":
        theta = _simple_fit(train)
        candidate = _simple_predict(evaluation, theta)
        params = {"theta": theta.tolist()}
    elif family == "LATENT_SET_DEPENDENCE":
        model, alpha = _latent_fit(train)
        candidate = _latent_predict(evaluation, model, alpha)
        params = {"alpha": alpha}
    else:
        raise JointN7Error(f"unknown dependence family {family}")
    mixed, supported = _fallback_mix(evaluation, candidate, bounds)
    params["support_lower"] = bounds[0].tolist()
    params["support_upper"] = bounds[1].tolist()
    return mixed, supported, params


def reliability(
    records: list[dict[str, Any]],
    probabilities: list[np.ndarray],
    model: str,
    split: str,
) -> pd.DataFrame:
    frames = []
    for r, p in zip(records, probabilities, strict=True):
        frames.append(
            pd.DataFrame(
                {
                    "probability": p,
                    "hit": np.arange(len(CONFIGS)) == r["realized_index"],
                }
            )
        )
    frame = pd.concat(frames, ignore_index=True)
    frame["bin"] = pd.qcut(frame.probability.rank(method="first"), 10, labels=False) + 1
    return (
        frame.groupby("bin", as_index=False)
        .agg(
            rows=("hit", "size"),
            mean_probability=("probability", "mean"),
            hit_rate=("hit", "mean"),
        )
        .assign(model=model, split=split)
    )


def _cell_reliability(value: pd.DataFrame) -> pd.DataFrame:
    source = value.loc[
        value.split.eq("LOCKED_TEST") & np.isfinite(value.calibrated_true_probability)
    ].copy()
    source["bin"] = (
        pd.qcut(
            source.calibrated_true_probability.rank(method="first"), 10, labels=False
        )
        + 1
    )
    return source.groupby("bin", as_index=False).agg(
        rows=("realized_outcome", "size"),
        mean_probability=("calibrated_true_probability", "mean"),
        outcome_rate=("realized_outcome", "mean"),
    )


def _plots(
    cell_rel: pd.DataFrame,
    ticket_rel: pd.DataFrame,
    metrics: pd.DataFrame,
    output: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], "--", color="black")
    ax.plot(cell_rel.mean_probability, cell_rel.outcome_rate, marker="o")
    ax.set(
        xlabel="Predicted probability",
        ylabel="Observed frequency",
        title="#205 cell reliability",
    )
    fig.tight_layout()
    fig.savefig(output / "cell_reliability.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(5.5, 5))
    for model, g in ticket_rel.groupby("model"):
        ax.plot(g.mean_probability, g.hit_rate, marker="o", label=model)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set(
        xlabel="Predicted ticket-hit probability",
        ylabel="Observed hit frequency",
        title="#205 N7 reliability",
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "ticket_reliability.png", dpi=160)
    plt.close(fig)
    locked = metrics.loc[metrics.split.eq("LOCKED_TEST")].sort_values("joint_log_loss")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(locked.model, locked.joint_log_loss)
    ax.tick_params(axis="x", rotation=25)
    ax.set(
        ylabel="Joint log loss (lower better)",
        title="#205 locked matched joint calibration",
    )
    fig.tight_layout()
    fig.savefig(output / "locked_joint_log_loss.png", dpi=160)
    plt.close(fig)


def run(inputs: Inputs) -> dict[str, Any]:
    output = inputs.output.resolve()
    if output.exists():
        raise JointN7Error(f"refusing to overwrite immutable output {output}")
    stage = output.with_name(f".{output.name}.stage")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        panel = load_match_panel(inputs.ledger.resolve(), inputs.gate_a_cells.resolve())
        values = build_value_matrix(panel)
        tickets, census = build_issue_tickets(panel)
        required_splits = {"CV_2021", "CV_2022", "CV_2023", "LOCKED_TEST"}
        if not required_splits.issubset(tickets):
            raise JointN7Error(
                f"missing chronological ticket splits {sorted(required_splits.difference(tickets))}"
            )
        families = ("SIMPLE_REGIME_DEPENDENCE", "LATENT_SET_DEPENDENCE")
        metrics: list[dict[str, Any]] = []
        cv_params: dict[str, Any] = {}
        for eval_year in (2022, 2023):
            train = [
                r for year in range(2021, eval_year) for r in tickets[f"CV_{year}"]
            ]
            evaluation = tickets[f"CV_{eval_year}"]
            baseline = [r["market_joint"] for r in evaluation]
            independent = [r["model_independent_joint"] for r in evaluation]
            metrics.extend(
                [
                    _metric_rows(
                        f"CV_{eval_year}", "MARKET_INDEPENDENCE", evaluation, baseline
                    ),
                    _metric_rows(
                        f"CV_{eval_year}", "MODEL_INDEPENDENCE", evaluation, independent
                    ),
                ]
            )
            for family in families:
                pred, supported, params = _fit_predict(train, evaluation, family)
                metrics.append(
                    _metric_rows(f"CV_{eval_year}", family, evaluation, pred, supported)
                )
                cv_params[f"{family}_CV_{eval_year}"] = params
        metric_frame = pd.DataFrame(metrics)
        cv_mean = (
            metric_frame.groupby("model", as_index=False)
            .joint_log_loss.mean()
            .sort_values("joint_log_loss", kind="mergesort")
        )
        candidates = cv_mean.loc[cv_mean.model.isin(families)]
        selected = str(candidates.iloc[0].model)
        baseline_cv = float(
            cv_mean.loc[cv_mean.model.eq("MARKET_INDEPENDENCE"), "joint_log_loss"].iloc[
                0
            ]
        )
        independence_cv = float(
            cv_mean.loc[cv_mean.model.eq("MODEL_INDEPENDENCE"), "joint_log_loss"].iloc[
                0
            ]
        )
        preregistered_advance = (
            float(candidates.iloc[0].joint_log_loss)
            < min(baseline_cv, independence_cv) - 1e-12
        )
        train_all = [r for year in (2021, 2022, 2023) for r in tickets[f"CV_{year}"]]
        locked = tickets["LOCKED_TEST"]
        locked_predictions: dict[str, list[np.ndarray]] = {
            "MARKET_INDEPENDENCE": [r["market_joint"] for r in locked],
            "MODEL_INDEPENDENCE": [r["model_independent_joint"] for r in locked],
        }
        selected_pred, selected_supported, locked_params = _fit_predict(
            train_all, locked, selected
        )
        locked_predictions[selected] = selected_pred
        for name, pred in locked_predictions.items():
            support = selected_supported if name == selected else None
            metrics.append(_metric_rows("LOCKED_TEST", name, locked, pred, support))
        metric_frame = pd.DataFrame(metrics)
        locked_metrics = metric_frame.loc[
            metric_frame.split.eq("LOCKED_TEST")
        ].set_index("model")
        locked_advance = (
            preregistered_advance
            and locked_metrics.loc[selected, PRIMARY_METRIC]
            < min(
                locked_metrics.loc["MARKET_INDEPENDENCE", PRIMARY_METRIC],
                locked_metrics.loc["MODEL_INDEPENDENCE", PRIMARY_METRIC],
            )
            - 1e-12
        )
        inherited = selected if locked_advance else "MARKET_INDEPENDENCE"
        final_probs = (
            locked_predictions[selected]
            if locked_advance
            else locked_predictions["MARKET_INDEPENDENCE"]
        )
        final_supported = (
            selected_supported if locked_advance else np.zeros(len(locked), dtype=bool)
        )
        ticket_rows = []
        for r, p, supported in zip(locked, final_probs, final_supported, strict=True):
            for idx, (config, probability, sp_product) in enumerate(
                zip(CONFIGS, p, r["sp_product"], strict=True)
            ):
                ticket_rows.append(
                    {
                        "issue": r["issue"],
                        "match_indices": "|".join(map(str, r["match_indices"])),
                        "ticket_identity": "|".join(OUTCOMES[i] for i in config),
                        "joint_probability": probability,
                        "predicted_sp_product": sp_product,
                        "expected_gross": probability * sp_product,
                        "expected_pre_tax_net": TAX_FACTOR * probability * sp_product
                        - 1,
                        "realized_hit": idx == r["realized_index"],
                        "scorer": inherited,
                        "fallback_applied": not bool(supported),
                    }
                )
        ticket_frame = pd.DataFrame(ticket_rows)
        rel = pd.concat(
            [
                reliability(locked, pred, name, "LOCKED_TEST")
                for name, pred in locked_predictions.items()
            ],
            ignore_index=True,
        )
        cell_rel = _cell_reliability(values)
        baseline_locked = float(
            locked_metrics.loc["MARKET_INDEPENDENCE", PRIMARY_METRIC]
        )
        for metric in (PRIMARY_METRIC, "joint_brier", "payout_mae"):
            base = metric_frame.loc[
                (metric_frame.split.eq("LOCKED_TEST"))
                & metric_frame.model.eq("MARKET_INDEPENDENCE"),
                metric,
            ].iloc[0]
            metric_frame[f"matched_lift_{metric}_vs_market"] = np.where(
                metric_frame.split.eq("LOCKED_TEST"),
                metric_frame[metric] - base,
                np.nan,
            )
        values.to_parquet(stage / "value_matrix.parquet", index=False)
        ticket_frame.to_parquet(
            stage / "locked_ticket_predictions.parquet", index=False
        )
        census.to_csv(stage / "ticket_census.csv", index=False)
        metric_frame.to_csv(stage / "metrics.csv", index=False)
        cv_mean.to_csv(stage / "cv_model_selection.csv", index=False)
        rel.to_csv(stage / "ticket_reliability.csv", index=False)
        cell_rel.to_csv(stage / "cell_reliability.csv", index=False)
        regime = ticket_frame.groupby("fallback_applied", as_index=False).agg(
            tickets=("realized_hit", "size"),
            hits=("realized_hit", "sum"),
            mean_probability=("joint_probability", "mean"),
            mean_utility=("expected_pre_tax_net", "mean"),
        )
        regime.to_csv(stage / "regime_diagnostics.csv", index=False)
        schema = {
            "version": VERSION,
            "outcome_axis": list(OUTCOMES),
            "n": N,
            "tax_factor_reference": TAX_FACTOR,
            "displayed_scalar": "expected_pre_tax_net = 0.65 * calibrated_true_probability * predicted_final_sp - 1",
            "ticket_formula": "0.65 * P(all seven outcomes hit | issue state) * product(predicted_final_sp) - 1",
            "channels": [
                "calibrated_true_probability",
                "predicted_final_sp",
                "probability_seed_std",
                "sp_seed_std",
                "predictive_entropy",
                "model_market_residual",
                "expected_gross",
                "expected_pre_tax_net",
            ],
            "baseline": "#204 frozen market probability plus #204 frozen pre-event SP-head prediction; joint probability is exact product over seven matches",
            "fallback": "unsupported/nonfinite/OOD joint cases use MARKET_INDEPENDENCE exactly; fewer than seven valid matches emit NO_BET_LT7",
            "ticket_roster": "first seven market-eligible labeled matches by match_idx per issue; exhaustive 3^7 outcome identities; no sampling or portfolio optimization",
        }
        _json(stage / "value_matrix_schema.json", schema)
        decision = {
            "version": VERSION,
            "primary_metric": PRIMARY_METRIC,
            "selected_on_cv": selected,
            "cv_dependence_improves_both_controls": preregistered_advance,
            "locked_dependence_improves_both_controls": locked_advance,
            "inherited_scorer": inherited,
            "disposition": "ADVANCE_DEPENDENCE_SCORER"
            if locked_advance
            else "INHERIT_EXACT_MARKET_BASELINE",
            "locked_market_joint_log_loss": baseline_locked,
            "locked_selected_joint_log_loss": float(
                locked_metrics.loc[selected, PRIMARY_METRIC]
            ),
            "covered_issues": int(selected_supported.sum()),
            "fallback_issues": int((~selected_supported).sum()),
        }
        _json(stage / "decision.json", decision)
        _json(
            stage / "model_parameters.json",
            {
                "cv": cv_params,
                "locked": {selected: locked_params},
                "feature_names": list(FEATURE_NAMES),
                "seed": 205001,
            },
        )
        _json(
            stage / "provenance.json",
            {
                "source_ledger": str(inputs.ledger),
                "source_ledger_sha256": _digest(inputs.ledger),
                "gate_a_cells": str(inputs.gate_a_cells),
                "gate_a_cells_sha256": _digest(inputs.gate_a_cells),
                "source_contract": SOURCE_LEDGER_ID,
                "environment": _environment(),
                "replay": "PYTHONPATH=src python scripts/run_bj205_joint_n7.py run --output results/issue-205",
            },
        )
        trace_record = locked[0]
        trace_index = int(trace_record["realized_index"])
        _json(
            stage / "inference_trace.json",
            {
                "version": VERSION,
                "issue": trace_record["issue"],
                "match_indices": trace_record["match_indices"],
                "outcome_axis": list(OUTCOMES),
                "realized_ticket_identity": [OUTCOMES[i] for i in CONFIGS[trace_index]],
                "configuration_index": trace_index,
                "market_independence_probability": float(trace_record["market_joint"][trace_index]),
                "accepted_model_independence_probability": float(trace_record["model_independent_joint"][trace_index]),
                "inherited_joint_probability": float(final_probs[0][trace_index]),
                "predicted_sp_product": float(trace_record["sp_product"][trace_index]),
                "expected_pre_tax_net": float(TAX_FACTOR * final_probs[0][trace_index] * trace_record["sp_product"][trace_index] - 1),
                "fallback_applied": not bool(final_supported[0]),
                "inherited_scorer": inherited,
                "market_joint_vector_sha256": hashlib.sha256(trace_record["market_joint"].tobytes()).hexdigest(),
                "inherited_joint_vector_sha256": hashlib.sha256(final_probs[0].tobytes()).hexdigest(),
                "configuration_axis_sha256": hashlib.sha256(CONFIGS.tobytes()).hexdigest(),
                "formula": "0.65 * joint_probability * predicted_sp_product - 1",
            },
        )
        (stage / "README.md").write_text(
            "# Issue #205 immutable evidence package\n\n"
            "Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj205_joint_n7.py verify --output results/issue-205`\n\n"
            "Replay to a new output directory: `PYTHONPATH=src .venv/bin/python scripts/run_bj205_joint_n7.py run --output <new-directory>`\n\n"
            "The package includes the value schema/matrix, exact inference trace, exhaustive locked ticket ledger, chronological metrics, reliability and regime diagnostics, plots, decision report, parameters, provenance and SHA-256 manifest.\n",
            encoding="utf-8",
            newline="\n",
        )
        report = f"""# Issue #205 decision report — M×3 value matrix and joint N7 payoff calibration

## Decision

`{decision["disposition"]}`. The preregistered metric is joint log loss (lower is better). The CV-selected challenger was `{selected}`. Locked matched joint log loss was {decision["locked_selected_joint_log_loss"]:.6f} versus {baseline_locked:.6f} for the exact market-independence baseline. The inherited scorer is `{inherited}`.

## Absolute and matched evidence

See `metrics.csv` for absolute joint log loss, Brier, payout error and predicted/realized net, plus matched lifts versus the same locked market rows. Covered-case and fallback counts are reported separately. The locked challenger covered {decision["covered_issues"]} issues and fell back on {decision["fallback_issues"]}.

## Challenger analysis and risks

- Sparse payouts: each issue contributes all 2,187 possible N7 outcome identities and exactly one realized hit; proper joint log loss is primary, while payout MAE is diagnostic.
- One-issue concentration: each issue contributes one deterministic first-seven panel and equal issue weight.
- Final-SP leakage: official final SP is retained only as a label channel; scoring uses the frozen #204 pre-event SP-head prediction. It is never an inference feature in the dependence layer.
- Support shift: source/feature context outside frozen development support uses the exact market baseline; issues with fewer than seven valid matches emit `NO_BET_LT7`.
- Proxy boundary: this is retrospective proxy evidence and grants no production, betting or #210 authority.

## Value representation inherited by ticket learning

Ticket learning inherits the versioned long-form J×3 schema in `value_matrix_schema.json`: calibrated probability, SP prediction, uncertainty, residual, gross and pre-tax-net remain separate. `displayed_scalar_utility` is only the documented projection `0.65*p*SP-1`, not a replacement for those channels.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact zero-correction baseline | Exhaustive product `MARKET_INDEPENDENCE`; fallback copies it byte-for-byte | PASS |
| Fixed N=7, no sampling/portfolio optimization | Deterministic first-seven roster plus exhaustive 3^7 identities | PASS |
| Chronological calibration and ablations | CV_2022/CV_2023 then locked test; market, model independence, simple and latent-set controls | PASS |
| Fallback-mixed no worse and dependence lift | `decision.json`, `metrics.csv` | {"PASS" if locked_advance else "FAIL — baseline inherited"} |
| Notebook/code/artifact layers | issue notebook, `src/unified_value/joint_n7.py`, this package | PASS |

Decision input: accept `{inherited}` as the #206 interface. Known risks: retrospective proxy grade, one fixed N7 roster per issue, sparse realized configurations and frozen #204 SP-head error. Explicit review request: verify identity construction, no-leak SP channel, matched-lift arithmetic, OOD fallback identity, and the conservative advancement decision. Do not merge or close until independent EV and PI review.
"""
        (stage / "DECISION_REPORT.md").write_text(
            report, encoding="utf-8", newline="\n"
        )
        _plots(cell_rel, rel, metric_frame, stage)
        payloads = {
            p.relative_to(stage).as_posix(): _digest(p)
            for p in sorted(stage.rglob("*"))
            if p.is_file() and p.name != "SHA256SUMS.json"
        }
        _json(stage / "SHA256SUMS.json", payloads)
        output.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(output)
        return {
            "output": str(output),
            "decision": decision,
            "files": len(payloads),
            "value_rows": len(values),
            "ticket_rows": len(ticket_frame),
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def verify(output: Path) -> dict[str, Any]:
    expected = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        p.relative_to(output).as_posix(): _digest(p)
        for p in sorted(output.rglob("*"))
        if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if actual != expected:
        raise JointN7Error("manifest mismatch")
    schema = json.loads(
        (output / "value_matrix_schema.json").read_text(encoding="utf-8")
    )
    if schema["n"] != 7 or schema["outcome_axis"] != list(OUTCOMES):
        raise JointN7Error("schema identity mismatch")
    return {
        "status": "PASS",
        "files": len(actual),
        "manifest_sha256": _digest(output / "SHA256SUMS.json"),
    }
