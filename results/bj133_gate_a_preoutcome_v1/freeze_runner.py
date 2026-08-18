#!/usr/bin/env python3
"""Freeze #133's outcome-unexposed, complete-issue N7 allocation frontier.

The runner consumes only the accepted #137 Gate-A v2 identity/role surface.
It never opens a settlement ledger, results database, final-SP payload, or
any post-kickoff source.  Allocators are compared on the same candidate pool,
target identity count, ticket count M, and ¥2 issue-level accounting.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


CONTRACT = "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001"
VERSION = "bj133-gate-a-v1"
CONTENT_VERSION = "bj133-gate-a-content-v1"
UPSTREAM_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
N = 7
FULL_TICKETS = 3 ** N
UNIT_STAKE_YUAN = 2
SEEDS = (133001, 133002, 133003)
MAX_CANDIDATES = 32


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
SOURCE = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
OUTPUT = ROOT / "results" / "bj133_gate_a_preoutcome_v1"

# The controls are part of the same outcome-unexposed allocation freeze.  The
# FULL row is an economic reference and is not represented as a sampled ticket
# allocation.  Its selected identities are nevertheless frozen identically.
CONFIGS = (
    {
        "config_id": "PRIMARY_NO_GATE_K4_M64",
        "gate_id": "NO_GATE",
        "top_k_id": "K4",
        "target_identity_count": 4,
        "ticket_M": 64,
        "probability_vector": "Q_WEIGHT",
        "ticket_mechanism": "Q_INFORMED_WOR_DISTINCT",
        "role": "PRIMARY_DIAGNOSTIC",
    },
    {
        "config_id": "PRIMARY_NO_GATE_K4_M128",
        "gate_id": "NO_GATE",
        "top_k_id": "K4",
        "target_identity_count": 4,
        "ticket_M": 128,
        "probability_vector": "Q_WEIGHT",
        "ticket_mechanism": "Q_INFORMED_WOR_DISTINCT",
        "role": "ADJACENT_M_SENSITIVITY",
    },
    {
        "config_id": "ECONOMIC_CONTROL_NO_GATE_K4_FULL",
        "gate_id": "NO_GATE",
        "top_k_id": "K4",
        "target_identity_count": 4,
        "ticket_M": FULL_TICKETS,
        "probability_vector": "UNIFORM_FULL",
        "ticket_mechanism": "EXACT_K4_FULL",
        "role": "ECONOMIC_CONTROL",
    },
    {
        "config_id": "SECONDARY_ESP300_GM290_K8_M128",
        "gate_id": "ESP300_GM290",
        "top_k_id": "K8",
        "target_identity_count": 8,
        "ticket_M": 128,
        "probability_vector": "Q_WEIGHT",
        "ticket_mechanism": "Q_INFORMED_WOR_DISTINCT",
        "role": "SECONDARY_SELECTION_SENSITIVITY",
    },
)

# A compact one-factor cap frontier plus three joint rules.  A failed strict
# cap is a frozen NO_BET—not a partial selection or an implicit relaxation.
ALLOCATORS = (
    {"allocator_id": "CONCENTRATED_TOP_SCORE", "match_cap": None, "delete_cap": None, "jaccard_cap": None, "family": "CONCENTRATED_CONTROL"},
    {"allocator_id": "MATCH_EXPOSURE_CAP_1", "match_cap": 1, "delete_cap": None, "jaccard_cap": None, "family": "MATCH_CAP"},
    {"allocator_id": "MATCH_EXPOSURE_CAP_2", "match_cap": 2, "delete_cap": None, "jaccard_cap": None, "family": "MATCH_CAP"},
    {"allocator_id": "MATCH_EXPOSURE_CAP_3", "match_cap": 3, "delete_cap": None, "jaccard_cap": None, "family": "MATCH_CAP"},
    {"allocator_id": "MATCH_EXPOSURE_CAP_4", "match_cap": 4, "delete_cap": None, "jaccard_cap": None, "family": "MATCH_CAP"},
    {"allocator_id": "JACCARD_CAP_050", "match_cap": None, "delete_cap": None, "jaccard_cap": 0.50, "family": "OVERLAP_CAP"},
    {"allocator_id": "JACCARD_CAP_075", "match_cap": None, "delete_cap": None, "jaccard_cap": 0.75, "family": "OVERLAP_CAP"},
    {"allocator_id": "JACCARD_CAP_100", "match_cap": None, "delete_cap": None, "jaccard_cap": 1.00, "family": "OVERLAP_CAP"},
    {"allocator_id": "Q_DELETE_EXPOSURE_CAP_1", "match_cap": None, "delete_cap": 1, "jaccard_cap": None, "family": "DELETE_CODE_CAP"},
    {"allocator_id": "Q_DELETE_EXPOSURE_CAP_2", "match_cap": None, "delete_cap": 2, "jaccard_cap": None, "family": "DELETE_CODE_CAP"},
    {"allocator_id": "Q_DELETE_EXPOSURE_CAP_4", "match_cap": None, "delete_cap": 4, "jaccard_cap": None, "family": "DELETE_CODE_CAP"},
    {"allocator_id": "Q_DELETE_EXPOSURE_CAP_8", "match_cap": None, "delete_cap": 8, "jaccard_cap": None, "family": "DELETE_CODE_CAP"},
    {"allocator_id": "JOINT_M2_J075_Q2", "match_cap": 2, "delete_cap": 2, "jaccard_cap": 0.75, "family": "JOINT_CAP"},
    {"allocator_id": "JOINT_M3_J075_Q3", "match_cap": 3, "delete_cap": 3, "jaccard_cap": 0.75, "family": "JOINT_CAP"},
    {"allocator_id": "JOINT_M4_J100_Q4", "match_cap": 4, "delete_cap": 4, "jaccard_cap": 1.00, "family": "JOINT_CAP"},
)

PLAN_FIELDS = (
    "config_id", "config_role", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "allocator_id", "allocator_family", "target_identity_count", "candidate_pool_count", "candidate_search_count",
    "match_exposure_cap", "q_delete_exposure_cap", "pairwise_jaccard_cap", "ticket_M", "probability_vector",
    "ticket_mechanism", "selected_identity_count", "selected_portfolio_ids", "selection_status", "reason",
    "planned_draw_count", "planned_stake_yuan", "full_control_draw_count", "full_control_stake_yuan",
    "unique_match_count", "total_leg_slots", "overlap_leg_slots", "max_match_exposure",
    "effective_independent_match_count", "max_pairwise_jaccard", "mean_pairwise_jaccard",
    "max_q_delete_exposure", "selected_q_delete_pairs", "selection_scope", "outcome_boundary",
)
SAMPLER_FIELDS = (
    "config_id", "gate_id", "top_k_id", "allocator_id", "ticket_M", "probability_vector", "ticket_mechanism",
    "seed", "seed_role", "duplicate_policy", "issue_total_draw_formula", "issue_total_stake_formula",
    "outcome_boundary",
)
SUMMARY_FIELDS = (
    "config_id", "allocator_id", "issue_rows", "available_rows", "no_bet_rows", "selected_identity_total",
    "planned_stake_yuan_total", "mean_effective_independent_match_count", "max_match_exposure_observed",
    "max_pairwise_jaccard_observed", "max_q_delete_exposure_observed",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def decompressed_digest(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def exact_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted upstream manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError("upstream manifest coverage drift")
    return declared


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with __import__("io").TextIOWrapper(zipped, newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
                writer.writeheader()
                writer.writerows(rows)


def read_gzip_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        return fields, list(reader)


def parse_ids(row: dict[str, str]) -> tuple[str, ...]:
    values = tuple(value for value in row["selected_match_ids"].split("|") if value)
    if len(values) != N or len(set(values)) != N:
        raise RuntimeError(f"invalid N7 match vector: {row['portfolio_id']}")
    return values


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def cap_text(value: float | int | None) -> str:
    return "NONE" if value is None else (format(value, ".2f") if isinstance(value, float) else str(value))


def geometry(selected: list[dict[str, str]]) -> dict[str, object]:
    exposure: Counter[str] = Counter()
    delete_exposure: Counter[tuple[str, str]] = Counter()
    match_sets: list[set[str]] = []
    for row in selected:
        match_ids = set(parse_ids(row))
        match_sets.append(match_ids)
        exposure.update(match_ids)
        delete_exposure[(row["q_min_delete_match_id"], row["q_min_delete_code"])] += 1
    pairs = [jaccard(match_sets[left], match_sets[right]) for left in range(len(match_sets)) for right in range(left + 1, len(match_sets))]
    total_slots = len(selected) * N
    denominator = sum(count * count for count in exposure.values())
    return {
        "unique_match_count": len(exposure),
        "total_leg_slots": total_slots,
        "overlap_leg_slots": total_slots - len(exposure),
        "max_match_exposure": max(exposure.values(), default=0),
        "effective_independent_match_count": (total_slots * total_slots / denominator) if denominator else 0.0,
        "max_pairwise_jaccard": max(pairs, default=0.0),
        "mean_pairwise_jaccard": (sum(pairs) / len(pairs)) if pairs else 0.0,
        "max_q_delete_exposure": max(delete_exposure.values(), default=0),
        "selected_q_delete_pairs": "|".join(f"{match_id}:{code}:{count}" for (match_id, code), count in sorted(delete_exposure.items())),
    }


def select_identities(candidates: list[dict[str, str]], target: int, spec: dict[str, object]) -> tuple[list[dict[str, str]], str]:
    selected: list[dict[str, str]] = []
    match_exposure: Counter[str] = Counter()
    delete_exposure: Counter[tuple[str, str]] = Counter()
    match_cap = spec["match_cap"]
    delete_cap = spec["delete_cap"]
    jaccard_cap = spec["jaccard_cap"]
    for candidate in candidates:
        matches = set(parse_ids(candidate))
        delete_key = (candidate["q_min_delete_match_id"], candidate["q_min_delete_code"])
        if match_cap is not None and any(match_exposure[match] + 1 > int(match_cap) for match in matches):
            continue
        if delete_cap is not None and delete_exposure[delete_key] + 1 > int(delete_cap):
            continue
        if jaccard_cap is not None and any(jaccard(matches, set(parse_ids(existing))) > float(jaccard_cap) + 1e-12 for existing in selected):
            continue
        selected.append(candidate)
        match_exposure.update(matches)
        delete_exposure[delete_key] += 1
        if len(selected) == target:
            return selected, "AVAILABLE"
    return [], "NO_BET_CAP_UNSATISFIED"


def load_source(source: Path) -> tuple[dict[str, str], list[dict[str, str]], tuple[str, ...], list[dict[str, str]], tuple[str, ...], list[dict[str, str]]]:
    manifest = exact_bundle(source, UPSTREAM_MANIFEST)
    identity_fields, identities = read_gzip_rows(source / "n7_identities.csv.gz")
    role_fields, roles = read_gzip_rows(source / "n7_role_vectors.csv.gz")
    with (source / "issue_participation_grid.csv").open(newline="", encoding="utf-8") as handle:
        participation = list(csv.DictReader(handle))
    required_identity = {"gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "candidate_rank_in_complete_issue", "selected_match_ids", "q_min_delete_match_id", "q_min_delete_code"}
    required_role = {"gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "match_id", "selection_rank", "q_weight3", "q_weight1", "q_weight0"}
    if not required_identity <= set(identity_fields) or not required_role <= set(role_fields):
        raise RuntimeError("upstream schema lacks allocation inputs")
    if len({(row["gate_id"], row["portfolio_id"]) for row in identities}) != len(identities):
        raise RuntimeError("upstream identity uniqueness drift")
    required_participation = {"gate_id", "top_k_id", "issue", "fold", "year", "issue_instance", "disposition"}
    if not participation or not required_participation <= set(participation[0]):
        raise RuntimeError("upstream participation schema lacks complete-issue metadata")
    return manifest, identities, identity_fields, roles, role_fields, participation


def freeze(output: Path, source: Path = SOURCE) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj133_gate_a_", dir=output.parent))
    try:
        upstream_manifest, identities, identity_fields, roles, role_fields, participation = load_source(source)
        by_issue_gate: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in identities:
            by_issue_gate[(row["gate_id"], row["issue"], row["fold"], row["year"])].append(row)
        for values in by_issue_gate.values():
            values.sort(key=lambda row: (int(row["candidate_rank_in_complete_issue"]), row["portfolio_id"]))

        plans: list[dict[str, object]] = []
        selected_keys: set[tuple[str, str]] = set()
        for config in CONFIGS:
            issue_rows = [
                row for row in participation
                if row["gate_id"] == config["gate_id"] and row["top_k_id"] == config["top_k_id"]
            ]
            if len(issue_rows) != 348:
                raise RuntimeError(f"complete-issue universe drift for {config['config_id']}: {len(issue_rows)}")
            for sample in sorted(issue_rows, key=lambda row: (int(row["year"]), int(row["issue"]))):
                key = (str(config["gate_id"]), sample["issue"], sample["fold"], sample["year"])
                candidates = by_issue_gate.get(key, [])[:MAX_CANDIDATES]
                for spec in ALLOCATORS:
                    selected, status = select_identities(candidates, int(config["target_identity_count"]), spec) if candidates else ([], "NO_BET_SOURCE_POOL_EMPTY")
                    if status == "AVAILABLE":
                        selected_keys.update((row["gate_id"], row["portfolio_id"]) for row in selected)
                        details = geometry(selected)
                        selected_ids = "|".join(row["portfolio_id"] for row in selected)
                        draw_count = len(selected) * int(config["ticket_M"])
                        reason = "CAPS_SATISFIED"
                    else:
                        details = geometry([])
                        selected_ids, draw_count = "", 0
                        reason = "STRICT_CAP_UNSATISFIED_NO_RELAXATION" if status == "NO_BET_CAP_UNSATISFIED" else "NO_GATE_A_CANDIDATE_POOL"
                    plans.append({
                        "config_id": config["config_id"], "config_role": config["role"], "gate_id": config["gate_id"],
                        "top_k_id": config["top_k_id"], "issue": sample["issue"], "fold": sample["fold"], "year": sample["year"],
                        "issue_instance": sample["issue_instance"], "allocator_id": spec["allocator_id"], "allocator_family": spec["family"],
                        "target_identity_count": config["target_identity_count"], "candidate_pool_count": len(by_issue_gate[key]),
                        "candidate_search_count": len(candidates), "match_exposure_cap": cap_text(spec["match_cap"]),
                        "q_delete_exposure_cap": cap_text(spec["delete_cap"]), "pairwise_jaccard_cap": cap_text(spec["jaccard_cap"]),
                        "ticket_M": config["ticket_M"], "probability_vector": config["probability_vector"],
                        "ticket_mechanism": config["ticket_mechanism"], "selected_identity_count": len(selected),
                        "selected_portfolio_ids": selected_ids, "selection_status": status, "reason": reason,
                        "planned_draw_count": draw_count, "planned_stake_yuan": draw_count * UNIT_STAKE_YUAN,
                        "full_control_draw_count": int(config["target_identity_count"]) * FULL_TICKETS,
                        "full_control_stake_yuan": int(config["target_identity_count"]) * FULL_TICKETS * UNIT_STAKE_YUAN,
                        **details, "selection_scope": "COMPLETE_ISSUE; source segments diagnostic-only",
                        "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
                    })
        plans.sort(key=lambda row: (int(str(row["year"])), int(str(row["issue"])), str(row["gate_id"]), str(row["config_id"]), str(row["allocator_id"])))

        candidate_catalog = [
            row for row in identities
            if row["gate_id"] in {str(config["gate_id"]) for config in CONFIGS}
            and int(row["candidate_rank_in_complete_issue"]) <= MAX_CANDIDATES
        ]
        allowed_keys = {(row["gate_id"], row["portfolio_id"]) for row in candidate_catalog}
        if not selected_keys <= allowed_keys:
            raise RuntimeError("allocation selected an identity outside the frozen candidate pool")
        role_catalog = [row for row in roles if (row["gate_id"], row["portfolio_id"]) in allowed_keys]
        if { (row["gate_id"], row["portfolio_id"]) for row in role_catalog } != allowed_keys:
            raise RuntimeError("candidate role coverage drift")

        sampler_rows: list[dict[str, object]] = []
        for config in CONFIGS:
            for allocator in ALLOCATORS:
                if config["ticket_mechanism"] == "EXACT_K4_FULL":
                    sampler_rows.append({
                        "config_id": config["config_id"], "gate_id": config["gate_id"], "top_k_id": config["top_k_id"],
                        "allocator_id": allocator["allocator_id"], "ticket_M": config["ticket_M"], "probability_vector": config["probability_vector"],
                        "ticket_mechanism": config["ticket_mechanism"], "seed": "NA", "seed_role": "CONTROL", "duplicate_policy": "NOT_APPLICABLE",
                        "issue_total_draw_formula": "selected_identity_count × 2187", "issue_total_stake_formula": "selected_identity_count × 2187 × ¥2",
                        "outcome_boundary": "pre-outcome allocation/ticket control only",
                    })
                else:
                    for seed in SEEDS:
                        sampler_rows.append({
                            "config_id": config["config_id"], "gate_id": config["gate_id"], "top_k_id": config["top_k_id"],
                            "allocator_id": allocator["allocator_id"], "ticket_M": config["ticket_M"], "probability_vector": config["probability_vector"],
                            "ticket_mechanism": config["ticket_mechanism"], "seed": seed,
                            "seed_role": "PRIMARY" if seed == SEEDS[0] else "SENSITIVITY", "duplicate_policy": "DEDUPLICATED",
                            "issue_total_draw_formula": "selected_identity_count × M", "issue_total_stake_formula": "selected_identity_count × M × ¥2",
                            "outcome_boundary": "pre-outcome allocation/ticket replay only",
                        })

        summaries: list[dict[str, object]] = []
        for config in CONFIGS:
            for allocator in ALLOCATORS:
                rows = [row for row in plans if row["config_id"] == config["config_id"] and row["allocator_id"] == allocator["allocator_id"]]
                available = [row for row in rows if row["selection_status"] == "AVAILABLE"]
                summaries.append({
                    "config_id": config["config_id"], "allocator_id": allocator["allocator_id"], "issue_rows": len(rows),
                    "available_rows": len(available), "no_bet_rows": len(rows) - len(available),
                    "selected_identity_total": sum(int(row["selected_identity_count"]) for row in available),
                    "planned_stake_yuan_total": format(sum(float(row["planned_stake_yuan"]) for row in available), ".2f"),
                    "mean_effective_independent_match_count": format(sum(float(row["effective_independent_match_count"]) for row in available) / len(available), ".12f") if available else "0.000000000000",
                    "max_match_exposure_observed": max((int(row["max_match_exposure"]) for row in available), default=0),
                    "max_pairwise_jaccard_observed": format(max((float(row["max_pairwise_jaccard"]) for row in available), default=0.0), ".12f"),
                    "max_q_delete_exposure_observed": max((int(row["max_q_delete_exposure"]) for row in available), default=0),
                })

        write_csv(stage / "allocation_plan.csv", PLAN_FIELDS, plans)
        write_csv(stage / "allocator_sampler_plan.csv", SAMPLER_FIELDS, sampler_rows)
        write_csv(stage / "allocator_frontier_summary.csv", SUMMARY_FIELDS, summaries)
        write_gzip_csv(stage / "candidate_identity_catalog.csv.gz", identity_fields, candidate_catalog)
        write_gzip_csv(stage / "candidate_role_vectors.csv.gz", role_fields, role_catalog)
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj137_gate_a_preoutcome_v2", "role": "accepted outcome-unexposed complete-issue candidate and Q-weight source", "identity": "SHA256SUMS.json", "sha256": UPSTREAM_MANIFEST, "rows": len(identities), "join_status": "only NO_GATE and ESP300_GM290 candidate pools up to deterministic rank 32 retained"},
            {"source": "#137 Gate B / #144", "role": "design attribution only; no ledger or outcome payload read", "identity": "NO_PROMOTION / NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING", "sha256": "NOT_APPLICABLE", "rows": 0, "join_status": "primary M64/M128 and secondary ESP300_GM290/K8 inputs are diagnostic controls, not accepted edges"},
        ])
        card = {
            "issue": 133,
            "contract": CONTRACT,
            "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_DIVERSIFIED_ALLOCATION_FREEZE",
            "source": {"bj137_gate_a_v2_manifest_sha256": UPSTREAM_MANIFEST, "bj137_gate_a_v2_content_identity_sha256": upstream_manifest["CONTENT_IDENTITY.json"]},
            "complete_issue_contract": {
                "primary_unit": "complete (issue, fold) lottery issue; source segments are diagnostic-only",
                "candidate_pool": "same frozen #137 identity pool, deterministic candidate-rank order, first 32 identities per complete issue×gate",
                "budget": "all allocator arms within a config have selected_identity_count × M × ¥2 stake; no partial allocation is substituted when a strict cap fails",
                "comparison": "allocator-minus-CONCENTRATED_TOP_SCORE and allocator-minus-exact-K-FULL are Gate-B matched effects on the same complete issues and configured issue budget",
                "no_bet": "strict cap infeasibility yields an explicit NO_BET_CAP_UNSATISFIED row; it never relaxes or borrows identities from another segment",
            },
            "configurations": CONFIGS,
            "allocator_frontier": ALLOCATORS,
            "metrics_frozen_for_gate_b": ["pre-tax no_tax_roi primary; tax_adjusted_roi secondary", "matched allocator-minus-concentrated and allocator-minus-FULL effects", "participation/capital utilization", "match exposure, q-deleted-code exposure, pairwise Jaccard and effective independent match count", "payout concentration, drawdown, issue bootstrap and multiple-comparison diagnostics"],
            "outcome_boundary": "No test outcome, score, final/winning SP, settlement, payout, ROI, tax realization, or post-kickoff input is read or emitted. The #137 outcome-informed result supplies only the accepted diagnostic configuration labels.",
            "gate_b_requirements": {"authorization": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE", "positive_result": "requires separate strict EV and later held-out/forward validation; no result promotes purchase, production, or betting"},
            "scope": "historical paper research only; no purchase, production, or promotion authority.",
            "denominator": {"source_identity_rows": len(identities), "candidate_identity_rows": len(candidate_catalog), "candidate_role_rows": len(role_catalog), "complete_issue_gate_pools": len(by_issue_gate), "configuration_rows": len(plans), "allocator_arms": len(ALLOCATORS), "configs": len(CONFIGS)},
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text(
            "# #133 Gate A: complete-issue diversified N7 allocation freeze\n\n"
            "This immutable package freezes the complete-issue identity pool, equal-budget allocator frontier, Q-deleted-code exposure, role vectors and ticket replay plans. "
            "It contains no outcomes and cannot settle a policy. Replay with `python3 freeze_runner.py --output <new-dir>`; staging occurs beside the requested output, never in `/tmp`.\n",
            encoding="utf-8",
        )
        gzip_names = ("candidate_identity_catalog.csv.gz", "candidate_role_vectors.csv.gz")
        content = {
            "contract_version": CONTENT_VERSION,
            "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": decompressed_digest(stage / name)[1]} for name in gzip_names},
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "plans": len(plans), "candidate_identities": len(candidate_catalog), "candidate_roles": len(role_catalog)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve(), args.source.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
