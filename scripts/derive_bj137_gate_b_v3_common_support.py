#!/usr/bin/env python3
"""Derive #137 Gate-B v3 common-support attribution from the audited v2r1 ledger.

The accepted Gate-A v2 selection and sampling freeze is not reopened.  This
post-settlement correction reads the exact v2r1 issue-policy ledger and derives
matched effects only on each pair's common settled complete-issue support.  It
also supplies the two corrected diagnostics requested in PR #143 review.

All temporary files are staged below ``results/``; /tmp is never used.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import random
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from settle_bj137_sampling_gate_b import (
    CALIBRATION_FIELDS,
    CODES,
    CONTRACT,
    FREEZE,
    FREEZE_MANIFEST,
    OUTCOME_MANIFEST,
    OUTCOME_PAYLOAD,
    ROOT,
    VECTOR_FIELDS,
    exact_bundle,
    fmt,
    load_outcomes,
    ratio,
    require_schema,
    sha,
    uncompressed,
    validate_inputs,
)


INPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v2r1"
INPUT_MANIFEST = "f4848d61b7eab31b97077751fdb2f49ad242e483033c6d29524ba4f7b43445fb"
OUTPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v3_common_support"
SOURCE_LEDGER = INPUT / "issue_policy_settlement.csv.gz"
SOURCE_SUMMARY = INPUT / "surface_summary.csv.gz"

LEDGER_KEY = ("gate_id", "top_k_id", "sampler_id", "probability_vector", "M", "seed")
NUMERIC_SEEDS = {"137001", "137002", "137003"}
HARD_CONTROLS = ("P_MIN_GLOBAL_DELETE_CONTROL", "Q_MIN_GLOBAL_DELETE_CONTROL")

EFFECT_FIELDS = (
    "scope", "scope_value", "effect", "gate_id", "top_k_id", "sampler_id", "probability_vector",
    "mechanism", "duplicate_policy", "M", "seed", "baseline_sampler_id", "baseline_probability_vector",
    "baseline_top_k_id", "baseline_M", "baseline_seed", "candidate_settled_issue_count",
    "baseline_settled_issue_count", "matched_settled_issue_count", "candidate_stake_yuan",
    "baseline_stake_yuan", "candidate_gross_pre_tax_yuan", "baseline_gross_pre_tax_yuan",
    "candidate_tax_yuan", "baseline_tax_yuan", "candidate_no_tax_roi", "baseline_no_tax_roi",
    "no_tax_roi_delta", "candidate_tax_adjusted_roi", "baseline_tax_adjusted_roi",
    "tax_adjusted_roi_delta", "candidate_coverage_hit_rate", "baseline_coverage_hit_rate",
    "coverage_hit_rate_delta",
)
TAX_SENSITIVITY_FIELDS = (
    "scope", "scope_value", "gate_id", "top_k_id", "sampler_id", "probability_vector", "M", "seed",
    "stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "source_ex_largest_issue_tax_adjusted_roi",
    "largest_issue_gross_yuan", "largest_issue_tax_yuan", "corrected_ex_largest_issue_no_tax_roi",
    "corrected_ex_largest_issue_tax_adjusted_roi",
)
CALIBRATION_CORRECTION_FIELDS = CALIBRATION_FIELDS
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "payload", "payload_sha256", "rows", "join_status")
FRAGILITY_FIELDS = (
    "gate_id", "top_k_id", "sampler_id", "probability_vector", "mechanism", "M", "seed",
    "baseline_sampler_id", "baseline_probability_vector", "baseline_M", "baseline_seed",
    "matched_settled_issue_count", "candidate_no_tax_roi", "baseline_no_tax_roi", "no_tax_roi_delta",
    "candidate_tax_adjusted_roi", "baseline_tax_adjusted_roi", "tax_adjusted_roi_delta",
    "candidate_gross_top_issue_share", "candidate_largest_issue", "candidate_largest_issue_gross_yuan",
    "candidate_ex_largest_issue_no_tax_roi", "baseline_ex_largest_issue_no_tax_roi",
    "ex_largest_issue_no_tax_roi_delta", "leave_one_issue_out_count",
    "leave_one_issue_out_positive_delta_count", "worst_leave_one_issue_out_no_tax_roi_delta",
    "bootstrap_draws", "bootstrap_seed", "bootstrap_no_tax_roi_delta_p025",
    "bootstrap_no_tax_roi_delta_p500", "bootstrap_no_tax_roi_delta_p975",
)
STABILITY_FIELDS = (
    "effect", "diagnostic_scope", "gate_id", "top_k_id", "sampler_id", "probability_vector",
    "mechanism", "M", "seed", "baseline_sampler_id", "baseline_top_k_id", "baseline_M",
    "observed_slices", "positive_pre_tax_delta_count", "positive_pre_tax_delta_fraction",
    "worst_pre_tax_delta", "best_pre_tax_delta", "mean_pre_tax_delta", "stddev_pre_tax_delta",
)


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush()
    text.detach()
    zipped.close()
    raw.close()


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def issue_key(row: dict[str, str]) -> str:
    return row["issue_instance"]


def plan_key(row: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    return tuple(row[field] for field in LEDGER_KEY)  # type: ignore[return-value]


def parse_float(row: dict[str, str], field: str) -> float:
    return float(row[field] or 0.0)


def iter_issue_rows() -> Iterator[list[dict[str, str]]]:
    with gzip.open(SOURCE_LEDGER, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError("empty v2r1 issue-policy ledger")
        current_key: str | None = None
        rows: list[dict[str, str]] = []
        for row in reader:
            key = issue_key(row)
            if current_key is not None and key != current_key:
                yield rows
                rows = []
            current_key = key
            rows.append(row)
        if rows:
            yield rows


@dataclass(slots=True)
class Side:
    settled: int = 0
    common: int = 0
    stake: float = 0.0
    gross: float = 0.0
    tax: float = 0.0
    coverage: int = 0

    def add(self, row: dict[str, str]) -> None:
        self.common += 1
        self.stake += parse_float(row, "planned_stake_yuan")
        self.gross += parse_float(row, "gross_pre_tax_yuan")
        self.tax += parse_float(row, "tax_yuan")
        self.coverage += int(row["coverage_hit"])


@dataclass(slots=True)
class PairAggregate:
    candidate: Side
    baseline: Side
    candidate_settled: int = 0
    baseline_settled: int = 0

    @classmethod
    def empty(cls) -> "PairAggregate":
        return cls(Side(), Side())

    def observe(self, candidate: dict[str, str], baseline: dict[str, str]) -> None:
        candidate_ok = candidate["settlement_status"] == "SETTLED"
        baseline_ok = baseline["settlement_status"] == "SETTLED"
        self.candidate_settled += int(candidate_ok)
        self.baseline_settled += int(baseline_ok)
        if candidate_ok and baseline_ok:
            self.candidate.add(candidate)
            self.baseline.add(baseline)


def pair_descriptor(
    effect: str, candidate: dict[str, str], baseline: dict[str, str],
) -> tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]]:
    return effect, plan_key(candidate), plan_key(baseline)


def issue_pairs(rows: list[dict[str, str]]) -> Iterator[tuple[str, dict[str, str], dict[str, str]]]:
    index = {plan_key(row): row for row in rows}
    if len(index) != len(rows):
        raise RuntimeError(f"non-unique policy rows within {rows[0]['issue_instance']}")
    full: dict[tuple[str, str], dict[str, str]] = {}
    controls: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        if row["sampler_id"] == "FULL_N7_CONTROL":
            full[(row["gate_id"], row["top_k_id"])] = row
        if row["sampler_id"] in HARD_CONTROLS:
            controls[(row["gate_id"], row["top_k_id"], row["sampler_id"])] = row
    for row in rows:
        gate, top, sampler = row["gate_id"], row["top_k_id"], row["sampler_id"]
        exact_full = full.get((gate, top))
        all_full = full.get((gate, "K_ALL"))
        if sampler == "FULL_N7_CONTROL" and top != "K_ALL" and all_full is not None:
            yield "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT", row, all_full
            continue
        if sampler == "FULL_N7_CONTROL":
            continue
        if exact_full is not None:
            yield "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT", row, exact_full
        if all_full is not None:
            yield "INTERACTION_VS_K_ALL_FULL_COMMON_SUPPORT", row, all_full
        if row["M"] == "1458":
            for control in HARD_CONTROLS:
                baseline = controls.get((gate, top, control))
                if baseline is not None and baseline is not row:
                    label = f"SAMPLER_VS_{control}_COMMON_SUPPORT"
                    yield label, row, baseline


def aggregate(selector: str) -> dict[tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]], PairAggregate]:
    values: dict[tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]], PairAggregate] = {}
    for rows in iter_issue_rows():
        for effect, candidate, baseline in issue_pairs(rows):
            key = pair_descriptor(effect, candidate, baseline)
            values.setdefault(key, PairAggregate.empty()).observe(candidate, baseline)
    return values


def aggregate_by_dimension(dimension: str) -> dict[str, dict[tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]], PairAggregate]]:
    values: dict[str, dict[tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]], PairAggregate]] = defaultdict(dict)
    for rows in iter_issue_rows():
        value = rows[0][dimension]
        bucket = values[value]
        for effect, candidate, baseline in issue_pairs(rows):
            key = pair_descriptor(effect, candidate, baseline)
            bucket.setdefault(key, PairAggregate.empty()).observe(candidate, baseline)
    return values


def subtract(left: PairAggregate, right: PairAggregate) -> PairAggregate:
    return PairAggregate(
        Side(
            settled=0,
            common=left.candidate.common-right.candidate.common,
            stake=left.candidate.stake-right.candidate.stake,
            gross=left.candidate.gross-right.candidate.gross,
            tax=left.candidate.tax-right.candidate.tax,
            coverage=left.candidate.coverage-right.candidate.coverage,
        ),
        Side(
            settled=0,
            common=left.baseline.common-right.baseline.common,
            stake=left.baseline.stake-right.baseline.stake,
            gross=left.baseline.gross-right.baseline.gross,
            tax=left.baseline.tax-right.baseline.tax,
            coverage=left.baseline.coverage-right.baseline.coverage,
        ),
        candidate_settled=left.candidate_settled-right.candidate_settled,
        baseline_settled=left.baseline_settled-right.baseline_settled,
    )


def effect_row(
    scope: str,
    scope_value: str,
    key: tuple[str, tuple[str, str, str, str, str, str], tuple[str, str, str, str, str, str]],
    value: PairAggregate,
) -> dict[str, object]:
    effect, candidate_key, baseline_key = key
    _, _, sampler, vector, m, seed = candidate_key
    gate, top, _, _, _, _ = candidate_key
    _, baseline_top, baseline_sampler, baseline_vector, baseline_m, baseline_seed = baseline_key
    candidate, baseline = value.candidate, value.baseline
    if candidate.common != baseline.common:
        raise RuntimeError("common-support accounting drift")
    candidate_no_tax = (candidate.gross-candidate.stake)/candidate.stake if candidate.stake else None
    baseline_no_tax = (baseline.gross-baseline.stake)/baseline.stake if baseline.stake else None
    candidate_tax = (candidate.gross-candidate.tax-candidate.stake)/candidate.stake if candidate.stake else None
    baseline_tax = (baseline.gross-baseline.tax-baseline.stake)/baseline.stake if baseline.stake else None
    candidate_cov = candidate.coverage/candidate.common if candidate.common else None
    baseline_cov = baseline.coverage/baseline.common if baseline.common else None
    return {
        "scope": scope, "scope_value": scope_value, "effect": effect, "gate_id": gate, "top_k_id": top,
        "sampler_id": sampler, "probability_vector": vector, "mechanism": sampler_mechanism(sampler),
        "duplicate_policy": sampler_duplicate_policy(sampler), "M": m, "seed": seed,
        "baseline_sampler_id": baseline_sampler, "baseline_probability_vector": baseline_vector,
        "baseline_top_k_id": baseline_top, "baseline_M": baseline_m, "baseline_seed": baseline_seed,
        "candidate_settled_issue_count": value.candidate_settled,
        "baseline_settled_issue_count": value.baseline_settled,
        "matched_settled_issue_count": candidate.common,
        "candidate_stake_yuan": fmt(candidate.stake), "baseline_stake_yuan": fmt(baseline.stake),
        "candidate_gross_pre_tax_yuan": fmt(candidate.gross), "baseline_gross_pre_tax_yuan": fmt(baseline.gross),
        "candidate_tax_yuan": fmt(candidate.tax), "baseline_tax_yuan": fmt(baseline.tax),
        "candidate_no_tax_roi": ratio(candidate_no_tax), "baseline_no_tax_roi": ratio(baseline_no_tax),
        "no_tax_roi_delta": ratio(candidate_no_tax-baseline_no_tax if candidate_no_tax is not None and baseline_no_tax is not None else None),
        "candidate_tax_adjusted_roi": ratio(candidate_tax), "baseline_tax_adjusted_roi": ratio(baseline_tax),
        "tax_adjusted_roi_delta": ratio(candidate_tax-baseline_tax if candidate_tax is not None and baseline_tax is not None else None),
        "candidate_coverage_hit_rate": ratio(candidate_cov), "baseline_coverage_hit_rate": ratio(baseline_cov),
        "coverage_hit_rate_delta": ratio(candidate_cov-baseline_cov if candidate_cov is not None and baseline_cov is not None else None),
    }


def sampler_mechanism(sampler: str) -> str:
    if sampler == "FULL_N7_CONTROL":
        return "ENUMERATE_FULL"
    if sampler == "TOP_MODEL_P_CAL_DISTINCT":
        return "DETERMINISTIC_TOP_MASS"
    if sampler.endswith("WR_DUPLICATE_STAKES"):
        return "INDEPENDENT_WITH_REPLACEMENT"
    if sampler in HARD_CONTROLS:
        return "GLOBAL_SINGLE_CODE_DELETE"
    return "WEIGHTED_WITHOUT_REPLACEMENT"


def sampler_duplicate_policy(sampler: str) -> str:
    return "DUPLICATE_STAKES" if sampler.endswith("WR_DUPLICATE_STAKES") else "DEDUPLICATED"


def corrected_calibration(outcomes: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    vectors = {
        "MODEL_P_CAL": ("p3", "p1", "p0"), "MARKET_WF_CAL": ("market_cal3", "market_cal1", "market_cal0"),
        "BLEND_A25": ("blend_a25_3", "blend_a25_1", "blend_a25_0"), "BLEND_A50": ("blend_a50_3", "blend_a50_1", "blend_a50_0"),
        "BLEND_A75": ("blend_a75_3", "blend_a75_1", "blend_a75_0"), "Q_WEIGHT": ("q3", "q1", "q0"),
    }
    totals: dict[tuple[str, str, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    with (FREEZE / "match_vectors.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_schema(reader, VECTOR_FIELDS, "Gate-A match vectors")
        for row in reader:
            outcome = outcomes.get(row["match_id"])
            for name, columns in vectors.items():
                for code, column in zip(CODES, columns):
                    probability = float(row[column])
                    item = totals[(name, code, min(9, int(probability*10)))]
                    if outcome is None:
                        item[4] += 1
                        continue
                    observed = int(outcome["result_code"] == code)
                    item[0] += 1
                    item[1] += probability
                    item[2] += observed
                    item[3] += (probability-observed)**2
    return [
        {
            "probability_vector": name, "outcome_code": code, "probability_decile": decile,
            "rows": int(values[0]), "mean_probability": ratio(values[1]/values[0] if values[0] else None),
            "observed_frequency": ratio(values[2]/values[0] if values[0] else None),
            "brier_component": ratio(values[3]/values[0] if values[0] else None),
            "outcome_coverage": ratio(values[0]/(values[0]+values[4]) if values[0]+values[4] else None),
            "outcome_gap_count": int(values[4]),
        }
        for (name, code, decile), values in sorted(totals.items())
    ]


@dataclass(frozen=True, slots=True)
class LargestEvent:
    gross: float
    tax: float


def keep_largest(
    values: dict[object, LargestEvent], key: object, gross: float, tax: float,
) -> None:
    current = values.get(key)
    if current is None or gross > current.gross:
        values[key] = LargestEvent(gross, tax)


def largest_events() -> tuple[
    dict[tuple[str, str, str, str, str, str], LargestEvent],
    dict[tuple[str, tuple[str, str, str, str, str, str]], LargestEvent],
    dict[tuple[str, tuple[str, str, str, str, str, str]], LargestEvent],
]:
    all_values: dict[tuple[str, str, str, str, str, str], LargestEvent] = {}
    year_values: dict[tuple[str, tuple[str, str, str, str, str, str]], LargestEvent] = {}
    fold_values: dict[tuple[str, tuple[str, str, str, str, str, str]], LargestEvent] = {}
    for rows in iter_issue_rows():
        for row in rows:
            if row["settlement_status"] != "SETTLED":
                continue
            key = plan_key(row)
            gross, tax = parse_float(row, "gross_pre_tax_yuan"), parse_float(row, "tax_yuan")
            keep_largest(all_values, key, gross, tax)
            keep_largest(year_values, (row["year"], key), gross, tax)
            keep_largest(fold_values, (row["fold"], key), gross, tax)
    return all_values, year_values, fold_values


def summary_key(row: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    return tuple(row[field] for field in LEDGER_KEY)  # type: ignore[return-value]


def sensitivity_rows() -> Iterator[dict[str, object]]:
    all_values, year_values, fold_values = largest_events()
    year_values_by_key: dict[tuple[str, str, str, str, str, str], list[tuple[str, LargestEvent]]] = defaultdict(list)
    for (year, key), event in year_values.items():
        year_values_by_key[key].append((year, event))
    with gzip.open(SOURCE_SUMMARY, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            key = summary_key(row)
            scope, value = row["scope"], row["scope_value"]
            if scope == "ALL":
                largest = all_values.get(key)
            elif scope == "YEAR":
                largest = year_values.get((value, key))
            elif scope == "FOLD":
                largest = fold_values.get((value, key))
            elif scope == "LEAVE_ONE_YEAR_OUT":
                remaining = [event for year, event in year_values_by_key.get(key, []) if year != value]
                largest = max(remaining, key=lambda event: event.gross, default=None)
            else:
                raise RuntimeError(f"unknown source summary scope: {scope}")
            stake, gross, tax = parse_float(row, "stake_yuan"), parse_float(row, "gross_pre_tax_yuan"), parse_float(row, "tax_yuan")
            largest_gross = largest.gross if largest is not None else 0.0
            largest_tax = largest.tax if largest is not None else 0.0
            corrected_no_tax = (gross-largest_gross-stake)/stake if stake else None
            corrected = (gross-largest_gross-(tax-largest_tax)-stake)/stake if stake else None
            yield {
                "scope": scope, "scope_value": value, "gate_id": row["gate_id"], "top_k_id": row["top_k_id"],
                "sampler_id": row["sampler_id"], "probability_vector": row["probability_vector"],
                "M": row["M"], "seed": row["seed"], "stake_yuan": fmt(stake),
                "gross_pre_tax_yuan": fmt(gross), "tax_yuan": fmt(tax),
                "source_ex_largest_issue_tax_adjusted_roi": row["ex_largest_issue_tax_adjusted_roi"],
                "largest_issue_gross_yuan": fmt(largest_gross), "largest_issue_tax_yuan": fmt(largest_tax),
                "corrected_ex_largest_issue_no_tax_roi": ratio(corrected_no_tax),
                "corrected_ex_largest_issue_tax_adjusted_roi": ratio(corrected),
            }


def pre_tax_positive(row: dict[str, str]) -> bool:
    """The PI-locked economic scale: BJ 0.65 factor included, ticket tax excluded."""
    return bool(row["no_tax_roi_delta"] and float(row["no_tax_roi_delta"]) > 0.0)


def no_tax_roi_positive(row: dict[str, str]) -> bool:
    return bool(row["candidate_no_tax_roi"] and float(row["candidate_no_tax_roi"]) > 0.0)


def candidate_descriptor(
    key: tuple[str, str, str, str], rows: list[dict[str, str]], kind: str,
) -> dict[str, object]:
    all_rows = [row for row in rows if row["scope"] == "ALL"]
    return {
        "gate_id": key[0],
        "top_k_id": key[1],
        "sampler_id": key[2],
        "M": key[3],
        "probability_vector": all_rows[0]["probability_vector"],
        "mechanism": all_rows[0]["mechanism"],
        "seed_kind": kind,
        "seeds": sorted(row["seed"] for row in all_rows),
        "matched_settled_issue_count_by_seed": {
            row["seed"]: int(row["matched_settled_issue_count"]) for row in all_rows
        },
        "all_scope_no_tax_roi_by_seed": {
            row["seed"]: row["candidate_no_tax_roi"] for row in all_rows
        },
        "all_scope_no_tax_delta_by_seed": {
            row["seed"]: row["no_tax_roi_delta"] for row in all_rows
        },
    }


def decision_from_common_effects(path: Path) -> dict[str, object]:
    sampler: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    selector: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    hard_control: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["effect"] == "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT":
                selector[(row["gate_id"], row["top_k_id"])].append(row)
            elif row["effect"] == "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT":
                sampler[(row["gate_id"], row["top_k_id"], row["sampler_id"], row["M"])].append(row)
            elif row["effect"].startswith("SAMPLER_VS_"):
                hard_control[(row["effect"], row["gate_id"], row["top_k_id"], row["sampler_id"], row["M"])].append(row)

    all_seed_numeric: list[tuple[str, str, str, str]] = []
    loyo_stable_numeric: list[tuple[str, str, str, str]] = []
    absolute_numeric: list[tuple[str, str, str, str]] = []
    all_seed_deterministic: list[tuple[str, str, str, str]] = []
    loyo_stable_deterministic: list[tuple[str, str, str, str]] = []
    absolute_deterministic: list[tuple[str, str, str, str]] = []
    stable_signal_rows: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    absolute_rows: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    for key, rows in sampler.items():
        all_rows = [row for row in rows if row["scope"] == "ALL"]
        loyo_rows = [row for row in rows if row["scope"] == "LEAVE_ONE_YEAR_OUT"]
        if key[2] == "TOP_MODEL_P_CAL_DISTINCT":
            if len(all_rows) == 1 and all_rows[0]["seed"] == "NA" and pre_tax_positive(all_rows[0]):
                all_seed_deterministic.append(key)
                if loyo_rows and all(pre_tax_positive(row) for row in loyo_rows):
                    loyo_stable_deterministic.append(key)
                    stable_signal_rows[key] = rows
                    if no_tax_roi_positive(all_rows[0]):
                        absolute_deterministic.append(key)
                        absolute_rows[key] = rows
            continue
        if {row["seed"] for row in all_rows} == NUMERIC_SEEDS and all(pre_tax_positive(row) for row in all_rows):
            all_seed_numeric.append(key)
            required_loyo = len(NUMERIC_SEEDS) * len({row["scope_value"] for row in loyo_rows})
            if loyo_rows and len(loyo_rows) == required_loyo and all(pre_tax_positive(row) for row in loyo_rows):
                loyo_stable_numeric.append(key)
                stable_signal_rows[key] = rows
                if all(no_tax_roi_positive(row) for row in all_rows):
                    absolute_numeric.append(key)
                    absolute_rows[key] = rows

    selector_all_seed = 0
    selector_loyo_stable = 0
    for rows in selector.values():
        all_rows = [row for row in rows if row["scope"] == "ALL"]
        loyo_rows = [row for row in rows if row["scope"] == "LEAVE_ONE_YEAR_OUT"]
        if len(all_rows) == 1 and pre_tax_positive(all_rows[0]):
            selector_all_seed += 1
            if loyo_rows and all(pre_tax_positive(row) for row in loyo_rows):
                selector_loyo_stable += 1

    hard_control_all_seed = 0
    hard_control_loyo_stable = 0
    for rows in hard_control.values():
        all_rows = [row for row in rows if row["scope"] == "ALL"]
        loyo_rows = [row for row in rows if row["scope"] == "LEAVE_ONE_YEAR_OUT"]
        if all_rows and all(pre_tax_positive(row) for row in all_rows):
            hard_control_all_seed += 1
            if loyo_rows and all(pre_tax_positive(row) for row in loyo_rows):
                hard_control_loyo_stable += 1

    stable_keys = sorted(set(loyo_stable_numeric + loyo_stable_deterministic))
    absolute_keys = sorted(set(absolute_numeric + absolute_deterministic))
    promotion_candidates = [
        candidate_descriptor(key, absolute_rows[key], "DETERMINISTIC" if key[2] == "TOP_MODEL_P_CAL_DISTINCT" else "THREE_FROZEN_SEEDS")
        for key in absolute_keys
    ]
    return {
        "decision": "POSITIVE_CONCENTRATED_REQUIRES_STRICT_INDEPENDENT_EV" if absolute_keys else (
            "EXPLORATORY_EFFICIENCY_SIGNAL_NO_PROMOTION" if stable_keys else "NO_PROMOTION"
        ),
        "promotion_authorized": False,
        "strict_independent_ev_required": bool(absolute_keys),
        "primary_economic_scale": "no_tax_roi (BJ Single Match 0.65 factor included; per-ticket tax not deducted)",
        "all_seed_positive_numeric_sampler_candidates": len(all_seed_numeric),
        "loyo_stable_numeric_sampler_candidates": len(set(loyo_stable_numeric)),
        "absolute_edge_numeric_sampler_candidates": len(set(absolute_numeric)),
        "all_seed_positive_deterministic_top_mass_candidates": len(all_seed_deterministic),
        "loyo_stable_deterministic_top_mass_candidates": len(set(loyo_stable_deterministic)),
        "absolute_edge_deterministic_top_mass_candidates": len(set(absolute_deterministic)),
        "all_scope_positive_selector_candidates": selector_all_seed,
        "loyo_stable_selector_candidates": selector_loyo_stable,
        "all_scope_positive_hard_control_candidates": hard_control_all_seed,
        "loyo_stable_hard_control_candidates": hard_control_loyo_stable,
        "stable_efficiency_signals": [candidate_descriptor(key, stable_signal_rows[key], "DETERMINISTIC" if key[2] == "TOP_MODEL_P_CAL_DISTINCT" else "THREE_FROZEN_SEEDS") for key in stable_keys],
        "promotion_candidates": promotion_candidates,
        "rule": "Primary ranking and decision use common-support no-tax ROI deltas. Numeric samplers require positive ALL deltas in all three frozen seeds and positive deltas in every leave-one-year-out omission and seed. Deterministic top-mass is evaluated separately without a numeric-seed requirement. YEAR and FOLD rows are diagnostics, not unanimity vetoes. A stable lift whose candidate no-tax ROI is positive in every frozen seed is a positive candidate requiring strict independent EV; tax-adjusted metrics remain secondary execution sensitivity.",
    }


def roi(gross: float, tax: float, stake: float, include_tax: bool) -> float | None:
    if not stake:
        return None
    return (gross - (tax if include_tax else 0.0) - stake) / stake


def delta_for_pairs(pairs: list[tuple[str, dict[str, str], dict[str, str]]]) -> float | None:
    candidate_stake = sum(parse_float(candidate, "planned_stake_yuan") for _, candidate, _ in pairs)
    baseline_stake = sum(parse_float(baseline, "planned_stake_yuan") for _, _, baseline in pairs)
    candidate_roi = roi(sum(parse_float(candidate, "gross_pre_tax_yuan") for _, candidate, _ in pairs), 0.0, candidate_stake, False)
    baseline_roi = roi(sum(parse_float(baseline, "gross_pre_tax_yuan") for _, _, baseline in pairs), 0.0, baseline_stake, False)
    return candidate_roi - baseline_roi if candidate_roi is not None and baseline_roi is not None else None


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise RuntimeError("empty bootstrap distribution")
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * probability)]


def candidate_fragility_rows(decision: dict[str, object]) -> Iterator[dict[str, object]]:
    """Issue-resampled, pair-preserving concentration diagnostics for absolute candidates."""
    targets: dict[tuple[str, str, str, str, str, str], dict[str, object]] = {}
    for candidate in decision["promotion_candidates"]:  # type: ignore[index]
        for seed in candidate["seeds"]:  # type: ignore[index]
            key = (
                str(candidate["gate_id"]), str(candidate["top_k_id"]), str(candidate["sampler_id"]),
                str(candidate["probability_vector"]), str(candidate["M"]), str(seed),
            )
            targets[key] = candidate
    paired: dict[tuple[str, str, str, str, str, str], list[tuple[str, dict[str, str], dict[str, str]]]] = defaultdict(list)
    for rows in iter_issue_rows():
        index = {plan_key(row): row for row in rows}
        for target in targets:
            gate, top, _, _, _, _ = target
            candidate = index.get(target)
            baseline = index.get((gate, top, "FULL_N7_CONTROL", "UNIFORM_FULL", "2187", "NA"))
            if candidate is not None and baseline is not None and candidate["settlement_status"] == baseline["settlement_status"] == "SETTLED":
                paired[target].append((rows[0]["issue_instance"], candidate, baseline))
    for key, rows in sorted(paired.items()):
        if not rows:
            raise RuntimeError(f"positive candidate lacks common settled support: {key}")
        descriptor = targets[key]
        candidate_stake = sum(parse_float(candidate, "planned_stake_yuan") for _, candidate, _ in rows)
        baseline_stake = sum(parse_float(baseline, "planned_stake_yuan") for _, _, baseline in rows)
        candidate_gross = sum(parse_float(candidate, "gross_pre_tax_yuan") for _, candidate, _ in rows)
        baseline_gross = sum(parse_float(baseline, "gross_pre_tax_yuan") for _, _, baseline in rows)
        candidate_tax = sum(parse_float(candidate, "tax_yuan") for _, candidate, _ in rows)
        baseline_tax = sum(parse_float(baseline, "tax_yuan") for _, _, baseline in rows)
        candidate_no_tax = roi(candidate_gross, candidate_tax, candidate_stake, False)
        baseline_no_tax = roi(baseline_gross, baseline_tax, baseline_stake, False)
        candidate_tax_adjusted = roi(candidate_gross, candidate_tax, candidate_stake, True)
        baseline_tax_adjusted = roi(baseline_gross, baseline_tax, baseline_stake, True)
        top = max(rows, key=lambda item: parse_float(item[1], "gross_pre_tax_yuan"))
        top_issue, top_candidate, _ = top
        ex_largest = [item for item in rows if item[0] != top_issue]
        ex_candidate_stake = sum(parse_float(candidate, "planned_stake_yuan") for _, candidate, _ in ex_largest)
        ex_baseline_stake = sum(parse_float(baseline, "planned_stake_yuan") for _, _, baseline in ex_largest)
        ex_candidate_no_tax = roi(sum(parse_float(candidate, "gross_pre_tax_yuan") for _, candidate, _ in ex_largest), 0.0, ex_candidate_stake, False)
        ex_baseline_no_tax = roi(sum(parse_float(baseline, "gross_pre_tax_yuan") for _, _, baseline in ex_largest), 0.0, ex_baseline_stake, False)
        loo_deltas = [delta_for_pairs([item for item in rows if item[0] != issue]) for issue, _, _ in rows]
        loo_deltas = [value for value in loo_deltas if value is not None]
        bootstrap_rng = random.Random("bj137-common-support-bootstrap|" + "|".join(key))
        bootstrap_draws = 5_000
        bootstrap: list[float] = []
        for _ in range(bootstrap_draws):
            draw = [rows[bootstrap_rng.randrange(len(rows))] for _ in range(len(rows))]
            value = delta_for_pairs(draw)
            if value is not None:
                bootstrap.append(value)
        yield {
            "gate_id": key[0], "top_k_id": key[1], "sampler_id": key[2], "probability_vector": key[3],
            "mechanism": descriptor["mechanism"], "M": key[4], "seed": key[5],
            "baseline_sampler_id": "FULL_N7_CONTROL", "baseline_probability_vector": "UNIFORM_FULL",
            "baseline_M": "2187", "baseline_seed": "NA", "matched_settled_issue_count": len(rows),
            "candidate_no_tax_roi": ratio(candidate_no_tax), "baseline_no_tax_roi": ratio(baseline_no_tax),
            "no_tax_roi_delta": ratio(candidate_no_tax-baseline_no_tax if candidate_no_tax is not None and baseline_no_tax is not None else None),
            "candidate_tax_adjusted_roi": ratio(candidate_tax_adjusted), "baseline_tax_adjusted_roi": ratio(baseline_tax_adjusted),
            "tax_adjusted_roi_delta": ratio(candidate_tax_adjusted-baseline_tax_adjusted if candidate_tax_adjusted is not None and baseline_tax_adjusted is not None else None),
            "candidate_gross_top_issue_share": ratio(parse_float(top_candidate, "gross_pre_tax_yuan") / candidate_gross if candidate_gross else None),
            "candidate_largest_issue": top_issue, "candidate_largest_issue_gross_yuan": fmt(parse_float(top_candidate, "gross_pre_tax_yuan")),
            "candidate_ex_largest_issue_no_tax_roi": ratio(ex_candidate_no_tax), "baseline_ex_largest_issue_no_tax_roi": ratio(ex_baseline_no_tax),
            "ex_largest_issue_no_tax_roi_delta": ratio(ex_candidate_no_tax-ex_baseline_no_tax if ex_candidate_no_tax is not None and ex_baseline_no_tax is not None else None),
            "leave_one_issue_out_count": len(loo_deltas), "leave_one_issue_out_positive_delta_count": sum(value > 0.0 for value in loo_deltas),
            "worst_leave_one_issue_out_no_tax_roi_delta": ratio(min(loo_deltas) if loo_deltas else None),
            "bootstrap_draws": len(bootstrap), "bootstrap_seed": "bj137-common-support-bootstrap",
            "bootstrap_no_tax_roi_delta_p025": ratio(percentile(bootstrap, 0.025)),
            "bootstrap_no_tax_roi_delta_p500": ratio(percentile(bootstrap, 0.5)),
            "bootstrap_no_tax_roi_delta_p975": ratio(percentile(bootstrap, 0.975)),
        }


def stability_rows(path: Path) -> Iterator[dict[str, object]]:
    """YEAR/FOLD dispersion diagnostics for every matched surface cell."""
    grouped: dict[tuple[str, str, str, str, str, str, str, str, str, str, str, str], list[float]] = defaultdict(list)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row["scope"] not in {"YEAR", "FOLD"} or not row["no_tax_roi_delta"]:
                continue
            key = (
                row["effect"], row["scope"], row["gate_id"], row["top_k_id"], row["sampler_id"],
                row["probability_vector"], row["mechanism"], row["M"], row["seed"],
                row["baseline_sampler_id"], row["baseline_top_k_id"], row["baseline_M"],
            )
            grouped[key].append(float(row["no_tax_roi_delta"]))
    for key, values in sorted(grouped.items()):
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        yield {
            "effect": key[0], "diagnostic_scope": key[1], "gate_id": key[2], "top_k_id": key[3],
            "sampler_id": key[4], "probability_vector": key[5], "mechanism": key[6], "M": key[7],
            "seed": key[8], "baseline_sampler_id": key[9], "baseline_top_k_id": key[10], "baseline_M": key[11],
            "observed_slices": len(values), "positive_pre_tax_delta_count": sum(value > 0.0 for value in values),
            "positive_pre_tax_delta_fraction": ratio(sum(value > 0.0 for value in values) / len(values)),
            "worst_pre_tax_delta": ratio(min(values)), "best_pre_tax_delta": ratio(max(values)),
            "mean_pre_tax_delta": ratio(mean), "stddev_pre_tax_delta": ratio(variance ** 0.5),
        }


def effect_summary(path: Path, decision: dict[str, object]) -> str:
    totals: dict[str, int] = defaultdict(int)
    best_sampler: dict[str, str] | None = None
    best_q_vs_p: dict[str, str] | None = None
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            totals[row["effect"]] += 1
            if row["scope"] != "ALL" or not row["no_tax_roi_delta"]:
                continue
            if row["effect"] == "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT":
                if best_sampler is None or float(row["no_tax_roi_delta"]) > float(best_sampler["no_tax_roi_delta"]):
                    best_sampler = row
            if row["effect"] == "SAMPLER_VS_P_MIN_GLOBAL_DELETE_CONTROL_COMMON_SUPPORT" and row["sampler_id"] == "Q_MIN_GLOBAL_DELETE_CONTROL":
                if best_q_vs_p is None or float(row["no_tax_roi_delta"]) > float(best_q_vs_p["no_tax_roi_delta"]):
                    best_q_vs_p = row
    lines = [
        "# #137 Gate B v3 — common-support parameter-surface interpretation",
        "",
        "This derivative preserves the accepted Gate-A v2 freeze and audited v2r1 ticket-tax ledger. It reattributes effects only on the exact complete-issue intersection where both candidate and baseline settle. The complete compact surface is `common_support_effects.csv.gz`; every row carries gate, K, M, vector, mechanism/WR-WOR semantics, support counts, primary pre-tax ROI and matched deltas, and secondary tax-adjusted results.",
        "",
        "## Effect families and coverage",
        "",
        "| Effect family | Rows | Comparator |",
        "| --- | ---: | --- |",
    ]
    labels = {
        "SELECTOR_VS_K_ALL_FULL_COMMON_SUPPORT": "FULL K against same-gate K_ALL FULL",
        "SAMPLER_VS_EXACT_K_FULL_COMMON_SUPPORT": "sampler against exact selected-K FULL",
        "INTERACTION_VS_K_ALL_FULL_COMMON_SUPPORT": "sampler against same-gate K_ALL FULL",
        "SAMPLER_VS_P_MIN_GLOBAL_DELETE_CONTROL_COMMON_SUPPORT": "M=1458 sampler against p_min hard delete",
        "SAMPLER_VS_Q_MIN_GLOBAL_DELETE_CONTROL_COMMON_SUPPORT": "M=1458 sampler against q hard delete",
    }
    for effect in sorted(totals):
        lines.append(f"| {effect} | {totals[effect]:,} | {labels.get(effect, 'documented in CSV')} |")
    lines.extend([
        "",
        "## Terminal interpretation",
        "",
        "- Primary decision scale: `no_tax_roi` and `no_tax_roi_delta`, including Beijing Single Match's 0.65 payout factor but before per-ticket tax. Tax-adjusted quantities are secondary execution sensitivity only.",
        f"- Numeric samplers: {decision['all_seed_positive_numeric_sampler_candidates']} ALL-scope three-seed pre-tax positives; {decision['loyo_stable_numeric_sampler_candidates']} remain positive in every LOYO omission; {decision['absolute_edge_numeric_sampler_candidates']} also have positive pre-tax ROI in every seed.",
        f"- Deterministic top-mass: {decision['all_seed_positive_deterministic_top_mass_candidates']} ALL-scope positives; {decision['loyo_stable_deterministic_top_mass_candidates']} LOYO-stable; {decision['absolute_edge_deterministic_top_mass_candidates']} absolute-edge candidates under its no-seed rule.",
        f"- FULL selector pairs: {decision['all_scope_positive_selector_candidates']} ALL-scope positives; {decision['loyo_stable_selector_candidates']} LOYO-stable. Hard-control deltas: {decision['all_scope_positive_hard_control_candidates']} ALL-scope positives; {decision['loyo_stable_hard_control_candidates']} LOYO-stable.",
        "- `stability_diagnostics.csv` summarizes each YEAR/FOLD parameter-surface cell's positive-slice fraction, worst/best/mean pre-tax delta and dispersion; these rows are not a high-variance N7 unanimity veto.",
        "- Consequently the result is `" + str(decision["decision"]) + "`. `candidate_fragility.csv` reports concentration, pre-tax leave-one-issue-out deltas and deterministic issue-bootstrap intervals for every positive absolute-edge candidate; no purchase or production authority follows from this package.",
        "",
        "## Largest common-support signals",
        "",
    ])
    if best_sampler is not None:
        lines.append(
            "- Best ALL-scope sampler-minus-exact-FULL primary pre-tax delta: "
            f"{best_sampler['gate_id']} / {best_sampler['top_k_id']} / {best_sampler['sampler_id']} / M={best_sampler['M']} / seed={best_sampler['seed']}; "
            f"matched support={best_sampler['matched_settled_issue_count']}, candidate pre-tax ROI={best_sampler['candidate_no_tax_roi']}, "
            f"pre-tax delta={best_sampler['no_tax_roi_delta']}, secondary tax delta={best_sampler['tax_adjusted_roi_delta']}. Its LOYO rows determine candidate stability; YEAR/FOLD rows remain diagnostic."
        )
    if best_q_vs_p is not None:
        lines.append(
            "- Largest ALL-scope q-minus-p hard-control primary pre-tax delta: "
            f"{best_q_vs_p['gate_id']} / {best_q_vs_p['top_k_id']} / M={best_q_vs_p['M']}; "
            f"matched support={best_q_vs_p['matched_settled_issue_count']}, pre-tax delta={best_q_vs_p['no_tax_roi_delta']}, secondary tax delta={best_q_vs_p['tax_adjusted_roi_delta']}. "
            "This is a matched control comparison, not evidence that q deletion is a stable edge."
        )
    lines.extend([
        "",
        "## Diagnostic corrections",
        "",
        "`largest_event_tax_sensitivity.csv` removes both the largest issue gross and that same issue's tax from each ALL/YEAR/FOLD/LOYO aggregate, and reports the corresponding pre-tax result. `calibration_diagnostics_corrected.csv` excludes missing outcomes from both the Brier numerator and denominator while retaining the gap count and coverage denominator.",
    ])
    return "\n".join(lines) + "\n"


def write_effects(stage: Path) -> dict[str, object]:
    handles = gzip_writer(stage / "common_support_effects.csv.gz", EFFECT_FIELDS)
    writer = handles[-1]
    try:
        all_values = aggregate("ALL")
        year_values = aggregate_by_dimension("year")
        for key, value in sorted(all_values.items()):
            writer.writerow(effect_row("ALL", "ALL", key, value))
        for year, values in sorted(year_values.items()):
            for key, value in sorted(values.items()):
                writer.writerow(effect_row("YEAR", year, key, value))
        years = sorted(year_values)
        zero = PairAggregate.empty()
        for omitted_year in years:
            for key, value in sorted(all_values.items()):
                writer.writerow(effect_row("LEAVE_ONE_YEAR_OUT", omitted_year, key, subtract(value, year_values.get(omitted_year, {}).get(key, zero))))
        del year_values
        del all_values
        fold_values = aggregate_by_dimension("fold")
        for fold, values in sorted(fold_values.items()):
            for key, value in sorted(values.items()):
                writer.writerow(effect_row("FOLD", fold, key, value))
    finally:
        close_gzip(handles)
    with gzip.open(stage / "common_support_effects.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        rows = sum(1 for _ in csv.DictReader(handle))
    return {"common_support_effect_rows": rows}


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    exact_bundle(INPUT, INPUT_MANIFEST)
    if not SOURCE_LEDGER.is_file() or not SOURCE_SUMMARY.is_file():
        raise RuntimeError("audited v2r1 parent lacks the required numeric ledger")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj137_gateb_v3_", dir=output.parent))
    try:
        provenance, snapshot = validate_inputs(stage)
        outcomes = load_outcomes(snapshot)
        effect_info = write_effects(stage)
        write_csv(stage / "largest_event_tax_sensitivity.csv", TAX_SENSITIVITY_FIELDS, sensitivity_rows())
        write_csv(stage / "calibration_diagnostics_corrected.csv", CALIBRATION_CORRECTION_FIELDS, corrected_calibration(outcomes))
        decision = decision_from_common_effects(stage / "common_support_effects.csv.gz")
        if not decision["promotion_candidates"]:
            raise RuntimeError("expected at least one PI-audited absolute pre-tax candidate; fail closed")
        write_csv(stage / "candidate_fragility.csv", FRAGILITY_FIELDS, candidate_fragility_rows(decision))
        write_csv(stage / "stability_diagnostics.csv", STABILITY_FIELDS, stability_rows(stage / "common_support_effects.csv.gz"))
        (stage / "parameter_surface_interpretation.md").write_text(effect_summary(stage / "common_support_effects.csv.gz", decision), encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj137_gate_b_outcome_settlement_v2r1", "role": "audited per-ticket-tax issue-policy source ledger", "manifest_sha256": INPUT_MANIFEST, "payload": "issue_policy_settlement.csv.gz; ticket_tax_ledger.csv.gz; ticket_tax_reconciliation.csv", "payload_sha256": sha(SOURCE_LEDGER), "rows": 5_028_600, "join_status": "exact parent manifest; all Gate-A v2 selection/sampling and tax settlement inherited unchanged"},
            {"source": "bj137_gate_a_preoutcome_v2", "role": "accepted outcome-unexposed source for calibration correction", "manifest_sha256": FREEZE_MANIFEST, "payload": "match_vectors.csv", "payload_sha256": provenance["gate_a_content_identity_sha256"], "rows": 47_819, "join_status": "only accepted v2 freeze; no v3 material read"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical final-SP outcomes for calibration correction", "manifest_sha256": OUTCOME_MANIFEST, "payload": "canonical_outcome_join.csv", "payload_sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "outcome rows missing canonical truth are excluded from Brier numerator and denominator"},
        ])
        card = {
            "issue": 137,
            "contract": CONTRACT,
            "runner_version": "bj137-gate-b-v3-common-support",
            "stage": "GATE_B_COMMON_SUPPORT_ATTRIBUTION_CORRECTION",
            "provenance": {
                "gate_a_manifest_sha256": FREEZE_MANIFEST,
                "outcome_manifest_sha256": OUTCOME_MANIFEST,
                "outcome_payload_sha256": OUTCOME_PAYLOAD,
                "v2r1_parent_manifest_sha256": INPUT_MANIFEST,
                "v2r1_issue_policy_ledger_sha256": sha(SOURCE_LEDGER),
            },
            "input_boundary": "This derivative reads only the accepted Gate-A v2 boundary through the audited v2r1 issue-policy ledger, plus the same canonical outcome source for a calibration diagnostic correction. It does not read Gate-A v3 or alter any frozen selection, sampled draw, ticket tax, final-SP outcome, stake, gross or parent-ledger value.",
            "common_support": "Every selector, sampler, interaction and M=1458 hard-control comparison sums candidate and baseline only over the exact complete-issue intersection where both policy rows have settlement_status=SETTLED. Candidate, baseline and matched support counts are carried on every result row.",
            "hard_controls": "At M=1458 each sampler is compared, where applicable, with P_MIN_GLOBAL_DELETE_CONTROL and Q_MIN_GLOBAL_DELETE_CONTROL on exact common support. P-versus-Q is reported in both directions for complete control attribution.",
            "primary_metric": "All strategy ranking, common-support lift, candidate signal and strict-EV trigger use no_tax_roi: BJ Single Match's 0.65 factor is already in payout; the per-ticket 20% tax is not deducted. tax_adjusted_roi is mandatory secondary execution sensitivity and cannot veto the pre-tax conclusion.",
            "stability_rule": "A numeric sampler needs positive common-support no-tax delta in every frozen seed at ALL scope and every LOYO omission/seed. YEAR and FOLD rows are retained as diagnostics only; stability_diagnostics.csv reports their positive-slice fraction, worst/best/mean delta and dispersion for every matched surface cell. A stable candidate whose absolute no-tax ROI is positive in every frozen seed requires strict independent EV; no promotion authority is granted here.",
            "diagnostics": "Largest-event sensitivity removes the same issue gross and tax. candidate_fragility.csv adds matched pre-tax largest-event removal, leave-one-issue-out matched delta and fixed-seed issue-bootstrap intervals. Calibration excludes missing canonical outcomes from both the Brier numerator and denominator while reporting outcome gap counts.",
            "decision": decision,
            "scope": "historical paper research only; no purchase, production or promotion authority.",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        lineage = {
            "parent_package": str(INPUT.relative_to(ROOT)),
            "parent_manifest_sha256": INPUT_MANIFEST,
            "parent_issue_policy_ledger_sha256": sha(SOURCE_LEDGER),
            "correction": "Recompute effect attribution on exact common settled complete-issue support; add M=1458 hard-control deltas; evaluate deterministic top-mass without a seed requirement; make no_tax_roi primary with ALL-plus-LOYO stability; treat YEAR/FOLD as diagnostics; correct largest-event tax removal and missing-outcome Brier handling; add candidate concentration, leave-one-issue-out and issue-bootstrap fragility diagnostics.",
        }
        (stage / "NUMERIC_LINEAGE.json").write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "common_support_runner.py")
        (stage / "README.md").write_text("# #137 Gate B v3 — common-support attribution\n\nImmutable derivative of audited v2r1. It leaves the accepted Gate-A v2 and v2r1 ticket-level settlement unchanged, and corrects matched comparison attribution, primary pre-tax decision logic, and requested diagnostics. Historical paper research only; a positive candidate still has no promotion authority and requires strict independent EV.\n", encoding="utf-8")
        snapshot.unlink()
        gzip_payloads = ("common_support_effects.csv.gz",)
        content = {
            "contract_version": "bj137-gate-b-common-support-v1",
            "gzip_payloads": {name: {"canonical_decompressed_sha256": uncompressed(stage / name)[0], "canonical_decompressed_bytes": uncompressed(stage / name)[1]} for name in gzip_payloads},
            "non_compressed_controls": {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_payloads},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha(output / "SHA256SUMS.json"), "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"), **effect_info, "decision": decision}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
