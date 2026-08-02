#!/usr/bin/env python3
"""Freeze #145 allocation mechanisms on the accepted #151/#137 identities.

Gate A is deliberately outcome-unexposed.  It copies the fixed #151
NO_GATE/K4 candidate and derives only the contract-authorized
ESP300_GM290/K8 sensitivity from #137's frozen participation rows.  It writes
the complete weight × mechanism × M/cap allocation surface and formulas, but
does not read or settle any match outcome, final SP, payout, or tax result.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

from bj145_allocation_engine import (
    ENGINE_VERSION,
    FULL_TICKETS as ENGINE_FULL_TICKETS,
    MECHANISMS as ENGINE_MECHANISMS,
    allocate,
    counts_fingerprint,
    golden_weights,
)


CONTRACT = "BJ-HIST-TICKET-ALLOCATION-001"
VERSION = "bj145-gate-a-v7"
CONTENT_VERSION = "bj145-gate-a-content-v7"
UNIT_STAKE_YUAN = 2
FULL_TICKETS = 3 ** 7
SEEDS = ("137001", "137002", "137003")
M_GRID = tuple(range(16, 257, 16)) + (512, 1024, 1458, FULL_TICKETS)
WEIGHT_SOURCES = (
    "MODEL_P_CAL",
    "MARKET_WF_CAL",
    "BLEND_A25",
    "BLEND_A50",
    "BLEND_A75",
    "Q_WEIGHT",
)
CAPS = (1, 2, 4, 8)
SOURCE_151_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
SOURCE_151_GATE_B_MANIFEST = "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2"
SOURCE_154_MANIFEST = "f81146959fd734c3d15a2579a3921b2afc86d6f633e174c8294763279f9937c5"
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
SOURCE_148_MANIFEST = "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6"

COHORT_FIELDS = (
    "arm_id", "source_package", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "source_disposition", "selection_status", "selected_identity_count", "selected_portfolio_ids",
    "selected_portfolio_ids_sha256", "full_ticket_count_per_identity", "full_issue_draw_count",
    "full_issue_stake_yuan", "candidate_definition", "outcome_boundary",
)
IDENTITY_FIELDS = (
    "arm_id", "source_package", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "portfolio_id", "candidate_match_id", "candidate_rank_in_complete_issue", "candidate_count_complete_issue",
    "selected_match_ids", "selected_n", "gm_e_sp", "full_k", "full_stake_yuan", "descriptor_sha256",
    "selection_scope", "fold_integrity", "source_identity_sha256", "outcome_boundary",
)
ROLE_FIELDS = (
    "arm_id", "source_package", "gate_id", "top_k_id", "portfolio_id", "issue", "fold", "year",
    "issue_instance", "match_id", "match_idx", "kickoff_ts", "selection_rank", "is_candidate", "e_sp",
    "p_min", "predicted_sp3", "predicted_sp1", "predicted_sp0", "p_model3", "p_model1", "p_model0",
    "p_market_raw3", "p_market_raw1", "p_market_raw0", "p_market_cal3", "p_market_cal1", "p_market_cal0",
    "p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0", "p_blend_a50_3", "p_blend_a50_1",
    "p_blend_a50_0", "p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0", "q_weight3", "q_weight1",
    "q_weight0", "p_min_delete_match_id", "p_min_delete_code", "q_min_delete_match_id", "q_min_delete_code",
    "source_role_sha256", "outcome_boundary",
)
PLAN_FIELDS = (
    "plan_id", "arm_id", "source_package", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "selection_status", "selected_identity_count", "selected_portfolio_ids_sha256", "weight_source", "mechanism",
    "sampling_role", "duplicate_policy", "cap", "M", "seed", "seed_role", "ticket_space_k",
    "planned_draw_count", "planned_stake_yuan", "outcome_boundary",
)
MECHANISM_FIELDS = (
    "mechanism", "sampling_role", "weight_source_scope", "seed_scope", "cap_scope", "allocation_rule",
    "expected_unique_formula", "realized_unique_rule", "duplicate_policy", "tax_unit_rule", "full_control", "outcome_boundary",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")
GRID_FIELDS = ("grid_ordinal", "M", "grid_band", "is_full_control", "low_M_surface", "outcome_boundary")


def find_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = find_root()
SOURCE_151 = ROOT / "results" / "bj151_gate_a_preoutcome_v1"
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_148 = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
OUTPUT = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
ALLOCATION_ENGINE_SOURCE = Path(__file__).resolve().with_name("bj145_allocation_engine.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def verified_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest = path / "SHA256SUMS.json"
    if not manifest.is_file() or sha256(manifest) != expected_manifest:
        raise RuntimeError(f"unaccepted source manifest: {path}")
    declared = read_json(manifest)
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return {str(k): str(v) for k, v in declared.items()}


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields, rows = tuple(reader.fieldnames or ()), list(reader)
    if not fields or not rows:
        raise RuntimeError(f"empty CSV: {path}")
    return fields, rows


def read_gzip_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields, rows = tuple(reader.fieldnames or ()), list(reader)
    if not fields or not rows:
        raise RuntimeError(f"empty gzip CSV: {path}")
    return fields, rows


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
                writer.writeheader()
                writer.writerows(rows)


def issue_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["issue"], row["fold"], row["year"], row["issue_instance"]


def selected_ids_hash(ids: tuple[str, ...]) -> str:
    return compact_hash(ids)


def source_row_to_cohort(
    source_row: dict[str, str], arm_id: str, source_package: str, definition: str,
) -> dict[str, object]:
    ids = tuple(filter(None, source_row.get("selected_portfolio_ids", "").split("|")))
    disposition = source_row.get("disposition", source_row.get("selection_status", ""))
    available = disposition == "AVAILABLE"
    if available and not ids:
        raise RuntimeError(f"available row has no identities: {arm_id}/{source_row['issue_instance']}")
    if not available and ids:
        raise RuntimeError(f"no-bet row has identities: {arm_id}/{source_row['issue_instance']}")
    status = "AVAILABLE" if available else "NO_BET_K_UNSATISFIED"
    return {
        "arm_id": arm_id, "source_package": source_package, "gate_id": source_row["gate_id"],
        "top_k_id": source_row["top_k_id"], "issue": source_row["issue"], "fold": source_row["fold"],
        "year": source_row["year"], "issue_instance": source_row["issue_instance"],
        "source_disposition": disposition, "selection_status": status, "selected_identity_count": len(ids),
        "selected_portfolio_ids": "|".join(ids), "selected_portfolio_ids_sha256": selected_ids_hash(ids),
        "full_ticket_count_per_identity": FULL_TICKETS, "full_issue_draw_count": len(ids) * FULL_TICKETS,
        "full_issue_stake_yuan": len(ids) * FULL_TICKETS * UNIT_STAKE_YUAN, "candidate_definition": definition,
        "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
    }


def load_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[str, str], dict[str, str], dict[str, str]]:
    manifest_151 = verified_bundle(SOURCE_151, SOURCE_151_MANIFEST)
    manifest_137 = verified_bundle(SOURCE_137, SOURCE_137_MANIFEST)
    manifest_148 = verified_bundle(SOURCE_148, SOURCE_148_MANIFEST)
    card_151 = read_json(SOURCE_151 / "gate_a_card.json")
    if card_151.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_FIXED_CANDIDATE_DENSE_M_FREEZE":
        raise RuntimeError("#151 Gate-A stage drift")
    if card_151.get("fixed_candidate", {}).get("gate_id") != "NO_GATE" or card_151.get("fixed_candidate", {}).get("top_k_id") != "K4":
        raise RuntimeError("#151 fixed candidate drift")
    fields_151, cohort_151 = read_csv(SOURCE_151 / "candidate_cohort.csv")
    if len(cohort_151) != 348 or Counter(row["selection_status"] for row in cohort_151) != {"AVAILABLE": 339, "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES": 9}:
        raise RuntimeError("#151 cohort drift")
    fields_137, participation_137 = read_csv(SOURCE_137 / "issue_participation_grid.csv")
    cohort_137 = [row for row in participation_137 if row["gate_id"] == "ESP300_GM290" and row["top_k_id"] == "K8"]
    if len(cohort_137) != 348 or Counter(row["disposition"] for row in cohort_137) != {"AVAILABLE": 273, "NO_BET": 75}:
        raise RuntimeError("#137 ESP300_GM290/K8 cohort drift")
    ids_151_fields, identities_151 = read_gzip_csv(SOURCE_151 / "candidate_identities.csv.gz")
    roles_151_fields, roles_151 = read_gzip_csv(SOURCE_151 / "candidate_role_vectors.csv.gz")
    ids_137_fields, identities_137 = read_gzip_csv(SOURCE_137 / "n7_identities.csv.gz")
    roles_137_fields, roles_137 = read_gzip_csv(SOURCE_137 / "n7_role_vectors.csv.gz")
    selected_151 = {(row["issue_instance"], portfolio_id) for row in cohort_151 for portfolio_id in filter(None, row["selected_portfolio_ids"].split("|"))}
    selected_137 = {(row["issue_instance"], portfolio_id) for row in cohort_137 for portfolio_id in filter(None, row["selected_portfolio_ids"].split("|"))}
    chosen_151 = [row for row in identities_151 if (row["issue_instance"], row["portfolio_id"]) in selected_151]
    chosen_137 = [row for row in identities_137 if row["gate_id"] == "ESP300_GM290" and (row["issue_instance"], row["portfolio_id"]) in selected_137]
    if len(chosen_151) != 1356 or len(chosen_137) != 2184:
        raise RuntimeError("selected identity cardinality drift")
    selected_role_151 = [row for row in roles_151 if (row["issue_instance"], row["portfolio_id"]) in selected_151]
    selected_role_137 = [row for row in roles_137 if row["gate_id"] == "ESP300_GM290" and (row["issue_instance"], row["portfolio_id"]) in selected_137]
    if len(selected_role_151) != 1356 * 7 or len(selected_role_137) != 2184 * 7:
        raise RuntimeError("selected role cardinality drift")
    return cohort_151, cohort_137, chosen_151, chosen_137, {**manifest_151, "SHA256SUMS.json": SOURCE_151_MANIFEST}, {**manifest_137, "SHA256SUMS.json": SOURCE_137_MANIFEST}, {**manifest_148, "SHA256SUMS.json": SOURCE_148_MANIFEST}


def normalize_identity(row: dict[str, str], arm_id: str, source_package: str) -> dict[str, object]:
    return {"arm_id": arm_id, "source_package": source_package, "gate_id": row["gate_id"], "top_k_id": "K4" if arm_id == "PRIMARY_NO_GATE_K4" else "K8", "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"], "portfolio_id": row["portfolio_id"], "candidate_match_id": row.get("candidate_match_id", ""), "candidate_rank_in_complete_issue": row.get("candidate_rank_in_complete_issue", ""), "candidate_count_complete_issue": row.get("candidate_count_complete_issue", ""), "selected_match_ids": row["selected_match_ids"], "selected_n": row["selected_n"], "gm_e_sp": row["gm_e_sp"], "full_k": row["full_k"], "full_stake_yuan": row["full_stake_yuan"], "descriptor_sha256": row.get("descriptor_sha256", ""), "selection_scope": row.get("selection_scope", "COMPLETE_ISSUE"), "fold_integrity": row.get("fold_integrity", "INTACT"), "source_identity_sha256": compact_hash([source_package, row["issue_instance"], row["portfolio_id"], row["selected_match_ids"]]), "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted"}


def normalize_role(row: dict[str, str], arm_id: str, source_package: str) -> dict[str, object]:
    result = {field: row.get(field, "") for field in ROLE_FIELDS if field not in {"arm_id", "source_package", "source_role_sha256", "outcome_boundary", "top_k_id"}}
    result.update({"arm_id": arm_id, "source_package": source_package, "top_k_id": "K4" if arm_id == "PRIMARY_NO_GATE_K4" else "K8", "source_role_sha256": compact_hash([source_package, row.get("issue_instance"), row.get("portfolio_id"), row.get("selection_rank"), row.get("match_id")]), "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted"})
    return result


def make_mechanisms() -> list[dict[str, object]]:
    rows = [
        {"mechanism": "WR_DUPLICATE_STAKE", "sampling_role": "PRIMARY_WEIGHTED_WR", "weight_source_scope": ";".join(WEIGHT_SOURCES), "seed_scope": ";".join(SEEDS), "cap_scope": "NA", "allocation_rule": "exact #137 stable_uniform(\"bj137\",\"WR\",seed,selected_match_ids,draw_index); exact duplicates retained", "expected_unique_formula": "sum_t[1-(1-w(t))^M]", "realized_unique_rule": "count distinct ticket codes; duplicate draws retained", "duplicate_policy": "each independent draw is a separate ¥2 ticket and separate tax unit", "tax_unit_rule": "per ¥2 ticket; no issue/policy pooling", "full_control": "false", "outcome_boundary": "pre-outcome allocation specification only"},
        {"mechanism": "WOR_DISTINCT", "sampling_role": "PRIMARY_WEIGHTED_WOR", "weight_source_scope": ";".join(WEIGHT_SOURCES), "seed_scope": ";".join(SEEDS), "cap_scope": "NA", "allocation_rule": "exact #137 stable_uniform(\"bj137\",\"WOR\",seed,selected_match_ids,ordinal); exponential-key weighted sampling without replacement", "expected_unique_formula": "M distinct ticket codes", "realized_unique_rule": "exactly M distinct ticket codes per identity", "duplicate_policy": "distinct ticket codes only within each identity", "tax_unit_rule": "per ¥2 ticket; no issue/policy pooling", "full_control": "false", "outcome_boundary": "pre-outcome allocation specification only"},
        {"mechanism": "RESIDUAL_SYSTEMATIC", "sampling_role": "RESIDUAL_PROPORTIONAL", "weight_source_scope": ";".join(WEIGHT_SOURCES), "seed_scope": "NA", "cap_scope": "NA", "allocation_rule": "Hamilton/largest-remainder integer allocation over 2187 ticket-code weights; deterministic ordinal tie-break", "expected_unique_formula": "positive-count codes from Hamilton allocation", "realized_unique_rule": "count positive integer multiplicities; retain every copy", "duplicate_policy": "integer multiplicities follow proportional quotas", "tax_unit_rule": "each repeated ¥2 copy is a separate ticket and tax unit; no pooling", "full_control": "false", "outcome_boundary": "pre-outcome allocation specification only"},
        {"mechanism": "CAPPED_REPEAT", "sampling_role": "CAPPED_PROPORTIONAL", "weight_source_scope": ";".join(WEIGHT_SOURCES), "seed_scope": "NA", "cap_scope": "1;2;4;8", "allocation_rule": "Hamilton proportional allocation with per-ticket-code cap; deterministic residual reallocation", "expected_unique_formula": "positive-count codes under frozen cap", "realized_unique_rule": "count positive codes and repeated copies; no code exceeds cap", "duplicate_policy": "repeats allowed up to frozen cap per exact N7 ticket code", "tax_unit_rule": "each repeated ¥2 copy is a separate ticket and tax unit; no pooling", "full_control": "false", "outcome_boundary": "pre-outcome allocation specification only"},
        {"mechanism": "DETERMINISTIC_TOP_MASS", "sampling_role": "TOP_MASS_CONTROL", "weight_source_scope": ";".join(WEIGHT_SOURCES), "seed_scope": "NA", "cap_scope": "1", "allocation_rule": "select M highest-weight exact ticket codes; weight desc then ordinal asc", "expected_unique_formula": "M distinct ticket codes", "realized_unique_rule": "exactly M distinct ticket codes per identity", "duplicate_policy": "distinct ticket codes only", "tax_unit_rule": "per ¥2 ticket; no issue/policy pooling", "full_control": "false", "outcome_boundary": "pre-outcome allocation specification only"},
        {"mechanism": "FULL_ENUMERATED", "sampling_role": "FULL_CONTROL", "weight_source_scope": "NA", "seed_scope": "NA", "cap_scope": "1", "allocation_rule": "enumerate all 2187 exact ticket codes once per identity", "expected_unique_formula": "2187 distinct ticket codes", "realized_unique_rule": "all 2187 distinct tickets per identity", "duplicate_policy": "all 2187 distinct tickets", "tax_unit_rule": "per ¥2 ticket; no issue/policy pooling", "full_control": "true", "outcome_boundary": "pre-outcome allocation specification only"},
    ]
    return rows


def make_grid() -> list[dict[str, object]]:
    rows = []
    for ordinal, value in enumerate(M_GRID, 1):
        band = "LOW_M_16_STEP" if value <= 256 else "HIGH_CONTROL"
        rows.append({"grid_ordinal": ordinal, "M": value, "grid_band": band, "is_full_control": str(value == FULL_TICKETS).lower(), "low_M_surface": str(value <= 256).lower(), "outcome_boundary": "pre-outcome allocation specification only"})
    return rows


def make_golden_vectors() -> dict[str, object]:
    if ENGINE_FULL_TICKETS != FULL_TICKETS or tuple(ENGINE_MECHANISMS) != tuple(row["mechanism"] for row in make_mechanisms()):
        raise RuntimeError("allocation engine mechanism contract drift")
    weights = golden_weights(FULL_TICKETS)
    specs = (
        {"mechanism": "WR_DUPLICATE_STAKE", "M": 16, "seed": "137001", "identity_signature": "golden-primary", "cap": None},
        {"mechanism": "WOR_DISTINCT", "M": 32, "seed": "137002", "identity_signature": "golden-secondary", "cap": None},
        {"mechanism": "RESIDUAL_SYSTEMATIC", "M": 64, "seed": "NA", "identity_signature": "golden-residual", "cap": None},
        {"mechanism": "CAPPED_REPEAT", "M": 128, "seed": "NA", "identity_signature": "golden-capped", "cap": 2},
        {"mechanism": "DETERMINISTIC_TOP_MASS", "M": 256, "seed": "NA", "identity_signature": "golden-top", "cap": None},
        {"mechanism": "FULL_ENUMERATED", "M": FULL_TICKETS, "seed": "NA", "identity_signature": "golden-full", "cap": None},
    )
    cases = []
    for spec in specs:
        counts = allocate(
            str(spec["mechanism"]), weights, int(spec["M"]), seed=str(spec["seed"]),
            identity_signature=str(spec["identity_signature"]), cap=spec["cap"],
        )
        fingerprint = counts_fingerprint(counts)
        cases.append({**spec, "ticket_space_k": FULL_TICKETS, **fingerprint})
    return {
        "schema_version": "bj145-allocation-golden-v1",
        "engine_version": ENGINE_VERSION,
        "weight_rule": "golden_weights_v2: raw=((ordinal*37+11)%1009)+1 then divide by sum(raw), ordinal 0..2186",
        "ticket_order": "#137 CODES=(3,1,0) product order; ordinal 0000000..2222222 is mapped through CODES",
        "outcome_boundary": "synthetic positive weights only; no outcome/final-SP/payout/ROI/tax data",
        "cases": cases,
    }


def make_cohorts(cohort_151: list[dict[str, str]], cohort_137: list[dict[str, str]]) -> list[dict[str, object]]:
    primary = [source_row_to_cohort(row, "PRIMARY_NO_GATE_K4", "results/bj151_gate_a_preoutcome_v1", "exact #151 fixed #137 NO_GATE/K4 identity list; no outcome reselection") for row in cohort_151]
    secondary = [source_row_to_cohort(row, "SECONDARY_ESP300_GM290_K8", "results/bj137_gate_a_preoutcome_v2", "exact #137 ESP300_GM290/K8 participation list; secondary sensitivity only") for row in cohort_137]
    result = sorted(primary + secondary, key=lambda row: (str(row["arm_id"]), int(str(row["year"])), int(str(row["issue"]))))
    if len(result) != 696 or Counter((str(r["arm_id"]), str(r["selection_status"])) for r in result) != Counter({("PRIMARY_NO_GATE_K4", "AVAILABLE"): 339, ("PRIMARY_NO_GATE_K4", "NO_BET_K_UNSATISFIED"): 9, ("SECONDARY_ESP300_GM290_K8", "AVAILABLE"): 273, ("SECONDARY_ESP300_GM290_K8", "NO_BET_K_UNSATISFIED"): 75}):
        raise RuntimeError("allocation cohort denominator drift")
    return result


def make_plan(cohorts: list[dict[str, object]], mechanisms: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cohort in cohorts:
        count = int(cohort["selected_identity_count"])
        available = str(cohort["selection_status"]) == "AVAILABLE"
        for weight in WEIGHT_SOURCES:
            for mechanism in mechanisms:
                name = str(mechanism["mechanism"])
                if name == "FULL_ENUMERATED":
                    m_values = (FULL_TICKETS,)
                else:
                    m_values = M_GRID
                caps = CAPS if name == "CAPPED_REPEAT" else ("NA",)
                seeds = SEEDS if name in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} else ("NA",)
                for cap in caps:
                    for m_value in m_values:
                        for seed in seeds:
                            seed_role = "PRIMARY" if seed == SEEDS[0] else ("SENSITIVITY" if seed != "NA" else "CONTROL")
                            rows.append({
                                "plan_id": compact_hash([CONTRACT, cohort["arm_id"], cohort["issue_instance"], weight, name, cap, m_value, seed]),
                                "arm_id": cohort["arm_id"], "source_package": cohort["source_package"], "gate_id": cohort["gate_id"], "top_k_id": cohort["top_k_id"],
                                "issue": cohort["issue"], "fold": cohort["fold"], "year": cohort["year"], "issue_instance": cohort["issue_instance"],
                                "selection_status": cohort["selection_status"], "selected_identity_count": count, "selected_portfolio_ids_sha256": cohort["selected_portfolio_ids_sha256"],
                                "weight_source": weight, "mechanism": name, "sampling_role": mechanism["sampling_role"], "duplicate_policy": mechanism["duplicate_policy"],
                                "cap": cap, "M": m_value, "seed": seed, "seed_role": seed_role, "ticket_space_k": FULL_TICKETS,
                                "planned_draw_count": count * int(m_value) if available else 0, "planned_stake_yuan": count * int(m_value) * UNIT_STAKE_YUAN if available else 0,
                                "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
                            })
    rows.sort(key=lambda r: (str(r["arm_id"]), int(str(r["year"])), int(str(r["issue"])), str(r["weight_source"]), str(r["mechanism"]), int(str(r["M"])), str(r["cap"]), str(r["seed"])))
    expected = len(cohorts) * len(WEIGHT_SOURCES) * (len(M_GRID) * (3 + 3 + 1 + len(CAPS) + 1) + 1)
    if len(rows) != expected or len({str(r["plan_id"]) for r in rows}) != len(rows):
        raise RuntimeError(f"allocation plan denominator drift: {len(rows)}")
    return rows


def normalize_assets(chosen_151: list[dict[str, str]], chosen_137: list[dict[str, str]], roles_151: list[dict[str, str]], roles_137: list[dict[str, str]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    selected_151 = {(r["issue_instance"], r["portfolio_id"]) for r in chosen_151}
    selected_137 = {(r["issue_instance"], r["portfolio_id"]) for r in chosen_137}
    ids = [normalize_identity(r, "PRIMARY_NO_GATE_K4", "results/bj151_gate_a_preoutcome_v1") for r in chosen_151]
    ids += [normalize_identity(r, "SECONDARY_ESP300_GM290_K8", "results/bj137_gate_a_preoutcome_v2") for r in chosen_137]
    roles = [normalize_role(r, "PRIMARY_NO_GATE_K4", "results/bj151_gate_a_preoutcome_v1") for r in roles_151 if (r["issue_instance"], r["portfolio_id"]) in selected_151]
    roles += [normalize_role(r, "SECONDARY_ESP300_GM290_K8", "results/bj137_gate_a_preoutcome_v2") for r in roles_137 if (r["issue_instance"], r["portfolio_id"]) in selected_137]
    if len(ids) != 3540 or len(roles) != 3540 * 7:
        raise RuntimeError("normalized asset denominator drift")
    return ids, roles


def freeze(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj145_gate_a_", dir=output.parent))
    try:
        cohort_151, cohort_137, chosen_151, chosen_137, manifest_151, manifest_137, manifest_148 = load_inputs()
        cohorts = make_cohorts(cohort_151, cohort_137)
        mechanisms = make_mechanisms()
        plans = make_plan(cohorts, mechanisms)
        ids_151_fields, identities_151 = read_gzip_csv(SOURCE_151 / "candidate_identities.csv.gz")
        roles_151_fields, roles_151 = read_gzip_csv(SOURCE_151 / "candidate_role_vectors.csv.gz")
        ids_137_fields, identities_137 = read_gzip_csv(SOURCE_137 / "n7_identities.csv.gz")
        roles_137_fields, roles_137 = read_gzip_csv(SOURCE_137 / "n7_role_vectors.csv.gz")
        identities, roles = normalize_assets(chosen_151, chosen_137, roles_151, roles_137)
        write_csv(stage / "selection_cohort.csv", COHORT_FIELDS, cohorts)
        write_csv(stage / "m_grid.csv", GRID_FIELDS, make_grid())
        write_gzip_csv(stage / "identity_catalog.csv.gz", IDENTITY_FIELDS, identities)
        write_gzip_csv(stage / "role_vectors.csv.gz", ROLE_FIELDS, roles)
        write_gzip_csv(stage / "allocation_plan.csv.gz", PLAN_FIELDS, plans)
        write_csv(stage / "mechanism_contract.csv", MECHANISM_FIELDS, mechanisms)
        shutil.copy2(ALLOCATION_ENGINE_SOURCE, stage / "bj145_allocation_engine.py")
        golden_vectors = make_golden_vectors()
        (stage / "allocation_golden_vectors.json").write_text(json.dumps(golden_vectors, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        allocation_binding = {
            "binding_version": "bj145-allocation-binding-v2",
            "module_file": "bj145_allocation_engine.py",
            "module_sha256": sha256(stage / "bj145_allocation_engine.py"),
            "golden_vectors_file": "allocation_golden_vectors.json",
            "golden_vectors_sha256": sha256(stage / "allocation_golden_vectors.json"),
            "engine_version": ENGINE_VERSION,
            "api": "allocate(mechanism, weights, M, seed, identity_signature, cap) -> integer multiplicities by #137 base-3 ticket ordinal",
            "mechanisms": list(ENGINE_MECHANISMS),
            "ticket_space": {"legs": 7, "outcomes_per_leg": 3, "k": FULL_TICKETS, "codes": ["3", "1", "0"], "ordinal_order": "#137 product order"},
            "identity_signature_rule": "exact selected_match_ids pipe string from frozen identity row; no portfolio_id substitution",
            "outcome_boundary": "executable allocation only; no outcome/final-SP/payout/ROI/tax input accepted",
        }
        (stage / "allocation_binding.json").write_text(json.dumps(allocation_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj151_gate_a_preoutcome_v1", "role": "fixed controlling #151 NO_GATE/K4 identities and Q vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_151_MANIFEST, "rows": 1356, "join_status": "all 348 #151 issue rows retained; 339 available and nine explicit no-bets"},
            {"source": "bj137_gate_a_preoutcome_v2", "role": "secondary ESP300_GM290/K8 sensitivity identities and vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_137_MANIFEST, "rows": 2184, "join_status": "all 348 K8 issue rows retained; 273 available and 75 explicit no-bets"},
            {"source": "bj148_gate_a_preoutcome_v1", "role": "historical dense-M namespace reference only; no outcomes read", "identity": "SHA256SUMS.json", "sha256": SOURCE_148_MANIFEST, "rows": 58, "join_status": "definition reference only"},
        ])
        card = {
            "issue": 145, "contract": CONTRACT, "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_TICKET_ALLOCATION_FREEZE",
            "sources": {"bj151_gate_a": {"manifest_sha256": SOURCE_151_MANIFEST, "role": "fixed primary NO_GATE/K4 candidate"}, "bj137_gate_a_v2": {"manifest_sha256": SOURCE_137_MANIFEST, "role": "secondary ESP300_GM290/K8 sensitivity"}, "bj148_gate_a": {"manifest_sha256": SOURCE_148_MANIFEST, "role": "dense-M definition reference only"}},
            "controlling_evidence": {"bj151_gate_b_terminal_reference": {"manifest_sha256": SOURCE_151_GATE_B_MANIFEST, "use": "contract amendment context only; no settled rows read"}, "bj154_independent_ev_reference": {"manifest_sha256": SOURCE_154_MANIFEST, "use": "contract amendment context only; no settled rows read"}},
            "selection_contract": {"primary": "exact #151 NO_GATE/K4 selected identities; no outcome reselection", "secondary": "exact #137 ESP300_GM290/K8 participation list only", "unit": "complete issue × gate × K; no issue segmentation", "no_bet": "retain NO_BET_K_UNSATISFIED with zero planned stake"},
            "weights": list(WEIGHT_SOURCES),
            "mechanisms": [row["mechanism"] for row in mechanisms],
            "allocation_binding": allocation_binding,
            "m_grid": list(M_GRID),
            "caps": list(CAPS),
            "seeds": list(SEEDS),
            "accounting": {"unit_stake_yuan": UNIT_STAKE_YUAN, "issue_stake": "selected_identity_count × M × ¥2", "tax_unit": "each ¥2 draw/repeat is a separate tax unit; no issue/policy pooling; tax is not computed at Gate A"},
            "allocation_contract": {"WR_DUPLICATE_STAKE": "independent weighted draws, exact duplicates retained", "WOR_DISTINCT": "weighted exponential-key distinct draws", "RESIDUAL_SYSTEMATIC": "Hamilton/largest remainder", "CAPPED_REPEAT": "Hamilton with caps 1/2/4/8", "DETERMINISTIC_TOP_MASS": "highest-weight distinct ticket codes", "FULL_ENUMERATED": "all 2187 tickets once"},
            "outcome_boundary": "No test outcome, score, final/winning SP, settlement, payout, ROI, tax realization, or post-kickoff input is read or emitted. Gate B is unauthorized.",
            "gate_b_requirements": {"authorization": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE", "primary_metric": "pre-tax no_tax_roi; tax-adjusted ROI secondary, calculated per winning ticket only", "required": ["mechanism-minus-mechanism at equal weight/M/stake", "FULL deltas", "duplicate multiplicity and coverage", "seed dispersion", "YEAR/FOLD/LOYO/issue bootstrap", "largest-issue exclusion and concentration", "multiple-comparison handling"]},
            "scope": "historical paper allocation research only; no purchase, production, betting, or promotion authority.",
            "denominator": {"cohort_rows": len(cohorts), "primary_available": 339, "primary_no_bet": 9, "secondary_available": 273, "secondary_no_bet": 75, "identity_rows": len(identities), "role_rows": len(roles), "allocation_plan_rows": len(plans), "m_points": len(M_GRID), "weight_sources": len(WEIGHT_SOURCES), "seed_count": len(SEEDS)},
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text("# #145 Gate A: calibrated ticket allocation freeze\n\nThis package freezes the accepted #151 fixed candidate, the contract-authorized #137 K8 sensitivity, six pre-result weight sources, and WR/WOR/residual/capped/FULL allocation rules. The manifest binds `bj145_allocation_engine.py` and its golden-vector fingerprints; Gate B must byte-verify this module and binding before settlement. It contains no outcome or settlement data. Every ¥2 repeat remains an individual future tax unit; no pooled tax is computed. Replay with `python3 freeze_runner.py --output <new-dir>`; staging remains under `results/`, never `/tmp`. Gate B requires PI authorization.\n", encoding="utf-8")
        compressed = ("identity_catalog.csv.gz", "role_vectors.csv.gz", "allocation_plan.csv.gz")
        content = {"contract_version": CONTENT_VERSION, "gzip_payloads": {name: {"canonical_decompressed_sha256": _decompressed_sha256(stage / name)} for name in compressed}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "counts": card["denominator"]}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _decompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
