#!/usr/bin/env python3
"""Run the frozen one-seed/one-fold #284 neural activity pilot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.linear_model import HuberRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.data import build_tensor  # noqa: E402
from issue209.models import build_match_units  # noqa: E402
from issue279.traces import build_cell_trace  # noqa: E402
from issue282.contract import CELL_FEATURES  # noqa: E402
from issue282.features import ISSUE_STATE_FEATURES  # noqa: E402
from issue284.pilot import (  # noqa: E402
    fit_subset_pilot,
    predict_subset_pilot,
    prepare_subset_arrays,
)

OUTCOMES = ("3", "1", "0")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", ROOT)),
    )
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-284")
    parser.add_argument("--validation-year", type=int, default=2022)
    parser.add_argument("--seed", type=int, default=284_201)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--run-tag", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact_root = args.artifact_root.resolve()
    output = args.output.resolve()
    suffix = f"_{args.run_tag}" if args.run_tag else ""
    labels_path = output / "pilot_subset_labels.parquet"
    probability_path = artifact_root / "results/issue-209/market_only_probabilities.parquet"
    value_path = artifact_root / "results/issue-209/cell_value_distribution.parquet"
    state_path = artifact_root / "results/issue-279/action_features.parquet"
    for path in (labels_path, probability_path, value_path, state_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    labels = pd.read_parquet(labels_path)
    labels["issue"] = labels["issue"].astype(str)
    if labels["issue_year"].ge(2024).any():
        raise RuntimeError("2024+ activity-pilot seal violated")
    labels = _attach_matched_baseline(labels)

    tensor = build_tensor()
    units = build_match_units(tensor)
    probabilities = pd.read_parquet(probability_path)
    values = pd.read_parquet(value_path)
    trace = build_cell_trace(
        units,
        probabilities,
        values,
        issues=set(labels["issue"]),
        horizon="10h",
    )
    cell_lookup = _cell_lookup(trace)
    cells, match_mask = _subset_cells(labels, cell_lookup)
    actions = _action_features(labels, state_path)
    issue_ids = tuple(sorted(labels["issue"].unique()))
    issue_to_index = {issue: index for index, issue in enumerate(issue_ids)}
    issue_index = labels["issue"].map(issue_to_index).to_numpy(dtype=int)
    calibration_year = args.validation_year - 1
    train = labels["issue_year"].lt(calibration_year).to_numpy()
    calibration = labels["issue_year"].eq(calibration_year).to_numpy()
    validation = labels["issue_year"].eq(args.validation_year).to_numpy()
    if not train.any() or not calibration.any() or not validation.any():
        raise RuntimeError("pilot chronological fold is empty")
    prediction_frames: list[pd.DataFrame] = []
    model_states: dict[str, dict[str, torch.Tensor]] = {}
    per_n_receipts: dict[str, dict[str, float | int]] = {}
    for n in sorted(labels["n"].unique()):
        n_mask = labels["n"].eq(n).to_numpy()
        global_rows = np.flatnonzero(n_mask)
        arrays = prepare_subset_arrays(
            cells[n_mask],
            match_mask[n_mask],
            actions[n_mask],
            labels.loc[n_mask, "matched_lift_cny100"].to_numpy(),
            issue_index[n_mask],
            train[n_mask],
        )
        model, receipt = fit_subset_pilot(
            arrays,
            train[n_mask],
            seed=args.seed + int(n),
            epochs=args.epochs,
        )
        calibration_prediction = predict_subset_pilot(
            model,
            arrays,
            calibration[n_mask],
            target_scale=float(receipt["target_scale"]),
        )
        prediction = predict_subset_pilot(
            model,
            arrays,
            validation[n_mask],
            target_scale=float(receipt["target_scale"]),
        )
        calibrator, calibration_receipt = _fit_calibrator(
            calibration_prediction,
            labels.loc[n_mask, "matched_lift_cny100"].to_numpy(),
            calibration[n_mask],
        )
        prediction["calibrated_expected_lift"] = calibrator.predict(
            _calibration_features(prediction)
        )
        prediction["row_index"] = global_rows[
            prediction["row_index"].to_numpy(dtype=int)
        ]
        prediction["scoring_model_n"] = int(n)
        prediction_frames.append(prediction)
        model_states[str(int(n))] = model.state_dict()
        per_n_receipts[str(int(n))] = {**receipt, **calibration_receipt}
    prediction = pd.concat(prediction_frames, ignore_index=True).sort_values(
        "row_index"
    )
    validation_labels = labels.iloc[prediction["row_index"].to_numpy()].reset_index(
        drop=True
    )
    prediction = prediction.drop(columns="row_index").reset_index(drop=True)
    scored = pd.concat([validation_labels, prediction], axis=1)
    scored["raw_policy_score"] = scored["calibrated_expected_lift"]
    baseline_score = (
        scored.loc[scored["is_matched_baseline"], ["issue", "raw_policy_score"]]
        .rename(columns={"raw_policy_score": "baseline_policy_score"})
    )
    scored = scored.merge(baseline_score, on="issue", how="left", validate="many_to_one")
    scored["policy_score"] = (
        scored["raw_policy_score"] - scored["baseline_policy_score"]
    )
    scored.to_parquet(
        output / f"pilot_predictions_{args.validation_year}{suffix}.parquet",
        index=False,
    )
    n_frontier = (
        scored.sort_values(
            ["issue", "n", "policy_score", "subset_id"],
            ascending=[True, True, False, True],
        )
        .groupby(["issue", "n"], as_index=False)
        .head(1)
        .copy()
    )
    n_frontier.to_parquet(
        output / f"pilot_n_frontier_{args.validation_year}{suffix}.parquet",
        index=False,
    )
    forced = (
        n_frontier.sort_values(
            ["issue", "policy_score", "subset_id"],
            ascending=[True, False, True],
        )
        .groupby("issue", as_index=False)
        .head(1)
        .copy()
    )
    fixed = scored.loc[scored["is_matched_baseline"]].copy()
    deviations = forced["policy_score"].gt(0) & ~forced["is_matched_baseline"]
    fallback = fixed.set_index("issue")
    selected = forced.set_index("issue")
    selected.loc[~deviations.to_numpy()] = fallback.loc[
        selected.index[~deviations.to_numpy()]
    ]
    selected = selected.reset_index()
    selected["selected_as_deviation"] = selected["issue"].isin(
        forced.loc[deviations, "issue"]
    )
    selected["matched_lift_cny100"] = (
        selected["normalized_pnl_cny100"] - selected["baseline_pnl_cny100"]
    )
    fixed = _normalize_risk(fixed)
    forced = _normalize_risk(forced)
    selected = _normalize_risk(selected)
    metrics = pd.DataFrame(
        [
            _metrics("PILOT_FIXED_N7_UNIFORM_K128", fixed),
            _metrics("PILOT_MODEL_FORCED_TOP", forced),
            _metrics("PILOT_MODEL_BASELINE_FALLBACK", selected),
        ]
    )
    metrics.to_csv(
        output / f"pilot_policy_metrics_{args.validation_year}{suffix}.csv",
        index=False,
    )
    activity = {
        "contract": "BJ-UNIFIED-SUBSET-POLICY-001/v1-pilot",
        "training_years": [int(labels["issue_year"].min()), args.validation_year - 1],
        "model_fit_years": [int(labels["issue_year"].min()), calibration_year - 1],
        "cross_n_calibration_year": calibration_year,
        "validation_year": args.validation_year,
        "training_rows": int(train.sum()),
        "training_issues": int(labels.loc[train, "issue"].nunique()),
        "calibration_rows": int(calibration.sum()),
        "calibration_issues": int(labels.loc[calibration, "issue"].nunique()),
        "validation_rows": int(validation.sum()),
        "validation_issues": int(labels.loc[validation, "issue"].nunique()),
        "prediction_std": float(scored["expected_value"].std(ddof=0)),
        "positive_relative_score_rows": int(scored["policy_score"].gt(0).sum()),
        "model_deviation_issues": int(deviations.sum()),
        "model_deviation_issue_fraction": float(deviations.mean()),
        "forced_selected_n": {
            str(int(n)): int(count) for n, count in forced["n"].value_counts().items()
        },
        "fallback_selected_n": {
            str(int(n)): int(count)
            for n, count in selected["n"].value_counts().items()
        },
        "fallback_selected_proposal_family": {
            str(family): int(count)
            for family, count in selected["proposal_family"].value_counts().items()
        },
        "fallback_matched_lift_cny100": float(
            selected["matched_lift_cny100"].sum()
        ),
        "fallback_ex_largest_matched_lift_cny100": _ex_largest(
            selected["matched_lift_cny100"]
        ),
        "activity_valid": bool(
            all(
                receipt["final_gradient_norm"] > 0
                for receipt in per_n_receipts.values()
            )
            and scored["expected_value"].std(ddof=0) > 1e-6
            and deviations.mean() >= 0.10
            and selected.loc[selected["selected_as_deviation"], "n"].nunique() >= 2
        ),
        "performance_promising": bool(
            deviations.mean() >= 0.10
            and selected["matched_lift_cny100"].sum() > 0
            and _ex_largest(selected["matched_lift_cny100"]) > 0
        ),
        "sealed_years_opened": [],
        "per_n_training_receipts": per_n_receipts,
    }
    (output / f"pilot_activity_decision{suffix}.json").write_text(
        json.dumps(activity, indent=2), encoding="utf-8"
    )
    torch.save(model_states, output / f"pilot_subset_models_per_n{suffix}.pt")
    print(json.dumps(activity, indent=2), flush=True)
    print(metrics.to_string(index=False), flush=True)
    return 0


def _cell_lookup(trace: pd.DataFrame) -> dict[tuple[str, str], np.ndarray]:
    rank = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    ordered = trace.assign(
        issue=trace["issue"].astype(str),
        match_idx=trace["match_idx"].astype(str),
        __outcome_rank=trace["outcome_code"].astype(str).map(rank),
    ).sort_values(["issue", "match_idx", "__outcome_rank"])
    lookup: dict[tuple[str, str], np.ndarray] = {}
    for (issue, match), group in ordered.groupby(["issue", "match_idx"], sort=False):
        if tuple(group["outcome_code"].astype(str)) != OUTCOMES:
            raise RuntimeError(f"noncanonical outcome cells for {issue}/{match}")
        lookup[(str(issue), str(match))] = group[list(CELL_FEATURES)].to_numpy(float)
    return lookup


def _subset_cells(
    labels: pd.DataFrame, lookup: dict[tuple[str, str], np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    max_n = int(labels["n"].max())
    cells = np.full((len(labels), max_n, 3, len(CELL_FEATURES)), np.nan, dtype=float)
    mask = np.zeros((len(labels), max_n), dtype=bool)
    for row, label in enumerate(labels.itertuples(index=False)):
        match_ids = json.loads(label.match_ids)
        matrix = np.stack([lookup[(str(label.issue), str(match))] for match in match_ids])
        cells[row, : len(matrix)] = matrix
        mask[row, : len(matrix)] = True
    return cells, mask


def _action_features(labels: pd.DataFrame, state_path: Path) -> np.ndarray:
    inherited = pd.read_parquet(state_path)
    inherited["issue"] = inherited["issue"].astype(str)
    states = inherited[["issue", *ISSUE_STATE_FEATURES]].drop_duplicates("issue")
    frame = labels[["issue", "n", "k", "issue_match_count", "proposal_family"]].merge(
        states, on="issue", how="left", validate="many_to_one"
    )
    features = frame[list(ISSUE_STATE_FEATURES)].astype(float).copy()
    features["action_n_fraction_of_10"] = frame["n"].astype(float) / 10.0
    features["action_n_fraction_of_issue"] = frame["n"].astype(float) / frame[
        "issue_match_count"
    ].clip(lower=1)
    features["action_log_issue_matches"] = np.log1p(frame["issue_match_count"])
    features["action_log2_k"] = np.log2(frame["k"].clip(lower=1))
    for family in (
        "UNIFORM",
        "VALUE_WEIGHTED",
        "DIVERGENCE_WEIGHTED",
        "SHAPE_STRATIFIED",
    ):
        features[f"proposal_{family}"] = frame["proposal_family"].eq(family).astype(float)
    return features.to_numpy(float)


def _calibration_features(prediction: pd.DataFrame) -> np.ndarray:
    return prediction[
        [
            "expected_value",
            "q10",
            "q50",
            "q90",
            "positive_probability",
        ]
    ].to_numpy(float)


def _fit_calibrator(
    prediction: pd.DataFrame,
    target: np.ndarray,
    calibration_mask: np.ndarray,
) -> tuple[object, dict[str, float | int]]:
    rows = prediction["row_index"].to_numpy(dtype=int)
    local_target = np.asarray(target, dtype=float)[rows]
    model = make_pipeline(
        StandardScaler(),
        HuberRegressor(alpha=1.0, epsilon=1.35, max_iter=500),
    )
    features = _calibration_features(prediction)
    model.fit(features, local_target)
    calibrated = model.predict(features)
    raw = prediction["expected_value"].to_numpy(float)
    return model, {
        "calibration_rows": int(len(rows)),
        "calibration_mask_rows": int(np.asarray(calibration_mask, dtype=bool).sum()),
        "calibration_raw_mae": float(np.abs(raw - local_target).mean()),
        "calibration_fitted_mae": float(np.abs(calibrated - local_target).mean()),
        "calibration_spearman": float(
            pd.Series(calibrated).corr(pd.Series(local_target), method="spearman")
        ),
    }


def _attach_matched_baseline(labels: pd.DataFrame) -> pd.DataFrame:
    baseline = labels.loc[
        labels["n"].eq(7) & labels["proposal_family"].eq("UNIFORM")
    ].copy()
    counts = baseline.groupby("issue").size()
    if not counts.eq(1).all() or set(counts.index) != set(labels["issue"]):
        raise RuntimeError("pilot requires exactly one N7/UNIFORM baseline per issue")
    baseline = baseline[["issue", "subset_id", "normalized_pnl_cny100"]].rename(
        columns={
            "subset_id": "baseline_subset_id",
            "normalized_pnl_cny100": "baseline_pnl_cny100",
        }
    )
    result = labels.merge(baseline, on="issue", how="left", validate="many_to_one")
    result["is_matched_baseline"] = result["subset_id"].eq(
        result["baseline_subset_id"]
    )
    result["matched_lift_cny100"] = (
        result["normalized_pnl_cny100"] - result["baseline_pnl_cny100"]
    )
    return result


def _normalize_risk(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["actual_stake_cny"] = result["stake_cny"]
    result["actual_pnl_cny"] = result["pnl_cny"]
    result["stake_cny"] = 100.0
    result["pnl_cny"] = result["normalized_pnl_cny100"]
    return result


def _metrics(policy: str, frame: pd.DataFrame) -> dict[str, float | int | str]:
    pnl = frame["pnl_cny"].to_numpy(float)
    stake = frame["stake_cny"].to_numpy(float)
    capital = 100_000.0 + np.cumsum(pnl)
    running_peak = np.maximum.accumulate(np.r_[100_000.0, capital])[:-1]
    drawdown = np.divide(
        running_peak - capital,
        running_peak,
        out=np.zeros_like(capital),
        where=running_peak > 0,
    )
    return {
        "policy": policy,
        "issues": int(frame["issue"].nunique()),
        "bet_issues": int((stake > 0).sum()),
        "positive_issues": int((pnl > 0).sum()),
        "turnover_cny": float(stake.sum()),
        "pnl_cny": float(pnl.sum()),
        "ending_capital_cny": float(100_000.0 + pnl.sum()),
        "ex_largest_pnl_cny": _ex_largest(pd.Series(pnl)),
        "max_drawdown_fraction": float(drawdown.max(initial=0.0)),
    }


def _ex_largest(values: pd.Series) -> float:
    pnl = values.to_numpy(float)
    positive = pnl[pnl > 0]
    return float(pnl.sum() - (positive.max() if len(positive) else 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
