#!/usr/bin/env python3
"""One-shot Gate-B settlement for #137's accepted sampling freeze.

The runner accepts only the merged Gate-A v2 bundle and the canonical final-SP
join.  It settles the entire frozen gate×K×M sampler surface at complete-issue
granularity.  All temporary data is staged below ``results/``; /tmp is never
used.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import multiprocessing
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-PROB-SAMPLING-N7-001"
VERSION = "bj137-gate-b-v1"
FREEZE_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
FULL_K, DELETE_K = 2187, 1458
UNIT_STAKE, PAYOUT_FACTOR = 2.0, 0.65
TAX_RATE, TAX_THRESHOLD = 0.20, 10000.0
M_GRID = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1458, 2187)


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
FREEZE = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
OUTCOME_BUNDLE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v1"

ISSUE_FIELDS = (
    "issue", "fold", "year", "issue_instance", "eligible_match_count", "first_kickoff_ts",
    "last_kickoff_ts", "source_segment_count", "issue_disposition", "fold_integrity",
    "selection_scope",
)
PARTICIPATION_FIELDS = ISSUE_FIELDS + (
    "gate_id", "top_k_id", "requested_n7_count", "available_identity_count", "selected_identity_count",
    "selected_portfolio_ids", "full_ticket_count", "full_stake_yuan", "sample_M_scope",
    "issue_total_draw_formula", "issue_total_stake_formula", "disposition", "reason",
)
IDENTITY_FIELDS = ISSUE_FIELDS + (
    "gate_id", "e_sp_min", "gm_e_sp_min", "portfolio_id", "candidate_match_id",
    "candidate_rank_in_complete_issue", "candidate_count_complete_issue", "candidate_search_count",
    "candidate_cap_applied", "selected_match_ids", "selected_n", "gm_e_sp", "full_k",
    "full_stake_yuan", "p_min_delete_match_id", "p_min_delete_code", "q_min_delete_match_id",
    "q_min_delete_code", "descriptor_sha256", "participation_rank", "selection_scope",
    "segment_boundary",
)
ROLE_FIELDS = (
    "gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "match_id",
    "match_idx", "kickoff_ts", "selection_rank", "is_candidate", "e_sp", "p_min",
    "predicted_sp3", "predicted_sp1", "predicted_sp0", "p_model3", "p_model1", "p_model0",
    "p_market_raw3", "p_market_raw1", "p_market_raw0", "p_market_cal3", "p_market_cal1",
    "p_market_cal0", "p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0", "p_blend_a50_3",
    "p_blend_a50_1", "p_blend_a50_0", "p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0",
    "q_weight3", "q_weight1", "q_weight0", "p_min_delete_match_id", "p_min_delete_code",
    "q_min_delete_match_id", "q_min_delete_code",
)
PLAN_FIELDS = (
    "gate_id", "top_k_id", "requested_n7_count", "sampler_id", "probability_vector", "mechanism",
    "duplicate_policy", "M", "M_scope", "seed", "seed_role", "ticket_space_k",
    "stake_per_draw_yuan", "issue_total_draw_formula", "issue_total_stake_formula",
    "expected_unique_formula", "realized_unique_rule", "outcome_boundary", "primary_or_sensitivity",
)
OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
VECTOR_FIELDS = (
    "issue", "fold", "year", "issue_instance", "match_id", "match_idx", "kickoff_ts", "p3", "p1",
    "p0", "p_min", "p_max", "argmin_code", "e_sp", "predicted_sp3", "predicted_sp1",
    "predicted_sp0", "q3", "q1", "q0", "q_min", "q_min_code", "handicap_bucket", "market_raw3",
    "market_raw1", "market_raw0", "market_cal3", "market_cal1", "market_cal0", "blend_a25_3",
    "blend_a25_1", "blend_a25_0", "blend_a50_3", "blend_a50_1", "blend_a50_0", "blend_a75_3",
    "blend_a75_1", "blend_a75_0", "q_weight3", "q_weight1", "q_weight0", "model_market_l1_distance",
)

ISSUE_SETTLEMENT_FIELDS = (
    "issue", "fold", "year", "issue_instance", "first_kickoff_ts", "gate_id", "top_k_id",
    "requested_n7_count", "sampler_id", "probability_vector", "mechanism", "duplicate_policy", "M",
    "seed", "seed_role", "primary_or_sensitivity", "frozen_disposition", "settlement_status",
    "selected_identity_count", "planned_draw_count", "planned_stake_yuan", "realized_unique_ticket_count",
    "expected_unique_ticket_count", "hit_ticket_count", "coverage_hit", "gross_pre_tax_yuan", "tax_yuan",
    "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi",
    "unique_match_count", "total_leg_slots", "overlap_leg_slots", "max_match_exposure",
    "gross_top_identity_share", "outcome_gap_count", "tax_bucket_key",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "gate_id", "top_k_id", "requested_n7_count", "sampler_id",
    "probability_vector", "mechanism", "duplicate_policy", "M", "seed", "seed_role",
    "primary_or_sensitivity", "frozen_available_issue_count", "frozen_no_bet_issue_count",
    "settled_issue_count", "unavailable_outcome_issue_count", "planned_draw_count", "stake_yuan",
    "expected_unique_ticket_count", "realized_unique_ticket_count", "hit_ticket_count", "coverage_hits",
    "coverage_hit_rate", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan",
    "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "max_drawdown_yuan",
    "longest_miss_streak", "gross_top_issue_share", "largest_issue_gross_yuan",
    "ex_largest_issue_tax_adjusted_roi", "mean_overlap_leg_slots", "max_match_exposure",
)
LIFT_FIELDS = (
    "scope", "scope_value", "effect", "gate_id", "top_k_id", "sampler_id", "M", "seed",
    "baseline_sampler_id", "baseline_top_k_id", "baseline_M", "stake_yuan", "baseline_stake_yuan",
    "no_tax_roi", "baseline_no_tax_roi", "no_tax_roi_delta", "tax_adjusted_roi",
    "baseline_tax_adjusted_roi", "tax_adjusted_roi_delta", "coverage_hit_rate",
    "baseline_coverage_hit_rate", "coverage_hit_rate_delta",
)
CALIBRATION_FIELDS = (
    "probability_vector", "outcome_code", "probability_decile", "rows", "mean_probability",
    "observed_frequency", "brier_component", "outcome_coverage", "outcome_gap_count",
)
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "payload", "payload_sha256", "rows", "join_status")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt(value: float | None, digits: int = 6) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.12f}"


def exact_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest = path / "SHA256SUMS.json"
    if not manifest.is_file() or sha(manifest) != expected_manifest:
        raise RuntimeError(f"unaccepted manifest: {path}")
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in path.iterdir() if item.is_file() and item.name != manifest.name}
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def require_schema(reader: csv.DictReader, fields: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != fields:
        raise RuntimeError(f"{label} schema drift")


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush(); text.detach(); zipped.close(); raw.close()


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def write_gzip_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    handles = gzip_writer(path, fields)
    try:
        handles[-1].writerows(rows)
    finally:
        close_gzip(handles)


def uncompressed(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block); size += len(block)
    return digest.hexdigest(), size


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def weights_for(roles: list[dict[str, str]], vector: str) -> list[float]:
    columns = {
        "MODEL_P_CAL": ("p_model3", "p_model1", "p_model0"),
        "MARKET_WF_CAL": ("p_market_cal3", "p_market_cal1", "p_market_cal0"),
        "BLEND_A25": ("p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0"),
        "BLEND_A50": ("p_blend_a50_3", "p_blend_a50_1", "p_blend_a50_0"),
        "BLEND_A75": ("p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0"),
        "Q_WEIGHT": ("q_weight3", "q_weight1", "q_weight0"),
    }[vector]
    weights = [1.0]
    for role in roles:
        p = [float(role[column]) for column in columns]
        if any(item <= 0 or not math.isfinite(item) for item in p) or abs(sum(p) - 1.0) > 1e-8:
            raise RuntimeError(f"invalid {vector} probability vector")
        weights = [prior * item for prior in weights for item in p]
    if len(weights) != FULL_K or abs(sum(weights) - 1.0) > 1e-8:
        raise RuntimeError("ticket-space normalization drift")
    return weights


def expected_unique(weights: list[float], draws: int) -> float:
    return sum(-math.expm1(draws * math.log1p(-weight)) for weight in weights)


def ticket_tax(winning_ticket_gross: float, hit_tickets: int) -> float:
    """Tax individual winning tickets; never manufacture a pooled threshold."""
    return hit_tickets * (winning_ticket_gross * TAX_RATE if winning_ticket_gross >= TAX_THRESHOLD else 0.0)


def target_index(roles: list[dict[str, str]], outcomes: dict[str, dict[str, str]]) -> tuple[int, float, bool]:
    index, payout, missing = 0, UNIT_STAKE * PAYOUT_FACTOR, False
    for role in roles:
        row = outcomes.get(role["match_id"])
        if row is None:
            missing = True
            code, winning_sp = "3", 0.0
        else:
            code, winning_sp = row["result_code"], float(row["winning_sp"])
        index = index * 3 + CODES.index(code)
        payout *= winning_sp
    return index, payout, missing


@dataclass(frozen=True)
class SampleStat:
    hit_tickets: int
    unique_tickets: int
    expected_unique_tickets: float


@dataclass
class Identity:
    row: dict[str, str]
    roles: list[dict[str, str]]
    signature: str
    truth_index: int
    winning_payout: float
    outcome_missing: bool


def prefix_stats_with_replacement(weights: list[float], truth: int, seed: int, key: str) -> dict[int, SampleStat]:
    cumulative: list[float] = []
    total = 0.0
    for weight in weights:
        total += weight; cumulative.append(total)
    if abs(total - 1.0) > 1e-8:
        raise RuntimeError("with-replacement cumulative probability drift")
    expected = {m: expected_unique(weights, m) for m in M_GRID}
    unique: set[int] = set(); hits = 0; output: dict[int, SampleStat] = {}
    for draw in range(1, FULL_K + 1):
        sampled = bisect.bisect_left(cumulative, stable_uniform("bj137", "WR", seed, key, draw - 1))
        if sampled == FULL_K: sampled -= 1
        unique.add(sampled); hits += sampled == truth
        if draw in expected:
            output[draw] = SampleStat(hits, len(unique), expected[draw])
    return output


def prefix_stats_without_replacement(weights: list[float], truth: int, seed: int, key: str) -> dict[int, SampleStat]:
    target = -math.log(max(stable_uniform("bj137", "WOR", seed, key, truth), 1e-18)) / weights[truth]
    rank = 1
    for ordinal, weight in enumerate(weights):
        if ordinal == truth:
            continue
        value = -math.log(max(stable_uniform("bj137", "WOR", seed, key, ordinal), 1e-18)) / weight
        rank += value < target
    return {m: SampleStat(int(rank <= m), m, float(m)) for m in M_GRID}


def top_mass_stats(weights: list[float], truth: int) -> dict[int, SampleStat]:
    truth_weight = weights[truth]
    rank = 1 + sum(weight > truth_weight or (weight == truth_weight and ordinal < truth) for ordinal, weight in enumerate(weights) if ordinal != truth)
    return {m: SampleStat(int(rank <= m), m, float(m)) for m in M_GRID}


def build_profile(identity: Identity) -> dict[tuple[str, str, int, str], SampleStat]:
    """Build all frozen sampling outcomes for one N7 identity without retaining ticket arrays."""
    profile: dict[tuple[str, str, int, str], SampleStat] = {}
    roles, truth, key = identity.roles, identity.truth_index, identity.signature
    model = weights_for(roles, "MODEL_P_CAL")
    for m, stat in top_mass_stats(model, truth).items():
        profile[("TOP_MODEL_P_CAL_DISTINCT", "MODEL_P_CAL", m, "NA")] = stat
    for seed in ("137001", "137002", "137003"):
        for m, stat in prefix_stats_with_replacement(model, truth, int(seed), key).items():
            profile[("MODEL_P_CAL_WR_DUPLICATE_STAKES", "MODEL_P_CAL", m, seed)] = stat
    for vector, sampler in (
        ("MODEL_P_CAL", "MODEL_P_CAL_WOR_DISTINCT"),
        ("MARKET_WF_CAL", "MARKET_WF_CAL_WOR_DISTINCT"),
        ("BLEND_A25", "BLEND_A25_WOR_DISTINCT"),
        ("BLEND_A50", "BLEND_A50_WOR_DISTINCT"),
        ("BLEND_A75", "BLEND_A75_WOR_DISTINCT"),
        ("Q_WEIGHT", "Q_INFORMED_WOR_DISTINCT"),
    ):
        weights = model if vector == "MODEL_P_CAL" else weights_for(roles, vector)
        for seed in ("137001", "137002", "137003"):
            for m, stat in prefix_stats_without_replacement(weights, truth, int(seed), key).items():
                profile[(sampler, vector, m, seed)] = stat
    profile[("FULL_N7_CONTROL", "UNIFORM_FULL", FULL_K, "NA")] = SampleStat(1, FULL_K, float(FULL_K))
    p_missing = any(role["match_id"] == identity.row["p_min_delete_match_id"] and outcomes_code(role) == identity.row["p_min_delete_code"] for role in roles)
    q_missing = any(role["match_id"] == identity.row["q_min_delete_match_id"] and outcomes_code(role) == identity.row["q_min_delete_code"] for role in roles)
    profile[("P_MIN_GLOBAL_DELETE_CONTROL", "MODEL_P_CAL", DELETE_K, "NA")] = SampleStat(int(not p_missing), DELETE_K, float(DELETE_K))
    profile[("Q_MIN_GLOBAL_DELETE_CONTROL", "Q_WEIGHT", DELETE_K, "NA")] = SampleStat(int(not q_missing), DELETE_K, float(DELETE_K))
    return profile


def outcomes_code(role: dict[str, str]) -> str:
    # Filled by load_identities after outcome validation; keeping truth code on the role
    # makes the no-outcome fallback explicit and prevents source re-reads.
    return role["_truth_code"]


def validate_inputs(stage: Path) -> tuple[dict[str, str], Path]:
    freeze = exact_bundle(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    denominator = {"eligible_matches": 47819, "issue_instances": 348, "gates": 10, "top_k_arms": 5, "portfolio_identities": 71704, "role_rows": 501928, "issue_participation_rows": 17400}
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_SAMPLING_FREEZE" or card.get("denominator") != denominator:
        raise RuntimeError("accepted Gate-A v2 card drift")
    outcome = exact_bundle(OUTCOME_BUNDLE, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    snapshot = stage / "canonical_outcome_join.snapshot.csv"
    shutil.copy2(OUTCOME_BUNDLE / "canonical_outcome_join.csv", snapshot)
    if sha(snapshot) != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome snapshot drift")
    return ({
        "gate_a_manifest_sha256": FREEZE_MANIFEST,
        "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
        "gate_a_role_vectors_sha256": freeze["n7_role_vectors.csv.gz"],
        "gate_a_participation_sha256": freeze["issue_participation_grid.csv"],
        "gate_a_sampler_plan_sha256": freeze["sampler_plan.csv"],
        "outcome_manifest_sha256": OUTCOME_MANIFEST,
        "outcome_payload_sha256": OUTCOME_PAYLOAD,
        "outcome_snapshot_sha256": sha(snapshot),
    }, snapshot)


def load_outcomes(snapshot: Path) -> dict[str, dict[str, str]]:
    with snapshot.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, OUTCOME_FIELDS, "canonical outcomes")
        values = {row["match_id"]: row for row in reader}
    for row in values.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or float(row["winning_sp"]) <= 0:
            raise RuntimeError("canonical outcome is not trusted")
    return values


def load_identities(outcomes: dict[str, dict[str, str]]) -> tuple[dict[tuple[str, str], Identity], dict[str, list[dict[str, str]]]]:
    roles: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(FREEZE / "n7_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, ROLE_FIELDS, "Gate-A role vectors")
        for row in reader:
            outcome = outcomes.get(row["match_id"])
            row["_truth_code"] = outcome["result_code"] if outcome else ""
            roles[(row["gate_id"], row["portfolio_id"])].append(row)
    if len(roles) != 71704 or sum(map(len, roles.values())) != 501928:
        raise RuntimeError("Gate-A role denominator drift")
    rows: dict[tuple[str, str], dict[str, str]] = {}
    signatures: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(FREEZE / "n7_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, IDENTITY_FIELDS, "Gate-A identities")
        for row in reader:
            rows[(row["gate_id"], row["portfolio_id"])] = row
    if len(rows) != 71704:
        raise RuntimeError("Gate-A identity denominator drift")
    identities: dict[tuple[str, str], Identity] = {}
    for key, row in rows.items():
        role_set = sorted(roles.get(key, []), key=lambda item: int(item["selection_rank"]))
        if len(role_set) != 7 or [int(item["selection_rank"]) for item in role_set] != list(range(1, 8)):
            raise RuntimeError(f"seven-leg role geometry drift: {key}")
        if "|".join(item["match_id"] for item in role_set) != row["selected_match_ids"]:
            raise RuntimeError(f"frozen identity/role mismatch: {key}")
        truth, payout, missing = target_index(role_set, outcomes)
        signature = row["selected_match_ids"]
        identities[key] = Identity(row, role_set, signature, truth, payout, missing)
        signatures[signature].append(row)
    return identities, signatures


def load_participation() -> dict[str, dict[tuple[str, str], dict[str, str]]]:
    by_issue: dict[str, dict[tuple[str, str], dict[str, str]]] = defaultdict(dict)
    with (FREEZE / "issue_participation_grid.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, PARTICIPATION_FIELDS, "Gate-A participation grid")
        for row in reader:
            key = (row["gate_id"], row["top_k_id"])
            if key in by_issue[row["issue_instance"]]:
                raise RuntimeError("duplicate participation cell")
            by_issue[row["issue_instance"]][key] = row
    if len(by_issue) != 348 or sum(len(values) for values in by_issue.values()) != 17400 or any(len(values) != 50 for values in by_issue.values()):
        raise RuntimeError("participation-grid denominator drift")
    return by_issue


def load_plans() -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with (FREEZE / "sampler_plan.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, PLAN_FIELDS, "Gate-A sampler plan")
        for row in reader:
            grouped[(row["gate_id"], row["top_k_id"])].append(row)
    if len(grouped) != 50 or sum(len(rows) for rows in grouped.values()) != 14450 or any(len(rows) != 289 for rows in grouped.values()):
        raise RuntimeError("sampler-plan denominator drift")
    return grouped


def plan_key(plan: dict[str, str]) -> tuple[str, str, str, str, str, str]:
    return plan["gate_id"], plan["top_k_id"], plan["sampler_id"], plan["probability_vector"], plan["M"], plan["seed"]


@dataclass
class Metric:
    meta: dict[str, str]
    available: int = 0
    no_bet: int = 0
    settled: int = 0
    unavailable: int = 0
    draws: int = 0
    stake: float = 0.0
    expected_unique: float = 0.0
    unique: int = 0
    hits: int = 0
    coverage: int = 0
    gross: float = 0.0
    tax: float = 0.0
    net: float = 0.0
    pre_tax_net: float = 0.0
    cumulative: float = 0.0
    peak: float = 0.0
    max_drawdown: float = 0.0
    miss_streak: int = 0
    max_miss_streak: int = 0
    largest_gross: float = 0.0
    overlap_sum: int = 0
    exposure_max: int = 0

    def add(self, item: dict[str, object]) -> None:
        status = str(item["settlement_status"])
        if status == "NO_BET_FROZEN":
            self.no_bet += 1; return
        self.available += 1
        if status != "SETTLED":
            self.unavailable += 1; return
        self.settled += 1
        draws, stake, gross, tax, net = int(item["planned_draw_count"]), float(item["planned_stake_yuan"]), float(item["gross_pre_tax_yuan"]), float(item["tax_yuan"]), float(item["tax_adjusted_net_yuan"])
        self.draws += draws; self.stake += stake; self.expected_unique += float(item["expected_unique_ticket_count"]); self.unique += int(item["realized_unique_ticket_count"]); self.hits += int(item["hit_ticket_count"]); self.coverage += int(item["coverage_hit"]); self.gross += gross; self.tax += tax; self.net += net; self.pre_tax_net += float(item["pre_tax_net_yuan"])
        self.cumulative += net; self.peak = max(self.peak, self.cumulative); self.max_drawdown = max(self.max_drawdown, self.peak - self.cumulative)
        self.miss_streak = 0 if int(item["coverage_hit"]) else self.miss_streak + 1; self.max_miss_streak = max(self.max_miss_streak, self.miss_streak)
        self.largest_gross = max(self.largest_gross, gross); self.overlap_sum += int(item["overlap_leg_slots"]); self.exposure_max = max(self.exposure_max, int(item["max_match_exposure"]))

    def row(self, scope: str, scope_value: str) -> dict[str, object]:
        gross_without_largest = self.gross - self.largest_gross
        net_without_largest = gross_without_largest - self.tax - self.stake
        return {
            "scope": scope, "scope_value": scope_value, **self.meta,
            "frozen_available_issue_count": self.available, "frozen_no_bet_issue_count": self.no_bet,
            "settled_issue_count": self.settled, "unavailable_outcome_issue_count": self.unavailable,
            "planned_draw_count": self.draws, "stake_yuan": fmt(self.stake),
            "expected_unique_ticket_count": fmt(self.expected_unique), "realized_unique_ticket_count": self.unique,
            "hit_ticket_count": self.hits, "coverage_hits": self.coverage,
            "coverage_hit_rate": ratio(self.coverage / self.settled if self.settled else None),
            "gross_pre_tax_yuan": fmt(self.gross), "tax_yuan": fmt(self.tax),
            "after_tax_gross_yuan": fmt(self.gross - self.tax), "pre_tax_net_yuan": fmt(self.pre_tax_net),
            "tax_adjusted_net_yuan": fmt(self.net), "no_tax_roi": ratio(self.pre_tax_net / self.stake if self.stake else None),
            "tax_adjusted_roi": ratio(self.net / self.stake if self.stake else None),
            "max_drawdown_yuan": fmt(self.max_drawdown), "longest_miss_streak": self.max_miss_streak,
            "gross_top_issue_share": ratio(self.largest_gross / self.gross if self.gross else None),
            "largest_issue_gross_yuan": fmt(self.largest_gross),
            "ex_largest_issue_tax_adjusted_roi": ratio(net_without_largest / self.stake if self.stake else None),
            "mean_overlap_leg_slots": ratio(self.overlap_sum / self.settled if self.settled else None),
            "max_match_exposure": self.exposure_max,
        }


def make_meta(plan: dict[str, str]) -> dict[str, str]:
    return {field: plan[field] for field in ("gate_id", "top_k_id", "requested_n7_count", "sampler_id", "probability_vector", "mechanism", "duplicate_policy", "M", "seed", "seed_role", "primary_or_sensitivity")}


def profile_stat(profile: dict[tuple[str, str, int, str], SampleStat], plan: dict[str, str]) -> SampleStat:
    key = (plan["sampler_id"], plan["probability_vector"], int(plan["M"]), plan["seed"])
    try:
        return profile[key]
    except KeyError as error:
        raise RuntimeError(f"missing frozen sampler profile {key}") from error


def overlap_geometry(selected: list[Identity]) -> tuple[int, int, int, int]:
    counts: dict[str, int] = defaultdict(int)
    for identity in selected:
        for role in identity.roles:
            counts[role["match_id"]] += 1
    return len(counts), len(selected) * 7, len(selected) * 7 - len(counts), max(counts.values(), default=0)


def issue_result(participation: dict[str, str], plan: dict[str, str], identities: dict[tuple[str, str], Identity], profiles: dict[str, dict[tuple[str, str, int, str], SampleStat]]) -> dict[str, object]:
    ids = [value for value in participation["selected_portfolio_ids"].split("|") if value]
    common = {
        "issue": participation["issue"], "fold": participation["fold"], "year": participation["year"], "issue_instance": participation["issue_instance"], "first_kickoff_ts": participation["first_kickoff_ts"],
        **make_meta(plan), "frozen_disposition": participation["disposition"], "selected_identity_count": len(ids),
        "tax_bucket_key": "|".join((participation["issue_instance"], plan["gate_id"], plan["top_k_id"], plan["sampler_id"], plan["M"], plan["seed"])),
    }
    if not ids:
        return {**common, "settlement_status": "NO_BET_FROZEN", "planned_draw_count": 0, "planned_stake_yuan": 0.0, "realized_unique_ticket_count": 0, "expected_unique_ticket_count": 0.0, "hit_ticket_count": 0, "coverage_hit": 0, "gross_pre_tax_yuan": 0.0, "tax_yuan": 0.0, "after_tax_gross_yuan": 0.0, "pre_tax_net_yuan": 0.0, "tax_adjusted_net_yuan": 0.0, "no_tax_roi": None, "tax_adjusted_roi": None, "unique_match_count": 0, "total_leg_slots": 0, "overlap_leg_slots": 0, "max_match_exposure": 0, "gross_top_identity_share": None, "outcome_gap_count": 0}
    selected = [identities[(plan["gate_id"], portfolio_id)] for portfolio_id in ids]
    missing = sum(identity.outcome_missing for identity in selected)
    unique_matches, total_slots, overlap, max_exposure = overlap_geometry(selected)
    if missing:
        return {**common, "settlement_status": "UNAVAILABLE_CANONICAL_OUTCOME", "planned_draw_count": 0, "planned_stake_yuan": 0.0, "realized_unique_ticket_count": 0, "expected_unique_ticket_count": 0.0, "hit_ticket_count": 0, "coverage_hit": 0, "gross_pre_tax_yuan": 0.0, "tax_yuan": 0.0, "after_tax_gross_yuan": 0.0, "pre_tax_net_yuan": 0.0, "tax_adjusted_net_yuan": 0.0, "no_tax_roi": None, "tax_adjusted_roi": None, "unique_match_count": unique_matches, "total_leg_slots": total_slots, "overlap_leg_slots": overlap, "max_match_exposure": max_exposure, "gross_top_identity_share": None, "outcome_gap_count": missing}
    stats = [profile_stat(profiles[identity.signature], plan) for identity in selected]
    individual_gross = [stat.hit_tickets * identity.winning_payout for stat, identity in zip(stats, selected)]
    # A realised ticket is the tax unit.  In particular, a WR duplicate is a
    # separately staked / separately assessed ticket, not a reason to pool
    # multiple identical draws into an artificial threshold-crossing payout.
    individual_tax = [ticket_tax(identity.winning_payout, stat.hit_tickets) for stat, identity in zip(stats, selected)]
    draws = len(selected) * int(plan["M"]); stake = draws * UNIT_STAKE; gross = sum(individual_gross); tax = sum(individual_tax)
    return {**common, "settlement_status": "SETTLED", "planned_draw_count": draws, "planned_stake_yuan": stake, "realized_unique_ticket_count": sum(stat.unique_tickets for stat in stats), "expected_unique_ticket_count": sum(stat.expected_unique_tickets for stat in stats), "hit_ticket_count": sum(stat.hit_tickets for stat in stats), "coverage_hit": int(any(stat.hit_tickets for stat in stats)), "gross_pre_tax_yuan": gross, "tax_yuan": tax, "after_tax_gross_yuan": gross-tax, "pre_tax_net_yuan": gross-stake, "tax_adjusted_net_yuan": gross-tax-stake, "no_tax_roi": (gross-stake)/stake if stake else None, "tax_adjusted_roi": (gross-tax-stake)/stake if stake else None, "unique_match_count": unique_matches, "total_leg_slots": total_slots, "overlap_leg_slots": overlap, "max_match_exposure": max_exposure, "gross_top_identity_share": max(individual_gross)/gross if gross else None, "outcome_gap_count": 0}


def serializable_issue(row: dict[str, object]) -> dict[str, object]:
    return {key: ratio(value) if key.endswith("_roi") else fmt(value) if key.endswith("_yuan") or key.endswith("_count") and isinstance(value, float) else value for key, value in row.items()}


def calibration_diagnostics(outcomes: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    vectors = {
        "MODEL_P_CAL": ("p3", "p1", "p0"), "MARKET_WF_CAL": ("market_cal3", "market_cal1", "market_cal0"),
        "BLEND_A25": ("blend_a25_3", "blend_a25_1", "blend_a25_0"), "BLEND_A50": ("blend_a50_3", "blend_a50_1", "blend_a50_0"),
        "BLEND_A75": ("blend_a75_3", "blend_a75_1", "blend_a75_0"), "Q_WEIGHT": ("q_weight3", "q_weight1", "q_weight0"),
    }
    totals: dict[tuple[str, str, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    with (FREEZE / "match_vectors.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); require_schema(reader, VECTOR_FIELDS, "Gate-A match vectors")
        for row in reader:
            outcome = outcomes.get(row["match_id"])
            for name, columns in vectors.items():
                for code, column in zip(CODES, columns):
                    probability = float(row[column]); decile = min(9, int(probability * 10))
                    item = totals[(name, code, decile)]
                    item[0] += 1; item[1] += probability; item[2] += outcome is not None and outcome["result_code"] == code; item[3] += (probability - int(outcome is not None and outcome["result_code"] == code)) ** 2; item[4] += outcome is None
    return [{"probability_vector": name, "outcome_code": code, "probability_decile": decile, "rows": int(values[0]), "mean_probability": ratio(values[1]/values[0] if values[0] else None), "observed_frequency": ratio(values[2]/(values[0]-values[4]) if values[0] > values[4] else None), "brier_component": ratio(values[3]/(values[0]-values[4]) if values[0] > values[4] else None), "outcome_coverage": ratio((values[0]-values[4])/values[0] if values[0] else None), "outcome_gap_count": int(values[4])} for (name, code, decile), values in sorted(totals.items())]


def lift_rows(summaries: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    index = {(row["scope"], row["scope_value"], row["gate_id"], row["top_k_id"], row["sampler_id"], row["M"], row["seed"]): row for row in summaries}
    selector, sampler, interaction = [], [], []
    for key, row in sorted(index.items()):
        scope, scope_value, gate, top_k, sampler_id, m, seed = key
        full_same = index.get((scope, scope_value, gate, top_k, "FULL_N7_CONTROL", "2187", "NA"))
        full_all = index.get((scope, scope_value, gate, "K_ALL", "FULL_N7_CONTROL", "2187", "NA"))
        if not full_same or not full_all:
            continue
        def effect(kind: str, baseline: dict[str, object]) -> dict[str, object]:
            no_tax = float(row["no_tax_roi"]) if row["no_tax_roi"] != "" else None
            tax_roi = float(row["tax_adjusted_roi"]) if row["tax_adjusted_roi"] != "" else None
            base_no_tax = float(baseline["no_tax_roi"]) if baseline["no_tax_roi"] != "" else None
            base_tax = float(baseline["tax_adjusted_roi"]) if baseline["tax_adjusted_roi"] != "" else None
            cov = float(row["coverage_hit_rate"]) if row["coverage_hit_rate"] != "" else None
            base_cov = float(baseline["coverage_hit_rate"]) if baseline["coverage_hit_rate"] != "" else None
            return {"scope": scope, "scope_value": scope_value, "effect": kind, "gate_id": gate, "top_k_id": top_k, "sampler_id": sampler_id, "M": m, "seed": seed, "baseline_sampler_id": baseline["sampler_id"], "baseline_top_k_id": baseline["top_k_id"], "baseline_M": baseline["M"], "stake_yuan": row["stake_yuan"], "baseline_stake_yuan": baseline["stake_yuan"], "no_tax_roi": row["no_tax_roi"], "baseline_no_tax_roi": baseline["no_tax_roi"], "no_tax_roi_delta": ratio(no_tax-base_no_tax if no_tax is not None and base_no_tax is not None else None), "tax_adjusted_roi": row["tax_adjusted_roi"], "baseline_tax_adjusted_roi": baseline["tax_adjusted_roi"], "tax_adjusted_roi_delta": ratio(tax_roi-base_tax if tax_roi is not None and base_tax is not None else None), "coverage_hit_rate": row["coverage_hit_rate"], "baseline_coverage_hit_rate": baseline["coverage_hit_rate"], "coverage_hit_rate_delta": ratio(cov-base_cov if cov is not None and base_cov is not None else None)}
        if sampler_id == "FULL_N7_CONTROL" and top_k != "K_ALL":
            selector.append(effect("SELECTOR_LIFT_VS_SAME_GATE_K_ALL_FULL", full_all))
        if sampler_id != "FULL_N7_CONTROL":
            sampler.append(effect("SAMPLER_LIFT_VS_EXACT_SELECTED_K_FULL", full_same))
            interaction.append(effect("JOINT_EFFECT_VS_SAME_GATE_K_ALL_FULL", full_all))
    return selector, sampler, interaction


def positive_delta(row: dict[str, object]) -> bool:
    return bool(row["no_tax_roi_delta"] and row["tax_adjusted_roi_delta"] and float(row["no_tax_roi_delta"]) > 0 and float(row["tax_adjusted_roi_delta"]) > 0)


def decision_from_lifts(selector: list[dict[str, object]], sampler: list[dict[str, object]]) -> dict[str, object]:
    """Apply the frozen all-seed + chronological persistence rule.

    A sparse single-M hit cannot nominate a policy: both no-tax and actual-tax
    matched deltas must stay positive across all three seeds and every YEAR,
    FOLD and leave-one-year-out view.  Selection-only FULL controls face the
    equivalent chronological test without a seed axis.
    """
    sampler_groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in sampler:
        sampler_groups[(str(row["gate_id"]), str(row["top_k_id"]), str(row["sampler_id"]), str(row["M"]))].append(row)
    all_seed_global = []
    robust_sampler = []
    for key, rows in sampler_groups.items():
        global_rows = [row for row in rows if row["scope"] == "ALL"]
        if {str(row["seed"]) for row in global_rows} == {"137001", "137002", "137003"} and all(positive_delta(row) for row in global_rows):
            all_seed_global.append(key)
            chronological = [row for row in rows if row["scope"] in {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}]
            if chronological and all(positive_delta(row) for row in chronological):
                robust_sampler.append(key)
    global_selector = [row for row in selector if row["scope"] == "ALL" and positive_delta(row)]
    robust_selector = []
    for row in global_selector:
        chronological = [candidate for candidate in selector if candidate["gate_id"] == row["gate_id"] and candidate["top_k_id"] == row["top_k_id"] and candidate["scope"] in {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}]
        if chronological and all(positive_delta(candidate) for candidate in chronological):
            robust_selector.append((str(row["gate_id"]), str(row["top_k_id"])))
    promotable = sorted(set(robust_sampler))
    return {
        "decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if promotable else "NO_PROMOTION",
        "promotion_authorized": False,
        "strict_independent_ev_required": bool(promotable),
        "all_seed_global_positive_sampler_candidates": len(all_seed_global),
        "all_seed_and_chronological_positive_sampler_candidates": len(promotable),
        "global_positive_selector_candidates": len(global_selector),
        "chronologically_positive_selector_candidates": len(set(robust_selector)),
        "promotion_candidates": ["|".join(value) for value in promotable],
        "rule": "Promotion requires positive matched no-tax and actual-tax deltas across all three frozen seeds and every YEAR/FOLD/LOYO view. A one-seed, sparse-M, raw-ROI or tax-only maximum is not promotable.",
    }


def build(output: Path, workers: int | None = None) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj137_gateb_", dir=output.parent))
    try:
        provenance, snapshot = validate_inputs(stage)
        outcomes = load_outcomes(snapshot)
        identities, _signatures = load_identities(outcomes)
        participation_by_issue, plans = load_participation(), load_plans()
        plan_by_key = {plan_key(plan): plan for group in plans.values() for plan in group}
        if len(plan_by_key) != 14450:
            raise RuntimeError("non-unique sampler plan surface")
        metrics: dict[tuple[str, str, tuple[str, str, str, str, str, str]], Metric] = {}
        def metric(scope: str, value: str, plan: dict[str, str]) -> Metric:
            key = (scope, value, plan_key(plan))
            if key not in metrics: metrics[key] = Metric(make_meta(plan))
            return metrics[key]
        settlement = gzip_writer(stage / "issue_policy_settlement.csv.gz", ISSUE_SETTLEMENT_FIELDS)
        issue_writer = settlement[-1]
        issue_count = 0
        ordered_issues = sorted(participation_by_issue.values(), key=lambda values: next(iter(values.values()))["first_kickoff_ts"])
        worker_count = max(1, min(4, workers if workers is not None else (os.cpu_count() or 1)))
        # Profiles are independent of every outcome except the canonical truth already
        # bound into each Identity.  Parallelising within an issue keeps the retained
        # profile cache small while preserving the frozen chronological ledger order.
        with multiprocessing.get_context("fork").Pool(processes=worker_count) as pool:
          for issue_cells in ordered_issues:
            issue_profiles: dict[str, dict[tuple[str, str, int, str], SampleStat]] = {}
            unique_identities: dict[str, Identity] = {}
            for (gate, _top_k), participation in issue_cells.items():
                for portfolio_id in filter(None, participation["selected_portfolio_ids"].split("|")):
                    identity = identities[(gate, portfolio_id)]
                    unique_identities.setdefault(identity.signature, identity)
            generated = pool.map(build_profile, unique_identities.values(), chunksize=1)
            for signature, profile in zip(unique_identities, generated):
                issue_profiles[signature] = profile
            for key, participation in sorted(issue_cells.items()):
                for plan in plans[key]:
                    row = issue_result(participation, plan, identities, issue_profiles)
                    issue_writer.writerow(serializable_issue(row)); issue_count += 1
                    metric("ALL", "ALL", plan).add(row)
                    metric("YEAR", str(row["year"]), plan).add(row)
                    metric("FOLD", str(row["fold"]), plan).add(row)
                    for omitted_year in range(2019, 2026):
                        if str(row["year"]) != str(omitted_year):
                            metric("LEAVE_ONE_YEAR_OUT", str(omitted_year), plan).add(row)
        close_gzip(settlement)
        if issue_count != 5_028_600:
            raise RuntimeError(f"unexpected Gate-B issue-policy surface: {issue_count}")
        summaries = [entry.row(scope, value) for (scope, value, _key), entry in sorted(metrics.items())]
        write_gzip_csv(stage / "surface_summary.csv.gz", SUMMARY_FIELDS, summaries)
        selector, sampler, interaction = lift_rows(summaries)
        write_gzip_csv(stage / "selector_lift.csv.gz", LIFT_FIELDS, selector)
        write_gzip_csv(stage / "sampler_lift.csv.gz", LIFT_FIELDS, sampler)
        write_gzip_csv(stage / "interaction_surface.csv.gz", LIFT_FIELDS, interaction)
        write_csv(stage / "calibration_diagnostics.csv", CALIBRATION_FIELDS, calibration_diagnostics(outcomes))
        decision = decision_from_lifts(selector, sampler)
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj137_gate_a_preoutcome_v2", "role": "accepted outcome-unexposed complete-issue sampling surface", "manifest_sha256": FREEZE_MANIFEST, "payload": "issue_participation_grid.csv; n7_role_vectors.csv.gz; sampler_plan.csv", "payload_sha256": provenance["gate_a_content_identity_sha256"], "rows": 71704, "join_status": "all 10×5 participation cells retained; explicit frozen no-bets remain"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical final-SP settlement truth", "manifest_sha256": OUTCOME_MANIFEST, "payload": "canonical_outcome_join.csv", "payload_sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "trusted canonical outcomes only; missing joins fail closed without stake"},
        ])
        card = {"issue": 137, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_COMPLETE_ISSUE_OUTCOME_SETTLEMENT", "provenance": provenance, "input_boundary": "Only accepted Gate-A v2 and canonical final-SP settlement input are read. Gate-A v3/post-acceptance material is not read.", "scope": "historical paper research only; no purchase, production, or promotion authority.", "sampling_replay": "The accepted Gate-A hash-based samplers are replayed exactly. Each ordered selected_match_ids tuple is its sampler key; duplicate draws retain stake, while WOR/top/delete arms are distinct-ticket mechanisms.", "settlement": "Each selected ticket pays ¥2×0.65×product(canonical final winning SP) per hit. Tax is assessed per realised winning ticket: 20% only where that individual ticket gross is at least ¥10,000. Tickets, identities and issue-policy arms are never aggregated merely to cross the tax threshold; duplicated WR hits are separately assessed tickets.", "accounting": "M is per selected N7. Issue draws and stake are selected_identity_count×M and selected_identity_count×M×¥2. K/M are frozen outputs rather than rejection gates. Frozen no-bets are retained separately from unavailable canonical outcomes. tax_bucket_key is retained as an issue-policy ledger partition only, not as a tax aggregation unit.", "metrics": "surface_summary.csv.gz contains ALL/YEAR/FOLD/LOYO; issue_policy_settlement is the issue-level ledger. Selector lift uses same-gate K_ALL FULL; sampler lift uses exact selected-K FULL; interaction uses K_ALL FULL. Overlap, duplicate/unique ticket coverage, concentration, drawdown, miss streak and largest-event sensitivity are retained.", "decision": decision}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text("# #137 Gate B — probability-weighted N7 sampling\n\nOne-shot canonical settlement of the accepted Gate-A v2 complete-issue gate×K×M sampling surface. This is historical paper research only.\n", encoding="utf-8")
        snapshot.unlink()
        compressed = ("issue_policy_settlement.csv.gz", "surface_summary.csv.gz", "selector_lift.csv.gz", "sampler_lift.csv.gz", "interaction_surface.csv.gz")
        content = {"contract_version": "bj137-gate-b-portable-content-v1", "gzip_payloads": {name: {"canonical_decompressed_sha256": uncompressed(stage / name)[0], "canonical_decompressed_bytes": uncompressed(stage / name)[1]} for name in compressed}, "non_compressed_controls": {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha(output / "SHA256SUMS.json"), "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"), "issue_policy_rows": issue_count, "summary_rows": len(summaries), "decision": decision}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.workers), sort_keys=True))


if __name__ == "__main__":
    main()
