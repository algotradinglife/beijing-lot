"""Issue #207: active fixed-N7 Stage-4 bankroll research.

The module reconstructs the frozen #206 research ticket bundles, keeps its empty
safe handoff separate, and evaluates capital allocation only.  scikit-learn
provides the simple and bounded neural ticket-weight controllers; custom code is
limited to frozen ticket binding, integer ¥2 projection, settlement, accounting,
and immutable evidence publication.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ticket_policy.fixed_n7 import (
    FEATURES,
    K_GRID,
    N,
    TAX_FACTOR,
    _fit_logistic_model,
    _fit_model,
    _score_model,
    _select,
    verify as verify_stage3,
)

VERSION = "bj207-fixed-n7-bankroll-v2"
SOURCE_VERSION = "bj206-fixed-n7-ticket-policy-v4"
INITIAL_BANKROLL = 100_000.0
TICKET_STAKE = 2.0
POLICIES = (
    "MARKET_WR",
    "MARKET_WOR",
    "LOGISTIC_BASELINE",
    "LEARNED_MLP",
    "TOP_K_EXPECTED",
)
CONTROLLING_K = 8
RISK_GRID = (0.01, 0.05, 0.25, 1.0)
CONTROL_FEATURES = FEATURES
SOURCE_PACKAGE = Path("results/issue-206")
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCIENTIFIC_LOCK = REPOSITORY_ROOT / "requirements.txt"
RUNNER = REPOSITORY_ROOT / "scripts/run_bj207_bankroll.py"
NOTEBOOK = REPOSITORY_ROOT / "notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb"
ACTIVE_METHODS = (
    "NATIVE_2_YUAN",
    "EQUAL_1PCT",
    "EQUAL_5PCT",
    "EQUAL_25PCT",
    "EQUAL_100PCT",
    "SCORE_WEIGHTED_5PCT",
    "SIMPLE_LOGISTIC",
    "BOUNDED_NEURAL",
)
LEARNED_METHODS = ("SIMPLE_LOGISTIC", "BOUNDED_NEURAL")
STAGE_MARKER = "_STAGE_RUN_STATE.json"


class Stage4Error(RuntimeError):
    """Raised when the Stage-4 contract fails closed."""


@dataclass(frozen=True)
class Inputs:
    source: Path
    output: Path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _notebook_contract_digest(path: Path) -> str:
    """Hash stable notebook inputs, excluding execution outputs and metadata.

    The notebook verifies the package and therefore displays its manifest.  A
    byte hash would create a notebook -> manifest -> provenance -> notebook
    cycle.  Cell source and type are the executable contract; outputs and
    executor-mutated metadata are independently reproducible receipts.
    """
    notebook = json.loads(path.read_text(encoding="utf-8"))
    cells = [
        {
            "cell_type": cell["cell_type"],
            "source": cell.get("source", []),
        }
        for cell in notebook["cells"]
    ]
    return _canonical_hash({"nbformat": notebook["nbformat"], "cells": cells})


def _json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            _fsync_file(path)
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_dir(path)
    _fsync_dir(root)


def _stage_marker(stage: Path) -> Path:
    return stage / STAGE_MARKER


def _prepare_output_stage(output: Path) -> Path:
    stage = output.with_name(f".{output.name}.stage")
    if output.exists():
        raise Stage4Error("immutable output path already exists")
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    _json(_stage_marker(stage), {"status": "IN_PROGRESS", "version": VERSION})
    return stage


def _remove_stage(stage: Path) -> None:
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)


def _publish_stage(stage: Path, output: Path) -> None:
    """Atomically publish a staged package or leave the target retryable."""
    stage.replace(output)
    try:
        _fsync_dir(output.parent)
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        try:
            _fsync_dir(output.parent)
        except BaseException:
            pass
        raise


def _validate_nonnegative_finite(name: str, value: float) -> float:
    numeric = float(value)
    if not np.isfinite(numeric) or numeric < 0:
        raise Stage4Error(f"{name} must be finite and non-negative")
    return numeric


def _experiment_role(method: str) -> str:
    if method in {"SIMPLE_LOGISTIC", "BOUNDED_NEURAL"}:
        return "ACTIVE_LEARNED_ONLY"
    if method == "SCORE_WEIGHTED_5PCT":
        return "ACTIVE_SCORE_WEIGHTED_CONTROL"
    return "ACTIVE_EQUAL_FUNDING_CONTROL"


def _method_family(method: str) -> str:
    if method in LEARNED_METHODS:
        return "LEARNED_CONTROLLER"
    if method == "SCORE_WEIGHTED_5PCT":
        return "SCORE_WEIGHTED_CONTROL"
    if method == "NATIVE_2_YUAN":
        return "NATIVE_EQUAL_CONTROL"
    if method.startswith("EQUAL_"):
        return "EQUAL_FUNDING_CONTROL"
    raise Stage4Error(f"unknown method family {method}")


def _environment() -> dict[str, str]:
    names = (
        "numpy",
        "pandas",
        "pyarrow",
        "scikit-learn",
        "matplotlib",
        "nbformat",
        "nbclient",
    )
    return {
        "python": platform.python_version(),
        **{name: importlib.metadata.version(name) for name in names},
    }


def _validate_candidates(frame: pd.DataFrame) -> None:
    required = {
        "split",
        "issue",
        "year",
        "ticket_identity",
        "match_indices",
        "outcomes",
        "source_cells_json",
        "n",
        "control_joint_probability",
        "predicted_sp_product",
        "expected_pre_tax_net",
        "labels_available",
        "realized_gross",
        *CONTROL_FEATURES,
    }
    if frame.empty or not required.issubset(frame.columns):
        raise Stage4Error(f"#206 candidate ledger missing {sorted(required - set(frame.columns))}")
    key = ["split", "issue", "ticket_identity"]
    if frame.duplicated(key).any():
        raise Stage4Error("#206 candidate identities are not unique")
    if not frame.n.eq(N).all():
        raise Stage4Error("non-N7 candidate entered Stage 4")
    numeric = frame.loc[:, ["control_joint_probability", "predicted_sp_product", *CONTROL_FEATURES]]
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise Stage4Error("non-finite Stage-4 pre-event input")
    if not (frame.control_joint_probability > 0).all() or not (frame.predicted_sp_product > 0).all():
        raise Stage4Error("non-positive Stage-4 probability/SP input")
    if not frame.labels_available.astype(bool).loc[frame.split.isin(["CV_2021", "CV_2022", "CV_2023"])].all():
        raise Stage4Error("historical candidate ledger has missing labels")
    if frame.labels_available.astype(bool).loc[frame.split.eq("LOCKED_TEST")].any():
        raise Stage4Error("future/locked labels leaked into Stage 4")
    if set(frame.split) != {"CV_2021", "CV_2022", "CV_2023", "LOCKED_TEST"}:
        raise Stage4Error("chronology split mismatch")
    for row in frame.itertuples(index=False):
        identity = str(row.ticket_identity).split("|")
        matches = str(row.match_indices).split("|")
        outcomes = str(row.outcomes).split("|")
        if len(identity) != N or len(matches) != N or len(set(matches)) != N or len(outcomes) != N:
            raise Stage4Error("malformed exact-N7 ticket trace")
        cells = json.loads(row.source_cells_json)
        if not isinstance(cells, list) or len(cells) != N:
            raise Stage4Error("malformed seven-cell source trace")
        for cell in cells:
            if not isinstance(cell, dict):
                raise Stage4Error("malformed source trace entry")
            if {
                "match_idx",
                "outcome",
                "control_probability",
                "predicted_final_sp",
                "predicted_final_sp_seed_std",
                "probability_source",
                "probability_source_grade",
            } - set(cell):
                raise Stage4Error("incomplete source trace entry")
            if not np.isfinite(float(cell["control_probability"])) or float(cell["control_probability"]) <= 0:
                raise Stage4Error("non-finite source-trace probability")
            if not np.isfinite(float(cell["predicted_final_sp"])) or float(cell["predicted_final_sp"]) <= 0:
                raise Stage4Error("non-finite source-trace predicted SP")


def _fit_stage3_models(candidates: pd.DataFrame) -> dict[str, Any]:
    train = candidates.loc[candidates.split.eq("CV_2021")]
    # The package-backed simple model is intentionally fitted before the MLP.
    logistic = _fit_logistic_model(train, FEATURES, seed=206001)
    mlp = _fit_model(train, FEATURES, seed=206001)
    return {"LOGISTIC_BASELINE": logistic, "LEARNED_MLP": mlp}


def reconstruct_active_requests(candidates: pd.DataFrame) -> pd.DataFrame:
    """Recompute all frozen five-policy bundles without reading Stage-4 outcomes."""
    models = _fit_stage3_models(candidates)
    outputs: list[pd.DataFrame] = []
    for (_, _), group in candidates.groupby(["split", "issue"], sort=False):
        for policy in POLICIES:
            scores = _score_model(models[policy], group, FEATURES) if policy in models else None
            for k in K_GRID:
                selected = _select(group, policy, k, scores=scores).copy()
                selected["k"] = k
                selected["rank"] = selected.ticket_order
                selected["requested_native_stake_yuan"] = TICKET_STAKE
                selected["source_package"] = SOURCE_PACKAGE.as_posix()
                selected["source_package_version"] = SOURCE_VERSION
                selected["research_only"] = True
                selected["promoted"] = False
                selected["capital_authority"] = "STAGE4_EXPERIMENT_ONLY"
                selected["panel_role"] = "CONTROLLING" if k == CONTROLLING_K else "SENSITIVITY_ONLY"
                selected["labels_used_for_identity"] = False
                selected["tax_adjusted_gross_multiple"] = selected["realized_gross"]
                selected["pre_tax_gross_multiple"] = selected["realized_gross"] / TAX_FACTOR
                outputs.append(selected)
    requests = pd.concat(outputs, ignore_index=True)
    columns = [
        "split",
        "issue",
        "year",
        "policy",
        "k",
        "rank",
        "ticket_identity",
        "match_indices",
        "outcomes",
        "n",
        "source_cells_json",
        "candidate_source",
        "requested_native_stake_yuan",
        "repeat_count",
        "control_joint_probability",
        "predicted_sp_product",
        "mean_selected_sp_seed_std",
        "max_selected_sp_seed_std",
        "expected_pre_tax_net",
        *CONTROL_FEATURES,
        "labels_available",
        "realized_hit",
        "realized_gross",
        "tax_adjusted_gross_multiple",
        "pre_tax_gross_multiple",
        "source_package",
        "source_package_version",
        "research_only",
        "promoted",
        "capital_authority",
        "panel_role",
        "labels_used_for_identity",
    ]
    return requests.loc[:, list(dict.fromkeys(columns))]


def _fit_controllers(candidates: pd.DataFrame) -> dict[str, Any]:
    train = candidates.loc[candidates.split.eq("CV_2021")]
    target = train.realized_hit.astype(int).to_numpy()
    if target.sum() < 3 or len(np.unique(target)) != 2:
        raise Stage4Error("insufficient CV_2021 hit labels for Stage-4 controllers")
    simple = make_pipeline(
        StandardScaler(),
        LogisticRegression(
            C=0.25,
            class_weight="balanced",
            max_iter=1000,
            random_state=207001,
            solver="lbfgs",
        ),
    )
    simple.fit(train.loc[:, CONTROL_FEATURES], target)
    neural = make_pipeline(
        StandardScaler(),
        MLPClassifier(
            hidden_layer_sizes=(8,),
            activation="relu",
            solver="adam",
            alpha=0.05,
            batch_size=256,
            learning_rate_init=0.001,
            max_iter=100,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=10,
            random_state=207001,
        ),
    )
    neural.fit(train.loc[:, CONTROL_FEATURES], target)
    return {"SIMPLE_LOGISTIC": simple, "BOUNDED_NEURAL": neural}


def _weights(bundle: pd.DataFrame, method: str, controllers: dict[str, Any]) -> np.ndarray:
    if method.startswith("EQUAL_") or method == "NATIVE_2_YUAN":
        values = np.ones(len(bundle), dtype=float)
    elif method == "SCORE_WEIGHTED_5PCT":
        values = bundle.control_joint_probability.to_numpy(dtype=float)
    elif method in controllers:
        values = controllers[method].predict_proba(bundle.loc[:, CONTROL_FEATURES])[:, 1]
    else:
        raise Stage4Error(f"unknown allocation method {method}")
    values = np.clip(np.asarray(values, dtype=float), 0.0, None)
    if not np.isfinite(values).all() or values.sum() <= 0:
        raise Stage4Error("invalid controller weights")
    return values / values.sum()


def _project_counts(weights: np.ndarray, budget_yuan: float) -> tuple[np.ndarray, float]:
    if not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1.0):
        raise Stage4Error("invalid simplex weights")
    budget_yuan = _validate_nonnegative_finite("budget_yuan", budget_yuan)
    units = int(np.floor(budget_yuan / TICKET_STAKE))
    raw = weights * units
    counts = np.floor(raw).astype(int)
    remainder = units - int(counts.sum())
    if remainder:
        order = np.argsort(-(raw - counts), kind="stable")
        counts[order[:remainder]] += 1
    residual = float(budget_yuan - counts.sum() * TICKET_STAKE)
    if residual < -1e-9 or residual >= TICKET_STAKE + 1e-9:
        raise Stage4Error("integer projection residual outside [0,2)")
    return counts, residual


def _risk_fraction(method: str, calibrated: dict[str, float]) -> float | None:
    if method == "NATIVE_2_YUAN":
        return None
    if method.startswith("EQUAL_"):
        return float(method.removeprefix("EQUAL_").removesuffix("PCT")) / 100.0
    if method == "SCORE_WEIGHTED_5PCT":
        return 0.05
    return calibrated[method]


def _validate_funding_schedule(selected: pd.DataFrame, funding_schedule: dict[str, float]) -> dict[str, float]:
    if not funding_schedule:
        raise Stage4Error("empty matched funding schedule")
    expected = [str(value) for value in selected.issue.astype(str).tolist()]
    provided = {str(issue): _validate_nonnegative_finite("schedule stake", stake) for issue, stake in funding_schedule.items()}
    if set(provided) != set(expected):
        raise Stage4Error("matched funding schedule issue set mismatch")
    return {issue: provided[issue] for issue in expected}


def replay_path(
    requests: pd.DataFrame,
    *,
    split: str,
    policy: str,
    k: int,
    method: str,
    controllers: dict[str, Any],
    calibrated: dict[str, float],
    funding_schedule: dict[str, float] | None = None,
) -> pd.DataFrame:
    selected = requests.loc[
        requests.split.eq(split) & requests.policy.eq(policy) & requests.k.eq(k)
    ].copy()
    if selected.empty:
        raise Stage4Error("empty active panel cannot become a cash path")
    if funding_schedule is not None:
        funding_schedule = _validate_funding_schedule(selected, funding_schedule)
    selected["_issue_num"] = pd.to_numeric(selected.issue, errors="raise")
    selected = selected.sort_values(["year", "_issue_num", "rank"], kind="stable")
    bankroll = _validate_nonnegative_finite("initial bankroll", INITIAL_BANKROLL)
    peak = bankroll
    rows: list[dict[str, Any]] = []
    fraction = _risk_fraction(method, calibrated)
    for (_, issue), bundle in selected.groupby(["year", "issue"], sort=False):
        if not bundle.labels_available.astype(bool).all():
            raise Stage4Error(f"settlement labels unavailable for {split}/{issue}")
        pre = _validate_nonnegative_finite("pre-issue bankroll", bankroll)
        weights = _weights(bundle, method, controllers)
        requested = (
            float(funding_schedule[str(issue)])
            if funding_schedule is not None
            else TICKET_STAKE * len(bundle)
            if fraction is None
            else pre * fraction
        )
        requested = _validate_nonnegative_finite("requested stake", requested)
        if funding_schedule is not None and requested > pre + 1e-9:
            raise Stage4Error("NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE")
        budget = min(pre, requested)
        budget = _validate_nonnegative_finite("funding budget", budget)
        counts, residual = _project_counts(weights, budget)
        funded = float(counts.sum() * TICKET_STAKE)
        if not np.isfinite(funded) or funded < 0:
            raise Stage4Error("negative or non-finite funded stake")
        pre_tax_multiples = bundle.pre_tax_gross_multiple.to_numpy(dtype=float)
        tax_adjusted_multiples = bundle.tax_adjusted_gross_multiple.to_numpy(dtype=float)
        payout = float(np.sum(counts * TICKET_STAKE * pre_tax_multiples))
        tax_adjusted_payout = float(np.sum(counts * TICKET_STAKE * tax_adjusted_multiples))
        if not np.isfinite(payout) or not np.isfinite(tax_adjusted_payout):
            raise Stage4Error("non-finite payout")
        bankroll = pre - funded + payout
        if funded < -1e-9 or funded > pre + 1e-9 or bankroll < -1e-9:
            raise Stage4Error("bankroll conservation/funding violation")
        peak = max(peak, bankroll)
        trace = [
            {
                "rank": int(rank),
                "ticket_identity": identity,
                "weight": float(weight),
                "repeat_count": int(count),
                "funded_stake_yuan": float(count * TICKET_STAKE),
                "pre_tax_gross_multiple": float(pre_tax_gross),
                "tax_adjusted_gross_multiple": float(tax_adjusted_gross),
            }
            for rank, identity, weight, count, pre_tax_gross, tax_adjusted_gross in zip(
                bundle["rank"],
                bundle.ticket_identity,
                weights,
                counts,
                bundle.pre_tax_gross_multiple,
                bundle.tax_adjusted_gross_multiple,
                strict=True,
            )
        ]
        rows.append(
            {
                "split": split,
                "year": int(bundle.year.iloc[0]),
                "issue": str(issue),
                "policy": policy,
                "k": int(k),
                "panel_role": "CONTROLLING" if k == CONTROLLING_K else "SENSITIVITY_ONLY",
                "controller": method,
                "controller_family": _method_family(method),
                "experiment_role": _experiment_role(method),
                "risk_fraction": np.nan if fraction is None else fraction,
                "pre_issue_bankroll_yuan": pre,
                "requested_stake_yuan": requested,
                "funded_stake_yuan": funded,
                "projection_residual_yuan": residual,
                "retained_cash_yuan": pre - funded,
                "gross_payout_yuan": payout,
                "tax_adjusted_reference_payout_yuan": tax_adjusted_payout,
                "net_pnl_yuan": payout - funded,
                "post_issue_bankroll_yuan": bankroll,
                "running_peak_yuan": peak,
                "drawdown_yuan": peak - bankroll,
                "drawdown_pct": 0.0 if peak == 0 else (peak - bankroll) / peak,
                "active": funded > 0,
                "unfunded_reason": "NONE" if funded > 0 else "BANKROLL_LT_NATIVE_TICKET",
                "minimum_fundable_capital_yuan": TICKET_STAKE,
                "ticket_count": int(counts.sum()),
                "ticket_hhi": float(np.sum((counts / counts.sum()) ** 2)) if counts.sum() else 0.0,
                "mean_pairwise_match_overlap": _mean_overlap(bundle),
                "decision_trace_json": json.dumps(trace, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
                "reason_code": "FUNDED_ACTIVE" if funded > 0 else "NO_BET_INSUFFICIENT_CAPITAL",
                "funding_schedule_source": "MATCHED_COMPARATOR_REPLAY" if funding_schedule is not None else "SELF_FUNDED_REPLAY",
            }
        )
    result = pd.DataFrame(rows)
    result["capital_schedule_hash"] = _canonical_hash(
        result.loc[:, ["issue", "funded_stake_yuan"]].to_dict(orient="records")
    )
    return result


def _mean_overlap(bundle: pd.DataFrame) -> float:
    sets = [set(map(int, value.split("|"))) for value in bundle.match_indices]
    if len(sets) < 2:
        return 0.0
    values = [len(sets[left] & sets[right]) / N for left in range(len(sets)) for right in range(left + 1, len(sets))]
    return float(np.mean(values))


def _calibrate_risk(
    requests: pd.DataFrame, controllers: dict[str, Any]
) -> tuple[dict[str, float], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    calibrated: dict[str, float] = {}
    for method in controllers:
        for fraction in RISK_GRID:
            temporary = {method: fraction}
            endings = []
            drawdowns = []
            for policy in POLICIES:
                path = replay_path(
                    requests,
                    split="CV_2022",
                    policy=policy,
                    k=CONTROLLING_K,
                    method=method,
                    controllers=controllers,
                    calibrated=temporary,
                )
                endings.append(float(path.post_issue_bankroll_yuan.iloc[-1]))
                drawdowns.append(float(path.drawdown_pct.max()))
            rows.append(
                {
                    "controller": method,
                    "risk_fraction": fraction,
                    "mean_ending_capital_yuan": float(np.mean(endings)),
                    "worst_max_drawdown_pct": float(np.max(drawdowns)),
                    "selection_split": "CV_2022",
                }
            )
        choices = pd.DataFrame([row for row in rows if row["controller"] == method]).sort_values(
            ["mean_ending_capital_yuan", "worst_max_drawdown_pct", "risk_fraction"],
            ascending=[False, True, True],
            kind="stable",
        )
        calibrated[method] = float(choices.risk_fraction.iloc[0])
    surface = pd.DataFrame(rows)
    surface["selected"] = surface.apply(
        lambda row: bool(np.isclose(row.risk_fraction, calibrated[row.controller])), axis=1
    )
    return calibrated, surface


def _trace_frame(ledger: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    base = [
        "split",
        "policy",
        "k",
        "controller",
        "year",
        "issue",
        "controller_family",
        "experiment_role",
        "risk_fraction",
        "pre_issue_bankroll_yuan",
        "funded_stake_yuan",
        "capital_schedule_hash",
    ]
    for row in ledger.loc[:, base + ["decision_trace_json"]].itertuples(index=False):
        for trace in json.loads(row.decision_trace_json):
            rows.append(
                {
                    "split": row.split,
                    "policy": row.policy,
                    "k": int(row.k),
                    "controller": row.controller,
                    "year": int(row.year),
                    "issue": str(row.issue),
                    "controller_family": row.controller_family,
                    "experiment_role": row.experiment_role,
                    "risk_fraction": row.risk_fraction,
                    "pre_issue_bankroll_yuan": float(row.pre_issue_bankroll_yuan),
                    "issue_funded_stake_yuan": float(row.funded_stake_yuan),
                    "capital_schedule_hash": row.capital_schedule_hash,
                    "rank": int(trace["rank"]),
                    "ticket_identity": str(trace["ticket_identity"]),
                    "weight": float(trace["weight"]),
                    "repeat_count": int(trace["repeat_count"]),
                    "tax_lot_count": int(trace["repeat_count"]),
                    "funded_stake_yuan": float(trace["funded_stake_yuan"]),
                    "pre_tax_gross_multiple": float(trace["pre_tax_gross_multiple"]),
                    "tax_adjusted_gross_multiple": float(trace["tax_adjusted_gross_multiple"]),
                }
            )
    return pd.DataFrame(rows)


def _recovery_summary(path: pd.DataFrame) -> dict[str, int]:
    longest_completed = 0
    completed = 0
    open_terminal = 0
    current = 0
    underwater = path.post_issue_bankroll_yuan.lt(path.running_peak_yuan).tolist()
    for active in underwater:
        if active:
            current += 1
            continue
        if current:
            completed += 1
            longest_completed = max(longest_completed, current)
            current = 0
    if current:
        open_terminal = current
    return {
        "completed_recovery_episodes": completed,
        "max_completed_recovery_issues": longest_completed,
        "terminal_open_underwater_issues": open_terminal,
    }


def _rolling_window_rows(path: pd.DataFrame, keys: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordered = path.sort_values(["year", "issue"], kind="stable").reset_index(drop=True)
    anchors = pd.DataFrame(
        [
            {
                "issue": "TIME_ZERO_100K",
                "year": 0,
                "post_issue_bankroll_yuan": INITIAL_BANKROLL,
                "drawdown_pct": 0.0,
                "active": False,
            }
        ]
    )
    capital = pd.concat([anchors, ordered.loc[:, ["issue", "year", "post_issue_bankroll_yuan", "drawdown_pct", "active"]]], ignore_index=True)
    for window in (5, 10, 20):
        if len(capital) <= window:
            rows.append(
                {
                    **keys,
                    "window_issues": window,
                    "start_issue": "TIME_ZERO_100K",
                    "end_issue": None,
                    "observation_index": 0,
                    "start_bankroll_yuan": INITIAL_BANKROLL,
                    "end_bankroll_yuan": np.nan,
                    "window_return": np.nan,
                    "window_pnl_yuan": np.nan,
                    "window_loss": np.nan,
                    "window_max_drawdown_pct": np.nan,
                    "active_issues_in_window": 0,
                    "time_zero_anchor": True,
                }
            )
            continue
        for end in range(window, len(capital)):
            start = end - window
            start_capital = float(capital.loc[start, "post_issue_bankroll_yuan"])
            end_capital = float(capital.loc[end, "post_issue_bankroll_yuan"])
            window_slice = ordered.iloc[start:end]
            # Compute holding-period drawdown locally. Seed the window peak with
            # capital immediately before its first issue; full-path running
            # peaks must not contaminate this metric.
            local_capital = np.concatenate(
                ([start_capital], window_slice.post_issue_bankroll_yuan.to_numpy(dtype=float))
            )
            local_peak = np.maximum.accumulate(local_capital)
            local_drawdown = np.divide(
                local_peak - local_capital,
                local_peak,
                out=np.zeros_like(local_capital),
                where=local_peak > 0,
            )
            rows.append(
                {
                    **keys,
                    "window_issues": window,
                    "start_issue": str(capital.loc[start, "issue"]),
                    "end_issue": str(capital.loc[end, "issue"]),
                    "observation_index": int(end - window + 1),
                    "start_bankroll_yuan": start_capital,
                    "end_bankroll_yuan": end_capital,
                    "window_return": (end_capital / start_capital - 1.0) if start_capital > 0 else np.nan,
                    "window_pnl_yuan": end_capital - start_capital,
                    "window_loss": bool(end_capital < start_capital),
                    "window_max_drawdown_pct": float(local_drawdown.max()),
                    "active_issues_in_window": int(window_slice.active.sum()) if not window_slice.empty else 0,
                    "time_zero_anchor": start == 0,
                }
            )
    return rows


def _path_metrics(ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["split", "policy", "k", "controller"]
    ticket_trace = _trace_frame(ledger)
    summaries: list[dict[str, Any]] = []
    rolling: list[dict[str, Any]] = []
    for identity, path in ledger.groupby(keys, sort=False):
        path = path.sort_values(["year", "issue"], kind="stable")
        pnl = path.net_pnl_yuan.to_numpy(dtype=float)
        losses = pnl < 0
        streak = current = 0
        for loss in losses:
            current = current + 1 if loss else 0
            streak = max(streak, current)
        stake = path.funded_stake_yuan.to_numpy(dtype=float)
        stake_share = stake / stake.sum() if stake.sum() else np.zeros(len(stake))
        largest = int(np.argmax(pnl)) if len(pnl) else 0
        ticket_slice = ticket_trace.loc[
            ticket_trace.split.eq(identity[0])
            & ticket_trace.policy.eq(identity[1])
            & ticket_trace.k.eq(identity[2])
            & ticket_trace.controller.eq(identity[3])
        ].copy()
        by_ticket = ticket_slice.groupby("ticket_identity", sort=False).funded_stake_yuan.sum()
        ticket_share = by_ticket / by_ticket.sum() if by_ticket.sum() else np.zeros(len(by_ticket))
        recovery = _recovery_summary(path)
        summaries.append(
            {
                **dict(zip(keys, identity, strict=True)),
                "issues": len(path),
                "active_issues": int(path.active.sum()),
                "ending_capital_yuan": float(path.post_issue_bankroll_yuan.iloc[-1]),
                "capital_growth_yuan": float(path.post_issue_bankroll_yuan.iloc[-1] - INITIAL_BANKROLL),
                "capital_growth_pct": float(path.post_issue_bankroll_yuan.iloc[-1] / INITIAL_BANKROLL - 1),
                "turnover_yuan": float(stake.sum()),
                "active_support_roi": float(pnl.sum() / stake.sum()) if stake.sum() else np.nan,
                "max_drawdown_yuan": float(path.drawdown_yuan.max()),
                "max_drawdown_pct": float(path.drawdown_pct.max()),
                "max_consecutive_losing_issues": streak,
                "time_under_water_issues": int((path.post_issue_bankroll_yuan < path.running_peak_yuan).sum()),
                **recovery,
                "ruin": bool(path.post_issue_bankroll_yuan.le(0).any()),
                "near_ruin": bool(path.post_issue_bankroll_yuan.le(INITIAL_BANKROLL * 0.05).any()),
                "minimum_capital_yuan": float(path.post_issue_bankroll_yuan.min()),
                "issue_stake_hhi": float(np.sum(stake_share**2)),
                "mean_issue_ticket_hhi": float(path.ticket_hhi.mean()),
                "ticket_identity_stake_hhi": float(np.sum(ticket_share**2)) if len(ticket_share) else 0.0,
                "mean_overlap": float(path.mean_pairwise_match_overlap.mean()),
                "ex_largest_issue_ending_capital_yuan": float(INITIAL_BANKROLL + pnl.sum() - pnl[largest]),
                "capital_schedule_hash": str(path.capital_schedule_hash.iloc[0]),
            }
        )
        rolling.extend(_rolling_window_rows(path, dict(zip(keys, identity, strict=True))))
    return pd.DataFrame(summaries), pd.DataFrame(rolling)


def _matched_reference(
    candidate: Any,
    *,
    reference_policy: str,
    reference_controller: str,
    ledger: pd.DataFrame,
    requests: pd.DataFrame,
    controllers: dict[str, Any],
    calibrated: dict[str, float],
    split: str,
) -> tuple[pd.Series | None, pd.DataFrame | None]:
    candidate_path = ledger.loc[
        ledger.split.eq(split)
        & ledger.policy.eq(candidate.policy)
        & ledger.k.eq(candidate.k)
        & ledger.controller.eq(candidate.controller)
    ].copy()
    schedule = dict(
        zip(
            candidate_path.issue.astype(str),
            candidate_path.funded_stake_yuan.astype(float),
            strict=True,
        )
    )
    try:
        reference = replay_path(
            requests,
            split=split,
            policy=reference_policy,
            k=int(candidate.k),
            method=reference_controller,
            controllers=controllers,
            calibrated=calibrated,
            funding_schedule=schedule,
        )
    except Stage4Error as exc:
        if "NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE" in str(exc):
            return None, None
        raise
    reference_metrics, _ = _path_metrics(reference)
    return reference_metrics.iloc[0], reference


def _comparison_row(
    candidate: Any,
    reference: pd.Series | None,
    *,
    role: str,
    reference_label: str,
    attribution: str,
    frozen_choice: str,
    terminal_evidentiary: bool,
) -> dict[str, Any]:
    identified = reference is not None
    return {
        "comparison_role": role,
        "split": candidate.split,
        "policy": candidate.policy,
        "k": candidate.k,
        "candidate_controller": candidate.controller,
        "comparator_controller": reference_label,
        "candidate_ending_capital_yuan": candidate.ending_capital_yuan,
        "comparator_ending_capital_yuan": np.nan if reference is None else float(reference.ending_capital_yuan),
        "matched_lift_ending_capital_yuan": np.nan if reference is None else candidate.ending_capital_yuan - float(reference.ending_capital_yuan),
        "candidate_max_drawdown_pct": candidate.max_drawdown_pct,
        "comparator_max_drawdown_pct": np.nan if reference is None else float(reference.max_drawdown_pct),
        "matched_lift_max_drawdown_pct": np.nan if reference is None else float(reference.max_drawdown_pct) - candidate.max_drawdown_pct,
        "candidate_turnover_yuan": candidate.turnover_yuan,
        "comparator_turnover_yuan": np.nan if reference is None else float(reference.turnover_yuan),
        "capital_schedule_hash": candidate.capital_schedule_hash,
        "comparator_schedule_hash": None if reference is None else reference.capital_schedule_hash,
        "equal_capital_schedule": identified and str(candidate.capital_schedule_hash) == str(reference.capital_schedule_hash),
        "identifiability": "IDENTIFIED_MATCHED_ACTIVE_FUNDING" if identified else "NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE",
        "attribution": attribution if identified else "NOT_IDENTIFIABLE",
        "frozen_learned_controller_choice": frozen_choice,
        "terminal_evidentiary": bool(terminal_evidentiary),
    }


def _freeze_learned_controller_choice(
    metrics: pd.DataFrame,
    ledger: pd.DataFrame,
    requests: pd.DataFrame,
    controllers: dict[str, Any],
    calibrated: dict[str, float],
) -> tuple[str, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    cv2022 = metrics.loc[
        metrics.split.eq("CV_2022")
        & metrics.k.eq(CONTROLLING_K)
        & metrics.controller.isin(LEARNED_METHODS)
    ].copy()
    for row in cv2022.itertuples(index=False):
        comparator = {
            0.01: "EQUAL_1PCT",
            0.05: "EQUAL_5PCT",
            0.25: "EQUAL_25PCT",
            1.0: "EQUAL_100PCT",
        }[float(row.risk_fraction)]
        reference, _ = _matched_reference(
            row,
            reference_policy=row.policy,
            reference_controller=comparator,
            ledger=ledger,
            requests=requests,
            controllers=controllers,
            calibrated=calibrated,
            split="CV_2022",
        )
        rows.append(
            {
                "split": "CV_2022",
                "policy": row.policy,
                "k": int(row.k),
                "controller": row.controller,
                "risk_fraction": float(row.risk_fraction),
                "equal_funding_comparator": comparator,
                "ending_capital_yuan": float(row.ending_capital_yuan),
                "max_drawdown_pct": float(row.max_drawdown_pct),
                "matched_lift_ending_capital_yuan": np.nan if reference is None else float(row.ending_capital_yuan - reference.ending_capital_yuan),
                "matched_lift_max_drawdown_pct": np.nan if reference is None else float(reference.max_drawdown_pct - row.max_drawdown_pct),
                "identifiability": "IDENTIFIED_MATCHED_ACTIVE_FUNDING" if reference is not None else "NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE",
            }
        )
    freeze = pd.DataFrame(rows).sort_values(
        ["matched_lift_ending_capital_yuan", "matched_lift_max_drawdown_pct", "ending_capital_yuan", "max_drawdown_pct", "controller", "policy"],
        ascending=[False, False, False, True, True, True],
        kind="stable",
    )
    chosen = str(freeze.controller.iloc[0])
    freeze["selected_terminal_controller"] = freeze.controller.eq(chosen)
    freeze["selection_split"] = "CV_2022"
    freeze["terminal_evaluation_split"] = "CV_2023"
    freeze["choice_rule"] = "select learned controller on CV_2022 only; prefer larger matched ending-capital lift, then non-worse matched drawdown lift, then higher ending capital, then lower drawdown"
    return chosen, freeze


def _matched_comparisons(
    metrics: pd.DataFrame,
    ledger: pd.DataFrame,
    requests: pd.DataFrame,
    controllers: dict[str, Any],
    calibrated: dict[str, float],
    *,
    frozen_learned_choice: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    test = metrics.loc[metrics.split.eq("CV_2023")].copy()
    equal_by_fraction = {
        0.01: "EQUAL_1PCT",
        0.05: "EQUAL_5PCT",
        0.25: "EQUAL_25PCT",
        1.0: "EQUAL_100PCT",
    }
    rows: list[dict[str, Any]] = []
    issue_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    for row in test.itertuples(index=False):
        if row.controller in {"NATIVE_2_YUAN"} or str(row.controller).startswith("EQUAL_"):
            continue
        comparator = "EQUAL_5PCT" if row.controller == "SCORE_WEIGHTED_5PCT" else equal_by_fraction[float(row.risk_fraction)]
        reference, reference_ledger = _matched_reference(
            row,
            reference_policy=row.policy,
            reference_controller=comparator,
            ledger=ledger,
            requests=requests,
            controllers=controllers,
            calibrated=calibrated,
            split="CV_2023",
        )
        terminal_evidentiary = row.controller not in LEARNED_METHODS or row.controller == frozen_learned_choice
        rows.append(_comparison_row(row, reference, role="EQUAL_FUNDING_CONTROL", reference_label=comparator, attribution="STAGE4_WITHIN_ISSUE_ALLOCATION", frozen_choice=frozen_learned_choice, terminal_evidentiary=terminal_evidentiary))
        if reference is not None:
            candidate_path = ledger.loc[
                ledger.split.eq("CV_2023")
                & ledger.policy.eq(row.policy)
                & ledger.k.eq(row.k)
                & ledger.controller.eq(row.controller)
            ].sort_values(["year", "issue"], kind="stable")
            joined = candidate_path.merge(
                reference_ledger.sort_values(["year", "issue"], kind="stable"),
                on=["split", "year", "issue"],
                how="inner",
                suffixes=("_candidate", "_comparator"),
            )
            for issue_row in joined.itertuples(index=False):
                issue_rows.append(
                    {
                        "comparison_role": "EQUAL_FUNDING_CONTROL",
                        "split": issue_row.split,
                        "policy": row.policy,
                        "k": int(row.k),
                        "candidate_controller": row.controller,
                        "comparator_controller": comparator,
                        "issue": str(issue_row.issue),
                        "candidate_funded_stake_yuan": float(issue_row.funded_stake_yuan_candidate),
                        "comparator_funded_stake_yuan": float(issue_row.funded_stake_yuan_comparator),
                        "candidate_gross_payout_yuan": float(issue_row.gross_payout_yuan_candidate),
                        "comparator_gross_payout_yuan": float(issue_row.gross_payout_yuan_comparator),
                        "candidate_post_issue_bankroll_yuan": float(issue_row.post_issue_bankroll_yuan_candidate),
                        "comparator_post_issue_bankroll_yuan": float(issue_row.post_issue_bankroll_yuan_comparator),
                        "candidate_ticket_count": int(issue_row.ticket_count_candidate),
                        "comparator_ticket_count": int(issue_row.ticket_count_comparator),
                        "candidate_schedule_hash": issue_row.capital_schedule_hash_candidate,
                        "comparator_schedule_hash": issue_row.capital_schedule_hash_comparator,
                        "matched_issue_bankroll_lift_yuan": float(issue_row.post_issue_bankroll_yuan_candidate - issue_row.post_issue_bankroll_yuan_comparator),
                        "matched_issue_payout_lift_yuan": float(issue_row.gross_payout_yuan_candidate - issue_row.gross_payout_yuan_comparator),
                        "terminal_evidentiary": terminal_evidentiary,
                        "frozen_learned_controller_choice": frozen_learned_choice,
                    }
                )
            candidate_tickets = _trace_frame(candidate_path)
            comparator_tickets = _trace_frame(reference_ledger)
            ticket_rows.extend(
                candidate_tickets.assign(
                    comparison_role="EQUAL_FUNDING_CONTROL",
                    candidate_controller=row.controller,
                    comparator_controller=comparator,
                    side="CANDIDATE",
                    terminal_evidentiary=terminal_evidentiary,
                    frozen_learned_controller_choice=frozen_learned_choice,
                ).to_dict(orient="records")
            )
            ticket_rows.extend(
                comparator_tickets.assign(
                    comparison_role="EQUAL_FUNDING_CONTROL",
                    candidate_controller=row.controller,
                    comparator_controller=comparator,
                    side="COMPARATOR",
                    terminal_evidentiary=terminal_evidentiary,
                    frozen_learned_controller_choice=frozen_learned_choice,
                ).to_dict(orient="records")
            )
    # Cross-policy MARKET_WR/K8 reference on the same controller and executable
    # issue-level schedule. Ticket identities stay distinct and source-bound.
    for row in test.loc[test.k.eq(CONTROLLING_K)].itertuples(index=False):
        if row.policy == "MARKET_WR":
            continue
        reference, _ = _matched_reference(
            row,
            reference_policy="MARKET_WR",
            reference_controller=row.controller,
            ledger=ledger,
            requests=requests,
            controllers=controllers,
            calibrated=calibrated,
            split="CV_2023",
        )
        rows.append(_comparison_row(row, reference, role="MARKET_WR_K8_REFERENCE", reference_label=f"MARKET_WR/{row.controller}", attribution="STAGE3_TICKET_POLICY_EFFECT_WITH_STAGE4_HELD", frozen_choice=frozen_learned_choice, terminal_evidentiary=(row.controller not in LEARNED_METHODS or row.controller == frozen_learned_choice)))
    # The score-weighted active component is reported even when the learned
    # controller selected a different CV-2022 risk fraction; that case is
    # explicitly non-identifiable rather than a fabricated zero effect.
    for row in test.loc[
        test.k.eq(CONTROLLING_K)
        & test.controller.isin(["SIMPLE_LOGISTIC", "BOUNDED_NEURAL"])
    ].itertuples(index=False):
        reference, _ = _matched_reference(
            row,
            reference_policy=row.policy,
            reference_controller="SCORE_WEIGHTED_5PCT",
            ledger=ledger,
            requests=requests,
            controllers=controllers,
            calibrated=calibrated,
            split="CV_2023",
        )
        rows.append(_comparison_row(row, reference, role="STRONGEST_ACTIVE_COMPONENT_SCORE_WEIGHTED", reference_label="SCORE_WEIGHTED_5PCT", attribution="STAGE4_CONTROLLER_VS_SCORE_WEIGHTED", frozen_choice=frozen_learned_choice, terminal_evidentiary=(row.controller == frozen_learned_choice)))
    return pd.DataFrame(rows), pd.DataFrame(issue_rows), pd.DataFrame(ticket_rows)


def _safe_ledger(source: Path) -> pd.DataFrame:
    gate = pd.read_csv(source / "issue_gate.csv", dtype={"issue": str})
    if not gate.fallback_mixed_path.eq("NO_BET").all():
        raise Stage4Error("#206 safe lane is no longer exact NO_BET")
    rows: list[dict[str, Any]] = []
    for row in gate.itertuples(index=False):
        for reference in ("SAFE_FALLBACK_MIXED", "CASH"):
            rows.append(
                {
                    "split": row.split,
                    "issue": row.issue,
                    "year": row.year,
                    "reference": reference,
                    "experiment_role": reference,
                    "requested_stake_yuan": 0.0,
                    "funded_stake_yuan": 0.0,
                    "retained_cash_yuan": INITIAL_BANKROLL,
                    "reason_code": row.fallback_reason if reference == "SAFE_FALLBACK_MIXED" else "PURE_CASH_REFERENCE",
                    "attribution": "LOWER_EXPOSURE_ONLY",
                    "research_only": True,
                    "promoted": False,
                }
            )
    return pd.DataFrame(rows)


def _decision(metrics: pd.DataFrame, matched: pd.DataFrame, *, frozen_learned_choice: str) -> dict[str, Any]:
    controlling = matched.loc[
        matched.k.eq(CONTROLLING_K)
        & matched.equal_capital_schedule
        & matched.comparison_role.eq("EQUAL_FUNDING_CONTROL")
    ]
    candidates = controlling.loc[
        controlling.candidate_controller.eq(frozen_learned_choice)
        & controlling.terminal_evidentiary.astype(bool)
    ]
    evidence_rows = candidates.loc[
        (candidates.matched_lift_ending_capital_yuan > 0)
        & (candidates.matched_lift_max_drawdown_pct >= 0)
    ]
    return {
        "version": VERSION,
        "ENGINE_VALID": True,
        "ACTIVE_OVERLAY_EVIDENCE": not evidence_rows.empty,
        "DEPLOYABLE_POLICY": False,
        "active_overlay_evidence_rule": "matched K8 active funding; positive ending-capital lift and non-worse max drawdown versus equal-funding control",
        "qualifying_active_rows": int(len(evidence_rows)),
        "deployable_policy_reason": "NO_COMPARABLE_ACCEPTED_STAGE3_TICKET_BASELINE_AND_HISTORICAL_CONFIRMATION_ONLY",
        "safe_reference_interpretation": "NO_BET/cash are LOWER_EXPOSURE_ONLY and excluded from active lift",
        "controlling_k": CONTROLLING_K,
        "sensitivity_k": [16, 32],
        "selection_split": "CV_2022",
        "terminal_historical_evaluation_split": "CV_2023",
        "frozen_learned_controller_choice": frozen_learned_choice,
        "terminal_evidentiary_rows_rule": "only the CV_2022-frozen learned controller may establish terminal CV_2023 active overlay evidence",
        "locked_test_boundary": "2025/2026 outcomes and official-final-SP labels unused",
        "negative_freeze": "NATIVE_2_YUAN" if evidence_rows.empty else None,
        "next_issue": "#208 receives schema/evidence only; remains blocked pending PI activation",
    }


def _assert_semantic_frame(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> None:
    try:
        pd.testing.assert_frame_equal(
            actual.reset_index(drop=True),
            expected.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-9,
        )
    except AssertionError as exc:
        raise Stage4Error(f"{label} semantic replay mismatch: {exc}") from exc


def _json_equal(output: Path, name: str, expected: Any) -> None:
    actual = json.loads((output / name).read_text(encoding="utf-8"))
    if actual != expected:
        raise Stage4Error(f"{name} semantic mismatch")


def _schema_catalog(
    requests: pd.DataFrame,
    safe: pd.DataFrame,
    ledger: pd.DataFrame,
    metrics: pd.DataFrame,
    rolling: pd.DataFrame,
    matched: pd.DataFrame,
    matched_issue: pd.DataFrame,
    matched_ticket: pd.DataFrame,
    attribution: pd.DataFrame,
    calibration: pd.DataFrame,
    freeze_choice: pd.DataFrame,
) -> dict[str, Any]:
    def table(df: pd.DataFrame, *, name: str, pk: list[str], fk: list[dict[str, Any]] | None = None, relationships: list[str] | None = None, units: dict[str, str] | None = None, domains: dict[str, list[Any] | str] | None = None) -> dict[str, Any]:
        missing = sorted(set(pk) - set(df.columns))
        if missing:
            raise Stage4Error(f"schema primary key columns missing for {name}: {missing}")
        if df.duplicated(pk, keep=False).any():
            raise Stage4Error(f"schema primary key is not unique for {name}")
        columns = []
        for column in df.columns:
            columns.append(
                {
                    "name": column,
                    "dtype": str(df[column].dtype),
                    "nullable": bool(df[column].isna().any()),
                    "unit": None if units is None else units.get(column),
                    "domain": None if domains is None else domains.get(column),
                }
            )
        return {
            "name": name,
            "primary_key": pk,
            "foreign_keys": fk or [],
            "relationships": relationships or [],
            "columns": columns,
        }

    common_units = {
        "risk_fraction": "fraction",
        "funded_stake_yuan": "yuan",
        "requested_stake_yuan": "yuan",
        "retained_cash_yuan": "yuan",
        "gross_payout_yuan": "yuan",
        "tax_adjusted_reference_payout_yuan": "yuan",
        "net_pnl_yuan": "yuan",
        "post_issue_bankroll_yuan": "yuan",
        "pre_issue_bankroll_yuan": "yuan",
        "running_peak_yuan": "yuan",
        "drawdown_yuan": "yuan",
        "drawdown_pct": "fraction",
        "ending_capital_yuan": "yuan",
        "capital_growth_yuan": "yuan",
        "capital_growth_pct": "fraction",
        "turnover_yuan": "yuan",
        "active_support_roi": "fraction",
        "matched_lift_ending_capital_yuan": "yuan",
        "matched_lift_max_drawdown_pct": "fraction",
        "window_return": "fraction",
        "window_pnl_yuan": "yuan",
        "start_bankroll_yuan": "yuan",
        "end_bankroll_yuan": "yuan",
        "ticket_identity_stake_hhi": "fraction",
        "issue_stake_hhi": "fraction",
        "mean_issue_ticket_hhi": "fraction",
        "ticket_hhi": "fraction",
    }
    return {
        "version": VERSION,
        "primary_economics": "PRE_TAX",
        "reference_economics": "TAX_ADJUSTED_0.65_REFERENCE_ONLY",
        "tables": [
            table(requests, name="active_research_ticket_requests.parquet", pk=["split", "issue", "policy", "k", "rank"], relationships=["one source ticket row per frozen #206 request"], domains={"panel_role": ["CONTROLLING", "SENSITIVITY_ONLY"]}),
            table(safe, name="safe_reference_ledger.csv", pk=["split", "issue", "reference"], relationships=["separate lower-exposure lane; never active evidence"], domains={"experiment_role": ["SAFE_FALLBACK_MIXED", "CASH"]}, units=common_units),
            table(ledger, name="issue_capital_ledger.parquet", pk=["split", "policy", "k", "controller", "issue"], relationships=["one bankroll replay row per issue"], units=common_units),
            table(metrics, name="capital_summary.csv", pk=["split", "policy", "k", "controller"], relationships=["path-level summary derived from issue_capital_ledger"], units=common_units),
            table(rolling, name="rolling_window_metrics.csv", pk=["split", "policy", "k", "controller", "window_issues", "observation_index"], relationships=["anchored rolling windows derived from issue_capital_ledger"], units=common_units),
            table(matched, name="matched_comparisons.csv", pk=["comparison_role", "split", "policy", "k", "candidate_controller", "comparator_controller"], relationships=["decisive matched comparator summary"], units=common_units),
            table(matched_issue, name="matched_comparator_issue_ledger.parquet", pk=["comparison_role", "split", "policy", "k", "candidate_controller", "comparator_controller", "issue"], relationships=["issue-by-issue replay for matched comparisons"], units=common_units),
            table(matched_ticket, name="matched_ticket_tax_lot_ledger.parquet", pk=["comparison_role", "side", "split", "policy", "k", "candidate_controller", "comparator_controller", "controller", "issue", "rank"], relationships=["ticket/tax-lot replay for matched comparisons"], units=common_units),
            table(attribution, name="attribution.csv", pk=["comparison_role", "split", "policy", "k", "candidate_controller", "comparator_controller"], relationships=["human-readable attribution ledger"], units=common_units),
            table(calibration, name="controller_calibration.csv", pk=["controller", "risk_fraction"], relationships=["CV_2022 risk-freeze surface"], units=common_units),
            table(freeze_choice, name="frozen_learned_controller_choice.csv", pk=["split", "policy", "k", "controller"], relationships=["CV_2022-only learned controller freeze"], units=common_units),
        ],
        "forbidden": ["change_n", "change_ticket_identity", "change_policy_or_k", "read_locked_test_labels", "terminal_model_choice_from_cv2023"],
    }


def _plots(ledger: pd.DataFrame, metrics: pd.DataFrame, calibration: pd.DataFrame, output: Path) -> None:
    chosen = ledger.loc[
        ledger.split.eq("CV_2023") & ledger.k.eq(CONTROLLING_K) & ledger.policy.eq("MARKET_WR")
    ]
    fig, ax = plt.subplots(figsize=(10, 5))
    for controller, group in chosen.groupby("controller", sort=False):
        ax.plot(np.arange(len(group)), group.post_issue_bankroll_yuan, label=controller)
    ax.axhline(INITIAL_BANKROLL, color="black", linewidth=0.8)
    ax.set(title="CV-2023 MARKET_WR/K8 active equity", xlabel="issue order", ylabel="bankroll (yuan)")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(output / "equity_paths.png", dpi=160)
    plt.close(fig)

    test = metrics.loc[metrics.split.eq("CV_2023") & metrics.k.eq(CONTROLLING_K)]
    fig, ax = plt.subplots(figsize=(8, 5))
    for controller, group in test.groupby("controller", sort=False):
        ax.scatter(group.max_drawdown_pct, group.capital_growth_pct, label=controller)
    ax.set(title="K8 risk-return frontier", xlabel="maximum drawdown", ylabel="capital growth")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "risk_return_frontier.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for controller, group in calibration.groupby("controller", sort=False):
        ax.plot(group.risk_fraction, group.mean_ending_capital_yuan, marker="o", label=controller)
    ax.set_xscale("log")
    ax.set(title="CV-2022 frozen controller risk calibration", xlabel="risk fraction", ylabel="mean ending capital")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "parameter_performance.png", dpi=160)
    plt.close(fig)


def _report(decision: dict[str, Any], metrics: pd.DataFrame, matched: pd.DataFrame) -> str:
    controlling = metrics.loc[metrics.split.eq("CV_2023") & metrics.k.eq(CONTROLLING_K)]
    best = controlling.sort_values("ending_capital_yuan", ascending=False, kind="stable").iloc[0]
    evidentiary = matched.loc[
        matched.comparison_role.eq("EQUAL_FUNDING_CONTROL")
        & matched.candidate_controller.eq(decision["frozen_learned_controller_choice"])
        & matched.terminal_evidentiary.astype(bool)
    ].sort_values(
        ["matched_lift_ending_capital_yuan", "matched_lift_max_drawdown_pct"],
        ascending=[False, False],
        kind="stable",
    )
    evidentiary_text = "No positive terminal row qualified."
    if not evidentiary.empty:
        top = evidentiary.iloc[0]
        evidentiary_text = (
            f"Frozen learned controller `{decision['frozen_learned_controller_choice']}` on `{top.policy}/K{int(top.k)}` "
            f"had matched ending-capital lift ¥{float(top.matched_lift_ending_capital_yuan):,.2f} and "
            f"matched drawdown lift {float(top.matched_lift_max_drawdown_pct):.4%} versus `{top.comparator_controller}`."
        )
    return f"""# Issue #207 decision report — active fixed-N7 bankroll allocation

## Terminal decisions

- `ENGINE_VALID={str(decision['ENGINE_VALID']).lower()}`: exact ¥2 projection, no-top-up conservation, chronology, source binding and replay checks pass.
- `ACTIVE_OVERLAY_EVIDENCE={str(decision['ACTIVE_OVERLAY_EVIDENCE']).lower()}` under the preregistered matched-active rule. Qualifying K8 rows: {decision['qualifying_active_rows']}.
- `DEPLOYABLE_POLICY=false`: no comparable accepted Stage-3 ticket baseline is bound and this is retrospective CV-2023 evidence only.
- Learned-controller freeze: `{decision['frozen_learned_controller_choice']}` was selected on CV-2022 only and is the only terminal-evidentiary learned controller on CV-2023.

The strongest absolute K8 row was `{best.policy}/{best.controller}` with ending capital ¥{best.ending_capital_yuan:,.2f}, growth {best.capital_growth_pct:.2%}, turnover ¥{best.turnover_yuan:,.2f}, active-support ROI {best.active_support_roi:.2%}, and maximum drawdown {best.max_drawdown_pct:.2%}. Absolute performance is not treated as lift: `matched_comparisons.csv` is controlling and compares each allocator to equal weights on identical issue/ticket support and an identical executable yuan schedule.
{evidentiary_text}

## Attribution and failure regimes

Ticket identity is frozen by the exact #206 selector. Stage 4 changes only issue risk fraction and non-negative ticket repeat counts. Within-issue reweighting is identified only where `capital_schedule_hash` matches. Any no-common-schedule row is `NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE`, never a zero effect. #206 fallback-mixed NO_BET and cash are a separate SAFE lane and are always `LOWER_EXPOSURE_ONLY`; they cannot establish Edge. Sparse N7 hits, integer residuals below ¥2, bankroll depletion, candidate overlap, retrospective calibration and the unresolved Stage-3 baseline remain material risks.

Primary bankroll accounting is pre-tax. The upstream #206 `realized_gross` is the frozen 0.65-adjusted reference multiple, so Stage 4 preserves it as `tax_adjusted_gross_multiple` and derives `pre_tax_gross_multiple = realized_gross / 0.65`. `gross_payout_yuan`, net PnL, equity, risk metrics and matched lift use only the pre-tax field; `tax_adjusted_reference_payout_yuan` is reference-only.

Machine-readable experiment roles are explicit: `ACTIVE_LEARNED_ONLY`, `ACTIVE_EQUAL_FUNDING_CONTROL`, `ACTIVE_SCORE_WEIGHTED_CONTROL`, `SAFE_FALLBACK_MIXED`, and `CASH`.

K=16/32 rows are sensitivity-only and do not select the controlling result. The bounded neural ablation is fitted only after the simple logistic controller. No 2025/2026 LOCKED_TEST outcome or official-final-SP label is used.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Non-empty active Lane A; exact SAFE Lane B | `active_research_ticket_requests.parquet`, `safe_reference_ledger.csv` | PASS |
| Exact #206 five-policy K8 identity binding | semantic verifier + active ledger | PASS |
| No cash pseudo-Edge | `attribution.csv`, lower-exposure regression test | PASS |
| Exact capital conservation / integer ¥2 | `issue_capital_ledger.parquet`, verifier/tests | PASS |
| CV-2021 fit / CV-2022 freeze / CV-2023 terminal test | `model_parameters.json`, `provenance.json` | PASS |
| Native/equal/score/simple/neural ablations | `capital_summary.csv`, `controller_calibration.csv` | PASS |
| Equity/drawdown/rolling/streak/concentration/ex-largest/completed-recovery | ledgers, tables and plots | PASS |
| Decisive matched comparator issue/ticket-tax-lot replay | `matched_comparator_issue_ledger.parquet`, `matched_ticket_tax_lot_ledger.parquet` | PASS |
| Full schema / provenance / handoff semantic verifier | `schema.json`, `provenance.json`, `stage4_handoff_schema.json` | PASS |
| Three separate decisions and #208 boundary | `decision.json`, `stage4_handoff_schema.json` | PASS |

Decision input: preserve the simplest active control when matched evidence is negative; never reinterpret cash as the optimal model. Known risks: high payout variance, bounded Stage-3 candidate recall, overlap, predicted-SP error, retrospective risk calibration and no accepted Stage-3 baseline. Explicit review request: independently recompute K8 identities, controller chronology, schedule hashes, integer projection, payout conservation, holding metrics, lower-exposure attribution, notebook clean-run and immutable replay before moving to PI Review. #208 remains blocked and receives no activation authority.
"""


def run(inputs: Inputs) -> dict[str, Any]:
    source = inputs.source.resolve()
    output = inputs.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = _prepare_output_stage(output)
    try:
        source_receipt = verify_stage3(source)
        candidates = pd.read_parquet(source / "candidate_ledger.parquet")
        _validate_candidates(candidates)
        requests = reconstruct_active_requests(candidates)
        if requests.empty:
            raise Stage4Error("#206 empty fallback ledger cannot become active Lane A")
        safe = _safe_ledger(source)
        controllers = _fit_controllers(candidates)
        calibrated, calibration = _calibrate_risk(requests, controllers)
        ledgers = [
            replay_path(
                requests,
                split=split,
                policy=policy,
                k=k,
                method=method,
                controllers=controllers,
                calibrated=calibrated,
            )
            for split in ("CV_2022", "CV_2023")
            for policy in POLICIES
            for k in K_GRID
            for method in ACTIVE_METHODS
        ]
        ledger = pd.concat(ledgers, ignore_index=True)
        metrics, rolling = _path_metrics(ledger)
        # Attach calibrated fractions for matched-control lookup.
        metrics["risk_fraction"] = metrics.controller.map(
            {
                "NATIVE_2_YUAN": np.nan,
                "EQUAL_1PCT": 0.01,
                "EQUAL_5PCT": 0.05,
                "EQUAL_25PCT": 0.25,
                "EQUAL_100PCT": 1.0,
                "SCORE_WEIGHTED_5PCT": 0.05,
                **calibrated,
            }
        )
        frozen_learned_choice, freeze_choice = _freeze_learned_controller_choice(
            metrics, ledger, requests, controllers, calibrated
        )
        matched, matched_issue, matched_ticket = _matched_comparisons(
            metrics, ledger, requests, controllers, calibrated, frozen_learned_choice=frozen_learned_choice
        )
        attribution = matched.loc[:, [
            "comparison_role", "split", "policy", "k", "candidate_controller", "comparator_controller",
            "equal_capital_schedule", "identifiability", "attribution",
            "matched_lift_ending_capital_yuan", "matched_lift_max_drawdown_pct", "terminal_evidentiary",
        ]].copy()
        attribution["experiment_role"] = attribution.candidate_controller.map(_experiment_role)
        attribution = pd.concat(
            [
                attribution,
                pd.DataFrame(
                    [
                        {"comparison_role": "SAFE_REFERENCE", "experiment_role": "SAFE_FALLBACK_MIXED", "split": "LOCKED_TEST", "policy": "SAFE_FALLBACK_MIXED", "k": 0, "candidate_controller": "NO_BET", "comparator_controller": "CASH", "equal_capital_schedule": True, "identifiability": "SAFETY_REFERENCE_ONLY", "attribution": "LOWER_EXPOSURE_ONLY", "matched_lift_ending_capital_yuan": 0.0, "matched_lift_max_drawdown_pct": 0.0, "terminal_evidentiary": False}
                    ]
                ),
            ],
            ignore_index=True,
        )
        decision = _decision(metrics, matched, frozen_learned_choice=frozen_learned_choice)

        requests.to_parquet(stage / "active_research_ticket_requests.parquet", index=False)
        safe.to_csv(stage / "safe_reference_ledger.csv", index=False)
        ledger.to_parquet(stage / "issue_capital_ledger.parquet", index=False)
        metrics.to_csv(stage / "capital_summary.csv", index=False)
        rolling.to_csv(stage / "rolling_window_metrics.csv", index=False)
        matched.to_csv(stage / "matched_comparisons.csv", index=False)
        matched_issue.to_parquet(stage / "matched_comparator_issue_ledger.parquet", index=False)
        matched_ticket.to_parquet(stage / "matched_ticket_tax_lot_ledger.parquet", index=False)
        attribution.to_csv(stage / "attribution.csv", index=False)
        calibration.to_csv(stage / "controller_calibration.csv", index=False)
        freeze_choice.to_csv(stage / "frozen_learned_controller_choice.csv", index=False)
        _json(stage / "decision.json", decision)
        _json(
            stage / "model_parameters.json",
            {
                "version": VERSION,
                "fit_split": "CV_2021",
                "calibration_and_risk_selection_split": "CV_2022",
                "terminal_evaluation_split": "CV_2023",
                "simple_model": "sklearn.pipeline(StandardScaler, LogisticRegression)",
                "simple_parameters": {"C": 0.25, "class_weight": "balanced", "solver": "lbfgs", "max_iter": 1000, "random_state": 207001},
                "neural_model": "sklearn.pipeline(StandardScaler, MLPClassifier)",
                "neural_parameters": {"hidden_layer_sizes": [8], "alpha": 0.05, "max_iter": 100, "early_stopping": True, "random_state": 207001},
                "fit_order": ["SIMPLE_LOGISTIC", "BOUNDED_NEURAL"],
                "features": list(CONTROL_FEATURES),
                "risk_grid": list(RISK_GRID),
                "selected_risk_fraction": calibrated,
                "frozen_learned_controller_choice": frozen_learned_choice,
                "learned_controller_selection_split": "CV_2022",
                "terminal_evidentiary_split": "CV_2023",
                "ticket_stake_yuan": TICKET_STAKE,
                "initial_bankroll_yuan": INITIAL_BANKROLL,
                "device": "CPU",
                "seed": 207001,
            },
        )
        _json(stage / "schema.json", _schema_catalog(requests, safe, ledger, metrics, rolling, matched, matched_issue, matched_ticket, attribution, calibration, freeze_choice))
        _json(
            stage / "stage4_handoff_schema.json",
            {
                "$id": "BJ-UNIFIED-N7-BANKROLL-LEARNING-001/STAGE4-HANDOFF/v1",
                "research_only": True,
                "promoted": False,
                "activation_authority": False,
                "required_decisions": ["ENGINE_VALID", "ACTIVE_OVERLAY_EVIDENCE", "DEPLOYABLE_POLICY"],
                "downstream_issue": 208,
                "downstream_state": "BLOCKED_PENDING_PI_TERMINAL_REVIEW_AND_EXPLICIT_ACTIVATION",
                "identity_fields": ["policy", "k", "ticket_identity", "capital_schedule_hash"],
                "terminal_evidentiary_split": "CV_2023",
                "frozen_learned_controller_choice": frozen_learned_choice,
            },
        )
        source_manifest = source / "SHA256SUMS.json"
        _json(
            stage / "provenance.json",
            {
                "version": VERSION,
                "source_package": str(inputs.source),
                "source_manifest_sha256": _digest(source_manifest),
                "source_verify_receipt": source_receipt,
                "implementation_sha256": _digest(Path(__file__).resolve()),
                "runner_sha256": _digest(RUNNER),
                "notebook_contract_sha256": _notebook_contract_digest(NOTEBOOK),
                "notebook_binding": "canonical cell type/source; execution outputs and executor metadata excluded to prevent manifest self-reference",
                "requirements_sha256": _digest(SCIENTIFIC_LOCK),
                "environment": _environment(),
                "replay": "PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py run --output <new-directory>",
                "verify": "PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207",
                "label_boundary": "CV_2021 fit; CV_2022 risk freeze; CV_2023 terminal evaluation; LOCKED_TEST labels unused",
                "learned_controller_choice_boundary": "SIMPLE_LOGISTIC vs BOUNDED_NEURAL selected on CV_2022 only; only frozen choice is terminal-evidentiary on CV_2023",
            },
        )
        _plots(ledger, metrics, calibration, stage)
        (stage / "DECISION_REPORT.md").write_text(_report(decision, metrics, matched), encoding="utf-8", newline="\n")
        (stage / "README.md").write_text(
            "# Issue #207 immutable evidence package\n\n"
            "Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207`.\n\n"
            "Replay: `PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py run --output <new-directory>`.\n\n"
            "Notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj207_notebook.py --kernel python3`.\n",
            encoding="utf-8",
            newline="\n",
        )
        payloads = {
            path.relative_to(stage).as_posix(): _digest(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name != "SHA256SUMS.json"
        }
        _json(stage / "SHA256SUMS.json", payloads)
        _fsync_tree(stage)
        _publish_stage(stage, output)
        return {
            "output": str(output),
            "files": len(payloads),
            "active_request_rows": len(requests),
            "capital_ledger_rows": len(ledger),
            "matched_issue_rows": len(matched_issue),
            "matched_ticket_rows": len(matched_ticket),
            "decision": decision,
        }
    except BaseException:
        _remove_stage(stage)
        raise


def verify(output: Path) -> dict[str, Any]:
    output = output.resolve()
    expected = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(output).as_posix(): _digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if expected != actual:
        raise Stage4Error("manifest mismatch")
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    source = Path(provenance["source_package"])
    if not source.is_absolute():
        source = next((parent / source for parent in output.parents if (parent / source).exists()), source)
    if _digest(source / "SHA256SUMS.json") != provenance["source_manifest_sha256"]:
        raise Stage4Error("#206 source-package binding mismatch")
    if _digest(Path(__file__).resolve()) != provenance["implementation_sha256"]:
        raise Stage4Error("Stage-4 implementation binding mismatch")
    if _digest(RUNNER) != provenance["runner_sha256"]:
        raise Stage4Error("Stage-4 runner binding mismatch")
    if _notebook_contract_digest(NOTEBOOK) != provenance["notebook_contract_sha256"]:
        raise Stage4Error("Stage-4 notebook binding mismatch")
    verify_stage3(source)
    candidates = pd.read_parquet(source / "candidate_ledger.parquet")
    _validate_candidates(candidates)
    requests = pd.read_parquet(output / "active_research_ticket_requests.parquet")
    if requests.empty or not requests.research_only.astype(bool).all() or requests.promoted.astype(bool).any():
        raise Stage4Error("active research lane boundary mismatch")
    if requests.labels_used_for_identity.astype(bool).any():
        raise Stage4Error("label entered ticket identity selection")
    expected_requests = reconstruct_active_requests(candidates)
    _assert_semantic_frame(requests, expected_requests, "complete #206 active panel")

    controllers = _fit_controllers(candidates)
    calibrated, expected_calibration = _calibrate_risk(expected_requests, controllers)
    expected_ledger = pd.concat(
        [
            replay_path(
                expected_requests,
                split=split,
                policy=policy,
                k=k,
                method=method,
                controllers=controllers,
                calibrated=calibrated,
            )
            for split in ("CV_2022", "CV_2023")
            for policy in POLICIES
            for k in K_GRID
            for method in ACTIVE_METHODS
        ],
        ignore_index=True,
    )
    ledger = pd.read_parquet(output / "issue_capital_ledger.parquet")
    _assert_semantic_frame(ledger, expected_ledger, "issue capital ledger")
    if not np.allclose(
        ledger.post_issue_bankroll_yuan,
        ledger.pre_issue_bankroll_yuan - ledger.funded_stake_yuan + ledger.gross_payout_yuan,
        rtol=0.0,
        atol=1e-8,
    ):
        raise Stage4Error("capital conservation mismatch")
    if (ledger.funded_stake_yuan < 0).any() or (ledger.funded_stake_yuan > ledger.pre_issue_bankroll_yuan + 1e-8).any():
        raise Stage4Error("negative or overfunded stake")
    if not np.isclose((ledger.funded_stake_yuan / TICKET_STAKE) % 1, 0.0, atol=1e-9).all():
        raise Stage4Error("non-integer ¥2 funding")
    if not ((ledger.projection_residual_yuan >= -1e-9) & (ledger.projection_residual_yuan < TICKET_STAKE + 1e-9)).all():
        raise Stage4Error("projection residual mismatch")
    decision = json.loads((output / "decision.json").read_text(encoding="utf-8"))
    if decision["DEPLOYABLE_POLICY"] is not False or decision["ENGINE_VALID"] is not True:
        raise Stage4Error("decision boundary mismatch")
    safe = pd.read_csv(output / "safe_reference_ledger.csv", dtype={"issue": str})
    _assert_semantic_frame(safe, _safe_ledger(source), "safe reference ledger")
    if not safe.funded_stake_yuan.eq(0).all() or not safe.attribution.eq("LOWER_EXPOSURE_ONLY").all():
        raise Stage4Error("safe lane pseudo-Edge boundary mismatch")
    required_roles = {
        "ACTIVE_LEARNED_ONLY",
        "ACTIVE_EQUAL_FUNDING_CONTROL",
        "ACTIVE_SCORE_WEIGHTED_CONTROL",
    }
    if set(ledger.experiment_role) != required_roles:
        raise Stage4Error("active experiment role boundary mismatch")
    if set(safe.experiment_role) != {"SAFE_FALLBACK_MIXED", "CASH"}:
        raise Stage4Error("safe experiment role boundary mismatch")
    matched = pd.read_csv(output / "matched_comparisons.csv")
    expected_metrics, expected_rolling = _path_metrics(expected_ledger)
    expected_metrics["risk_fraction"] = expected_metrics.controller.map(
        {
            "NATIVE_2_YUAN": np.nan,
            "EQUAL_1PCT": 0.01,
            "EQUAL_5PCT": 0.05,
            "EQUAL_25PCT": 0.25,
            "EQUAL_100PCT": 1.0,
            "SCORE_WEIGHTED_5PCT": 0.05,
            **calibrated,
        }
    )
    frozen_learned_choice, expected_freeze_choice = _freeze_learned_controller_choice(
        expected_metrics, expected_ledger, expected_requests, controllers, calibrated
    )
    expected_matched, expected_matched_issue, expected_matched_ticket = _matched_comparisons(
        expected_metrics,
        expected_ledger,
        expected_requests,
        controllers,
        calibrated,
        frozen_learned_choice=frozen_learned_choice,
    )
    _assert_semantic_frame(matched, expected_matched, "matched comparisons")
    identified = matched.equal_capital_schedule.astype(bool)
    if not matched.loc[identified, "identifiability"].eq("IDENTIFIED_MATCHED_ACTIVE_FUNDING").all():
        raise Stage4Error("matched active attribution mismatch")
    if not np.allclose(
        matched.loc[identified, "candidate_turnover_yuan"],
        matched.loc[identified, "comparator_turnover_yuan"],
        rtol=0.0,
        atol=1e-8,
    ):
        raise Stage4Error("matched capital schedules have unequal turnover")
    if not matched.loc[identified, "capital_schedule_hash"].eq(
        matched.loc[identified, "comparator_schedule_hash"]
    ).all():
        raise Stage4Error("matched capital schedule hash mismatch")
    metrics = pd.read_csv(output / "capital_summary.csv")
    rolling = pd.read_csv(
        output / "rolling_window_metrics.csv",
        dtype={"start_issue": "string", "end_issue": "string"},
    )
    calibration = pd.read_csv(output / "controller_calibration.csv")
    freeze_choice = pd.read_csv(output / "frozen_learned_controller_choice.csv")
    matched_issue = pd.read_parquet(output / "matched_comparator_issue_ledger.parquet")
    matched_ticket = pd.read_parquet(output / "matched_ticket_tax_lot_ledger.parquet")
    attribution = pd.read_csv(output / "attribution.csv")
    _assert_semantic_frame(metrics, expected_metrics, "capital summary")
    _assert_semantic_frame(rolling, expected_rolling, "rolling window metrics")
    _assert_semantic_frame(calibration, expected_calibration, "controller calibration")
    _assert_semantic_frame(freeze_choice, expected_freeze_choice, "frozen learned controller choice")
    _assert_semantic_frame(matched_issue, expected_matched_issue, "matched comparator issue ledger")
    _assert_semantic_frame(matched_ticket, expected_matched_ticket, "matched ticket tax-lot ledger")
    expected_attribution = matched.loc[:, [
        "comparison_role", "split", "policy", "k", "candidate_controller", "comparator_controller",
        "equal_capital_schedule", "identifiability", "attribution",
        "matched_lift_ending_capital_yuan", "matched_lift_max_drawdown_pct", "terminal_evidentiary",
    ]].copy()
    expected_attribution["experiment_role"] = expected_attribution.candidate_controller.map(_experiment_role)
    expected_attribution = pd.concat(
        [
            expected_attribution,
            pd.DataFrame(
                [
                    {"comparison_role": "SAFE_REFERENCE", "experiment_role": "SAFE_FALLBACK_MIXED", "split": "LOCKED_TEST", "policy": "SAFE_FALLBACK_MIXED", "k": 0, "candidate_controller": "NO_BET", "comparator_controller": "CASH", "equal_capital_schedule": True, "identifiability": "SAFETY_REFERENCE_ONLY", "attribution": "LOWER_EXPOSURE_ONLY", "matched_lift_ending_capital_yuan": 0.0, "matched_lift_max_drawdown_pct": 0.0, "terminal_evidentiary": False}
                ]
            ),
        ],
        ignore_index=True,
    )
    _assert_semantic_frame(attribution, expected_attribution, "attribution")
    if matched.loc[matched.candidate_controller.isin(LEARNED_METHODS), "terminal_evidentiary"].astype(bool).any():
        observed = set(matched.loc[matched.terminal_evidentiary.astype(bool) & matched.candidate_controller.isin(LEARNED_METHODS), "candidate_controller"])
        if observed != {frozen_learned_choice}:
            raise Stage4Error("terminal model-choice leakage")
    expected_decision = _decision(metrics, matched, frozen_learned_choice=frozen_learned_choice)
    for key in ("ENGINE_VALID", "ACTIVE_OVERLAY_EVIDENCE", "DEPLOYABLE_POLICY", "qualifying_active_rows", "frozen_learned_controller_choice"):
        if decision[key] != expected_decision[key]:
            raise Stage4Error(f"decision semantic mismatch: {key}")
    if decision["frozen_learned_controller_choice"] != frozen_learned_choice:
        raise Stage4Error("decision/model-choice leakage")
    _json_equal(
        output,
        "schema.json",
        _schema_catalog(expected_requests, _safe_ledger(source), expected_ledger, expected_metrics, expected_rolling, expected_matched, expected_matched_issue, expected_matched_ticket, expected_attribution, expected_calibration, expected_freeze_choice),
    )
    _json_equal(
        output,
        "model_parameters.json",
        {
            "version": VERSION,
            "fit_split": "CV_2021",
            "calibration_and_risk_selection_split": "CV_2022",
            "terminal_evaluation_split": "CV_2023",
            "simple_model": "sklearn.pipeline(StandardScaler, LogisticRegression)",
            "simple_parameters": {"C": 0.25, "class_weight": "balanced", "solver": "lbfgs", "max_iter": 1000, "random_state": 207001},
            "neural_model": "sklearn.pipeline(StandardScaler, MLPClassifier)",
            "neural_parameters": {"hidden_layer_sizes": [8], "alpha": 0.05, "max_iter": 100, "early_stopping": True, "random_state": 207001},
            "fit_order": ["SIMPLE_LOGISTIC", "BOUNDED_NEURAL"],
            "features": list(CONTROL_FEATURES),
            "risk_grid": list(RISK_GRID),
            "selected_risk_fraction": calibrated,
            "frozen_learned_controller_choice": frozen_learned_choice,
            "learned_controller_selection_split": "CV_2022",
            "terminal_evidentiary_split": "CV_2023",
            "ticket_stake_yuan": TICKET_STAKE,
            "initial_bankroll_yuan": INITIAL_BANKROLL,
            "device": "CPU",
            "seed": 207001,
        },
    )
    _json_equal(
        output,
        "stage4_handoff_schema.json",
        {
            "$id": "BJ-UNIFIED-N7-BANKROLL-LEARNING-001/STAGE4-HANDOFF/v1",
            "research_only": True,
            "promoted": False,
            "activation_authority": False,
            "required_decisions": ["ENGINE_VALID", "ACTIVE_OVERLAY_EVIDENCE", "DEPLOYABLE_POLICY"],
            "downstream_issue": 208,
            "downstream_state": "BLOCKED_PENDING_PI_TERMINAL_REVIEW_AND_EXPLICIT_ACTIVATION",
            "identity_fields": ["policy", "k", "ticket_identity", "capital_schedule_hash"],
            "terminal_evidentiary_split": "CV_2023",
            "frozen_learned_controller_choice": frozen_learned_choice,
        },
    )
    _json_equal(
        output,
        "provenance.json",
        {
            "version": VERSION,
            "source_package": provenance["source_package"],
            "source_manifest_sha256": _digest(source / "SHA256SUMS.json"),
            "source_verify_receipt": verify_stage3(source),
            "implementation_sha256": _digest(Path(__file__).resolve()),
            "runner_sha256": _digest(RUNNER),
            "notebook_contract_sha256": _notebook_contract_digest(NOTEBOOK),
            "notebook_binding": "canonical cell type/source; execution outputs and executor metadata excluded to prevent manifest self-reference",
            "requirements_sha256": _digest(SCIENTIFIC_LOCK),
            "environment": _environment(),
            "replay": "PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py run --output <new-directory>",
            "verify": "PYTHONPATH=src .venv/bin/python scripts/run_bj207_bankroll.py verify --output results/issue-207",
            "label_boundary": "CV_2021 fit; CV_2022 risk freeze; CV_2023 terminal evaluation; LOCKED_TEST labels unused",
            "learned_controller_choice_boundary": "SIMPLE_LOGISTIC vs BOUNDED_NEURAL selected on CV_2022 only; only frozen choice is terminal-evidentiary on CV_2023",
        },
    )
    report_text = (output / "DECISION_REPORT.md").read_text(encoding="utf-8")
    if report_text != _report(decision, metrics, matched):
        raise Stage4Error("decision report semantic mismatch")
    return {
        "status": "PASS",
        "files": len(actual),
        "manifest_sha256": _digest(output / "SHA256SUMS.json"),
        "active_request_rows": len(requests),
        "capital_ledger_rows": len(ledger),
        "matched_issue_rows": len(matched_issue),
        "matched_ticket_rows": len(matched_ticket),
        "engine_valid": decision["ENGINE_VALID"],
        "active_overlay_evidence": decision["ACTIVE_OVERLAY_EVIDENCE"],
        "deployable_policy": decision["DEPLOYABLE_POLICY"],
    }
