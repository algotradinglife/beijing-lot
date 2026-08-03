#!/usr/bin/env python3
"""Freeze #159's selected-baseline WOR cross-N allocation surface.

Gate A is deliberately outcome-unexposed.  It binds the accepted #127
``ESP300_GM305_LOWP20`` selector and the #145 allocation contract, then
generalises only the number of legs in the selected identity.  Selection is
performed over the complete lottery issue (``issue@fold``), not over a native
pool or segment.  Native pools are retained only as provenance.  No result,
score, final SP, payout, tax or settlement file is opened by this program.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path


CONTRACT = "BJ-HIST-SELECTED-WOR-CROSS-N-001"
VERSION = "bj159-gate-a-v2"
CONTENT_VERSION = "bj159-selected-wor-cross-n-content-v2"
SOURCE_127_MANIFEST = "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da"
SOURCE_145_MANIFEST = "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c"
SOURCE_127_VARIANT = "ESP300_GM305_LOWP20"
E_SP_MIN = 3.0
GM_E_SP_MIN = 3.05
LOW_P_MAX = 0.20
MAX_CANDIDATES = 32
N_GRID = tuple(range(2, 11))
M_GRID = (32, 64, 128)
SEEDS = ("137001", "137002", "137003")
UNIT_STAKE = 2
CODES = ("3", "1", "0")

POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
SCATTER_FIELDS = POOL_FIELDS + (
    "match_id", "match_idx", "p_min", "e_sp", "p3", "p1", "p0", "q3", "q1", "q0",
)
IDENTITY_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "source_pool_ids",
    "source_segment_indices", "n", "candidate_match_id", "candidate_rank_in_issue",
    "candidate_count_in_issue", "candidate_search_count", "candidate_cap_applied",
    "selected_match_ids", "selected_n", "selected_source_pool_count", "gm_e_sp",
    "selection_scope", "selection_rule", "source_variant", "descriptor_sha256",
    "outcome_boundary",
)
ROLE_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "source_pool_id",
    "source_segment_index", "n", "match_id", "match_idx", "kickoff_ts",
    "selection_rank", "is_candidate", "e_sp", "p_min", "p3", "p1", "p0", "q3",
    "q1", "q0", "q_weight3", "q_weight1", "q_weight0", "predicted_sp3",
    "predicted_sp1", "predicted_sp0", "selection_scope", "outcome_boundary",
)
POOL_CENSUS_FIELDS = POOL_FIELDS + ("issue_instance", "selection_scope")
PARTICIPATION_FIELDS = (
    "issue", "fold", "year", "issue_instance", "n", "source_pool_count",
    "available_pool_count", "selected_identity_count", "selected_identity_ids",
    "selection_status", "planned_M_values", "effective_M_by_n", "planned_seed_values",
    "complete_issue_unit", "outcome_boundary",
)
PLAN_FIELDS = (
    "n", "nominal_M", "effective_M", "seed", "allocator", "probability_vector",
    "mechanism", "duplicate_policy", "ticket_space_k", "coverage_fraction",
    "stake_per_ticket_yuan", "issue_draw_formula", "issue_stake_formula",
    "identity_signature_rule", "sampling_rule", "saturation_status", "outcome_boundary",
    "primary_or_sensitivity",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
SOURCE_127 = ROOT / "results" / "bj127_gate_a_preoutcome_v2"
SOURCE_145 = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
OUTPUT = ROOT / "results" / "bj159_gate_a_preoutcome_v2r1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def manifest(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted immutable source: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"source manifest coverage drift: {path}")
    return declared


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite numeric output")
    return format(value, ".12f")


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush()
    text.detach()
    zipped.close()
    raw.close()


def issue_instance(row: dict[str, str]) -> str:
    return f"{row['issue']}@{row['fold']}"


def selected_sort(row: dict[str, str]) -> tuple[float, float, int, str]:
    return (-float(row["e_sp"]), float(row["p_min"]), int(row["match_idx"]), row["match_id"])


def candidate_sort(row: dict[str, str]) -> tuple[float, int, str]:
    return (float(row["p_min"]), int(row["match_idx"]), row["match_id"])


def geometric(rows: list[dict[str, str]]) -> float:
    if not rows or any(float(row["e_sp"]) <= 0 for row in rows):
        raise RuntimeError("invalid E_SP for geometric mean")
    return math.exp(sum(math.log(float(row["e_sp"])) for row in rows) / len(rows))


def normalize_q(row: dict[str, str]) -> tuple[float, float, float]:
    values = [float(row[f"q{code}"]) for code in CODES]
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise RuntimeError(f"invalid q vector: {row['match_id']}")
    total = sum(values)
    return tuple(value / total for value in values)


def read_csv(path: Path, fields: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if fields is not None and actual != fields:
            raise RuntimeError(f"schema drift: {path}")
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"empty source: {path}")
    return rows


def read_gzip_csv(path: Path, fields: tuple[str, ...] | None = None) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        if fields is not None and actual != fields:
            raise RuntimeError(f"schema drift: {path}")
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"empty source: {path}")
    return rows


def read_legacy_target_sets(path: Path) -> set[tuple[str, ...]]:
    rows = read_gzip_csv(path / "portfolio_role_assignments.csv.gz")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if row["variant_id"] == SOURCE_127_VARIANT:
            grouped[row["portfolio_id"]].append(row)
    target_sets = {
        tuple(row["match_id"] for row in sorted(items, key=lambda item: int(item["selection_rank"])))
        for items in grouped.values()
    }
    if len(target_sets) != 371:
        raise RuntimeError("#127 target identity denominator drift")
    return target_sets


def load_inputs() -> tuple[dict[str, str], dict[str, str], list[dict[str, str]], dict[str, list[dict[str, str]]], dict[tuple[str, str, str], list[dict[str, str]]], set[tuple[str, ...]]]:
    source_127 = manifest(SOURCE_127, SOURCE_127_MANIFEST)
    source_145 = manifest(SOURCE_145, SOURCE_145_MANIFEST)
    scatter = read_gzip_csv(SOURCE_127 / "scatter_coordinates.csv.gz", SCATTER_FIELDS)
    pools: dict[str, dict[str, str]] = {}
    by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    by_issue: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in scatter:
        pool_id = row["pool_id"]
        pools.setdefault(pool_id, {field: row[field] for field in POOL_FIELDS})
        by_pool[pool_id].append(row)
        by_issue[(row["issue"], row["fold"], row["year"])].append(row)
    if len(pools) != 2659 or len({row["issue"] for row in pools.values()}) != 344:
        raise RuntimeError("#127 native pool/issue denominator drift")
    for pool_rows in by_pool.values():
        pool_rows.sort(key=selected_sort)
    for issue_rows in by_issue.values():
        issue_rows.sort(key=lambda row: (row["pool_id"], int(row["match_idx"]), row["match_id"]))
    provenance = {
        "bj127_gate_a_manifest_sha256": SOURCE_127_MANIFEST,
        "bj127_scatter_payload_sha256": source_127["scatter_coordinates.csv.gz"],
        "bj127_role_payload_sha256": source_127["portfolio_role_assignments.csv.gz"],
        "bj145_gate_a_manifest_sha256": SOURCE_145_MANIFEST,
        "bj145_allocation_engine_sha256": source_145["bj145_allocation_engine.py"],
        "scatter_rows": str(len(scatter)),
    }
    return source_127, source_145, list(pools.values()), by_pool, by_issue, read_legacy_target_sets(SOURCE_127)


def make_identity(issue_key: tuple[str, str, str], candidate: dict[str, str], selected: list[dict[str, str]], n: int, candidate_rank: int, candidate_count: int) -> dict[str, object]:
    issue, fold, year = issue_key
    ordered_ids = tuple(row["match_id"] for row in selected)
    source_pools = tuple(sorted({row["pool_id"] for row in selected}))
    source_segments = tuple(sorted({row["segment_index"] for row in selected}, key=lambda value: int(value)))
    descriptor = {
        "contract": CONTRACT, "source_variant": SOURCE_127_VARIANT, "issue_instance": f"{issue}@{fold}",
        "n": n, "candidate_match_id": candidate["match_id"], "selected_match_ids": ordered_ids,
    }
    identity_id = compact_hash(descriptor)
    return {
        "identity_id": identity_id, "issue": issue, "fold": fold, "year": year,
        "issue_instance": f"{issue}@{fold}", "source_pool_ids": "|".join(source_pools),
        "source_segment_indices": "|".join(source_segments), "n": n,
        "candidate_match_id": candidate["match_id"], "candidate_rank_in_issue": candidate_rank,
        "candidate_count_in_issue": candidate_count, "candidate_search_count": MAX_CANDIDATES,
        "candidate_cap_applied": "TRUE" if candidate_count > MAX_CANDIDATES else "FALSE",
        "selected_match_ids": "|".join(ordered_ids), "selected_n": n,
        "selected_source_pool_count": len(source_pools), "gm_e_sp": fmt(geometric(selected)),
        "selection_scope": "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOLS_PROVENANCE_ONLY",
        "selection_rule": "#127 ESP300_GM305_LOWP20: candidate p_min<=0.20; N-1 highest-E_SP companions with E_SP>=3.00; GM_E_SP>=3.05; top-32 candidate search; deterministic dedup",
        "source_variant": SOURCE_127_VARIANT,
        "descriptor_sha256": compact_hash(descriptor),
        "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
    }


def build_identities(pools: list[dict[str, str]], by_issue: dict[tuple[str, str, str], list[dict[str, str]]], legacy_sets: set[tuple[str, ...]]) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[tuple[str, str], list[str]], dict[str, object]]:
    identities: list[dict[str, object]] = []
    roles: list[dict[str, object]] = []
    by_issue_n: dict[tuple[str, str], list[str]] = defaultdict(list)
    n7_generated: set[tuple[str, ...]] = set()
    for issue_key in sorted(by_issue, key=lambda key: (int(key[2]), int(key[0]), key[1])):
        issue, fold, year = issue_key
        issue_rows = by_issue[issue_key]
        # A match occurs in exactly one native pool in this accepted source.
        # Keep this guard so a future source cannot silently duplicate a leg.
        by_match: dict[str, dict[str, str]] = {}
        for row in issue_rows:
            if row["pool_disposition"] != "AVAILABLE":
                continue
            if row["match_id"] in by_match:
                raise RuntimeError(f"duplicate available match in complete issue: {issue_key} {row['match_id']}")
            by_match[row["match_id"]] = row
        available_rows = list(by_match.values())
        candidates_all = sorted((row for row in available_rows if float(row["p_min"]) <= LOW_P_MAX), key=candidate_sort)
        candidates = candidates_all[:MAX_CANDIDATES]
        for n in N_GRID:
            seen: set[tuple[str, ...]] = set()
            for rank, candidate in enumerate(candidates, 1):
                companions = sorted(
                    (row for row in available_rows if row["match_id"] != candidate["match_id"] and float(row["e_sp"]) >= E_SP_MIN),
                    key=selected_sort,
                )[: n - 1]
                if len(companions) != n - 1:
                    continue
                selected = sorted([candidate, *companions], key=selected_sort)
                if geometric(selected) < GM_E_SP_MIN:
                    continue
                ids = tuple(row["match_id"] for row in selected)
                if ids in seen:
                    continue
                seen.add(ids)
                if n == 7:
                    n7_generated.add(ids)
                identity = make_identity(issue_key, candidate, selected, n, rank, len(candidates_all))
                identities.append(identity)
                by_issue_n[(f"{issue}@{fold}", str(n))].append(str(identity["identity_id"]))
                for selection_rank, role in enumerate(selected, 1):
                    q_weight = normalize_q(role)
                    p = tuple(float(role[f"p{code}"]) for code in CODES)
                    q = tuple(float(role[f"q{code}"]) for code in CODES)
                    predicted_sp = tuple(q[index] / p[index] for index in range(3))
                    roles.append({
                        "identity_id": identity["identity_id"], "issue": issue, "fold": fold, "year": year,
                        "issue_instance": f"{issue}@{fold}", "source_pool_id": role["pool_id"],
                        "source_segment_index": role["segment_index"], "n": n, "match_id": role["match_id"],
                        "match_idx": role["match_idx"], "kickoff_ts": role["first_kickoff_ts"],
                        "selection_rank": selection_rank, "is_candidate": int(role["match_id"] == candidate["match_id"]),
                        "e_sp": role["e_sp"], "p_min": role["p_min"], "p3": role["p3"], "p1": role["p1"], "p0": role["p0"],
                        "q3": role["q3"], "q1": role["q1"], "q0": role["q0"], "q_weight3": fmt(q_weight[0]),
                        "q_weight1": fmt(q_weight[1]), "q_weight0": fmt(q_weight[2]), "predicted_sp3": fmt(predicted_sp[0]),
                        "predicted_sp1": fmt(predicted_sp[1]), "predicted_sp0": fmt(predicted_sp[2]),
                        "selection_scope": "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOLS_PROVENANCE_ONLY",
                        "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
                    })
    legacy_sha = compact_hash(sorted("|".join(ids) for ids in legacy_sets))
    corrected_sha = compact_hash(sorted("|".join(ids) for ids in n7_generated))
    bridge = {
        "legacy_segment_baseline_identity_count": len(legacy_sets),
        "corrected_complete_issue_identity_count": len(n7_generated),
        "exact_intersection_count": len(legacy_sets & n7_generated),
        "legacy_only_count": len(legacy_sets - n7_generated),
        "corrected_only_count": len(n7_generated - legacy_sets),
        "legacy_identity_set_sha256": legacy_sha,
        "corrected_identity_set_sha256": corrected_sha,
        "bridge_status": "LEGACY_SEGMENT_BASELINE_NOT_EQUAL_COMPLETE_ISSUE_SELECTION",
        "legacy_rule": "#127 accepted target identities selected within native pool/segment",
        "corrected_rule": "#159 candidates, companions, GM filter, and dedup applied once over complete issue_instance",
        "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
    }
    return identities, roles, by_issue_n, bridge


def write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj159_gatea_v2_", dir=output.parent))
    try:
        source_127, source_145, pools, _by_pool, by_issue, legacy_sets = load_inputs()
        identities, roles, by_issue_n, bridge = build_identities(pools, by_issue, legacy_sets)
        identities.sort(key=lambda row: (int(row["year"]), int(row["issue"]), int(row["n"]), row["issue_instance"], row["identity_id"]))
        roles.sort(key=lambda row: (int(row["year"]), int(row["issue"]), int(row["n"]), row["identity_id"], int(row["selection_rank"])))
        issue_meta: dict[tuple[str, str, str], dict[str, object]] = {}
        for pool in pools:
            key = (pool["issue"], pool["fold"], pool["year"])
            item = issue_meta.setdefault(key, {"pool_count": 0, "available_pool_count": 0})
            item["pool_count"] += 1
            item["available_pool_count"] += pool["pool_disposition"] == "AVAILABLE"
        participation = []
        for (issue, fold, year), meta in sorted(issue_meta.items(), key=lambda item: (int(item[0][2]), int(item[0][0]), item[0][1])):
            instance = f"{issue}@{fold}"
            for n in N_GRID:
                ids = sorted(by_issue_n.get((instance, str(n)), []))
                effective = "|".join(f"{m}:{min(m, 3 ** n)}" for m in M_GRID) if ids else ""
                participation.append({
                    "issue": issue, "fold": fold, "year": year, "issue_instance": instance, "n": n,
                    "source_pool_count": meta["pool_count"], "available_pool_count": meta["available_pool_count"],
                    "selected_identity_count": len(ids), "selected_identity_ids": "|".join(ids),
                    "selection_status": "AVAILABLE" if ids else "NO_BET_NO_IDENTITY", "planned_M_values": "32|64|128" if ids else "",
                    "effective_M_by_n": effective, "planned_seed_values": "137001|137002|137003" if ids else "",
                    "complete_issue_unit": "TRUE", "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
                })
        plans = []
        saturated_cells = []
        for n in N_GRID:
            ticket_space = 3 ** n
            for nominal_m in M_GRID:
                effective_m = min(nominal_m, ticket_space)
                status = "FULL_SPACE_SATURATED" if nominal_m > ticket_space else "PARTIAL_WOR"
                if status == "FULL_SPACE_SATURATED":
                    saturated_cells.extend((n, nominal_m, seed) for seed in SEEDS)
                for seed in SEEDS:
                    plans.append({
                        "n": n, "nominal_M": nominal_m, "effective_M": effective_m, "seed": seed,
                        "allocator": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT",
                        "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT", "duplicate_policy": "EFFECTIVE_M_DISTINCT_TICKETS_PER_IDENTITY",
                        "ticket_space_k": ticket_space, "coverage_fraction": fmt(effective_m / ticket_space), "stake_per_ticket_yuan": UNIT_STAKE,
                        "issue_draw_formula": "sum(selected_identity_count) × effective_M", "issue_stake_formula": "sum(selected_identity_count) × effective_M × ¥2",
                        "identity_signature_rule": "exact selected_match_ids pipe string; no portfolio_id substitution",
                        "sampling_rule": "#145 bj145 allocation exponential-key WOR with #137 stable_uniform namespace and base-3 code order generalized to N legs",
                        "saturation_status": status, "outcome_boundary": "Pre-outcome allocation specification only; Gate B joins canonical final outcome after this freeze",
                        "primary_or_sensitivity": "PRIMARY" if nominal_m == 64 else "SENSITIVITY",
                    })
        pool_rows = [{**pool, "issue_instance": issue_instance(pool), "selection_scope": "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOLS_PROVENANCE_ONLY"} for pool in sorted(pools, key=lambda row: (int(row["issue"]), row["pool_id"]))]
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj127_gate_a_preoutcome_v2", "role": "accepted ESP300_GM305_LOWP20 selector and outcome-unexposed p/E_SP/q vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_127_MANIFEST, "rows": sum(len(items) for items in by_issue.values()), "join_status": "all immutable scatter rows read; no outcomes or settlement fields opened"},
            {"source": "bj145_gate_a_preoutcome_v8", "role": "accepted Q-informed WOR allocator and identity-signature contract", "identity": "SHA256SUMS.json", "sha256": SOURCE_145_MANIFEST, "rows": "allocation contract", "join_status": "allocation contract only; no Gate-B rows or outcomes opened"},
        ])
        write_csv(stage / "pool_census.csv", POOL_CENSUS_FIELDS, pool_rows)
        handles = gzip_writer(stage / "identity_catalog.csv.gz", IDENTITY_FIELDS)
        handles[-1].writerows(identities)
        close_gzip(handles)
        handles = gzip_writer(stage / "role_vectors.csv.gz", ROLE_FIELDS)
        handles[-1].writerows(roles)
        close_gzip(handles)
        write_csv(stage / "issue_participation.csv", PARTICIPATION_FIELDS, participation)
        write_csv(stage / "sampling_plan.csv", PLAN_FIELDS, plans)
        (stage / "n7_reference_audit.json").write_text(json.dumps({**bridge, "source_variant": SOURCE_127_VARIANT}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {
            "issue": 159, "contract": CONTRACT, "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_SELECTED_BASELINE_CROSS_N_FREEZE",
            "sources": {"bj127_gate_a_preoutcome_v2": {"manifest_sha256": SOURCE_127_MANIFEST, "variant": SOURCE_127_VARIANT, "role": "frozen selector and p/E_SP/q vectors"}, "bj145_gate_a_preoutcome_v8": {"manifest_sha256": SOURCE_145_MANIFEST, "role": "fixed Q-informed WOR allocator contract"}},
            "selection": {"variant": SOURCE_127_VARIANT, "e_sp_min": E_SP_MIN, "gm_e_sp_min": GM_E_SP_MIN, "p_min_max": LOW_P_MAX, "candidate_search_cap": MAX_CANDIDATES, "candidate_rule": "p_min <= 0.20, ranked by p_min then match_idx then match_id across complete issue_instance", "companion_rule": "N-1 highest-E_SP other matches with E_SP >= 3.00 across the complete issue_instance", "identity_rule": "sort candidate plus companions by descending E_SP, ascending p_min, match_idx, match_id; deduplicate selected match-id tuples once per complete issue_instance", "analysis_unit": "complete lottery issue_instance issue@fold; native pool/segment retained only as provenance, never as a selection or settlement boundary", "n_grid": list(N_GRID), "n7_bridge_audit": bridge},
            "sampling": {"allocator": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT = normalized outcome-unexposed q=p_cal×predicted_SP per leg", "nominal_M_grid": list(M_GRID), "seeds": list(SEEDS), "ticket_space": "3^N base-3 code order #137-compatible", "saturation_rule": "effective_M=min(nominal_M,3^N); coverage_fraction=effective_M/(3^N); nominal rows with FULL_SPACE_SATURATED share one actual full-space allocation per identity and seed", "unit_stake_yuan": UNIT_STAKE, "tax": "Gate B only; each winning ¥2 ticket is an independent tax unit; no issue/policy pooling"},
            "denominator": {"native_pools": len(pools), "native_issues": len({row['issue'] for row in pools}), "issue_instances": len(issue_meta), "identity_rows": len(identities), "role_rows": len(roles), "participation_rows": len(participation), "sampling_plan_rows": len(plans), "saturated_plan_rows": len(saturated_cells), "identity_count_by_n": {str(n): sum(1 for row in identities if int(row["n"]) == n) for n in N_GRID}, "issue_count_by_n": {str(n): len({row["issue_instance"] for row in identities if int(row["n"]) == n}) for n in N_GRID}},
            "gate_b_requirements": ["pre-tax no_tax_roi primary; tax-adjusted ROI secondary", "nominal/effective M, actual draw count and stake; saturated cells are one allocation, not duplicate WOR", "total stake/per-issue distribution/participation/identity count", "complete-ticket hit rate/winning-ticket count/coverage/miss streak", "GM expected SP/actual payout/tax-line share", "YEAR/FOLD/LOYO/issue bootstrap", "largest issue and ex-largest ROI", "matched/common-support deltas vs N=7", "complete N→ROI/hit/capital/tax curves"],
            "outcome_boundary": "No result, score, final SP, payout, tax, ROI, settlement or post-kickoff field is read or emitted. Gate B is NOT_RUN until this exact Gate-A package is accepted.",
            "scope": "historical paper-only research; no purchase, production, betting or promotion authority",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text("# #159 Gate A v2 — selected-baseline WOR cross-N\n\nOutcome-unexposed freeze of the accepted #127 ESP300_GM305_LOWP20 selector for N=2..10 and the fixed #145 Q-informed WOR allocator at nominal M=32/64/128 and seeds 137001/137002/137003. Selection is performed once over each complete `issue@fold`; native pool/segment IDs are provenance only. Gate B must consume this package without recomputing identities. For nominal M above 3^N, `effective_M` and actual stake use the full ticket space and the saturated nominal rows are one allocation, not duplicate WOR. Run `python3 freeze_runner.py --output <new-dir>` from a compatible checkout; staging remains beside the output under `.scratch` and never uses `/tmp`.\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "freeze_runner.py")

        gzip_names = ("identity_catalog.csv.gz", "role_vectors.csv.gz")
        def decompressed(path: Path) -> tuple[str, int]:
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
                    size += len(block)
            return digest.hexdigest(), size
        content = {"contract_version": CONTENT_VERSION, "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed(stage / name)[0], "canonical_decompressed_bytes": decompressed(stage / name)[1]} for name in gzip_names}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "identity_rows": len(identities), "role_rows": len(roles), "identity_count_by_n": {str(n): sum(1 for row in identities if int(row["n"]) == n) for n in N_GRID}, "n7_bridge": bridge, "saturated_plan_rows": len(saturated_cells)}
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
