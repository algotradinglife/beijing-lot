"""Paired pre-event value selection crossed with frozen fixed-R3 support.

The decision layer is completed before evaluation labels are opened.  The
paired uncertainty distribution is calibrated only from same-issue
candidate/incumbent pairs in 2022, with each calibration issue carrying equal
total weight.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.top2_factorial.contract import FEATURE_COLUMNS
from src.top2_factorial.pipeline import (
    _attach_training_targets,
    _load_labels,
    _model,
    sha256_file,
)
from src.value_veto_r3_n7.pipeline import (
    _frame_sha,
    _markdown,
    _max_completed_recovery,
    _terminal_underwater,
    _worst_window,
    evaluation_labels,
    fit_oof_sp_intervals,
    prepare_value_surface,
)

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CALIBRATION_YEAR,
    CELLS,
    CONTRACT_ID,
    EVAL_YEARS,
    EXPECTED_EVALUATION_LABEL_FRAME_SHA256,
    EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256,
    EXPECTED_PAIR_CALIBRATION_FRAME_SHA256,
    EXPECTED_PREOUTCOME_BUNDLE_FRAME_SHA256,
    EXPECTED_PROBABILITY_SOURCE_SHA256,
    EXPECTED_SETTLEMENT_SOURCE_SHA256,
    EXPECTED_VALUE_SURFACE_FRAME_SHA256,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    MAX_RETAINED_MASS_DROP,
    MODEL_SELECTION_FIT_YEARS,
    MODEL_SELECTION_YEAR,
    N_LEGS,
    OUTCOMES,
    PAIR_LOWER_QUANTILE,
    PAYOUT_FACTOR,
    PROBABILITY_THRESHOLDS,
    R_DEPTH,
    SELECTORS,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    TICKETS,
    UNITS_PER_TICKET,
)


PAIR_COLUMNS = [
    "issue",
    "candidate_issue",
    "incumbent_issue",
    "candidate_match_idx",
    "incumbent_match_idx",
    "candidate_g_pred",
    "incumbent_g_pred",
    "candidate_g_actual",
    "incumbent_g_actual",
    "point_log_ratio",
    "realized_log_ratio",
    "paired_log_residual",
    "retained_mass_delta",
    "issue_weight",
]

VALUE_SURFACE_COLUMNS = [
    "issue",
    "issue_year",
    "issue_anchor_ts",
    "match_idx",
    "canonical_fixture_key",
    "causal_grade",
    "baseline_support",
    "qeu_support",
    "support_changed",
    "support_pressure",
    "retained_mass",
    *[f"q_eu_{code}" for code in OUTCOMES],
    *[f"q_line_{code}" for code in OUTCOMES],
    *[f"pred_sp_{code}" for code in OUTCOMES],
    "g_point",
]

FREEZE_COLUMNS = [
    "issue",
    "issue_year",
    "issue_anchor_ts",
    "cell",
    "selector",
    "r",
    "selected_match_ids",
    "support_json",
    "replacement_count",
    "ticket_count",
    "funded_units",
    "stake_cny",
]

PACKAGE_NAMES = (
    "sp_model_receipt.json",
    "sp_calibration_residuals.parquet",
    "evaluation_sp_predictions.parquet",
    "pair_calibration.parquet",
    "pair_calibration_receipt.json",
    "value_surface.parquet",
    "pair_opportunities.parquet",
    "preoutcome_bundles.parquet",
    "replacement_ledger.parquet",
    "freeze_receipt.json",
    "evaluation_labels.parquet",
    "settlement_source_receipt.json",
    "issue_bundles.parquet",
    "tickets.parquet",
    "support_attribution.parquet",
    "settlement_coverage_ledger.csv",
    "performance.csv",
    "risk_diagnostics.csv",
    "capital_paths.csv",
    "contrasts.csv",
    "baseline_parity.json",
    "decision.json",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _semantic_frame_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    if list(left.columns) != list(right.columns) or left.shape != right.shape:
        return False
    for column in left.columns:
        if pd.api.types.is_numeric_dtype(left[column]) and pd.api.types.is_numeric_dtype(right[column]):
            if not np.allclose(
                pd.to_numeric(left[column], errors="coerce"),
                pd.to_numeric(right[column], errors="coerce"),
                rtol=0,
                atol=1e-8,
                equal_nan=True,
            ):
                return False
        elif not left[column].fillna("<NA>").astype(str).equals(
            right[column].fillna("<NA>").astype(str)
        ):
            return False
    return True


def weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 1 or weights.ndim != 1 or len(values) != len(weights) or not len(values):
        raise ValueError("weighted quantile requires equal non-empty vectors")
    if not np.isfinite(values).all() or not np.isfinite(weights).all() or (weights < 0).any():
        raise ValueError("weighted quantile received invalid values or weights")
    total = float(weights.sum())
    if total <= 0 or not 0 <= quantile <= 1:
        raise ValueError("weighted quantile received invalid total weight or quantile")
    order = np.argsort(values, kind="stable")
    ordered_values = values[order]
    cumulative = np.cumsum(weights[order]) / total
    index = min(int(np.searchsorted(cumulative, quantile, side="left")), len(values) - 1)
    return float(ordered_values[index])


def _supported_value(row: pd.Series, sp_prefix: str, probability_prefix: str) -> float:
    support = tuple(str(code) for code in row["baseline_support"])
    return float(sum(
        float(row[f"{probability_prefix}{code}"]) * float(row[f"{sp_prefix}{code}"])
        for code in support
    ) / 2.0)


def _fixture_table_vectorized(frame: pd.DataFrame) -> pd.DataFrame:
    """Vectorized equivalent of the inherited fixture materializer for 10h rows."""

    keys = ["issue_code", "issue_year", "snapshot_kind", "canonical_fixture_key", "match_idx"]
    frame = frame.drop_duplicates([*keys, "outcome_code"], keep="first").copy()
    counts = frame.groupby(keys, observed=True)["outcome_code"].nunique()
    valid_index = counts[counts.eq(len(OUTCOMES))].index
    valid = pd.DataFrame(valid_index.tolist(), columns=keys)
    frame = frame.merge(valid, on=keys, validate="many_to_one")
    representative = frame.sort_values([*keys, "outcome_code"], kind="stable").drop_duplicates(keys)
    representative = representative.set_index(keys)

    def pivot(column: str, prefix: str) -> pd.DataFrame:
        wide = frame.pivot(index=keys, columns="outcome_code", values=column)
        wide = wide.loc[:, list(OUTCOMES)].rename(columns={code: f"{prefix}{code}" for code in OUTCOMES})
        return wide

    fixtures = pd.concat([
        pivot("q_eu_bjline", "q"),
        pivot("q_line_only_control", "line_q"),
        pivot("eu_vs_line_divergence", "div"),
    ], axis=1).reset_index()
    metadata = representative[[
        "issue_anchor_ts", "temporal_role", "native_handicap_line",
        "n_available_books", "causal_grade",
    ]].reset_index()
    fixtures = fixtures.merge(metadata, on=keys, validate="one_to_one")
    q = fixtures[[f"q{code}" for code in OUTCOMES]].to_numpy(float)
    # np.argsort is stable, so ties preserve the frozen 3/1/0 column order.
    order = np.argsort(-q, axis=1, kind="stable")
    code_array = np.asarray(OUTCOMES)
    fixtures["top1_code"] = code_array[order[:, 0]]
    fixtures["top2_codes"] = [tuple(code_array[row[:2]]) for row in order]
    fixtures["retained_mass"] = np.take_along_axis(q, order[:, :2], axis=1).sum(axis=1)
    fixtures["entropy"] = -(q * np.log(np.maximum(q, 1e-12))).sum(axis=1)
    fixtures["q_gap"] = np.take_along_axis(q, order[:, :1], axis=1).ravel() - np.take_along_axis(
        q, order[:, 1:2], axis=1
    ).ravel()
    fixtures["issue_anchor_ts"] = pd.to_datetime(fixtures["issue_anchor_ts"]).map(
        lambda value: value.isoformat()
    )
    fixtures["abs_handicap_line"] = fixtures["native_handicap_line"].abs()
    issue_keys = ["issue_code", "issue_year", "snapshot_kind"]
    grouped = fixtures.groupby(issue_keys, observed=True)
    fixtures["issue_retained_mean"] = grouped["retained_mass"].transform("mean")
    fixtures["issue_retained_std"] = grouped["retained_mass"].transform("std").fillna(0.0)
    divergence = fixtures[[f"div{code}" for code in OUTCOMES]].abs()
    fixtures["issue_div_abs_mean"] = pd.concat([
        grouped[f"div{code}"].transform(lambda values: values.abs().mean())
        for code in OUTCOMES
    ], axis=1).mean(axis=1)
    fixtures["retained_pct_rank"] = grouped["retained_mass"].rank(
        pct=True, method="average"
    )
    if not np.isfinite(divergence.to_numpy(float)).all():
        raise ValueError("non-finite divergence in calibration fixtures")
    return fixtures.rename(columns={"snapshot_kind": "horizon"})


def build_pair_calibration(
    data_root: Path,
    model_receipt: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Create a 2022 issue-balanced distribution of paired log-value error."""

    probability_path = (
        data_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    )
    settlement_path = data_root / "derived/beidan_xlsm/beidan_xlsm.sqlite"
    fit_years = (*MODEL_SELECTION_FIT_YEARS, MODEL_SELECTION_YEAR)
    probability_columns = [
        "canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind",
        "issue_anchor_ts", "issue_year", "temporal_role", "native_handicap_line",
        "n_available_books", "causal_grade", "mapping_accepted", "outcome_code",
        "q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence",
    ]
    probability = pd.read_parquet(
        probability_path,
        columns=probability_columns,
        filters=[
            ("issue_year", "in", [*fit_years, CALIBRATION_YEAR]),
            ("snapshot_kind", "==", "10h"),
        ],
    )
    probability["issue_code"] = probability["issue_code"].astype(str)
    probability["outcome_code"] = probability["outcome_code"].astype(str)
    probability = probability[
        probability["mapping_accepted"].fillna(False)
        & probability["q_eu_bjline"].notna()
    ].copy()
    fixtures = _fixture_table_vectorized(probability)
    labels = _load_labels(settlement_path, (*fit_years, CALIBRATION_YEAR))
    training = _attach_training_targets(
        fixtures[fixtures["issue_year"].isin((*fit_years, CALIBRATION_YEAR))],
        labels,
    )
    if "match_idx" not in training.columns:
        if not training["match_idx_x"].eq(training["match_idx_y"]).all():
            raise AssertionError("fixture and settlement match_idx disagree")
        training = training.rename(columns={"match_idx_x": "match_idx"}).drop(
            columns=["match_idx_y"]
        )
    training = training[training["horizon"].eq("10h")].copy()
    fit = training[training["issue_year"].isin(fit_years)].copy()
    calibration = training[training["issue_year"].eq(CALIBRATION_YEAR)].copy()
    if fit.empty or calibration.empty:
        raise ValueError("pair calibration fit or 2022 partition is empty")

    x_fit = fit.loc[:, FEATURE_COLUMNS].astype(float)
    x_calibration = calibration.loc[:, FEATURE_COLUMNS].astype(float)
    for code in OUTCOMES:
        params = model_receipt["model_selection"][code]["selected_params"]
        target = pd.to_numeric(fit[f"official_sp_{code}"], errors="coerce")
        mask = target.gt(0) & np.isfinite(target)
        estimator = _model(dict(params)).fit(
            x_fit.loc[mask],
            np.log1p(target.loc[mask]),
        )
        calibration[f"pred_sp_{code}"] = np.maximum(
            np.expm1(estimator.predict(x_calibration)),
            1.01,
        )

    calibration["baseline_support"] = calibration["top2_codes"].map(
        lambda value: "".join(map(str, value))
    )
    calibration["g_pred"] = calibration.apply(
        lambda row: _supported_value(row, "pred_sp_", "q"), axis=1
    )
    calibration["g_actual"] = calibration.apply(
        lambda row: _supported_value(row, "official_sp_", "q"), axis=1
    )
    if (
        not np.isfinite(calibration[["g_pred", "g_actual"]].to_numpy(float)).all()
        or calibration[["g_pred", "g_actual"]].le(0).any().any()
    ):
        raise ValueError("pair calibration contains invalid supported values")

    rows: list[dict[str, Any]] = []
    for issue, group in calibration.groupby("issue_code", sort=True, observed=True):
        group = group.sort_values(
            ["retained_mass", "match_idx"],
            ascending=[False, True],
            kind="stable",
        )
        if len(group) <= N_LEGS:
            continue
        incumbents = group.head(N_LEGS)
        candidates = group.iloc[N_LEGS:]
        issue_rows: list[dict[str, Any]] = []
        for candidate in candidates.itertuples(index=False):
            for incumbent in incumbents.itertuples(index=False):
                mass_delta = float(candidate.retained_mass - incumbent.retained_mass)
                if mass_delta < -MAX_RETAINED_MASS_DROP:
                    continue
                point_log_ratio = math.log(float(candidate.g_pred) / float(incumbent.g_pred))
                realized_log_ratio = math.log(float(candidate.g_actual) / float(incumbent.g_actual))
                issue_rows.append({
                    "issue": str(issue),
                    "candidate_issue": str(issue),
                    "incumbent_issue": str(issue),
                    "candidate_match_idx": int(candidate.match_idx),
                    "incumbent_match_idx": int(incumbent.match_idx),
                    "candidate_g_pred": float(candidate.g_pred),
                    "incumbent_g_pred": float(incumbent.g_pred),
                    "candidate_g_actual": float(candidate.g_actual),
                    "incumbent_g_actual": float(incumbent.g_actual),
                    "point_log_ratio": point_log_ratio,
                    "realized_log_ratio": realized_log_ratio,
                    "paired_log_residual": realized_log_ratio - point_log_ratio,
                    "retained_mass_delta": mass_delta,
                })
        if not issue_rows:
            continue
        issue_weight = 1.0 / len(issue_rows)
        for row in issue_rows:
            row["issue_weight"] = issue_weight
        rows.extend(issue_rows)

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError("no mass-admissible 2022 calibration pairs")
    if not frame["candidate_issue"].eq(frame["incumbent_issue"]).all():
        raise AssertionError("pair calibration crossed issue boundaries")
    issue_count = int(frame["issue"].nunique())
    frame["issue_weight"] = frame["issue_weight"] / issue_count
    weight_by_issue = frame.groupby("issue", observed=True)["issue_weight"].sum()
    if not np.allclose(weight_by_issue, 1.0 / issue_count, rtol=0, atol=1e-12):
        raise AssertionError("calibration issues do not have equal total weight")
    frame = frame.loc[:, PAIR_COLUMNS].sort_values(
        ["issue", "candidate_match_idx", "incumbent_match_idx"], kind="stable"
    ).reset_index(drop=True)
    frame_hash = _frame_sha(frame, PAIR_COLUMNS)
    receipt = {
        "contract": CONTRACT_ID,
        "calibration_year": CALIBRATION_YEAR,
        "fit_through_year": MODEL_SELECTION_YEAR,
        "candidate_definition": "outside_retained_mass_top7",
        "incumbent_definition": "retained_mass_top7",
        "same_issue_pairs_only": True,
        "max_retained_mass_drop": MAX_RETAINED_MASS_DROP,
        "pair_rows": int(len(frame)),
        "calibration_issues": issue_count,
        "each_issue_total_weight": float(1.0 / issue_count),
        "total_weight": float(frame["issue_weight"].sum()),
        "paired_residual_q10": weighted_quantile(
            frame["paired_log_residual"].to_numpy(float),
            frame["issue_weight"].to_numpy(float),
            PAIR_LOWER_QUANTILE,
        ),
        "pair_calibration_frame_sha256": frame_hash,
        "probability_source_sha256": sha256_file(probability_path),
        "settlement_source_sha256": sha256_file(settlement_path),
        "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
    }
    return frame, receipt


def attach_evaluation_proxy_context(data_root: Path, surface: pd.DataFrame) -> pd.DataFrame:
    """Attach frozen 10h line probabilities and proxy grade to the value surface."""

    probability_path = (
        data_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    )
    source = pd.read_parquet(
        probability_path,
        columns=[
            "issue_code", "issue_year", "canonical_fixture_key", "match_idx",
            "snapshot_kind", "mapping_accepted", "causal_grade", "outcome_code",
            "q_eu_bjline", "q_line_only_control",
        ],
        filters=[
            ("issue_year", "in", list(EVAL_YEARS)),
            ("snapshot_kind", "==", "10h"),
        ],
    )
    source = source[
        source["mapping_accepted"].fillna(False)
        & source["q_eu_bjline"].notna()
        & source["q_line_only_control"].notna()
    ].copy()
    source["issue"] = source["issue_code"].astype(str)
    source["outcome_code"] = source["outcome_code"].astype(str)
    keys = ["issue", "issue_year", "canonical_fixture_key", "match_idx"]
    source = source.drop_duplicates([*keys, "outcome_code"], keep="first")
    complete = source.groupby(keys, observed=True)["outcome_code"].nunique()
    if not complete.eq(len(OUTCOMES)).all():
        raise AssertionError("evaluation proxy context lacks complete 3-way fixtures")
    wide = source.pivot(
        index=keys,
        columns="outcome_code",
        values=["q_eu_bjline", "q_line_only_control"],
    )
    wide.columns = [
        f"q_eu_source_{code}" if metric == "q_eu_bjline" else f"q_line_source_{code}"
        for metric, code in wide.columns
    ]
    grade = source.groupby(keys, observed=True)["causal_grade"].agg(
        lambda values: values.astype(str).iloc[0]
        if values.astype(str).nunique() == 1
        else "MIXED"
    )
    context = wide.join(grade.rename("causal_grade")).reset_index()
    enriched = surface.merge(context, on=keys, how="left", validate="one_to_one")
    if enriched["causal_grade"].isna().any():
        raise AssertionError("value surface is not fully covered by the 10h proxy source")
    for code in OUTCOMES:
        source_values = enriched.pop(f"q_eu_source_{code}").to_numpy(float)
        if not np.allclose(
            enriched[f"q_eu_{code}"].to_numpy(float),
            source_values,
            rtol=0,
            atol=1e-12,
        ):
            raise AssertionError(f"q_eu_{code} differs from the frozen 10h source")
        line_source = enriched.pop(f"q_line_source_{code}")
        if f"q_line_{code}" in enriched:
            if not np.allclose(
                enriched[f"q_line_{code}"].to_numpy(float),
                line_source.to_numpy(float),
                rtol=0,
                atol=1e-12,
            ):
                raise AssertionError(f"q_line_{code} differs from the frozen 10h source")
        else:
            enriched[f"q_line_{code}"] = line_source
    return enriched


def paired_metrics(
    point_log_ratio: float,
    calibration: pd.DataFrame,
) -> tuple[float, float]:
    cache = calibration.attrs.get("paired_distribution_cache")
    if cache is None:
        residual = calibration["paired_log_residual"].to_numpy(float)
        weights = calibration["issue_weight"].to_numpy(float)
        order = np.argsort(residual, kind="stable")
        sorted_residual = residual[order]
        sorted_weights = weights[order]
        cumulative = np.cumsum(sorted_weights) / sorted_weights.sum()
        cache = (
            sorted_residual,
            cumulative,
            weighted_quantile(residual, weights, PAIR_LOWER_QUANTILE),
        )
        calibration.attrs["paired_distribution_cache"] = cache
    sorted_residual, cumulative, lower_quantile = cache
    index = int(np.searchsorted(sorted_residual, -point_log_ratio, side="right"))
    probability = float(1.0 - (cumulative[index - 1] if index else 0.0))
    lower_margin = float(point_log_ratio + lower_quantile)
    return probability, lower_margin


def _selector_accepts(selector: str, point_log_ratio: float, probability: float, lower: float) -> bool:
    if point_log_ratio <= 0:
        return False
    if selector == "POINT":
        return True
    if selector == "PAIR_L10":
        return lower > 0
    if selector.startswith("P"):
        threshold = int(selector[1:]) / 100.0
        if threshold not in PROBABILITY_THRESHOLDS:
            raise ValueError(f"undeclared probability threshold: {selector}")
        return probability >= threshold
    raise ValueError(f"unknown selector: {selector}")


def _pair_row(candidate: Any, incumbent: Any, calibration: pd.DataFrame) -> dict[str, Any]:
    point_log_ratio = math.log(float(candidate.g_point) / float(incumbent.g_point))
    probability, lower = paired_metrics(point_log_ratio, calibration)
    return {
        "issue": str(candidate.issue),
        "issue_year": int(candidate.issue_year),
        "candidate_match_idx": int(candidate.match_idx),
        "incumbent_match_idx": int(incumbent.match_idx),
        "candidate_g_point": float(candidate.g_point),
        "incumbent_g_point": float(incumbent.g_point),
        "point_delta_g": float(candidate.g_point - incumbent.g_point),
        "point_log_ratio": point_log_ratio,
        "paired_probability_positive": probability,
        "paired_l10_log_margin": lower,
        "candidate_retained_mass": float(candidate.retained_mass),
        "incumbent_retained_mass": float(incumbent.retained_mass),
        "retained_mass_delta": float(candidate.retained_mass - incumbent.retained_mass),
    }


def enumerate_pair_opportunities(
    surface: pd.DataFrame,
    calibration: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (_, _), group in surface.groupby(["issue", "issue_year"], sort=True, observed=True):
        rows.extend(_evaluation_pair_rows(group, calibration))
    return pd.DataFrame(rows).sort_values(
        ["issue_year", "issue", "candidate_match_idx", "incumbent_match_idx"],
        kind="stable",
    ).reset_index(drop=True)


def _evaluation_pair_rows(
    group: pd.DataFrame,
    calibration: pd.DataFrame,
) -> list[dict[str, Any]]:
    initial = group.sort_values(
        ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
    ).head(N_LEGS)
    candidates = group[~group["match_idx"].isin(initial["match_idx"])]
    rows: list[dict[str, Any]] = []
    for candidate in candidates.itertuples(index=False):
        for incumbent in initial.itertuples(index=False):
            if candidate.issue != incumbent.issue:
                raise AssertionError("evaluation pair crossed issue boundary")
            if float(candidate.retained_mass - incumbent.retained_mass) < -MAX_RETAINED_MASS_DROP:
                continue
            rows.append(_pair_row(candidate, incumbent, calibration))
    return rows


def select_pairwise(
    group: pd.DataFrame,
    calibration: pd.DataFrame,
    selector: str,
    pair_rows: list[dict[str, Any]] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monotone same-issue one-for-one replacement before outcome support."""

    initial = group.sort_values(
        ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
    ).head(N_LEGS)
    selected_ids = set(initial["match_idx"].astype(int))
    replaceable_incumbent_ids = set(selected_ids)
    available_candidate_ids = set(
        group.loc[~group["match_idx"].isin(selected_ids), "match_idx"].astype(int)
    )
    rows: list[dict[str, Any]] = []
    # Pair scores are static and roles are frozen to the original Top-7 versus
    # the original outside pool.  Precompute once, then greedily take the best
    # still-disjoint pair; this is exactly equivalent to rebuilding the same
    # lawful list after every monotone step.
    pair_rows = _evaluation_pair_rows(group, calibration) if pair_rows is None else pair_rows
    lawful = [
        pair for pair in pair_rows
        if _selector_accepts(
            selector,
            pair["point_log_ratio"],
            pair["paired_probability_positive"],
            pair["paired_l10_log_margin"],
        )
    ]
    lawful.sort(key=lambda row: (
            -row["paired_probability_positive"],
            -row["paired_l10_log_margin"],
            -row["point_log_ratio"],
            -row["retained_mass_delta"],
            row["candidate_match_idx"],
            row["incumbent_match_idx"],
    ))
    max_steps = min(len(replaceable_incumbent_ids), len(available_candidate_ids))
    for chosen in lawful:
        if len(rows) >= max_steps:
            break
        incumbent_id = int(chosen["incumbent_match_idx"])
        candidate_id = int(chosen["candidate_match_idx"])
        if (
            incumbent_id not in replaceable_incumbent_ids
            or candidate_id not in available_candidate_ids
        ):
            continue
        selected_ids.remove(incumbent_id)
        selected_ids.add(candidate_id)
        replaceable_incumbent_ids.remove(incumbent_id)
        available_candidate_ids.remove(candidate_id)
        rows.append({"selector": selector, "step": len(rows) + 1, **chosen})

    selected = group[group["match_idx"].isin(selected_ids)].copy()
    if len(selected) != N_LEGS:
        raise AssertionError("pairwise selector did not retain exactly seven matches")
    ledger = pd.DataFrame(rows)
    return selected.sort_values("match_idx", kind="stable"), ledger


def freeze_bundles(
    surface: pd.DataFrame,
    calibration: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    ledgers: list[pd.DataFrame] = []
    for (issue, year, anchor), group in surface.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        if len(group) < N_LEGS:
            continue
        selections: dict[str, pd.DataFrame] = {
            "S0": group.sort_values(
                ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
            ).head(N_LEGS).sort_values("match_idx", kind="stable")
        }
        issue_pair_rows = _evaluation_pair_rows(group, calibration)
        for selector in SELECTORS:
            selected, ledger = select_pairwise(
                group, calibration, selector, pair_rows=issue_pair_rows
            )
            selections[selector] = selected
            if not ledger.empty:
                ledgers.append(ledger)

        for selector, selected in selections.items():
            for r in (0, R_DEPTH):
                cell = f"{selector}R{r}A0"
                rank = selected["support_pressure"].rank(
                    method="first", ascending=False
                ).astype(int)
                activated = selected["support_changed"].astype(bool) & rank.le(r)
                supports = np.where(activated, selected["qeu_support"], selected["baseline_support"])
                support_map = {
                    str(int(match_idx)): list(str(support))
                    for match_idx, support in zip(selected["match_idx"], supports, strict=True)
                }
                baseline_ids = set(selections["S0"]["match_idx"].astype(int))
                selected_ids = set(selected["match_idx"].astype(int))
                rows.append({
                    "issue": str(issue),
                    "issue_year": int(year),
                    "issue_anchor_ts": str(anchor),
                    "cell": cell,
                    "selector": selector,
                    "r": r,
                    "selected_match_ids": "|".join(map(str, sorted(selected_ids))),
                    "support_json": json.dumps(support_map, sort_keys=True, separators=(",", ":")),
                    "replacement_count": int(len(baseline_ids - selected_ids)),
                    "mean_retained_mass": float(selected["retained_mass"].mean()),
                    "min_retained_mass": float(selected["retained_mass"].min()),
                    "portfolio_g_point": float(math.prod(selected["g_point"])),
                    "portfolio_gm_point": float(math.prod(selected["g_point"]) ** (1 / N_LEGS)),
                    "portfolio_diagnostic": float(PAYOUT_FACTOR * math.prod(selected["g_point"])),
                    "activated_changes": int(activated.sum()),
                    "ticket_count": TICKETS,
                    "funded_units": FUNDED_UNITS,
                    "stake_cny": ISSUE_STAKE_CNY,
                })
    frozen = pd.DataFrame(rows)
    if set(frozen["cell"].unique()) != set(CELLS):
        raise AssertionError("predeclared selector × R cells are incomplete")
    replacements = pd.concat(ledgers, ignore_index=True) if ledgers else pd.DataFrame(
        columns=[
            "selector", "step", "issue", "issue_year", "candidate_match_idx",
            "incumbent_match_idx", "candidate_g_point", "incumbent_g_point",
            "point_delta_g", "point_log_ratio", "paired_probability_positive",
            "paired_l10_log_margin", "candidate_retained_mass",
            "incumbent_retained_mass", "retained_mass_delta",
        ]
    )
    return frozen.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "cell"], kind="stable"
    ).reset_index(drop=True), replacements


def settle_bundles(
    frozen: pd.DataFrame,
    labels: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    label_map = labels.set_index(["issue_code", "match_idx"])
    bundle_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    for bundle in frozen.itertuples(index=False):
        support_map = json.loads(bundle.support_json)
        selected: list[tuple[int, str, float]] = []
        for match_text in sorted(support_map, key=int):
            key = (str(bundle.issue), int(match_text))
            if key not in label_map.index:
                selected = []
                break
            label = label_map.loc[key]
            if isinstance(label, pd.DataFrame):
                raise ValueError("duplicate evaluation settlement identity")
            trusted = label["has_trusted_settlement"]
            if trusted not in (0, 1, False, True):
                raise TypeError("has_trusted_settlement must be a strict boolean domain")
            if int(trusted) != 1:
                selected = []
                break
            result = str(label["result_code"])
            winning_sp = float(label["winning_sp"])
            if result not in OUTCOMES or not np.isfinite(winning_sp) or winning_sp <= 0:
                raise ValueError("trusted result or winning SP is outside its domain")
            selected.append((int(match_text), result, winning_sp))
        if len(selected) != N_LEGS:
            continue
        supports = [support_map[str(match_idx)] for match_idx, _, _ in selected]
        included = [result in support for (_, result, _), support in zip(selected, supports, strict=True)]
        misses = int(sum(not value for value in included))
        gross = float(
            STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR
            * math.prod(sp for _, _, sp in selected)
        ) if misses == 0 else 0.0
        bundle_rows.append({
            **bundle._asdict(),
            "gross_cny": gross,
            "pnl_cny": gross - ISSUE_STAKE_CNY,
            "miss_count": misses,
            "hit": misses == 0,
        })
        for ordinal, outcomes in enumerate(itertools.product(*supports)):
            ticket_rows.append({
                "issue": str(bundle.issue),
                "issue_year": int(bundle.issue_year),
                "cell": bundle.cell,
                "ticket_ordinal": ordinal,
                "ticket_code": "|".join(outcomes),
                "units": UNITS_PER_TICKET,
                "stake_cny": UNITS_PER_TICKET * STAKE_PER_UNIT_CNY,
            })
        for (match_idx, result, winning_sp), support, ok in zip(
            selected, supports, included, strict=True
        ):
            attribution_rows.append({
                "issue": str(bundle.issue),
                "issue_year": int(bundle.issue_year),
                "cell": bundle.cell,
                "match_idx": match_idx,
                "active_support": "".join(support),
                "result_code": result,
                "winning_sp": winning_sp,
                "realized_in_support": bool(ok),
            })

    bundles = pd.DataFrame(bundle_rows)
    tickets = pd.DataFrame(ticket_rows)
    attribution = pd.DataFrame(attribution_rows)
    if bundles.empty:
        return bundles, tickets, attribution
    counts = bundles.groupby(["issue", "issue_year"], observed=True)["cell"].nunique()
    common_keys = counts[counts.eq(len(CELLS))].index
    common = pd.DataFrame(common_keys.tolist(), columns=["issue", "issue_year"])
    bundles = bundles.merge(common, on=["issue", "issue_year"], validate="many_to_one")
    tickets = tickets.merge(common, on=["issue", "issue_year"], validate="many_to_one")
    attribution = attribution.merge(common, on=["issue", "issue_year"], validate="many_to_one")
    _assert_matched(bundles, tickets)
    return bundles, tickets, attribution


def _assert_matched(bundles: pd.DataFrame, tickets: pd.DataFrame) -> None:
    if not bundles.groupby(["issue", "issue_year"])["cell"].nunique().eq(len(CELLS)).all():
        raise AssertionError("selector × R exact-common support failed")
    receipt = tickets.groupby(["issue", "issue_year", "cell"], observed=True).agg(
        rows=("ticket_code", "size"),
        unique=("ticket_code", "nunique"),
        units=("units", "sum"),
        stake=("stake_cny", "sum"),
    )
    if not receipt["rows"].eq(TICKETS).all() or not receipt["unique"].eq(TICKETS).all():
        raise AssertionError("ticket identity is not exactly 128 distinct tickets")
    if not receipt["units"].eq(FUNDED_UNITS).all() or not np.allclose(
        receipt["stake"], ISSUE_STAKE_CNY, rtol=0, atol=1e-12
    ):
        raise AssertionError("ticket funding mismatch")


def settlement_coverage_ledger(
    frozen: pd.DataFrame,
    labels: pd.DataFrame,
    bundles: pd.DataFrame,
) -> pd.DataFrame:
    label_map = labels.drop_duplicates(["issue_code", "match_idx"]).set_index(
        ["issue_code", "match_idx"]
    )
    if not label_map.index.is_unique:
        raise AssertionError("settlement labels are not unique by issue and match")
    settled = set(bundles["issue"].astype(str))
    rows: list[dict[str, Any]] = []
    for (issue, year), group in frozen.groupby(["issue", "issue_year"], sort=True):
        required = sorted({
            int(match_idx)
            for encoded in group["selected_match_ids"]
            for match_idx in str(encoded).split("|")
        })
        missing: list[int] = []
        untrusted: list[int] = []
        invalid: list[int] = []
        for match_idx in required:
            key = (str(issue), match_idx)
            if key not in label_map.index:
                missing.append(match_idx)
                continue
            label = label_map.loc[key]
            if int(label["has_trusted_settlement"]) != 1:
                untrusted.append(match_idx)
            elif (
                str(label["result_code"]) not in OUTCOMES
                or not np.isfinite(float(label["winning_sp"]))
                or float(label["winning_sp"]) <= 0
            ):
                invalid.append(match_idx)
        included = str(issue) in settled
        reasons = []
        if missing:
            reasons.append("missing_match_label")
        if untrusted:
            reasons.append("untrusted_settlement")
        if invalid:
            reasons.append("invalid_result_or_sp")
        if not included and not reasons:
            reasons.append("failed_all_cell_common_support")
        rows.append({
            "issue": str(issue),
            "issue_year": int(year),
            "status": "INCLUDED" if included else "EXCLUDED",
            "reason": "included" if included else "+".join(reasons),
            "required_matches": len(required),
            "missing_match_indices": "|".join(map(str, missing)),
            "untrusted_match_indices": "|".join(map(str, untrusted)),
            "invalid_match_indices": "|".join(map(str, invalid)),
        })
    return pd.DataFrame(rows)


def _longest_run(mask: np.ndarray) -> int:
    return max(
        (sum(1 for _ in run) for value, run in itertools.groupby(mask) if value),
        default=0,
    )


def _ex_largest(values: np.ndarray) -> float:
    if not len(values):
        return float("nan")
    return float(values.sum() - values[np.argmax(np.abs(values))])


def _period_groups(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [
        (str(year), frame[frame["issue_year"].eq(year)].copy()) for year in EVAL_YEARS
    ] + [("ALL", frame.copy())]


def evaluate(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summaries: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    for cell, cell_group in bundles.groupby("cell", sort=True, observed=True):
        for period, group in _period_groups(cell_group):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            if group.empty:
                continue
            pnl = group["pnl_cny"].to_numpy(float)
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            equity = np.r_[STARTING_CAPITAL_CNY, capital]
            peaks = np.maximum.accumulate(equity)
            drawdown = (peaks - equity) / np.maximum(peaks, 1e-9)
            summaries.append({
                "cell": cell,
                "period": period,
                "issues": int(len(group)),
                "stake_cny": float(group["stake_cny"].sum()),
                "gross_cny": float(group["gross_cny"].sum()),
                "pnl_cny": float(pnl.sum()),
                "ending_capital_cny": float(capital[-1]),
                "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                "hit_issues": int(group["hit"].sum()),
                "hit_rate": float(group["hit"].mean()),
                "miss_by_1": int(group["miss_count"].eq(1).sum()),
                "miss_by_2": int(group["miss_count"].eq(2).sum()),
                "mean_replacements": float(group["replacement_count"].mean()),
            })
            risks.append({
                "cell": cell,
                "period": period,
                "max_drawdown_fraction": float(drawdown.max()),
                "max_consecutive_losing_issues": _longest_run(pnl < 0),
                "worst_rolling_5_cny": _worst_window(pnl, 5),
                "worst_rolling_10_cny": _worst_window(pnl, 10),
                "worst_rolling_20_cny": _worst_window(pnl, 20),
                "max_completed_recovery_issues": _max_completed_recovery(equity),
                "terminal_underwater_issues": _terminal_underwater(equity),
                "largest_payout_share": float(group["gross_cny"].max() / max(group["gross_cny"].sum(), 1e-9)),
                "payout_hhi": float(
                    np.square(group["gross_cny"].to_numpy(float) / group["gross_cny"].sum()).sum()
                    if group["gross_cny"].sum() > 0 else 0.0
                ),
            })
            for order, row in enumerate(group.itertuples(index=False), start=1):
                paths.append({
                    "cell": cell,
                    "period": period,
                    "issue_order": order,
                    "issue": str(row.issue),
                    "issue_year": int(row.issue_year),
                    "issue_anchor_ts": str(row.issue_anchor_ts),
                    "pnl_cny": float(row.pnl_cny),
                    "capital_cny": float(capital[order - 1]),
                })

    contrast_rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for period, subset in _period_groups(bundles):
        pivot = subset.pivot(index="issue", columns="cell", values="pnl_cny")
        definitions: list[tuple[str, str, str]] = [("R3_UNDER_S0", "S0R3A0", "S0R0A0")]
        for selector in SELECTORS:
            definitions.extend([
                (f"{selector}_UNDER_R3", f"{selector}R3A0", "S0R3A0"),
                (f"{selector}_UNDER_R0", f"{selector}R0A0", "S0R0A0"),
                (f"R3_UNDER_{selector}", f"{selector}R3A0", f"{selector}R0A0"),
            ])
        for name, challenger, control in definitions:
            delta = (pivot[challenger] - pivot[control]).to_numpy(float)
            draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
            contrast_rows.append({
                "contrast": name,
                "challenger": challenger,
                "control": control,
                "period": period,
                "issues": int(len(delta)),
                "lift_cny": float(delta.sum()),
                "ex_largest_lift_cny": _ex_largest(delta),
                "bootstrap_p05_cny": float(np.quantile(draws, 0.05)),
                "bootstrap_p50_cny": float(np.quantile(draws, 0.50)),
                "bootstrap_p95_cny": float(np.quantile(draws, 0.95)),
                "bootstrap_positive_fraction": float((draws > 0).mean()),
            })
        for selector in SELECTORS:
            delta = (
                (pivot[f"{selector}R3A0"] - pivot["S0R3A0"])
                - (pivot[f"{selector}R0A0"] - pivot["S0R0A0"])
            ).to_numpy(float)
            draws = rng.choice(delta, size=(BOOTSTRAP_DRAWS, len(delta)), replace=True).sum(axis=1)
            contrast_rows.append({
                "contrast": f"{selector}_R3_INTERACTION",
                "challenger": f"({selector}R3A0-S0R3A0)",
                "control": f"({selector}R0A0-S0R0A0)",
                "period": period,
                "issues": int(len(delta)),
                "lift_cny": float(delta.sum()),
                "ex_largest_lift_cny": _ex_largest(delta),
                "bootstrap_p05_cny": float(np.quantile(draws, 0.05)),
                "bootstrap_p50_cny": float(np.quantile(draws, 0.50)),
                "bootstrap_p95_cny": float(np.quantile(draws, 0.95)),
                "bootstrap_positive_fraction": float((draws > 0).mean()),
            })
    return (
        pd.DataFrame(summaries),
        pd.DataFrame(risks),
        pd.DataFrame(paths),
        pd.DataFrame(contrast_rows),
    )


def baseline_parity(repo_root: Path, bundles: pd.DataFrame) -> dict[str, Any]:
    accepted = pd.read_parquet(repo_root / "results/qeu_threshold_n7/issue_bundles.parquet")
    accepted = accepted[accepted["arm"].isin(["R0", "R3_CORRECTED"])].copy()
    accepted["cell"] = accepted["arm"].map({"R0": "S0R0A0", "R3_CORRECTED": "S0R3A0"})
    current = bundles[bundles["cell"].isin(["S0R0A0", "S0R3A0"])].copy()
    joined = current.merge(
        accepted[["issue", "issue_year", "cell", "selected_match_ids", "support_json", "gross_cny"]],
        on=["issue", "issue_year", "cell"],
        suffixes=("_current", "_accepted"),
        validate="one_to_one",
    )
    checks = {
        "rows": int(len(joined)),
        "expected_common_rows": int(len(current)),
        "accepted_full_rows": int(len(accepted)),
        "rows_excluded_by_all_cell_common_support": int(len(accepted) - len(joined)),
        "match_identity": bool(
            joined["selected_match_ids_current"].eq(joined["selected_match_ids_accepted"]).all()
        ),
        "support_identity": bool(
            joined["support_json_current"].eq(joined["support_json_accepted"]).all()
        ),
        "gross_identity_rtol0_atol1e_8": bool(np.allclose(
            joined["gross_cny_current"], joined["gross_cny_accepted"], rtol=0, atol=1e-8
        )),
    }
    checks["pass"] = bool(
        checks["rows"] == checks["expected_common_rows"]
        and checks["match_identity"]
        and checks["support_identity"]
        and checks["gross_identity_rtol0_atol1e_8"]
    )
    return checks


def decide(
    contrasts: pd.DataFrame,
    replacements: pd.DataFrame,
    frozen_issue_count: int,
) -> dict[str, Any]:
    candidates: list[str] = []
    tail_only: list[str] = []
    selector_rows: list[dict[str, Any]] = []
    for selector in SELECTORS:
        annual = contrasts[
            contrasts["contrast"].eq(f"{selector}_UNDER_R3")
            & contrasts["period"].isin([str(year) for year in EVAL_YEARS])
        ].sort_values("period")
        action_issues = int(
            replacements.loc[replacements["selector"].eq(selector), "issue"].nunique()
        ) if not replacements.empty else 0
        nontrivial = 0 < action_issues < frozen_issue_count
        raw_both = bool(len(annual) == 2 and annual["lift_cny"].gt(0).all())
        ex_both = bool(len(annual) == 2 and annual["ex_largest_lift_cny"].gt(0).all())
        if nontrivial and raw_both and ex_both:
            candidates.append(selector)
        elif nontrivial and raw_both:
            tail_only.append(selector)
        selector_rows.append({
            "selector": selector,
            "action_issues": action_issues,
            "action_fraction_of_frozen_issues": action_issues / max(frozen_issue_count, 1),
            "raw_lift_positive_both_years": raw_both,
            "ex_largest_lift_positive_both_years": ex_both,
        })
    if candidates:
        verdict = "PAIRED_VALUE_CANDIDATE"
    elif tail_only:
        verdict = "TAIL_ONLY"
    else:
        verdict = "NO_INCREMENT"
    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "verdict": verdict,
        "candidate_selectors": candidates,
        "tail_only_selectors": tail_only,
        "selector_diagnostics": selector_rows,
        "replacement_rows": int(len(replacements)),
        "replacement_issues": int(replacements["issue"].nunique()) if not replacements.empty else 0,
        "promotable_to_210": False,
        "modifies_218": False,
        "historical_only": True,
        "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
        "payout_factor_application": "ticket_level_once",
    }


def _write_figures(
    repo_root: Path,
    paths: pd.DataFrame,
    contrasts: pd.DataFrame,
    replacements: pd.DataFrame,
) -> list[Path]:
    folder = repo_root / "docs/research/figures"
    folder.mkdir(parents=True, exist_ok=True)
    capital_path = folder / "issue_345_paired_value_capital.png"
    view = paths[
        paths["period"].eq("ALL")
        & paths["cell"].isin(["S0R3A0", *[f"{selector}R3A0" for selector in SELECTORS]])
    ]
    fig, axis = plt.subplots(figsize=(12, 5.5))
    for cell, group in view.groupby("cell", sort=True):
        axis.plot(group["issue_order"], group["capital_cny"], label=cell, linewidth=1.2)
    axis.axhline(STARTING_CAPITAL_CNY, color="black", linewidth=0.8)
    axis.set(
        title="#345 continuous 2023–2024 capital — paired selectors under R3",
        xlabel="Issue order",
        ylabel="CNY",
    )
    axis.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(capital_path, dpi=160)
    plt.close(fig)

    curve_path = folder / "issue_345_paired_value_curve.png"
    lift_view = contrasts[
        contrasts["contrast"].isin([f"{selector}_UNDER_R3" for selector in SELECTORS])
        & contrasts["period"].isin([str(year) for year in EVAL_YEARS])
    ].copy()
    lift_view["selector"] = lift_view["contrast"].str.replace("_UNDER_R3", "", regex=False)
    pivot = lift_view.pivot(index="selector", columns="period", values="lift_cny").reindex(SELECTORS)
    action_counts = (
        replacements.groupby("selector", observed=True)["issue"].nunique().reindex(SELECTORS).fillna(0)
        if not replacements.empty else pd.Series(0, index=SELECTORS)
    )
    fig, axis = plt.subplots(figsize=(11, 5))
    pivot.plot.bar(ax=axis)
    axis.axhline(0, color="black", linewidth=0.8)
    axis.set(title="#345 paired value selection lift under fixed R3", ylabel="Matched lift (CNY)")
    secondary = axis.twinx()
    secondary.plot(range(len(SELECTORS)), action_counts.to_numpy(), color="black", marker="o")
    secondary.set_ylabel("Issues with ≥1 replacement")
    fig.tight_layout()
    fig.savefig(curve_path, dpi=160)
    plt.close(fig)
    return [capital_path, curve_path]


def _write_report(
    repo_root: Path,
    decision: dict[str, Any],
    performance: pd.DataFrame,
    risk: pd.DataFrame,
    contrasts: pd.DataFrame,
    replacements: pd.DataFrame,
    pair_receipt: dict[str, Any],
    parity: dict[str, Any],
    coverage: pd.DataFrame,
) -> Path:
    path = repo_root / "docs/research/Issue-Paired-Value-R3-N7.md"
    replacement_summary = (
        replacements.groupby(["selector", "issue_year"], observed=True).agg(
            replacement_rows=("step", "size"),
            action_issues=("issue", "nunique"),
            median_point_delta_g=("point_delta_g", "median"),
            median_probability=("paired_probability_positive", "median"),
            median_l10_log_margin=("paired_l10_log_margin", "median"),
        ).reset_index()
        if not replacements.empty
        else pd.DataFrame(columns=[
            "selector", "issue_year", "replacement_rows", "action_issues",
            "median_point_delta_g", "median_probability", "median_l10_log_margin",
        ])
    )
    primary_contrasts = contrasts[
        contrasts["contrast"].isin([f"{selector}_UNDER_R3" for selector in SELECTORS])
    ]
    r3_performance = performance[
        performance["cell"].isin(["S0R3A0", *[f"{selector}R3A0" for selector in SELECTORS]])
    ]
    r3_risk = risk[
        risk["cell"].isin(["S0R3A0", *[f"{selector}R3A0" for selector in SELECTORS]])
    ]
    decision_table = r3_performance[r3_performance["period"].eq("ALL")][[
        "cell", "issues", "ending_capital_cny", "capital_return", "hit_rate",
    ]].merge(
        r3_risk[r3_risk["period"].eq("ALL")][[
            "cell", "max_drawdown_fraction", "max_consecutive_losing_issues",
            "max_completed_recovery_issues", "terminal_underwater_issues",
        ]],
        on="cell",
        validate="one_to_one",
    ).sort_values("ending_capital_cny", ascending=False, kind="stable")
    accepted_performance = pd.read_csv(
        repo_root / "results/qeu_threshold_n7/performance.csv"
    )
    accepted_risk = pd.read_csv(
        repo_root / "results/qeu_threshold_n7/risk_diagnostics.csv"
    )
    prior_baseline = accepted_performance[
        accepted_performance["arm"].eq("R3_CORRECTED")
    ][[
        "issue_year", "issues", "ending_capital_cny", "capital_return", "hit_rate",
    ]].merge(
        accepted_risk[accepted_risk["arm"].eq("R3_CORRECTED")][[
            "issue_year", "max_drawdown_fraction", "max_consecutive_losing_issues",
        ]],
        on="issue_year",
        validate="one_to_one",
    )
    all_contrasts = contrasts[contrasts["period"].eq("ALL")].set_index("contrast")
    baseline_r3_lift = all_contrasts.loc["R3_UNDER_S0"]
    strict_selection_lift = all_contrasts.loc["PAIR_L10_UNDER_R3"]
    strict_r3_lift = all_contrasts.loc["R3_UNDER_PAIR_L10"]
    strict_interaction = all_contrasts.loc["PAIR_L10_R3_INTERACTION"]
    excluded = coverage[coverage["status"].eq("EXCLUDED")]
    text = f"""# Issue #345 — Paired value selection × fixed R3 on Top-2 N7

## Five-minute decision

**Verdict: `{decision['verdict']}`.** This experiment replaces #342's unfair
candidate-marginal-lower-bound versus incumbent-marginal-upper-bound screen with
a same-issue paired error distribution. Match selection is completed first;
fixed R3 is recomputed only inside each final seven-match set.

This remains historical exploration on a `10h` `RETROSPECTIVE_RELATIVE_PROXY`.
It does not change #210 or #218 and makes no exact-clock or deployable claim.

## Frozen design

- Exact #319 probability Top-2 starting selector; N7 throughout.
- `POINT`, `P50`, `P60`, `P70`, `P80`, and `PAIR_L10` are all predeclared.
- Every selector is crossed with R0 and corrected fixed R3; A0 stays equal.
- Exactly 128 distinct tickets, 512 CNY2 units and CNY1,024 per issue.
- The Beijing 0.65 payout factor is applied once to a complete winning N7 ticket.
- 2014–2020 selects model candidates, 2021 tunes, 2022 alone calibrates paired
  error, and 2023/2024 are exposed historical evaluation years.

## Paired calibration

- Calibration issues: {pair_receipt['calibration_issues']}
- Same-issue candidate/incumbent rows: {pair_receipt['pair_rows']}
- Each issue carries equal total weight: {pair_receipt['each_issue_total_weight']:.8f}
- Issue-balanced paired log-residual q10: {pair_receipt['paired_residual_q10']:.6f}

## Replacement/action curve

{_markdown(replacement_summary)}

## Absolute R3 performance

{_markdown(r3_performance)}

## Decision table — capital and path risk together

{_markdown(decision_table)}

## Accepted #338 baseline on its original 105-issue denominator

{_markdown(prior_baseline)}

The current experiment does not redefine that baseline. Its all-cell comparison
uses 96 issues because every one of the 14 cells must settle on the same issue
set. On those 96 issues, `S0R3A0` is exactly identical to accepted #338 row by
row; the higher current terminal capital is a denominator effect, not a new
baseline improvement.

## Primary matched selection lift under R3

{_markdown(primary_contrasts)}

## Adversarial PI interpretation

1. The accepted R3 support layer remains the strongest signal on this matched
   denominator: `R3_UNDER_S0` adds CNY {baseline_r3_lift['lift_cny']:.0f}, and
   its issue-bootstrap p05 is CNY {baseline_r3_lift['bootstrap_p05_cny']:.0f}.
2. `PAIR_L10` is the least damaging selector under R3, but it still loses CNY
   {abs(strict_selection_lift['lift_cny']):.0f} against `S0R3`. Removing each
   arm's largest payout reverses that comparison to CNY
   {strict_selection_lift['ex_largest_lift_cny']:.0f}; this is a tail-shape
   observation, not evidence of superior expected capital.
3. R3 still adds CNY {strict_r3_lift['lift_cny']:.0f} inside `PAIR_L10`, while
   the selector×R3 interaction is CNY {strict_interaction['lift_cny']:.0f} and
   its bootstrap interval crosses zero. Selection and outcome support therefore
   cannot be treated as additive, but strict value screening does not erase all
   of R3's contribution.
4. `P70R3` reduces drawdown and losing-run length, yet gives up most of the
   terminal capital. No selector dominates `S0R3` jointly on capital, drawdown
   and losing runs.
5. Even `PAIR_L10` acts in 100/119 frozen issues. The supposedly conservative
   value rule is not sparse in practice; the negative result may reflect
   replacement breadth as well as imperfect SP-value prediction.

This report does not choose a replacement-count cap or a new probability
threshold after seeing outcomes. The defensible handoff is to keep R3 frozen,
carry paired value as a diagnostic/risk feature, and test N=3–10 against each
N's own probability Top-2/R3 baseline before any MoE construction.

## Path risk under R3

{_markdown(r3_risk)}

## Denominator and parity

- Frozen issues: {len(coverage)}
- Exact all-cell settled issues: {int(coverage['status'].eq('INCLUDED').sum())}
- Excluded issues: {len(excluded)}; reasons are recorded in
  `results/paired_value_r3_n7/settlement_coverage_ledger.csv`.
- Exact accepted #338 R0/R3 parity: `{parity['pass']}`
  ({parity['rows']}/{parity['expected_common_rows']} common rows).

## Interpretation boundary

1. A paired residual screen is fairer than combining two adverse marginal tails,
   but its 2022 empirical distribution is still an exchangeable historical model,
   not a confidence interval for a live individual match.
2. `POINT` is an aggressive diagnostic boundary. It cannot be selected after
   outcomes merely because it has the largest historical payout.
3. The four contrast families keep match selection, R3 support and their
   interaction separate. A stack result is not assumed additive.
4. The issue, not the pair, match, outcome or ticket, is the uncertainty unit.
5. 2024 has been inspected before; it is transfer evidence, not a holdout.

## REQ evidence

| Requirement | Evidence |
| --- | --- |
| REQ-PV01 | `sp_model_receipt.json`, `pair_calibration_receipt.json`, frozen frame hashes |
| REQ-PV02 | `pair_calibration.parquet`, `pair_opportunities.parquet`, strict same-issue tests |
| REQ-PV03 | `preoutcome_bundles.parquet`, `replacement_ledger.parquet`, R3 recomputation tests |
| REQ-PV04 | `contrasts.csv`, exact all-cell common-support verifier |
| REQ-PV05 | `tickets.parquet`, `support_attribution.parquet`, payout-once verifier |
| REQ-PV06 | `performance.csv`, `risk_diagnostics.csv`, `capital_paths.csv` |
| REQ-PV07 | package, tests, executed notebook, figures, manifest and this report |
| REQ-PV08 | focused adversarial tamper and domain tests |
| REQ-PV09 | proxy grade in source/calibration/freeze receipts and report |
| REQ-PV10 | decision has `promotable_to_210=false`, `modifies_218=false` |

## Reproduction

```bash
.venv/bin/python scripts/run_paired_value_r3_n7.py --data-root data
.venv/bin/python scripts/verify_paired_value_r3_n7.py
.venv/bin/pytest -q tests/test_paired_value_r3_n7.py
```
"""
    path.write_text(text, encoding="utf-8")
    return path


def _write_notebook(repo_root: Path) -> Path:
    path = repo_root / "notebooks/research/paired-value-r3-n7/paired_value_r3_n7.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {
        "display_name": "Python 3", "language": "python", "name": "python3"
    }
    notebook["cells"] = [
        nbformat.v4.new_markdown_cell(
            "# Issue #345 — paired value selector × fixed R3\n\n"
            "Executed analysis notebook. The issue is the independent evaluation unit."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "candidates=[Path.cwd(), *Path.cwd().parents]\n"
            "root=next((p for p in candidates if (p/'results/paired_value_r3_n7').exists()), None)\n"
            "if root is None: raise FileNotFoundError('paired value package not found')\n"
            "package=root/'results/paired_value_r3_n7'\n"
            "decision=json.loads((package/'decision.json').read_text())\ndecision"
        ),
        nbformat.v4.new_markdown_cell("## Data completeness and paired calibration"),
        nbformat.v4.new_code_cell(
            "coverage=pd.read_csv(package/'settlement_coverage_ledger.csv',dtype={'issue':str})\n"
            "pairs=pd.read_parquet(package/'pair_calibration.parquet')\n"
            "pair_receipt=json.loads((package/'pair_calibration_receipt.json').read_text())\n"
            "display(coverage.groupby(['status','reason']).size().rename('issues'))\n"
            "display(pairs.groupby('issue').agg(rows=('issue','size'),weight=('issue_weight','sum')).describe())\n"
            "pair_receipt"
        ),
        nbformat.v4.new_markdown_cell("## Replacement curve and matched performance"),
        nbformat.v4.new_code_cell(
            "replacements=pd.read_parquet(package/'replacement_ledger.parquet')\n"
            "performance=pd.read_csv(package/'performance.csv')\n"
            "contrasts=pd.read_csv(package/'contrasts.csv')\n"
            "display(replacements.groupby(['selector','issue_year']).agg(rows=('step','size'),issues=('issue','nunique')) if len(replacements) else 'No replacements')\n"
            "display(performance[(performance.cell.str.endswith('R3A0'))])\n"
            "display(contrasts[contrasts.contrast.str.endswith('_UNDER_R3')])"
        ),
        nbformat.v4.new_markdown_cell("## Continuous capital and holding risk"),
        nbformat.v4.new_code_cell(
            "risk=pd.read_csv(package/'risk_diagnostics.csv')\n"
            "display(risk[(risk.period.astype(str)=='ALL') & risk.cell.str.endswith('R3A0')])\n"
            "from IPython.display import Image, display\n"
            "display(Image(filename=str(root/'docs/research/figures/issue_345_paired_value_capital.png')))\n"
            "display(Image(filename=str(root/'docs/research/figures/issue_345_paired_value_curve.png')))"
        ),
        nbformat.v4.new_markdown_cell(
            "## Boundary\n\nThe 10h surface is a retrospective relative proxy. "
            "No historical result here unlocks #210 or changes #218."
        ),
    ]
    nbformat.write(notebook, path)
    client = NotebookClient(nbformat.read(path, as_version=4), timeout=600, kernel_name="python3")
    executed = client.execute(cwd=str(repo_root))
    nbformat.write(executed, path)
    return path


def build_package(repo_root: Path, output: Path, data_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = data_root.resolve()
    try:
        output.relative_to(repo_root)
    except ValueError as error:
        raise ValueError("output directory must be inside repo_root") from error
    output.mkdir(parents=True, exist_ok=True)

    intervals, marginal_residuals, sp_predictions, model_receipt = fit_oof_sp_intervals(
        repo_root, data_root
    )
    if model_receipt["probability_source_sha256"] != EXPECTED_PROBABILITY_SOURCE_SHA256:
        raise AssertionError("probability source differs from the accepted historical snapshot")
    if model_receipt["training_settlement_source_sha256"] != EXPECTED_SETTLEMENT_SOURCE_SHA256:
        raise AssertionError("settlement source differs from the accepted historical snapshot")
    if (
        model_receipt["evaluation_prediction_frame_sha256"]
        != EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256
    ):
        raise AssertionError("evaluation SP prediction lineage differs from #342")
    _write_json(output / "sp_model_receipt.json", model_receipt)
    marginal_residuals.to_parquet(output / "sp_calibration_residuals.parquet", index=False)
    sp_predictions.to_parquet(output / "evaluation_sp_predictions.parquet", index=False)

    pair_calibration, pair_receipt = build_pair_calibration(data_root, model_receipt)
    pair_hash = pair_receipt["pair_calibration_frame_sha256"]
    if (
        EXPECTED_PAIR_CALIBRATION_FRAME_SHA256 != "PENDING"
        and pair_hash != EXPECTED_PAIR_CALIBRATION_FRAME_SHA256
    ):
        raise AssertionError("paired calibration differs from the frozen replay")
    pair_calibration.to_parquet(output / "pair_calibration.parquet", index=False)
    _write_json(output / "pair_calibration_receipt.json", pair_receipt)

    surface = prepare_value_surface(repo_root, intervals, sp_predictions)
    surface = attach_evaluation_proxy_context(data_root, surface)
    missing = set(VALUE_SURFACE_COLUMNS) - set(surface.columns)
    if missing:
        raise ValueError(f"value surface is missing required columns: {sorted(missing)}")
    surface_audit = surface.loc[:, VALUE_SURFACE_COLUMNS].copy()
    if not surface_audit["causal_grade"].eq("RETROSPECTIVE_RELATIVE_PROXY").all():
        raise AssertionError("10h proxy grade was silently upgraded or mixed")
    value_hash = _frame_sha(surface_audit, VALUE_SURFACE_COLUMNS)
    if EXPECTED_VALUE_SURFACE_FRAME_SHA256 != "PENDING" and value_hash != EXPECTED_VALUE_SURFACE_FRAME_SHA256:
        raise AssertionError("paired value surface differs from the frozen replay")
    opportunities = enumerate_pair_opportunities(surface_audit, pair_calibration)
    frozen, replacements = freeze_bundles(surface_audit, pair_calibration)
    bundle_hash = _frame_sha(frozen, FREEZE_COLUMNS)
    if (
        EXPECTED_PREOUTCOME_BUNDLE_FRAME_SHA256 != "PENDING"
        and bundle_hash != EXPECTED_PREOUTCOME_BUNDLE_FRAME_SHA256
    ):
        raise AssertionError("pre-outcome selector × R bundle differs from the frozen replay")
    freeze_receipt = {
        "contract": CONTRACT_ID,
        "evaluation_outcomes_opened_before_freeze": False,
        "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
        "n": N_LEGS,
        "r": R_DEPTH,
        "cells": list(CELLS),
        "selectors": list(SELECTORS),
        "tickets": TICKETS,
        "funded_units": FUNDED_UNITS,
        "issue_stake_cny": ISSUE_STAKE_CNY,
        "max_retained_mass_drop": MAX_RETAINED_MASS_DROP,
        "value_surface_rows": int(len(surface_audit)),
        "frozen_issues": int(frozen["issue"].nunique()),
        "value_surface_frame_sha256": value_hash,
        "pair_calibration_frame_sha256": pair_hash,
        "preoutcome_bundle_frame_sha256": bundle_hash,
        "evaluation_prediction_frame_sha256": model_receipt[
            "evaluation_prediction_frame_sha256"
        ],
        "selection_then_support": True,
        "r3_recomputed_within_final_seven": True,
        "payout_factor_application": "ticket_level_once",
    }
    surface_audit.to_parquet(output / "value_surface.parquet", index=False)
    opportunities.to_parquet(output / "pair_opportunities.parquet", index=False)
    frozen.to_parquet(output / "preoutcome_bundles.parquet", index=False)
    replacements.to_parquet(output / "replacement_ledger.parquet", index=False)
    _write_json(output / "freeze_receipt.json", freeze_receipt)

    labels, settlement_receipt = evaluation_labels(repo_root, data_root)
    label_hash = _frame_sha(labels, list(labels.columns))
    settlement_receipt["evaluation_label_frame_sha256"] = label_hash
    if label_hash != EXPECTED_EVALUATION_LABEL_FRAME_SHA256:
        raise AssertionError("evaluation labels differ from the frozen settlement replay")
    labels.to_parquet(output / "evaluation_labels.parquet", index=False)
    _write_json(output / "settlement_source_receipt.json", settlement_receipt)

    bundles, tickets, attribution = settle_bundles(frozen, labels)
    coverage = settlement_coverage_ledger(frozen, labels, bundles)
    performance, risk, paths, contrasts = evaluate(bundles)
    parity = baseline_parity(repo_root, bundles)
    if not parity["pass"]:
        raise AssertionError(f"accepted #338 baseline parity failed: {parity}")
    decision = decide(contrasts, replacements, int(frozen["issue"].nunique()))

    bundles.to_parquet(output / "issue_bundles.parquet", index=False)
    tickets.to_parquet(output / "tickets.parquet", index=False)
    attribution.to_parquet(output / "support_attribution.parquet", index=False)
    coverage.to_csv(output / "settlement_coverage_ledger.csv", index=False)
    performance.to_csv(output / "performance.csv", index=False, float_format="%.17g")
    risk.to_csv(output / "risk_diagnostics.csv", index=False, float_format="%.17g")
    paths.to_csv(output / "capital_paths.csv", index=False, float_format="%.17g")
    contrasts.to_csv(output / "contrasts.csv", index=False, float_format="%.17g")
    _write_json(output / "baseline_parity.json", parity)
    _write_json(output / "decision.json", decision)

    figures = _write_figures(repo_root, paths, contrasts, replacements)
    report = _write_report(
        repo_root,
        decision,
        performance,
        risk,
        contrasts,
        replacements,
        pair_receipt,
        parity,
        coverage,
    )
    notebook = _write_notebook(repo_root)

    paths_to_hash = [
        *(output / name for name in PACKAGE_NAMES),
        report,
        notebook,
        *figures,
    ]
    manifest = {
        "contract": CONTRACT_ID,
        "files": {
            str(path.relative_to(repo_root)): {
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in paths_to_hash
        },
    }
    _write_json(output / "MANIFEST.json", manifest)
    return {
        "status": "BUILT",
        "contract": CONTRACT_ID,
        "decision": decision,
        "frozen_issues": int(frozen["issue"].nunique()),
        "settled_common_issues": int(bundles["issue"].nunique()),
        "pair_calibration_frame_sha256": pair_hash,
        "value_surface_frame_sha256": value_hash,
        "preoutcome_bundle_frame_sha256": bundle_hash,
    }


def _exact_cartesian(
    frozen: pd.DataFrame,
    tickets: pd.DataFrame,
) -> bool:
    ticket_groups = {
        key: set(group["ticket_code"].astype(str))
        for key, group in tickets.groupby(["issue", "issue_year", "cell"], observed=True)
    }
    for row in frozen.itertuples(index=False):
        key = (str(row.issue), int(row.issue_year), str(row.cell))
        if key not in ticket_groups:
            continue
        support_map = json.loads(row.support_json)
        supports = [support_map[name] for name in sorted(support_map, key=int)]
        expected = {"|".join(values) for values in itertools.product(*supports)}
        if ticket_groups[key] != expected:
            return False
    return True


def verify_package(repo_root: Path, output: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    if "PENDING" in {
        EXPECTED_PAIR_CALIBRATION_FRAME_SHA256,
        EXPECTED_VALUE_SURFACE_FRAME_SHA256,
        EXPECTED_PREOUTCOME_BUNDLE_FRAME_SHA256,
    }:
        raise AssertionError("frozen semantic hashes are not finalized")

    manifest = _json(output / "MANIFEST.json")
    expected_paths = {
        str((output / name).relative_to(repo_root)) for name in PACKAGE_NAMES
    } | {
        "docs/research/Issue-Paired-Value-R3-N7.md",
        "docs/research/figures/issue_345_paired_value_capital.png",
        "docs/research/figures/issue_345_paired_value_curve.png",
        "notebooks/research/paired-value-r3-n7/paired_value_r3_n7.ipynb",
    }
    manifest_files = set(manifest.get("files", {}))
    hashes = all(
        (repo_root / relative).is_file()
        and sha256_file(repo_root / relative) == metadata["sha256"]
        and (repo_root / relative).stat().st_size == metadata["bytes"]
        for relative, metadata in manifest.get("files", {}).items()
    )

    model_receipt = _json(output / "sp_model_receipt.json")
    pair_receipt = _json(output / "pair_calibration_receipt.json")
    freeze_receipt = _json(output / "freeze_receipt.json")
    settlement_receipt = _json(output / "settlement_source_receipt.json")
    parity = _json(output / "baseline_parity.json")
    decision = _json(output / "decision.json")
    pair_calibration = pd.read_parquet(output / "pair_calibration.parquet")
    surface = pd.read_parquet(output / "value_surface.parquet")
    opportunities = pd.read_parquet(output / "pair_opportunities.parquet")
    frozen = pd.read_parquet(output / "preoutcome_bundles.parquet")
    replacements = pd.read_parquet(output / "replacement_ledger.parquet")
    labels = pd.read_parquet(output / "evaluation_labels.parquet")
    bundles = pd.read_parquet(output / "issue_bundles.parquet")
    tickets = pd.read_parquet(output / "tickets.parquet")
    attribution = pd.read_parquet(output / "support_attribution.parquet")
    coverage = pd.read_csv(
        output / "settlement_coverage_ledger.csv",
        dtype={"issue": str},
        keep_default_na=False,
    )
    performance = pd.read_csv(output / "performance.csv", dtype={"period": str})
    risk = pd.read_csv(output / "risk_diagnostics.csv", dtype={"period": str})
    paths = pd.read_csv(output / "capital_paths.csv", dtype={"period": str, "issue": str})
    contrasts = pd.read_csv(output / "contrasts.csv", dtype={"period": str})

    expected_frozen, expected_replacements = freeze_bundles(surface, pair_calibration)
    (
        expected_performance,
        expected_risk,
        expected_capital_paths,
        expected_contrasts,
    ) = evaluate(bundles)
    expected_decision = decide(
        expected_contrasts,
        expected_replacements,
        int(expected_frozen["issue"].nunique()),
    )
    expected_coverage = settlement_coverage_ledger(frozen, labels, bundles)
    expected_parity = baseline_parity(repo_root, bundles)

    ticket_receipt = tickets.groupby(["issue", "issue_year", "cell"], observed=True).agg(
        rows=("ticket_code", "size"),
        unique=("ticket_code", "nunique"),
        units=("units", "sum"),
        stake=("stake_cny", "sum"),
    )
    bundle_keys = set(map(tuple, bundles[["issue", "issue_year", "cell"]].itertuples(index=False, name=None)))
    ticket_keys = set(map(tuple, ticket_receipt.index.tolist()))
    attribution_reconciliation = attribution.groupby(
        ["issue", "issue_year", "cell"], observed=True
    ).agg(
        legs=("match_idx", "size"),
        all_included=("realized_in_support", "all"),
        winning_sp_product=("winning_sp", "prod"),
    ).reset_index()
    attribution_reconciliation["expected_gross_cny"] = np.where(
        attribution_reconciliation["all_included"],
        STAKE_PER_UNIT_CNY * UNITS_PER_TICKET * PAYOUT_FACTOR
        * attribution_reconciliation["winning_sp_product"],
        0.0,
    )
    gross_join = bundles.merge(
        attribution_reconciliation,
        on=["issue", "issue_year", "cell"],
        validate="one_to_one",
    )
    label_join = attribution.merge(
        labels[["issue_code", "match_idx", "result_code", "winning_sp", "has_trusted_settlement"]],
        left_on=["issue", "match_idx"],
        right_on=["issue_code", "match_idx"],
        suffixes=("_attribution", "_label"),
        validate="many_to_one",
    )
    issue_weights = pair_calibration.groupby("issue", observed=True)["issue_weight"].sum()

    checks = {
        "manifest_contract": manifest.get("contract") == CONTRACT_ID,
        "manifest_file_set": manifest_files == expected_paths,
        "manifest_hashes": hashes,
        "probability_source_binding": (
            model_receipt["probability_source_sha256"]
            == pair_receipt["probability_source_sha256"]
            == EXPECTED_PROBABILITY_SOURCE_SHA256
        ),
        "settlement_source_binding": (
            model_receipt["training_settlement_source_sha256"]
            == pair_receipt["settlement_source_sha256"]
            == settlement_receipt["database_source_sha256"]
            == EXPECTED_SETTLEMENT_SOURCE_SHA256
        ),
        "prediction_frame_binding": (
            _frame_sha(
                pd.read_parquet(output / "evaluation_sp_predictions.parquet"),
                list(pd.read_parquet(output / "evaluation_sp_predictions.parquet").columns),
            )
            == model_receipt["evaluation_prediction_frame_sha256"]
            == EXPECTED_EVALUATION_PREDICTION_FRAME_SHA256
        ),
        "pair_frame_binding": (
            _frame_sha(pair_calibration, PAIR_COLUMNS)
            == pair_receipt["pair_calibration_frame_sha256"]
            == freeze_receipt["pair_calibration_frame_sha256"]
            == EXPECTED_PAIR_CALIBRATION_FRAME_SHA256
        ),
        "pair_same_issue": bool(
            pair_calibration["issue"].eq(pair_calibration["candidate_issue"]).all()
            and pair_calibration["issue"].eq(pair_calibration["incumbent_issue"]).all()
            and pair_calibration["candidate_match_idx"].ne(
                pair_calibration["incumbent_match_idx"]
            ).all()
        ),
        "pair_equal_issue_weight": bool(
            np.allclose(issue_weights, 1.0 / len(issue_weights), rtol=0, atol=1e-12)
            and np.isclose(pair_calibration["issue_weight"].sum(), 1.0, rtol=0, atol=1e-12)
        ),
        "pair_mass_admissible": bool(
            pair_calibration["retained_mass_delta"].ge(-MAX_RETAINED_MASS_DROP - 1e-12).all()
        ),
        "value_surface_binding": (
            _frame_sha(surface, VALUE_SURFACE_COLUMNS)
            == freeze_receipt["value_surface_frame_sha256"]
            == EXPECTED_VALUE_SURFACE_FRAME_SHA256
        ),
        "proxy_grade_preserved": bool(
            surface["causal_grade"].eq("RETROSPECTIVE_RELATIVE_PROXY").all()
            and pair_receipt["proxy_grade"] == "RETROSPECTIVE_RELATIVE_PROXY"
            and freeze_receipt["proxy_grade"] == "RETROSPECTIVE_RELATIVE_PROXY"
        ),
        "preoutcome_bundle_binding": (
            _frame_sha(frozen, FREEZE_COLUMNS)
            == freeze_receipt["preoutcome_bundle_frame_sha256"]
            == EXPECTED_PREOUTCOME_BUNDLE_FRAME_SHA256
        ),
        "selection_recomputation": _semantic_frame_equal(frozen, expected_frozen),
        "replacement_recomputation": _semantic_frame_equal(replacements, expected_replacements),
        "all_cells": set(frozen["cell"].unique()) == set(CELLS),
        "outcomes_unopened_at_freeze": freeze_receipt["evaluation_outcomes_opened_before_freeze"] is False,
        "ticket_group_keys": ticket_keys == bundle_keys,
        "ticket_rows": bool(ticket_receipt["rows"].eq(TICKETS).all()),
        "ticket_unique": bool(ticket_receipt["unique"].eq(TICKETS).all()),
        "ticket_exact_cartesian": _exact_cartesian(frozen, tickets),
        "ticket_units": bool(
            tickets["units"].eq(UNITS_PER_TICKET).all()
            and ticket_receipt["units"].eq(FUNDED_UNITS).all()
        ),
        "ticket_stake": bool(
            tickets["stake_cny"].eq(UNITS_PER_TICKET * STAKE_PER_UNIT_CNY).all()
            and np.allclose(ticket_receipt["stake"], ISSUE_STAKE_CNY, rtol=0, atol=1e-12)
        ),
        "seven_leg_attribution": bool(gross_join["legs"].eq(N_LEGS).all()),
        "payout_once_reconciliation": bool(np.allclose(
            gross_join["gross_cny"], gross_join["expected_gross_cny"], rtol=0, atol=1e-8
        )),
        "bundle_pnl_identity": bool(np.allclose(
            bundles["pnl_cny"], bundles["gross_cny"] - bundles["stake_cny"], rtol=0, atol=1e-12
        )),
        "evaluation_label_binding": (
            _frame_sha(labels, list(labels.columns))
            == settlement_receipt["evaluation_label_frame_sha256"]
            == EXPECTED_EVALUATION_LABEL_FRAME_SHA256
        ),
        "attribution_label_reconciliation": bool(
            len(label_join) == len(attribution)
            and label_join["has_trusted_settlement"].eq(1).all()
            and label_join["result_code_attribution"].astype(str).eq(
                label_join["result_code_label"].astype(str)
            ).all()
            and np.allclose(
                label_join["winning_sp_attribution"],
                label_join["winning_sp_label"],
                rtol=0,
                atol=1e-12,
            )
        ),
        "baseline_parity": bool(parity == expected_parity and parity["pass"]),
        "performance_recomputation": _semantic_frame_equal(performance, expected_performance),
        "risk_recomputation": _semantic_frame_equal(risk, expected_risk),
        "capital_path_recomputation": _semantic_frame_equal(paths, expected_capital_paths),
        "contrast_recomputation": _semantic_frame_equal(contrasts, expected_contrasts),
        "decision_recomputation": decision == expected_decision,
        "coverage_recomputation": _semantic_frame_equal(coverage, expected_coverage),
        "control_plane_boundary": (
            decision["promotable_to_210"] is False and decision["modifies_218"] is False
        ),
        "opportunity_domain": bool(
            not opportunities.empty
            and opportunities["retained_mass_delta"].ge(-MAX_RETAINED_MASS_DROP - 1e-12).all()
            and np.isfinite(opportunities[[
                "point_delta_g", "point_log_ratio", "paired_probability_positive",
                "paired_l10_log_margin",
            ]].to_numpy(float)).all()
        ),
    }
    if not all(checks.values()):
        raise AssertionError({name: value for name, value in checks.items() if not value})
    return {
        "status": "PASS",
        "contract": CONTRACT_ID,
        "checks": checks,
        "issues": int(bundles["issue"].nunique()),
        "cells": int(bundles["cell"].nunique()),
    }
