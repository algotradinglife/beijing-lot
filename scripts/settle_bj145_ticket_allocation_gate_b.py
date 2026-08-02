#!/usr/bin/env python3
"""One-shot Gate-B settlement for #145's immutable ticket-allocation freeze.

The runner consumes only the merged #145 Gate-A v8 package and the accepted
canonical final-SP/result join.  Allocation is performed from the
manifest-bound v8 engine (with a bisect/rank fast path whose outputs are
checked against that engine); no candidate, weight, M, cap, seed, or stake
rule is selected after an outcome is read.  Issue rows are streamed through a
stage-local SQLite index and all published compressed payloads use a
deterministic gzip header.  No /tmp path is used.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import ctypes
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import importlib.util
import io
import itertools
import json
import math
import os
import random
import shutil
import sqlite3
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Iterable


CONTRACT = "BJ-HIST-TICKET-ALLOCATION-001"
VERSION = "bj145-gate-b-v1-outcome-settlement"
GATE_A_MANIFEST = "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
SOURCE_151_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
SOURCE_154_MANIFEST = "f81146959fd734c3d15a2579a3921b2afc86d6f633e174c8294763279f9937c5"
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
SOURCE_148_MANIFEST = "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6"
CODES = ("3", "1", "0")
N, FULL_TICKETS = 7, 2187
UNIT_STAKE = Decimal("2")
PAYOUT_FACTOR = Decimal("0.65")
TAX_RATE, TAX_THRESHOLD = Decimal("0.20"), Decimal("10000")
MONEY_QUANTUM = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 200
getcontext().prec = 80

OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
WEIGHT_SOURCES = ("MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50", "BLEND_A75", "Q_WEIGHT")
WEIGHT_FIELDS = {
    "MODEL_P_CAL": "p_model{}",
    "MARKET_WF_CAL": "p_market_cal{}",
    "BLEND_A25": "p_blend_a25_{}",
    "BLEND_A50": "p_blend_a50_{}",
    "BLEND_A75": "p_blend_a75_{}",
    "Q_WEIGHT": "q_weight{}",
}

ISSUE_FIELDS = (
    "arm_id", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance", "selection_status",
    "settlement_status", "weight_source", "mechanism", "sampling_role", "cap", "M", "seed", "seed_role",
    "selected_identity_count", "planned_draw_count", "planned_stake_yuan", "frozen_planned_draw_count",
    "frozen_planned_stake_yuan", "full_control_stake_yuan", "frozen_full_control_stake_yuan",
    "capital_utilization_vs_full", "unique_ticket_draw_count", "duplicate_ticket_draw_count",
    "duplicate_ticket_draw_group_count", "unique_ticket_coverage", "duplicate_ticket_ratio", "hit_ticket_count",
    "coverage_hit", "winning_identity_count", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "gross_top_identity_share",
    "outcome_gap_count", "taxable_hit_ticket_count", "non_taxable_hit_ticket_count", "truth_target_mass_mean",
    "truth_realized_frequency", "truth_frequency_delta",
)
TICKET_FIELDS = (
    "arm_id", "issue", "fold", "year", "issue_instance", "weight_source", "mechanism", "sampling_role",
    "cap", "M", "seed", "portfolio_id", "winning_code", "winning_ticket_gross_yuan", "winning_ticket_count",
    "per_ticket_tax_yuan", "tax_yuan", "tax_rule",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "arm_id", "gate_id", "top_k_id", "weight_source", "mechanism", "sampling_role",
    "cap", "M", "seed", "frozen_issue_count", "frozen_available_issue_count", "frozen_no_bet_issue_count",
    "settled_issue_count", "unavailable_outcome_issue_count", "planned_draw_count", "frozen_planned_draw_count",
    "stake_yuan", "frozen_stake_yuan", "full_control_stake_yuan", "frozen_full_control_stake_yuan",
    "capital_utilization_vs_full", "stake_mean_yuan", "stake_p50_yuan", "stake_p90_yuan", "stake_p95_yuan",
    "stake_max_yuan", "unique_ticket_draw_count", "duplicate_ticket_draw_count", "duplicate_ticket_draw_group_count",
    "unique_ticket_coverage", "duplicate_ticket_ratio", "hit_ticket_count", "winning_identity_count",
    "coverage_hits", "coverage_hit_rate", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "gross_top_issue_share",
    "gross_issue_hhi", "gross_top_identity_share", "largest_issue_gross_yuan", "max_drawdown_yuan",
    "longest_miss_streak", "outcome_gap_count", "truth_target_mass_mean", "truth_realized_frequency",
    "truth_frequency_delta",
)
FULL_DELTA_FIELDS = (
    "scope", "scope_value", "arm_id", "weight_source", "sampling_role", "mechanism", "cap", "M", "seed",
    "baseline_mechanism", "baseline_M", "support_issue_count", "no_tax_roi", "full_no_tax_roi", "no_tax_roi_delta",
    "tax_adjusted_roi", "full_tax_adjusted_roi", "tax_adjusted_roi_delta", "coverage_hit_rate",
    "full_coverage_hit_rate", "coverage_hit_rate_delta", "unique_ticket_coverage", "full_unique_ticket_coverage",
    "unique_ticket_coverage_delta", "duplicate_ticket_ratio", "full_duplicate_ticket_ratio",
    "duplicate_ticket_ratio_delta", "comparison_rule",
)
PAIR_FIELDS = (
    "scope", "scope_value", "arm_id", "weight_source", "M", "left_mechanism", "left_cap", "left_seed",
    "right_mechanism", "right_cap", "right_seed", "support_issue_count", "left_no_tax_roi", "right_no_tax_roi",
    "no_tax_roi_delta_left_minus_right", "left_tax_adjusted_roi", "right_tax_adjusted_roi",
    "tax_adjusted_roi_delta_left_minus_right", "coverage_hit_rate_delta_left_minus_right",
    "duplicate_ratio_delta_left_minus_right", "comparison_rule",
)
BOOTSTRAP_FIELDS = (
    "comparison", "scope", "scope_value", "arm_id", "weight_source", "mechanism", "cap", "M", "seed",
    "baseline_mechanism", "baseline_cap", "baseline_seed", "metric", "support_issue_count", "replicates",
    "point_estimate", "ci95_low", "ci95_high", "one_sided_positive_p", "two_sided_sign_p",
)
CODE_FIELDS = (
    "scope", "scope_value", "arm_id", "weight_source", "mechanism", "sampling_role", "cap", "M", "seed",
    "truth_code", "identity_count", "draw_count", "target_mass_sum", "target_mass_mean", "hit_ticket_count",
    "realized_frequency", "frequency_delta",
)
MC_FIELDS = (
    "family", "family_count", "comparison", "arm_id", "weight_source", "mechanism", "cap", "M", "seed",
    "raw_p", "holm_rank", "holm_p", "positive_issue_count", "negative_issue_count", "zero_issue_count",
    "support_issue_count", "multiplicity_rule",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")

_FAST_ALLOCATOR = None
_FAST_ALLOCATOR_SOURCE = None


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
GATE_A = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj145_gate_b_outcome_settlement_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def decompressed_digest(path: Path) -> tuple[str, int]:
    digest, count = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            count += len(block)
    return digest.hexdigest(), count


def decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal | float | int | None) -> str:
    return "" if value is None else format(Decimal(str(value)).quantize(MONEY_QUANTUM), "f")


def ratio(value: Decimal | float | int | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def verified_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, newline="", encoding="utf-8")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush()
    text.detach()
    zipped.close()
    raw.close()


def load_engine():
    binding = json.loads((GATE_A / "allocation_binding.json").read_text(encoding="utf-8"))
    module_path = GATE_A / binding["module_file"]
    if sha256(module_path) != binding["module_sha256"]:
        raise RuntimeError("Gate-A allocator module binding drift")
    spec = importlib.util.spec_from_file_location("bj145_gate_b_allocator", module_path)
    if not spec or not spec.loader:
        raise RuntimeError("Gate-A allocator import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if tuple(module.CODES) != CODES or tuple(module.MECHANISMS) != (
        "WR_DUPLICATE_STAKE", "WOR_DISTINCT", "RESIDUAL_SYSTEMATIC", "CAPPED_REPEAT", "DETERMINISTIC_TOP_MASS", "FULL_ENUMERATED",
    ):
        raise RuntimeError("allocator mechanism namespace drift")
    golden_path = GATE_A / binding["golden_vectors_file"]
    if sha256(golden_path) != binding["golden_vectors_sha256"]:
        raise RuntimeError("Gate-A golden-vector binding drift")
    vectors = json.loads(golden_path.read_text(encoding="utf-8"))
    weights = module.golden_weights(FULL_TICKETS)
    for case in vectors["cases"]:
        counts = module.allocate(case["mechanism"], weights, case["M"], seed=case["seed"], identity_signature=case["identity_signature"], cap=case["cap"])
        if module.counts_fingerprint(counts) != {key: case[key] for key in ("counts_sha256", "draw_count", "unique_count", "duplicate_count", "max_multiplicity")}:
            raise RuntimeError(f"golden-vector mismatch: {case['mechanism']}")
    return module, binding, vectors


def fast_profile(weights: tuple[float, ...], truth: int, cap: int, m_grid: tuple[int, ...]) -> dict[int, tuple[int, int, int, int]]:
    """Use a compiled dependency-free mirror for Hamilton/capped metrics.

    The C++ routine is deliberately limited to the integer allocation and
    metric loop.  Stable hash sampling and all identity/payout accounting
    remain in Python, while the exact frozen implementation is retained as
    the binding reference and is cross-checked by tests.
    """
    global _FAST_ALLOCATOR, _FAST_ALLOCATOR_SOURCE
    if _FAST_ALLOCATOR is None:
        source_candidates = [Path(__file__).with_name("bj145_fast_alloc.cpp"), ROOT / "scripts" / "bj145_fast_alloc.cpp"]
        source = next((item for item in source_candidates if item.is_file()), None)
        if source is None:
            raise RuntimeError("fast allocator source unavailable")
        build_dir = ROOT / ".scratch"
        build_dir.mkdir(parents=True, exist_ok=True)
        library = build_dir / "bj145_fast_alloc.so"
        if not library.is_file() or library.stat().st_mtime < source.stat().st_mtime:
            subprocess.run(["g++", "-O3", "-std=c++17", "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
        _FAST_ALLOCATOR = ctypes.CDLL(str(library))
        _FAST_ALLOCATOR.bj145_profile.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        _FAST_ALLOCATOR.bj145_profile.restype = None
        for name in ("bj145_wr_profile", "bj145_wor_profile"):
            function = getattr(_FAST_ALLOCATOR, name)
            function.argtypes = [ctypes.POINTER(ctypes.c_double), ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
            function.restype = None
        _FAST_ALLOCATOR_SOURCE = source
    values = (ctypes.c_double * len(weights))(*weights)
    ms = (ctypes.c_int * len(m_grid))(*m_grid)
    result = (ctypes.c_int * (len(m_grid) * 4))()
    _FAST_ALLOCATOR.bj145_profile(values, len(weights), int(truth), int(cap), ms, len(m_grid), result)
    return {m: tuple(int(result[index * 4 + offset]) for offset in range(4)) for index, m in enumerate(m_grid)}


def fast_sample_profile(weights: tuple[float, ...], truth: int, mechanism: str, seed: str, signature: str, m_grid: tuple[int, ...]) -> dict[int, tuple[int, int, int, int]]:
    global _FAST_ALLOCATOR
    if _FAST_ALLOCATOR is None:
        fast_profile(weights, truth, 0, (m_grid[0],))
    values = (ctypes.c_double * len(weights))(*weights)
    ms = (ctypes.c_int * len(m_grid))(*m_grid)
    result = (ctypes.c_int * (len(m_grid) * 4))()
    function = _FAST_ALLOCATOR.bj145_wr_profile if mechanism == "WR_DUPLICATE_STAKE" else _FAST_ALLOCATOR.bj145_wor_profile
    function(values, len(weights), int(truth), str(seed).encode(), signature.encode(), ms, len(m_grid), result)
    return {m: tuple(int(result[index * 4 + offset]) for offset in range(4)) for index, m in enumerate(m_grid)}


def load_outcomes() -> dict[str, dict[str, str]]:
    outcome_manifest = verified_bundle(OUTCOME_SOURCE, OUTCOME_MANIFEST)
    if outcome_manifest.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    with (OUTCOME_SOURCE / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        rows = list(reader)
    outcomes = {row["match_id"]: row for row in rows}
    if len(outcomes) != len(rows):
        raise RuntimeError("duplicate canonical outcome match id")
    for row in outcomes.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or decimal(row["winning_sp"], "winning SP") <= 0:
            raise RuntimeError("untrusted canonical outcome")
    return outcomes


@dataclass
class Identity:
    arm_id: str
    issue_instance: str
    portfolio_id: str
    roles: tuple[dict[str, str], ...]
    truth_index: int | None
    truth_code: str | None
    payout_per_ticket: Decimal | None
    gap_count: int
    _weights: dict[str, tuple[float, ...]]

    def weights(self, source: str) -> tuple[float, ...]:
        if source not in self._weights:
            values = [1.0]
            template = WEIGHT_FIELDS[source]
            for role in self.roles:
                vector = tuple(float(role[template.format(code)]) for code in CODES)
                if any(not math.isfinite(value) or value <= 0 for value in vector) or sum(vector) <= 0:
                    raise RuntimeError(f"invalid {source} vector: {self.portfolio_id}")
                values = tuple(prefix * value for prefix in values for value in vector)
            if len(values) != FULL_TICKETS or sum(values) <= 0:
                raise RuntimeError(f"invalid {source} ticket vector: {self.portfolio_id}")
            self._weights[source] = values
        return self._weights[source]


def load_freeze(engine, outcomes: dict[str, dict[str, str]]) -> tuple[list[dict[str, str]], dict[tuple[str, str], list[Identity]], dict[tuple[str, str], list[dict[str, str]]], dict[str, str]]:
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    content = json.loads((GATE_A / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_TICKET_ALLOCATION_FREEZE":
        raise RuntimeError("Gate-A contract drift")
    if content.get("contract_version") != "bj145-gate-a-content-v7":
        raise RuntimeError("Gate-A content contract drift")
    for name in ("identity_catalog.csv.gz", "role_vectors.csv.gz", "allocation_plan.csv.gz"):
        expected = content["gzip_payloads"][name]["canonical_decompressed_sha256"]
        if decompressed_digest(GATE_A / name)[0] != expected:
            raise RuntimeError(f"Gate-A canonical gzip drift: {name}")
    with (GATE_A / "selection_cohort.csv").open(newline="", encoding="utf-8") as handle:
        cohort = list(csv.DictReader(handle))
    if len(cohort) != 696 or Counter((r["arm_id"], r["selection_status"]) for r in cohort) != Counter({
        ("PRIMARY_NO_GATE_K4", "AVAILABLE"): 339, ("PRIMARY_NO_GATE_K4", "NO_BET_K_UNSATISFIED"): 9,
        ("SECONDARY_ESP300_GM290_K8", "AVAILABLE"): 273, ("SECONDARY_ESP300_GM290_K8", "NO_BET_K_UNSATISFIED"): 75,
    }):
        raise RuntimeError("Gate-A cohort drift")
    with gzip.open(GATE_A / "identity_catalog.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identity_rows = list(csv.DictReader(handle))
    with gzip.open(GATE_A / "role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        role_rows = list(csv.DictReader(handle))
    if len(identity_rows) != 3540 or len(role_rows) != 24780:
        raise RuntimeError("Gate-A identity/role denominator drift")
    role_map: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in role_rows:
        role_map[(row["arm_id"], row["issue_instance"], row["portfolio_id"])].append(row)
    by_issue: dict[tuple[str, str], list[Identity]] = defaultdict(list)
    for row in identity_rows:
        key = (row["arm_id"], row["issue_instance"], row["portfolio_id"])
        roles = tuple(sorted(role_map[key], key=lambda value: int(value["selection_rank"])))
        if len(roles) != N or [int(value["selection_rank"]) for value in roles] != list(range(1, N + 1)):
            raise RuntimeError(f"role geometry drift: {key}")
        if "|".join(value["match_id"] for value in roles) != row["selected_match_ids"]:
            raise RuntimeError(f"identity/role binding drift: {key}")
        truth, product, gaps = 0, Decimal(1), 0
        for role in roles:
            outcome = outcomes.get(role["match_id"])
            if outcome is None:
                gaps += 1
                continue
            truth = truth * 3 + CODES.index(outcome["result_code"])
            product *= decimal(outcome["winning_sp"], "winning SP")
        by_issue[(row["arm_id"], row["issue_instance"])].append(Identity(
            row["arm_id"], row["issue_instance"], row["portfolio_id"], roles,
            None if gaps else truth, None if gaps else engine.ticket_code(truth),
            None if gaps else UNIT_STAKE * PAYOUT_FACTOR * product, gaps, {},
        ))
    cohorts = {(r["arm_id"], r["issue_instance"]): r for r in cohort}
    if set(by_issue) != {key for key, row in cohorts.items() if row["selection_status"] == "AVAILABLE"}:
        raise RuntimeError("identity/cohort membership drift")
    if sum(len(values) for values in by_issue.values()) != 3540:
        raise RuntimeError("identity count drift")
    manifest = verified_bundle(GATE_A, GATE_A_MANIFEST)
    return cohort, by_issue, role_map, {**manifest, "SHA256SUMS.json": GATE_A_MANIFEST}


def iter_plan_groups() -> Iterable[tuple[tuple[str, str], list[dict[str, str]]]]:
    current: tuple[str, str] | None = None
    group: list[dict[str, str]] = []
    with gzip.open(GATE_A / "allocation_plan.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["arm_id"], row["issue_instance"])
            if current is not None and key != current:
                yield current, group
                group = []
            current = key
            group.append(row)
    if current is not None:
        yield current, group


def profile_metrics(engine, weights: tuple[float, ...], truth: int, seed: str, signature: str, mechanism: str, cap: int | None, m_grid: tuple[int, ...]) -> dict[int, tuple[int, int, int, int]]:
    """Return hit/unique/duplicate/group counts for every M in one allocation cell.

    WR uses bisect over the exact raw-unit cumulative semantics.  WOR and top
    use the exact engine key/order definitions but only retain the truth rank;
    residual/capped/full call the manifest-bound implementation directly.
    """
    maximum = max(m_grid)
    if mechanism == "WR_DUPLICATE_STAKE":
        return fast_sample_profile(weights, truth, mechanism, seed, signature, m_grid)
    if mechanism == "WOR_DISTINCT":
        return fast_sample_profile(weights, truth, mechanism, seed, signature, m_grid)
    if mechanism == "RESIDUAL_SYSTEMATIC":
        return fast_profile(weights, truth, 0, m_grid)
    if mechanism == "CAPPED_REPEAT":
        if cap is None:
            raise RuntimeError("capped allocation missing cap")
        return fast_profile(weights, truth, cap, m_grid)
    if mechanism == "DETERMINISTIC_TOP_MASS":
        rank = 1 + sum(((-weights[ordinal], ordinal) < (-weights[truth], truth)) for ordinal in range(FULL_TICKETS) if ordinal != truth)
        return {m: (int(rank <= m), m, 0, 0) for m in m_grid}
    output = {}
    for m in m_grid:
        if mechanism == "FULL_ENUMERATED":
            counts = (1,) * FULL_TICKETS
        else:
            raise RuntimeError(f"unknown allocation mechanism: {mechanism}")
        unique = sum(value > 0 for value in counts)
        output[m] = (int(counts[truth]), unique, m - unique, sum(value > 1 for value in counts))
    return output


def profile_request(request: tuple[tuple[str, str, str, str, str], Identity, str, str, int | None, str, tuple[int, ...], object]) -> tuple[tuple[str, str, str, str, str], dict[int, tuple[int, int, int, int]]]:
    cache_key, identity, weight_source, mechanism, cap, seed, m_grid, engine = request
    weights = identity.weights(weight_source)
    profile = profile_metrics(engine, weights, int(identity.truth_index), seed, "|".join(role["match_id"] for role in identity.roles), mechanism, cap, m_grid)
    return cache_key, profile


def outcome_row(plan: dict[str, str], status: str, identities: list[Identity], metrics: list[tuple[Identity, tuple[int, int, int, int], float]], full_frozen: int) -> dict[str, object]:
    frozen_draw = int(plan["planned_draw_count"])
    frozen_stake = Decimal(plan["planned_stake_yuan"])
    count = int(plan["selected_identity_count"])
    if status != "SETTLED":
        return {
            **{key: plan[key] for key in ("arm_id", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance", "selection_status", "weight_source", "mechanism", "sampling_role", "cap", "M", "seed", "seed_role")},
            "settlement_status": status, "selected_identity_count": count, "planned_draw_count": 0, "planned_stake_yuan": money(0),
            "frozen_planned_draw_count": frozen_draw, "frozen_planned_stake_yuan": money(frozen_stake), "full_control_stake_yuan": money(0),
            "frozen_full_control_stake_yuan": money(full_frozen), "capital_utilization_vs_full": "", "unique_ticket_draw_count": 0,
            "duplicate_ticket_draw_count": 0, "duplicate_ticket_draw_group_count": 0, "unique_ticket_coverage": "", "duplicate_ticket_ratio": "",
            "hit_ticket_count": 0, "coverage_hit": 0, "winning_identity_count": 0, "gross_pre_tax_yuan": money(0), "tax_yuan": money(0),
            "after_tax_gross_yuan": money(0), "pre_tax_net_yuan": money(0), "tax_adjusted_net_yuan": money(0), "no_tax_roi": "", "tax_adjusted_roi": "",
            "gross_top_identity_share": "", "outcome_gap_count": sum(identity.gap_count for identity in identities), "taxable_hit_ticket_count": 0,
            "non_taxable_hit_ticket_count": 0, "truth_target_mass_mean": "", "truth_realized_frequency": "", "truth_frequency_delta": "",
        }
    draws = count * int(plan["M"])
    unique = sum(item[1] for _, item, _ in metrics)
    duplicates = sum(item[2] for _, item, _ in metrics)
    groups = sum(item[3] for _, item, _ in metrics)
    hits = sum(item[0] for _, item, _ in metrics)
    gross = sum((identity.payout_per_ticket or Decimal(0)) * item[0] for identity, item, _ in metrics)
    tax = sum(((identity.payout_per_ticket or Decimal(0)).quantize(MONEY_QUANTUM) * TAX_RATE).quantize(MONEY_QUANTUM) * item[0] if (identity.payout_per_ticket or Decimal(0)).quantize(MONEY_QUANTUM) >= TAX_THRESHOLD else Decimal(0) for identity, item, _ in metrics)
    gross_by_identity = [(identity.payout_per_ticket or Decimal(0)) * item[0] for identity, item, _ in metrics]
    target_mass = sum(Decimal(str(weight)) for _, _, weight in metrics) / Decimal(count) if count else None
    realized_frequency = Decimal(hits) / Decimal(draws) if draws else None
    full_stake = Decimal(full_frozen)
    stake = Decimal(draws) * UNIT_STAKE
    per_ticket_net = gross - stake
    tax_net = gross - tax - stake
    return {
        **{key: plan[key] for key in ("arm_id", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance", "selection_status", "weight_source", "mechanism", "sampling_role", "cap", "M", "seed", "seed_role")},
        "settlement_status": "SETTLED", "selected_identity_count": count, "planned_draw_count": draws, "planned_stake_yuan": money(stake),
        "frozen_planned_draw_count": frozen_draw, "frozen_planned_stake_yuan": money(frozen_stake), "full_control_stake_yuan": money(full_stake),
        "frozen_full_control_stake_yuan": money(full_stake), "capital_utilization_vs_full": ratio(stake / full_stake if full_stake else None),
        "unique_ticket_draw_count": unique, "duplicate_ticket_draw_count": duplicates, "duplicate_ticket_draw_group_count": groups,
        "unique_ticket_coverage": ratio(Decimal(unique) / Decimal(draws) if draws else None), "duplicate_ticket_ratio": ratio(Decimal(duplicates) / Decimal(draws) if draws else None),
        "hit_ticket_count": hits, "coverage_hit": int(hits > 0), "winning_identity_count": sum(item[0] > 0 for _, item, _ in metrics),
        "gross_pre_tax_yuan": money(gross), "tax_yuan": money(tax), "after_tax_gross_yuan": money(gross - tax),
        "pre_tax_net_yuan": money(per_ticket_net), "tax_adjusted_net_yuan": money(tax_net), "no_tax_roi": ratio(per_ticket_net / stake if stake else None),
        "tax_adjusted_roi": ratio(tax_net / stake if stake else None), "gross_top_identity_share": ratio(max(gross_by_identity, default=Decimal(0)) / gross if gross else None),
        "outcome_gap_count": 0, "taxable_hit_ticket_count": sum(item[0] for identity, item, _ in metrics if (identity.payout_per_ticket or Decimal(0)).quantize(MONEY_QUANTUM) >= TAX_THRESHOLD),
        "non_taxable_hit_ticket_count": sum(item[0] for identity, item, _ in metrics if (identity.payout_per_ticket or Decimal(0)).quantize(MONEY_QUANTUM) < TAX_THRESHOLD),
        "truth_target_mass_mean": ratio(target_mass), "truth_realized_frequency": ratio(realized_frequency), "truth_frequency_delta": ratio(realized_frequency - target_mass if realized_frequency is not None and target_mass is not None else None),
    }


def config_key(row: dict[str, object]) -> tuple[str, str, str, str, str, str, str]:
    return (str(row["arm_id"]), str(row["weight_source"]), str(row["mechanism"]), str(row["sampling_role"]), str(row["cap"]), str(row["M"]), str(row["seed"]))


def summary(scope: str, scope_value: str, rows: list[dict[str, str]]) -> dict[str, object]:
    if not rows:
        raise RuntimeError("empty summary scope")
    settled = [row for row in rows if row["settlement_status"] == "SETTLED"]
    stake = sum((decimal(row["planned_stake_yuan"], "stake") for row in rows), Decimal(0))
    frozen_stake = sum((decimal(row["frozen_planned_stake_yuan"], "frozen stake") for row in rows), Decimal(0))
    full_stake = sum((decimal(row["full_control_stake_yuan"], "full stake") for row in rows), Decimal(0))
    frozen_full = sum((decimal(row["frozen_full_control_stake_yuan"], "frozen full stake") for row in rows), Decimal(0))
    gross = sum((decimal(row["gross_pre_tax_yuan"], "gross") for row in rows), Decimal(0))
    tax = sum((decimal(row["tax_yuan"], "tax") for row in rows), Decimal(0))
    net = sum((decimal(row["pre_tax_net_yuan"], "pre-tax net") for row in rows), Decimal(0))
    tax_net = sum((decimal(row["tax_adjusted_net_yuan"], "tax net") for row in rows), Decimal(0))
    draws = sum(int(row["planned_draw_count"]) for row in rows)
    frozen_draws = sum(int(row["frozen_planned_draw_count"]) for row in rows)
    unique = sum(int(row["unique_ticket_draw_count"]) for row in rows)
    duplicate = sum(int(row["duplicate_ticket_draw_count"]) for row in rows)
    duplicate_groups = sum(int(row["duplicate_ticket_draw_group_count"]) for row in rows)
    hits = sum(int(row["hit_ticket_count"]) for row in rows)
    winning_identities = sum(int(row["winning_identity_count"]) for row in rows)
    coverage_hits = sum(int(row["coverage_hit"]) for row in rows)
    issue_gross = [decimal(row["gross_pre_tax_yuan"], "issue gross") for row in rows]
    cumulative = peak = drawdown = Decimal(0)
    misses = longest = 0
    for row in sorted(rows, key=lambda item: (int(item["year"]), int(item["issue"]))):
        cumulative += decimal(row["tax_adjusted_net_yuan"], "tax net")
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        if int(row["coverage_hit"]):
            misses = 0
        else:
            misses += 1
            longest = max(longest, misses)
    first = rows[0]
    target_values = [Decimal(row["truth_target_mass_mean"]) for row in settled if row["truth_target_mass_mean"]]
    realized_values = [Decimal(row["truth_realized_frequency"]) for row in settled if row["truth_realized_frequency"]]
    target_mean = sum(target_values, Decimal(0)) / len(target_values) if target_values else None
    realized_mean = sum(realized_values, Decimal(0)) / len(realized_values) if realized_values else None
    hhi = sum((item / gross) ** 2 for item in issue_gross) if gross else None
    return {
        "scope": scope, "scope_value": scope_value, **{key: first[key] for key in ("arm_id", "gate_id", "top_k_id", "weight_source", "mechanism", "sampling_role", "cap", "M", "seed")},
        "frozen_issue_count": len(rows), "frozen_available_issue_count": sum(row["selection_status"] == "AVAILABLE" for row in rows),
        "frozen_no_bet_issue_count": sum(row["selection_status"] != "AVAILABLE" for row in rows), "settled_issue_count": len(settled),
        "unavailable_outcome_issue_count": sum(row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME" for row in rows),
        "planned_draw_count": draws, "frozen_planned_draw_count": frozen_draws, "stake_yuan": money(stake), "frozen_stake_yuan": money(frozen_stake),
        "full_control_stake_yuan": money(full_stake), "frozen_full_control_stake_yuan": money(frozen_full),
        "capital_utilization_vs_full": ratio(stake / full_stake if full_stake else None), "stake_mean_yuan": money(stake / len(rows)),
        "stake_p50_yuan": money(sorted(decimal(row["planned_stake_yuan"], "stake") for row in rows)[len(rows) // 2]),
        "stake_p90_yuan": money(sorted(decimal(row["planned_stake_yuan"], "stake") for row in rows)[math.ceil(len(rows) * .90) - 1]),
        "stake_p95_yuan": money(sorted(decimal(row["planned_stake_yuan"], "stake") for row in rows)[math.ceil(len(rows) * .95) - 1]),
        "stake_max_yuan": money(max(decimal(row["planned_stake_yuan"], "stake") for row in rows)), "unique_ticket_draw_count": unique,
        "duplicate_ticket_draw_count": duplicate, "duplicate_ticket_draw_group_count": duplicate_groups,
        "unique_ticket_coverage": ratio(Decimal(unique) / Decimal(draws) if draws else None), "duplicate_ticket_ratio": ratio(Decimal(duplicate) / Decimal(draws) if draws else None),
        "hit_ticket_count": hits, "winning_identity_count": winning_identities, "coverage_hits": coverage_hits,
        "coverage_hit_rate": ratio(Decimal(coverage_hits) / Decimal(len(rows))), "gross_pre_tax_yuan": money(gross), "tax_yuan": money(tax),
        "after_tax_gross_yuan": money(gross - tax), "pre_tax_net_yuan": money(net), "tax_adjusted_net_yuan": money(tax_net),
        "no_tax_roi": ratio(net / stake if stake else None), "tax_adjusted_roi": ratio(tax_net / stake if stake else None),
        "gross_top_issue_share": ratio(max(issue_gross, default=Decimal(0)) / gross if gross else None), "gross_issue_hhi": ratio(hhi),
        "gross_top_identity_share": ratio(max((decimal(row["gross_top_identity_share"], "identity share") for row in settled if row["gross_top_identity_share"]), default=Decimal(0))),
        "largest_issue_gross_yuan": money(max(issue_gross, default=Decimal(0))), "max_drawdown_yuan": money(drawdown), "longest_miss_streak": longest,
        "outcome_gap_count": sum(int(row["outcome_gap_count"]) for row in rows), "truth_target_mass_mean": ratio(target_mean),
        "truth_realized_frequency": ratio(realized_mean), "truth_frequency_delta": ratio(realized_mean - target_mean if target_mean is not None and realized_mean is not None else None),
    }


def grouped_scopes(rows: list[dict[str, str]]) -> Iterable[tuple[str, str, list[dict[str, str]]]]:
    yield "ALL", "ALL", rows
    for field, scope in (("year", "YEAR"), ("fold", "FOLD")):
        values = sorted({row[field] for row in rows})
        for value in values:
            yield scope, value, [row for row in rows if row[field] == value]
    for value in sorted({row["year"] for row in rows}):
        yield "LOYO", f"WITHOUT_{value}", [row for row in rows if row["year"] != value]


def p_sign(values: list[Decimal]) -> tuple[float, int, int, int]:
    nonzero = [value for value in values if value != 0]
    n = len(nonzero)
    positive = sum(value > 0 for value in nonzero)
    negative = n - positive
    if not n:
        return 1.0, 0, 0, len(values)
    tail = sum(math.comb(n, k) for k in range(max(positive, negative), n + 1)) / (2 ** n)
    return min(1.0, 2 * tail), positive, negative, len(values) - n


def holm(rows: list[dict[str, object]], family: str) -> list[dict[str, object]]:
    selected = [row for row in rows if row["family"] == family]
    selected.sort(key=lambda row: (float(row["raw_p"]), str(row["comparison"])))
    m = len(selected)
    previous = 0.0
    for rank, row in enumerate(selected, 1):
        adjusted = min(1.0, max(previous, float(row["raw_p"]) * (m - rank + 1)))
        previous = adjusted
        row["family_count"] = m
        row["holm_rank"] = rank
        row["holm_p"] = adjusted
    return rows


def bootstrap_pair(candidate: list[dict[str, str]], baseline: list[dict[str, str]], metric: str, seed_text: str) -> dict[str, object]:
    joined = [(a, b) for a, b in zip(sorted(candidate, key=lambda r: r["issue_instance"]), sorted(baseline, key=lambda r: r["issue_instance"])) if a["issue_instance"] == b["issue_instance"]]
    valid = [(a, b) for a, b in joined if decimal(a["planned_stake_yuan"], "candidate stake") > 0 and decimal(b["planned_stake_yuan"], "baseline stake") > 0]
    if not valid:
        return {"support_issue_count": 0, "point_estimate": None, "ci95_low": None, "ci95_high": None, "one_sided_positive_p": None, "two_sided_sign_p": None, "replicates": BOOTSTRAP_REPLICATES}
    def value(a, b):
        return (decimal(a[metric], metric) / decimal(a["planned_stake_yuan"], "candidate stake")) - (decimal(b[metric], metric) / decimal(b["planned_stake_yuan"], "baseline stake"))
    point_values = [value(a, b) for a, b in valid]
    point = sum(point_values, Decimal(0)) / len(point_values)
    rng = random.Random(int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big"))
    samples, positive, negative = [], 0, 0
    n = len(valid)
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [valid[rng.randrange(n)] for _ in range(n)]
        total_a = total_b = stake_a = stake_b = Decimal(0)
        for a, b in sample:
            total_a += decimal(a[metric], metric); stake_a += decimal(a["planned_stake_yuan"], "candidate stake")
            total_b += decimal(b[metric], metric); stake_b += decimal(b["planned_stake_yuan"], "baseline stake")
        delta = total_a / stake_a - total_b / stake_b
        samples.append(delta)
        positive += delta >= 0
        negative += delta <= 0
    samples.sort()
    return {
        "support_issue_count": n, "point_estimate": point, "ci95_low": samples[math.floor(.025 * len(samples))],
        "ci95_high": samples[math.ceil(.975 * len(samples)) - 1], "one_sided_positive_p": Decimal(1 + negative) / Decimal(1 + len(samples)),
        "two_sided_sign_p": min(Decimal(1), Decimal(2) * min(Decimal(1 + positive) / Decimal(1 + len(samples)), Decimal(1 + negative) / Decimal(1 + len(samples)))),
        "replicates": BOOTSTRAP_REPLICATES,
    }


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj145_gate_b_", dir=output.parent))
    db_path = stage / "issue_allocation_index.sqlite"
    try:
        engine, binding, vectors = load_engine()
        outcome_manifest = verified_bundle(OUTCOME_SOURCE, OUTCOME_MANIFEST)
        outcomes = load_outcomes()
        cohort, identities_by_issue, role_map, gate_a_manifest = load_freeze(engine, outcomes)
        with (GATE_A / "m_grid.csv").open(newline="", encoding="utf-8") as handle:
            m_grid = tuple(int(row["M"]) for row in csv.DictReader(handle))
        if m_grid != tuple(range(16, 257, 16)) + (512, 1024, 1458, 2187):
            raise RuntimeError("Gate-A M-grid drift")
        cohort_map = {(row["arm_id"], row["issue_instance"]): row for row in cohort}
        plan_groups = iter_plan_groups()
        connection = sqlite3.connect(db_path)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("CREATE TABLE issue_rows (config TEXT NOT NULL, arm_id TEXT NOT NULL, weight_source TEXT NOT NULL, mechanism TEXT NOT NULL, sampling_role TEXT NOT NULL, cap TEXT NOT NULL, m_value INTEGER NOT NULL, seed TEXT NOT NULL, issue_instance TEXT NOT NULL, year INTEGER NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE INDEX issue_rows_config ON issue_rows (config, year, issue_instance)")
        issue_output = gzip_writer(stage / "issue_allocation_settlement.csv.gz", ISSUE_FIELDS)
        ticket_output = gzip_writer(stage / "winning_ticket_tax_ledger.csv.gz", TICKET_FIELDS)
        issue_writer, ticket_writer = issue_output[-1], ticket_output[-1]
        profiles: dict[tuple[str, str, str, str, str], dict[int, tuple[int, int, int, int]]] = {}
        code_agg: defaultdict[tuple[str, str, str, str, str, str, str, str], list[Decimal | int]] = defaultdict(lambda: [0, 0, Decimal(0), 0])
        tax_audit: defaultdict[tuple[str, str, str, str, str, str, str], list[Decimal | int]] = defaultdict(lambda: [0, 0, Decimal(0)])
        expected_plan_rows = 0
        issue_group_count = 0
        try:
            for key, plans in plan_groups:
                issue_group_count += 1
                if key not in cohort_map:
                    raise RuntimeError(f"plan group outside frozen cohort: {key}")
                cohort_row = cohort_map[key]
                if len(plans) != 1446:
                    raise RuntimeError(f"per-issue allocation plan drift: {key} ({len(plans)})")
                identities = identities_by_issue.get(key, [])
                complete = bool(identities) and all(identity.gap_count == 0 for identity in identities)
                if complete:
                    requests = {}
                    for frozen_plan in plans:
                        mechanism_name = frozen_plan["mechanism"]
                        cap_value = None if frozen_plan["cap"] == "NA" else int(frozen_plan["cap"])
                        for identity in identities:
                            cache_key = (identity.portfolio_id, frozen_plan["weight_source"], mechanism_name, frozen_plan["cap"], frozen_plan["seed"])
                            requests.setdefault(cache_key, (cache_key, identity, frozen_plan["weight_source"], mechanism_name, cap_value, frozen_plan["seed"], m_grid, engine))
                    # Initialize the shared ctypes library before threads can
                    # race on its lazy loader; the work itself releases the
                    # GIL inside the native metric loop.
                    first_identity = identities[0]
                    fast_profile(first_identity.weights("MODEL_P_CAL"), int(first_identity.truth_index), 0, (m_grid[0],))
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        for cache_key, profile in executor.map(profile_request, requests.values()):
                            profiles[cache_key] = profile
                for plan in plans:
                    expected_plan_rows += 1
                    available = plan["selection_status"] == "AVAILABLE"
                    full_frozen = int(plan["selected_identity_count"]) * FULL_TICKETS * int(UNIT_STAKE) if available else 0
                    if not available:
                        status = "NO_BET_GATE_A"
                        metrics = []
                    elif not complete:
                        status = "UNAVAILABLE_CANONICAL_OUTCOME"
                        metrics = []
                    else:
                        status = "SETTLED"
                        metrics = []
                        mechanism, cap, m_value, seed = plan["mechanism"], (None if plan["cap"] == "NA" else int(plan["cap"])), int(plan["M"]), plan["seed"]
                        for identity in identities:
                            cache_key = (identity.portfolio_id, plan["weight_source"], mechanism, plan["cap"], seed)
                            profile = profiles[cache_key][m_value]
                            weights = identity.weights(plan["weight_source"])
                            metrics.append((identity, profile, weights[int(identity.truth_index)]))
                            code_key = (key[0], plan["weight_source"], mechanism, plan["sampling_role"], plan["cap"], str(m_value), seed, identity.truth_code or "")
                            code_agg[code_key][0] += 1
                            code_agg[code_key][1] += m_value
                            code_agg[code_key][2] += Decimal(str(weights[int(identity.truth_index)]))
                            code_agg[code_key][3] += profile[0]
                            if profile[0]:
                                gross = (identity.payout_per_ticket or Decimal(0)).quantize(MONEY_QUANTUM)
                                per_tax = (gross * TAX_RATE).quantize(MONEY_QUANTUM) if gross >= TAX_THRESHOLD else Decimal(0)
                                tax_key = (key[0], plan["weight_source"], mechanism, plan["cap"], str(m_value), seed, plan["sampling_role"])
                                tax_audit[tax_key][0] += profile[0]
                                tax_audit[tax_key][1] += int(bool(per_tax)) * profile[0]
                                tax_audit[tax_key][2] += per_tax * profile[0]
                                ticket_writer.writerow({"arm_id": key[0], "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"], "issue_instance": key[1], "weight_source": plan["weight_source"], "mechanism": mechanism, "sampling_role": plan["sampling_role"], "cap": plan["cap"], "M": m_value, "seed": seed, "portfolio_id": identity.portfolio_id, "winning_code": identity.truth_code, "winning_ticket_gross_yuan": money(gross), "winning_ticket_count": profile[0], "per_ticket_tax_yuan": money(per_tax), "tax_yuan": money(per_tax * profile[0]), "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"})
                    row = outcome_row(plan, status, identities, metrics, full_frozen)
                    config = "|".join(config_key(row))
                    issue_writer.writerow({field: row[field] for field in ISSUE_FIELDS})
                    connection.execute("INSERT INTO issue_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (config, row["arm_id"], row["weight_source"], row["mechanism"], row["sampling_role"], row["cap"], int(row["M"]), row["seed"], row["issue_instance"], int(row["year"]), json.dumps(row, sort_keys=True, separators=(",", ":"))))
                # Portfolio identities are issue-local.  Release the profile
                # metrics as soon as this 1,446-row issue block is persisted;
                # retaining the whole 348-issue surface causes unnecessary
                # gigabyte-scale memory growth without changing accounting.
                profiles.clear()
                if issue_group_count % 25 == 0:
                    print(f"settled issue groups: {issue_group_count}/696", flush=True)
            if expected_plan_rows != 1_006_416:
                raise RuntimeError(f"allocation-plan row denominator drift: {expected_plan_rows}")
        finally:
            close_gzip(issue_output); close_gzip(ticket_output)
        connection.commit()
        config_rows = list(connection.execute("SELECT DISTINCT config, arm_id, weight_source, mechanism, sampling_role, cap, m_value, seed FROM issue_rows ORDER BY arm_id, weight_source, mechanism, cap, m_value, seed"))
        if len(config_rows) != 2892:
            raise RuntimeError(f"configuration count drift: {len(config_rows)}")
        summaries = []
        for config, *_ in config_rows:
            payloads = [json.loads(value[0]) for value in connection.execute("SELECT payload FROM issue_rows WHERE config=? ORDER BY year, issue_instance", (config,))]
            if len(payloads) != 348:
                raise RuntimeError(f"configuration issue denominator drift: {config}")
            summaries.extend(summary(scope, value, subset) for scope, value, subset in grouped_scopes(payloads))
        summaries.sort(key=lambda row: (row["arm_id"], row["weight_source"], row["mechanism"], str(row["cap"]), int(row["M"]), row["seed"], row["scope"], row["scope_value"]))
        write_csv(stage / "mechanism_weight_surface_summary.csv", SUMMARY_FIELDS, summaries)
        full_index = {(row["scope"], row["scope_value"], row["arm_id"], row["weight_source"]): row for row in summaries if row["mechanism"] == "FULL_ENUMERATED"}
        full_deltas = []
        for row in summaries:
            if row["mechanism"] == "FULL_ENUMERATED":
                continue
            baseline = full_index[(row["scope"], row["scope_value"], row["arm_id"], row["weight_source"])]
            def diff(field):
                return ratio(Decimal(row[field]) - Decimal(baseline[field])) if row[field] and baseline[field] else ""
            full_deltas.append({"scope": row["scope"], "scope_value": row["scope_value"], "arm_id": row["arm_id"], "weight_source": row["weight_source"], "sampling_role": row["sampling_role"], "mechanism": row["mechanism"], "cap": row["cap"], "M": row["M"], "seed": row["seed"], "baseline_mechanism": "FULL_ENUMERATED", "baseline_M": FULL_TICKETS, "support_issue_count": row["settled_issue_count"], "no_tax_roi": row["no_tax_roi"], "full_no_tax_roi": baseline["no_tax_roi"], "no_tax_roi_delta": diff("no_tax_roi"), "tax_adjusted_roi": row["tax_adjusted_roi"], "full_tax_adjusted_roi": baseline["tax_adjusted_roi"], "tax_adjusted_roi_delta": diff("tax_adjusted_roi"), "coverage_hit_rate": row["coverage_hit_rate"], "full_coverage_hit_rate": baseline["coverage_hit_rate"], "coverage_hit_rate_delta": diff("coverage_hit_rate"), "unique_ticket_coverage": row["unique_ticket_coverage"], "full_unique_ticket_coverage": baseline["unique_ticket_coverage"], "unique_ticket_coverage_delta": diff("unique_ticket_coverage"), "duplicate_ticket_ratio": row["duplicate_ticket_ratio"], "full_duplicate_ticket_ratio": baseline["duplicate_ticket_ratio"], "duplicate_ticket_ratio_delta": diff("duplicate_ticket_ratio"), "comparison_rule": "same arm/weight/scope and exact frozen issue support; FULL stake is the K=2187 economic control"})
        write_csv(stage / "full_control_deltas.csv", FULL_DELTA_FIELDS, full_deltas)
        all_summary = {(row["arm_id"], row["weight_source"], row["mechanism"], row["cap"], row["M"], row["seed"]): row for row in summaries if row["scope"] == "ALL"}
        def load_config_rows(key: tuple[str, str, str, str, str, str]) -> list[dict[str, str]]:
            arm, weight, mechanism, cap, m_value, seed = key
            payloads = [json.loads(value[0]) for value in connection.execute(
                "SELECT payload FROM issue_rows WHERE arm_id=? AND weight_source=? AND mechanism=? AND cap=? AND m_value=? AND seed=? ORDER BY year, issue_instance",
                (arm, weight, mechanism, cap, int(m_value), seed),
            )]
            if len(payloads) != 348:
                raise RuntimeError(f"configuration issue denominator drift during replay: {key}: {len(payloads)}")
            return payloads
        pair_rows = []
        mechanisms = ("WR_DUPLICATE_STAKE", "WOR_DISTINCT", "RESIDUAL_SYSTEMATIC", "CAPPED_REPEAT", "DETERMINISTIC_TOP_MASS")
        for arm in ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8"):
            for weight in WEIGHT_SOURCES:
                for m in range(16, 257, 16):
                    variants = []
                    for mechanism in mechanisms:
                        caps = ("NA",) if mechanism != "CAPPED_REPEAT" else ("1", "2", "4", "8")
                        seeds = ("NA",) if mechanism not in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} else ("137001", "137002", "137003")
                        for cap in caps:
                            for seed in seeds:
                                variants.append((mechanism, cap, seed, all_summary[(arm, weight, mechanism, cap, str(m), seed)]))
                    for left, right in itertools.combinations(variants, 2):
                        if left[2] != right[2] and left[2] != "NA" and right[2] != "NA":
                            continue
                        l, r = left[3], right[3]
                        pair_rows.append({"scope": "ALL", "scope_value": "ALL", "arm_id": arm, "weight_source": weight, "M": m, "left_mechanism": left[0], "left_cap": left[1], "left_seed": left[2], "right_mechanism": right[0], "right_cap": right[1], "right_seed": right[2], "support_issue_count": min(int(l["settled_issue_count"]), int(r["settled_issue_count"])), "left_no_tax_roi": l["no_tax_roi"], "right_no_tax_roi": r["no_tax_roi"], "no_tax_roi_delta_left_minus_right": ratio(Decimal(l["no_tax_roi"]) - Decimal(r["no_tax_roi"])) if l["no_tax_roi"] and r["no_tax_roi"] else "", "left_tax_adjusted_roi": l["tax_adjusted_roi"], "right_tax_adjusted_roi": r["tax_adjusted_roi"], "tax_adjusted_roi_delta_left_minus_right": ratio(Decimal(l["tax_adjusted_roi"]) - Decimal(r["tax_adjusted_roi"])) if l["tax_adjusted_roi"] and r["tax_adjusted_roi"] else "", "coverage_hit_rate_delta_left_minus_right": ratio(Decimal(l["coverage_hit_rate"]) - Decimal(r["coverage_hit_rate"])), "duplicate_ratio_delta_left_minus_right": ratio(Decimal(l["duplicate_ticket_ratio"] or 0) - Decimal(r["duplicate_ticket_ratio"] or 0)), "comparison_rule": "equal arm/weight/M and issue-level stake; deterministic cells are compared against each frozen randomized seed"})
        write_csv(stage / "mechanism_pairwise_deltas.csv", PAIR_FIELDS, pair_rows)
        weight_pairs = []
        for arm in ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8"):
            for mechanism, cap, m, seed in {(row["mechanism"], row["cap"], row["M"], row["seed"]) for row in summaries if row["scope"] == "ALL" and row["mechanism"] != "FULL_ENUMERATED"}:
                for left_weight, right_weight in itertools.combinations(WEIGHT_SOURCES, 2):
                    l, r = all_summary[(arm, left_weight, mechanism, cap, m, seed)], all_summary[(arm, right_weight, mechanism, cap, m, seed)]
                    weight_pairs.append({"scope": "ALL", "scope_value": "ALL", "arm_id": arm, "weight_source": f"{left_weight}_VS_{right_weight}", "M": m, "left_mechanism": mechanism, "left_cap": cap, "left_seed": seed, "right_mechanism": mechanism, "right_cap": cap, "right_seed": seed, "support_issue_count": min(int(l["settled_issue_count"]), int(r["settled_issue_count"])), "left_no_tax_roi": l["no_tax_roi"], "right_no_tax_roi": r["no_tax_roi"], "no_tax_roi_delta_left_minus_right": ratio(Decimal(l["no_tax_roi"]) - Decimal(r["no_tax_roi"])) if l["no_tax_roi"] and r["no_tax_roi"] else "", "left_tax_adjusted_roi": l["tax_adjusted_roi"], "right_tax_adjusted_roi": r["tax_adjusted_roi"], "tax_adjusted_roi_delta_left_minus_right": ratio(Decimal(l["tax_adjusted_roi"]) - Decimal(r["tax_adjusted_roi"])) if l["tax_adjusted_roi"] and r["tax_adjusted_roi"] else "", "coverage_hit_rate_delta_left_minus_right": ratio(Decimal(l["coverage_hit_rate"]) - Decimal(r["coverage_hit_rate"])), "duplicate_ratio_delta_left_minus_right": ratio(Decimal(l["duplicate_ticket_ratio"] or 0) - Decimal(r["duplicate_ticket_ratio"] or 0)), "comparison_rule": "equal arm/mechanism/cap/M/seed and issue-level stake; weight-source effect only"})
        write_csv(stage / "weight_pairwise_deltas.csv", PAIR_FIELDS, weight_pairs)
        code_rows = []
        for key, values in sorted(code_agg.items()):
            arm, weight, mechanism, sampling_role, cap, m, seed, code = key
            identity_count, draw_count, target_sum, hit_count = values
            code_rows.append({"scope": "ALL", "scope_value": "ALL", "arm_id": arm, "weight_source": weight, "mechanism": mechanism, "sampling_role": sampling_role, "cap": cap, "M": m, "seed": seed, "truth_code": code, "identity_count": identity_count, "draw_count": draw_count, "target_mass_sum": ratio(target_sum), "target_mass_mean": ratio(target_sum / Decimal(identity_count)), "hit_ticket_count": hit_count, "realized_frequency": ratio(Decimal(hit_count) / Decimal(draw_count)), "frequency_delta": ""})
        write_csv(stage / "outcome_code_frequency.csv", CODE_FIELDS, code_rows)
        bootstrap_rows = []
        for row in full_deltas:
            if row["scope"] != "ALL":
                continue
            key = (row["arm_id"], row["weight_source"], row["mechanism"], row["sampling_role"], row["cap"], str(row["M"]), row["seed"])
            baseline_key = (row["arm_id"], row["weight_source"], "FULL_ENUMERATED", "FULL_ENUMERATED", "NA", str(FULL_TICKETS), "NA")
            candidate_key = (row["arm_id"], row["weight_source"], row["mechanism"], row["cap"], str(row["M"]), row["seed"])
            baseline_key = (row["arm_id"], row["weight_source"], "FULL_ENUMERATED", "NA", str(FULL_TICKETS), "NA")
            candidate, baseline = load_config_rows(candidate_key), load_config_rows(baseline_key)
            result = bootstrap_pair(candidate, baseline, "pre_tax_net_yuan", f"{CONTRACT}|BOOTSTRAP|{key}")
            bootstrap_rows.append({"comparison": "VS_FULL", "scope": "ALL", "scope_value": "ALL", "arm_id": row["arm_id"], "weight_source": row["weight_source"], "mechanism": row["mechanism"], "cap": row["cap"], "M": row["M"], "seed": row["seed"], "baseline_mechanism": "FULL_ENUMERATED", "baseline_cap": "NA", "baseline_seed": "NA", "metric": "no_tax_roi_delta", "support_issue_count": result["support_issue_count"], "replicates": result["replicates"], "point_estimate": ratio(result["point_estimate"]), "ci95_low": ratio(result["ci95_low"]), "ci95_high": ratio(result["ci95_high"]), "one_sided_positive_p": ratio(result["one_sided_positive_p"]), "two_sided_sign_p": ratio(result["two_sided_sign_p"])})
            result_tax = bootstrap_pair(candidate, baseline, "tax_adjusted_net_yuan", f"{CONTRACT}|BOOTSTRAP_TAX|{key}")
            bootstrap_rows.append({"comparison": "VS_FULL", "scope": "ALL", "scope_value": "ALL", "arm_id": row["arm_id"], "weight_source": row["weight_source"], "mechanism": row["mechanism"], "cap": row["cap"], "M": row["M"], "seed": row["seed"], "baseline_mechanism": "FULL_ENUMERATED", "baseline_cap": "NA", "baseline_seed": "NA", "metric": "tax_adjusted_roi_delta", "support_issue_count": result_tax["support_issue_count"], "replicates": result_tax["replicates"], "point_estimate": ratio(result_tax["point_estimate"]), "ci95_low": ratio(result_tax["ci95_low"]), "ci95_high": ratio(result_tax["ci95_high"]), "one_sided_positive_p": ratio(result_tax["one_sided_positive_p"]), "two_sided_sign_p": ratio(result_tax["two_sided_sign_p"])})
        write_csv(stage / "issue_bootstrap.csv", BOOTSTRAP_FIELDS, bootstrap_rows)
        mc_rows = []
        for row in full_deltas:
            if row["scope"] != "ALL" or not row["no_tax_roi_delta"]:
                continue
            key = (row["arm_id"], row["weight_source"], row["mechanism"], row["sampling_role"], row["cap"], str(row["M"]), row["seed"])
            baseline_key = (row["arm_id"], row["weight_source"], "FULL_ENUMERATED", "FULL_ENUMERATED", "NA", str(FULL_TICKETS), "NA")
            candidate_key = (row["arm_id"], row["weight_source"], row["mechanism"], row["cap"], str(row["M"]), row["seed"])
            baseline_key = (row["arm_id"], row["weight_source"], "FULL_ENUMERATED", "NA", str(FULL_TICKETS), "NA")
            candidate, baseline = load_config_rows(candidate_key), load_config_rows(baseline_key)
            values = []
            for a, b in zip(candidate, baseline):
                if decimal(a["planned_stake_yuan"], "candidate stake") and decimal(b["planned_stake_yuan"], "baseline stake"):
                    values.append(decimal(a["no_tax_roi"], "candidate ROI") - decimal(b["no_tax_roi"], "baseline ROI"))
            raw, positive, negative, zero = p_sign(values)
            mc_rows.append({"family": "ALL_FULL_NO_TAX_ROI", "family_count": "", "comparison": "VS_FULL", "arm_id": row["arm_id"], "weight_source": row["weight_source"], "mechanism": row["mechanism"], "cap": row["cap"], "M": row["M"], "seed": row["seed"], "raw_p": raw, "holm_rank": "", "holm_p": "", "positive_issue_count": positive, "negative_issue_count": negative, "zero_issue_count": zero, "support_issue_count": len(values), "multiplicity_rule": "two-sided paired issue sign test; Holm-Bonferroni over complete ALL-scope surface"})
        holm(mc_rows, "ALL_FULL_NO_TAX_ROI")
        write_csv(stage / "multiple_comparison.csv", MC_FIELDS, mc_rows)
        status_counts = Counter(row[0] for row in connection.execute("SELECT json_extract(payload, '$.settlement_status') FROM issue_rows"))
        if status_counts["SETTLED"] + status_counts["UNAVAILABLE_CANONICAL_OUTCOME"] + status_counts["NO_BET_GATE_A"] != 1_006_416:
            raise RuntimeError("settlement status denominator drift")
        # Reconcile every tax configuration against its individual-ticket ledger.
        ledger_keys = set(tax_audit)
        for key, audit in tax_audit.items():
            arm, weight, mechanism, cap, m, seed, sampling_role = key
            query = "SELECT payload FROM issue_rows WHERE arm_id=? AND weight_source=? AND mechanism=? AND cap=? AND m_value=? AND seed=?"
            issue_tax = sum((decimal(json.loads(payload)["tax_yuan"], "issue tax") for (payload,) in connection.execute(query, (arm, weight, mechanism, cap, int(m), seed))), Decimal(0))
            if abs(audit[2] - issue_tax) > MONEY_QUANTUM:
                raise RuntimeError(f"tax ledger mismatch: {key}: {audit[2] - issue_tax}")
        decision = {
            "decision": "DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION",
            "promotion_authorized": False,
            "gate_b_authorization": "PI_AUTHORIZED_ON_MERGED_PR_161",
            "primary_metric": "pre-tax no_tax_roi including BJ Single Match 0.65 factor; per-ticket tax secondary",
            "candidate_selection": "fixed #151 NO_GATE/K4 primary; exact #137 ESP300_GM290/K8 secondary; no reselection",
            "surface": "all 6 weight sources × 6 allocation mechanisms × frozen M/cap/seed surface × both arms",
            "positive_same_window_rule": "descriptive only; any positive cell requires strict independent EV and genuinely held-out/forward validation",
            "top_pre_tax_full_deltas": sorted((row for row in full_deltas if row["scope"] == "ALL" and row["no_tax_roi_delta"]), key=lambda row: float(row["no_tax_roi_delta"]), reverse=True)[:20],
            "negative_control": "No purchase, production, betting or promotion authority; no tax pooling",
        }
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = stage / "report.md"
        report.write_text("\n".join([
            "# #145 Gate B — calibrated ticket allocation settlement",
            "",
            f"This is the one-shot historical settlement of the immutable #145 Gate-A v8 package. Gate-A manifest: `{GATE_A_MANIFEST}`. Canonical outcome manifest: `{OUTCOME_MANIFEST}` / payload `{OUTCOME_PAYLOAD}`.",
            "",
            "Primary scale is pre-tax `no_tax_roi` (including the 0.65 BJ Single Match factor); tax-adjusted ROI is secondary and tax is assessed per individual winning ¥2 ticket only. No issue, identity, policy, or arm tax pooling is used.",
            "",
            "The complete surface is retained in `mechanism_weight_surface_summary.csv`, matched FULL deltas in `full_control_deltas.csv`, equal-stake mechanism contrasts in `mechanism_pairwise_deltas.csv`, weight-source contrasts in `weight_pairwise_deltas.csv`, outcome-code target/realized frequencies in `outcome_code_frequency.csv`, issue bootstrap in `issue_bootstrap.csv`, and Holm-adjusted paired issue tests in `multiple_comparison.csv`.",
            "",
            "This historical window is outcome-informed by construction. Any positive row is descriptive and requires strict independent EV plus genuinely held-out/forward validation. No result authorizes purchase, production, betting, or promotion.",
            "",
        ]) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj145_gate_a_preoutcome_v8", "role": "accepted immutable allocation identities, vectors and complete mechanism plan surface", "identity": "SHA256SUMS.json", "sha256": GATE_A_MANIFEST, "rows": 1_006_416, "join_status": "byte-verified before outcome read; no selection/M/weight/seed/stake rule changed"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical trusted result and final-SP join", "identity": "canonical_outcome_join.csv", "sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "trusted complete-issue settlement only; incomplete issues zero executed stake"},
            {"source": "bj151_gate_b_outcome_settlement_v1", "role": "contract context only; not read for outcome numbers", "identity": "SHA256SUMS.json", "sha256": "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2", "rows": "NA", "join_status": "#151/#154 lineage retained; no settled rows imported"},
            {"source": "bj154_independent_ev_v1", "role": "contract context only; not read for outcome numbers", "identity": "SHA256SUMS.json", "sha256": SOURCE_154_MANIFEST, "rows": "NA", "join_status": "independent EV lineage retained; no settlement rows imported"},
        ])
        card = {
            "issue": 145, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_ONE_SHOT_TICKET_ALLOCATION_OUTCOME_SETTLEMENT",
            "gate_a_manifest_sha256": GATE_A_MANIFEST, "outcome_manifest_sha256": OUTCOME_MANIFEST, "outcome_payload_sha256": OUTCOME_PAYLOAD,
            "allocator_binding": binding, "surface": {"issue_rows": expected_plan_rows, "configurations": len(config_rows), "summary_rows": len(summaries), "full_delta_rows": len(full_deltas), "mechanism_pairwise_rows": len(pair_rows), "weight_pairwise_rows": len(weight_pairs), "bootstrap_rows": len(bootstrap_rows), "code_rows": len(code_rows), "multiple_comparison_rows": len(mc_rows)},
            "accounting": {"unit_stake_yuan": 2, "primary": "pre-tax no_tax_roi", "tax_secondary": "20pct if individual winning ticket gross >= 10000; no pooling", "incomplete_issue_rule": "zero executed stake; retained in every denominator"},
            "outcome_boundary": "settled historical result/final-SP data is read only after Gate-A v8 byte verification; no future/prospective input or selection tuning",
            "decision": decision,
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "settlement_runner.py")
        if _FAST_ALLOCATOR_SOURCE is not None:
            shutil.copy2(_FAST_ALLOCATOR_SOURCE, stage / "bj145_fast_alloc.cpp")
        shutil.copy2(GATE_A / "bj145_allocation_engine.py", stage / "bj145_allocation_engine.py")
        connection.close(); db_path.unlink()
        compressed = ("issue_allocation_settlement.csv.gz", "winning_ticket_tax_ledger.csv.gz")
        content = {"contract_version": "bj145-gate-b-portable-content-v1", "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": decompressed_digest(stage / name)[1]} for name in compressed}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "issue_rows": expected_plan_rows, "configurations": len(config_rows), "summary_rows": len(summaries), "decision": decision["decision"]}
    except Exception:
        try:
            connection.close()
        except Exception:
            pass
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
