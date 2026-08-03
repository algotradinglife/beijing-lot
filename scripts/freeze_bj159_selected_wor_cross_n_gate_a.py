#!/usr/bin/env python3
"""Freeze #159's selected-baseline WOR cross-N allocation surface.

Gate A is deliberately outcome-unexposed.  It binds the accepted #127
``ESP300_GM305_LOWP20`` selector and the #145 allocation contract, then
generalises only the number of legs in the selected identity.  No result,
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
VERSION = "bj159-gate-a-v1"
CONTENT_VERSION = "bj159-selected-wor-cross-n-content-v1"
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
    "identity_id", "issue", "fold", "year", "issue_instance", "pool_id", "segment_index",
    "n", "candidate_match_id", "candidate_rank_in_pool", "candidate_count_in_pool",
    "candidate_search_count", "candidate_cap_applied", "selected_match_ids", "selected_n",
    "gm_e_sp", "selection_scope", "selection_rule", "source_variant", "descriptor_sha256",
    "outcome_boundary",
)
ROLE_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "pool_id", "segment_index",
    "n", "match_id", "match_idx", "kickoff_ts", "selection_rank", "is_candidate", "e_sp",
    "p_min", "p3", "p1", "p0", "q3", "q1", "q0", "q_weight3", "q_weight1", "q_weight0",
    "predicted_sp3", "predicted_sp1", "predicted_sp0", "outcome_boundary",
)
POOL_CENSUS_FIELDS = POOL_FIELDS + ("issue_instance", "selection_scope")
PARTICIPATION_FIELDS = (
    "issue", "fold", "year", "issue_instance", "n", "source_pool_count", "available_pool_count",
    "selected_identity_count", "selected_identity_ids", "selection_status", "planned_M_values",
    "planned_seed_values", "complete_issue_unit", "outcome_boundary",
)
PLAN_FIELDS = (
    "n", "M", "seed", "allocator", "probability_vector", "mechanism", "duplicate_policy",
    "ticket_space_k", "stake_per_ticket_yuan", "issue_draw_formula", "issue_stake_formula",
    "identity_signature_rule", "sampling_rule", "outcome_boundary", "primary_or_sensitivity",
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
OUTPUT = ROOT / "results" / "bj159_gate_a_preoutcome_v1"


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
    if total <= 0:
        raise RuntimeError("q vector has no mass")
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


def load_inputs() -> tuple[dict[str, str], dict[str, str], list[dict[str, str]], dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    source_127 = manifest(SOURCE_127, SOURCE_127_MANIFEST)
    source_145 = manifest(SOURCE_145, SOURCE_145_MANIFEST)
    scatter = read_gzip_csv(SOURCE_127 / "scatter_coordinates.csv.gz", SCATTER_FIELDS)
    pools: dict[str, dict[str, str]] = {}
    by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in scatter:
        pool_id = row["pool_id"]
        pools.setdefault(pool_id, {field: row[field] for field in POOL_FIELDS})
        by_pool[pool_id].append(row)
    if len(pools) != 2659 or len({row["issue"] for row in pools.values()}) != 344:
        raise RuntimeError("#127 native pool/issue denominator drift")
    for pool_rows in by_pool.values():
        pool_rows.sort(key=selected_sort)
    # Rebuild the accepted N7 target directly from the source role rows.  This
    # is a semantic guard: our N=7 generalisation must be byte-independent but
    # identity-set identical to #127's accepted target variant.
    target_roles = read_gzip_csv(SOURCE_127 / "portfolio_role_assignments.csv.gz")
    target_sets: set[tuple[str, ...]] = set()
    current: tuple[str, str] | None = None
    current_rows: list[dict[str, str]] = []
    for row in target_roles:
        if row["variant_id"] != SOURCE_127_VARIANT:
            continue
        key = row["portfolio_id"], row["pool_id"]
        if current is not None and key != current:
            target_sets.add(tuple(item["match_id"] for item in current_rows))
            current_rows = []
        current = key
        current_rows.append(row)
    if current is not None:
        target_sets.add(tuple(item["match_id"] for item in current_rows))
    if len(target_sets) != 371:
        raise RuntimeError("#127 target identity denominator drift")
    provenance = {
        "bj127_gate_a_manifest_sha256": SOURCE_127_MANIFEST,
        "bj127_scatter_payload_sha256": source_127["scatter_coordinates.csv.gz"],
        "bj127_role_payload_sha256": source_127["portfolio_role_assignments.csv.gz"],
        "bj145_gate_a_manifest_sha256": SOURCE_145_MANIFEST,
        "bj145_allocation_engine_sha256": source_145["bj145_allocation_engine.py"],
    }
    return source_127, source_145, list(pools.values()), by_pool, sorted(target_sets)


def make_identity(pool: dict[str, str], candidate: dict[str, str], selected: list[dict[str, str]], n: int, candidate_rank: int, candidate_count: int) -> dict[str, object]:
    ordered_ids = tuple(row["match_id"] for row in selected)
    descriptor = {"contract": CONTRACT, "source_variant": SOURCE_127_VARIANT, "pool_id": pool["pool_id"], "n": n, "candidate_match_id": candidate["match_id"], "selected_match_ids": ordered_ids}
    identity_id = compact_hash(descriptor)
    return {
        "identity_id": identity_id, "issue": pool["issue"], "fold": pool["fold"], "year": pool["year"],
        "issue_instance": f"{pool['issue']}@{pool['fold']}", "pool_id": pool["pool_id"], "segment_index": pool["segment_index"],
        "n": n, "candidate_match_id": candidate["match_id"], "candidate_rank_in_pool": candidate_rank,
        "candidate_count_in_pool": candidate_count, "candidate_search_count": MAX_CANDIDATES,
        "candidate_cap_applied": "TRUE" if candidate_count > MAX_CANDIDATES else "FALSE",
        "selected_match_ids": "|".join(ordered_ids), "selected_n": n, "gm_e_sp": fmt(geometric(selected)),
        "selection_scope": "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOL_IDENTITY",
        "selection_rule": "#127 ESP300_GM305_LOWP20: candidate p_min<=0.20; N-1 highest-E_SP companions with E_SP>=3.00; GM_E_SP>=3.05; top-32 candidate search; deterministic dedup",
        "source_variant": SOURCE_127_VARIANT, "descriptor_sha256": compact_hash(descriptor),
        "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
    }


def build_identities(pools: list[dict[str, str]], by_pool: dict[str, list[dict[str, str]]], target_sets: set[tuple[str, ...]]) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[tuple[str, str], list[str]], dict[str, str]]:
    identities: list[dict[str, object]] = []
    roles: list[dict[str, object]] = []
    by_issue_n: dict[tuple[str, str], list[str]] = defaultdict(list)
    n7_generated: set[tuple[str, ...]] = set()
    for pool in sorted(pools, key=lambda row: (int(row["issue"]), row["pool_id"])):
        available = pool["pool_disposition"] == "AVAILABLE"
        rows = by_pool[pool["pool_id"]] if available else []
        candidates_all = sorted((row for row in rows if float(row["p_min"]) <= LOW_P_MAX), key=candidate_sort)
        candidates = candidates_all[:MAX_CANDIDATES]
        for n in N_GRID:
            seen: set[tuple[str, ...]] = set()
            for rank, candidate in enumerate(candidates, 1):
                companions = [row for row in rows if row["match_id"] != candidate["match_id"] and float(row["e_sp"]) >= E_SP_MIN][: n - 1]
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
                identity = make_identity(pool, candidate, selected, n, rank, len(candidates_all))
                identities.append(identity)
                by_issue_n[(pool["issue"], str(n))].append(str(identity["identity_id"]))
                for selection_rank, role in enumerate(selected, 1):
                    q_weight = normalize_q(role)
                    p = tuple(float(role[f"p{code}"]) for code in CODES)
                    q = tuple(float(role[f"q{code}"]) for code in CODES)
                    predicted_sp = tuple(q[index] / p[index] for index in range(3))
                    roles.append({
                        "identity_id": identity["identity_id"], "issue": pool["issue"], "fold": pool["fold"], "year": pool["year"],
                        "issue_instance": f"{pool['issue']}@{pool['fold']}", "pool_id": pool["pool_id"], "segment_index": pool["segment_index"],
                        "n": n, "match_id": role["match_id"], "match_idx": role["match_idx"], "kickoff_ts": role["first_kickoff_ts"],
                        "selection_rank": selection_rank, "is_candidate": int(role["match_id"] == candidate["match_id"]), "e_sp": role["e_sp"], "p_min": role["p_min"],
                        "p3": role["p3"], "p1": role["p1"], "p0": role["p0"], "q3": role["q3"], "q1": role["q1"], "q0": role["q0"],
                        "q_weight3": fmt(q_weight[0]), "q_weight1": fmt(q_weight[1]), "q_weight0": fmt(q_weight[2]),
                        "predicted_sp3": fmt(predicted_sp[0]), "predicted_sp1": fmt(predicted_sp[1]), "predicted_sp0": fmt(predicted_sp[2]),
                        "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
                    })
    if n7_generated != set(target_sets):
        raise RuntimeError(f"#127 N=7 identity equivalence drift: generated={len(n7_generated)} target={len(target_sets)}")
    n7_hash = compact_hash(sorted("|".join(ids) for ids in n7_generated))
    return identities, roles, by_issue_n, {"n7_identity_count": str(len(n7_generated)), "n7_identity_set_sha256": n7_hash}


def write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj159_gatea_", dir=output.parent))
    try:
        source_127, source_145, pools, by_pool, target_sets = load_inputs()
        identities, roles, by_issue_n, n7_audit = build_identities(pools, by_pool, target_sets)
        identities.sort(key=lambda row: (int(row["year"]), int(row["issue"]), int(row["n"]), row["pool_id"], row["identity_id"]))
        roles.sort(key=lambda row: (int(row["year"]), int(row["issue"]), int(row["n"]), row["identity_id"], int(row["selection_rank"])))
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj127_gate_a_preoutcome_v2", "role": "accepted ESP300_GM305_LOWP20 selector and outcome-unexposed p/E_SP/q vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_127_MANIFEST, "rows": 47819, "join_status": "all immutable scatter rows read; no outcomes or settlement fields opened"},
            {"source": "bj145_gate_a_preoutcome_v8", "role": "accepted Q-informed WOR allocator and identity-signature contract", "identity": "SHA256SUMS.json", "sha256": SOURCE_145_MANIFEST, "rows": 24780, "join_status": "allocation contract only; no Gate-B rows or outcomes opened"},
        ])
        pool_rows = []
        for pool in sorted(pools, key=lambda row: (int(row["issue"]), row["pool_id"])):
            pool_rows.append({**pool, "issue_instance": f"{pool['issue']}@{pool['fold']}", "selection_scope": "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOL_IDENTITY"})
        write_csv(stage / "pool_census.csv", POOL_CENSUS_FIELDS, pool_rows)
        handles = gzip_writer(stage / "identity_catalog.csv.gz", IDENTITY_FIELDS)
        handles[-1].writerows(identities)
        close_gzip(handles)
        handles = gzip_writer(stage / "role_vectors.csv.gz", ROLE_FIELDS)
        handles[-1].writerows(roles)
        close_gzip(handles)
        # Every native issue remains in the denominator.  Selection is derived
        # pre-outcome; Gate B aggregates all identities by complete issue.
        issue_meta: dict[tuple[str, str, str], dict[str, object]] = {}
        for pool in pools:
            key = (pool["issue"], pool["fold"], pool["year"])
            item = issue_meta.setdefault(key, {"pool_count": 0, "available_pool_count": 0})
            item["pool_count"] += 1
            item["available_pool_count"] += pool["pool_disposition"] == "AVAILABLE"
        participation = []
        for (issue, fold, year), meta in sorted(issue_meta.items(), key=lambda item: (int(item[0][2]), int(item[0][0]))):
            for n in N_GRID:
                ids = sorted(by_issue_n.get((issue, str(n)), []))
                participation.append({
                    "issue": issue, "fold": fold, "year": year, "issue_instance": f"{issue}@{fold}", "n": n,
                    "source_pool_count": meta["pool_count"], "available_pool_count": meta["available_pool_count"], "selected_identity_count": len(ids),
                    "selected_identity_ids": "|".join(ids), "selection_status": "AVAILABLE" if ids else "NO_BET_NO_IDENTITY",
                    "planned_M_values": "32|64|128" if ids else "", "planned_seed_values": "137001|137002|137003" if ids else "",
                    "complete_issue_unit": "TRUE", "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
                })
        write_csv(stage / "issue_participation.csv", PARTICIPATION_FIELDS, participation)
        plans = []
        for n in N_GRID:
            for m in M_GRID:
                for seed in SEEDS:
                    plans.append({
                        "n": n, "M": m, "seed": seed, "allocator": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT",
                        "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT", "duplicate_policy": "M_DISTINCT_TICKETS_PER_IDENTITY",
                        "ticket_space_k": 3 ** n, "stake_per_ticket_yuan": UNIT_STAKE,
                        "issue_draw_formula": "sum(selected_identity_count) × M", "issue_stake_formula": "sum(selected_identity_count) × M × ¥2",
                        "identity_signature_rule": "exact selected_match_ids pipe string; no portfolio_id substitution",
                        "sampling_rule": "#145 bj145 allocation exponential-key WOR with #137 stable_uniform namespace and base-3 code order generalized to N legs",
                        "outcome_boundary": "Pre-outcome allocation specification only; Gate B joins canonical final outcome after this freeze",
                        "primary_or_sensitivity": "PRIMARY" if m == 64 else "SENSITIVITY",
                    })
        write_csv(stage / "sampling_plan.csv", PLAN_FIELDS, plans)
        (stage / "n7_reference_audit.json").write_text(json.dumps({**n7_audit, "source_variant": SOURCE_127_VARIANT, "rule": "Generated N=7 selected match sets equal accepted #127 ESP300_GM305_LOWP20 role identity sets exactly", "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {
            "issue": 159, "contract": CONTRACT, "generator_version": VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_SELECTED_BASELINE_CROSS_N_FREEZE",
            "sources": {"bj127_gate_a_preoutcome_v2": {"manifest_sha256": SOURCE_127_MANIFEST, "variant": SOURCE_127_VARIANT, "role": "frozen selector and p/E_SP/q vectors"}, "bj145_gate_a_preoutcome_v8": {"manifest_sha256": SOURCE_145_MANIFEST, "role": "fixed Q-informed WOR allocator contract"}},
            "selection": {"variant": SOURCE_127_VARIANT, "e_sp_min": E_SP_MIN, "gm_e_sp_min": GM_E_SP_MIN, "p_min_max": LOW_P_MAX, "candidate_search_cap": MAX_CANDIDATES, "candidate_rule": "p_min <= 0.20, ranked by p_min then match_idx then match_id", "companion_rule": "N-1 highest-E_SP other matches with E_SP >= 3.00 from the same native pool", "identity_rule": "sort candidate plus companions by descending E_SP, ascending p_min, match_idx, match_id; deduplicate selected match-id tuples", "analysis_unit": "complete lottery issue; native pool retained only as frozen provenance, never as a separate settlement unit", "n_grid": list(N_GRID), "n7_equivalence": n7_audit},
            "sampling": {"allocator": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT = normalized outcome-unexposed q=p_cal×predicted_SP per leg", "M_grid": list(M_GRID), "seeds": list(SEEDS), "ticket_space": "3^N base-3 code order #137-compatible", "identity_signature": "exact selected_match_ids pipe string", "unit_stake_yuan": UNIT_STAKE, "tax": "Gate B only; each winning ¥2 ticket is an independent tax unit; no issue/policy pooling"},
            "denominator": {"native_pools": len(pools), "native_issues": len({row['issue'] for row in pools}), "issue_instances": len(issue_meta), "identity_rows": len(identities), "role_rows": len(roles), "participation_rows": len(participation), "sampling_plan_rows": len(plans), "identity_count_by_n": {str(n): sum(1 for row in identities if int(row['n']) == n) for n in N_GRID}, "issue_count_by_n": {str(n): len({row['issue'] for row in identities if int(row['n']) == n}) for n in N_GRID}},
            "gate_b_requirements": ["pre-tax no_tax_roi primary; tax-adjusted ROI secondary", "total stake/per-issue distribution/participation/identity count", "complete-ticket hit rate/winning-ticket count/coverage/miss streak", "GM expected SP/actual payout/tax-line share", "YEAR/FOLD/LOYO/issue bootstrap", "largest issue and ex-largest ROI", "matched/common-support deltas vs N=7", "complete N→ROI/hit/capital/tax curves"],
            "outcome_boundary": "No result, score, final SP, payout, tax, ROI, settlement or post-kickoff field is read or emitted. Gate B is NOT_RUN until this exact Gate-A package is accepted.",
            "scope": "historical paper-only research; no purchase, production, betting or promotion authority",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text("# #159 Gate A — selected-baseline WOR cross-N\n\nOutcome-unexposed freeze of the accepted #127 ESP300_GM305_LOWP20 selector for N=2..10 and the fixed #145 Q-informed WOR allocator at M=32/64/128 and seeds 137001/137002/137003. Gate B must consume this package without recomputing identities. Run `python3 freeze_runner.py --output <new-dir>` from a compatible checkout; staging remains beside the output under `.scratch` and never uses `/tmp`.\n", encoding="utf-8")
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
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "identity_rows": len(identities), "role_rows": len(roles), "n7_identity_count": len(target_sets), "identity_count_by_n": {str(n): sum(1 for row in identities if int(row["n"]) == n) for n in N_GRID}}
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
