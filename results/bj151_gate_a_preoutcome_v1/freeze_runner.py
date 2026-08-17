#!/usr/bin/env python3
"""Freeze #151's fixed #137 candidate across the #148 dense M grid.

This outcome-unexposed generator binds only the accepted #137 Gate-A v2
`NO_GATE/K4` selected identities and their frozen Q vectors.  It deliberately
does not inspect any #137 or #148 settlement output: Gate B is the sole place
where final outcomes can be joined after PI authorization.
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


CONTRACT = "BJ-HIST-N7-CANDIDATE-REPRO-001"
VERSION = "bj151-gate-a-v1"
CONTENT_VERSION = "bj151-gate-a-content-v1"
FULL_TICKETS = 3 ** 7
UNIT_STAKE_YUAN = 2
SEEDS = ("137001", "137002", "137003")
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
SOURCE_148_GATE_A_MANIFEST = "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6"


def dense_m_grid() -> tuple[int, ...]:
    values = tuple(range(16, 513, 16)) + tuple(range(576, 1025, 64)) + tuple(range(1088, 2113, 64)) + (FULL_TICKETS,)
    if len(values) != 58 or len(set(values)) != 58 or values[-1] != FULL_TICKETS:
        raise RuntimeError("dense M grid contract drift")
    return values


M_GRID = dense_m_grid()
SAMPLED_M = tuple(value for value in M_GRID if value != FULL_TICKETS)
COHORT_FIELDS = (
    "issue", "fold", "year", "issue_instance", "gate_id", "top_k_id", "source_disposition", "source_reason",
    "selection_status", "selected_identity_count", "selected_portfolio_ids", "selected_portfolio_ids_sha256",
    "full_ticket_count_per_identity", "full_issue_draw_count", "full_issue_stake_yuan", "candidate_definition",
    "outcome_boundary",
)
GRID_FIELDS = ("grid_ordinal", "M", "grid_band", "is_full_control", "WR_plan_count", "WOR_plan_count", "full_plan_count", "ticket_space_k", "outcome_boundary")
PLAN_FIELDS = (
    "plan_id", "sampling_role", "ticket_mechanism", "duplicate_policy", "gate_id", "top_k_id", "issue", "fold", "year",
    "issue_instance", "selection_status", "reason", "candidate_identity_count", "selected_portfolio_ids_sha256", "M", "seed",
    "seed_role", "ticket_space_k", "planned_draw_count", "planned_stake_yuan", "expected_unique_formula", "realized_unique_rule", "outcome_boundary",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_148 = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
OUTPUT = ROOT / "results" / "bj151_gate_a_preoutcome_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def verified_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted source manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


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


def identity_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["issue"], row["fold"], row["year"], row["portfolio_id"]


def band_for(m_value: int) -> str:
    if m_value == FULL_TICKETS:
        return "FULL"
    if m_value <= 512:
        return "DENSE_16"
    if m_value <= 1024:
        return "DENSE_64_MID"
    return "DENSE_64_HIGH"


def load_candidate(source_137: Path, source_148: Path) -> tuple[dict[str, str], dict[str, str], tuple[str, ...], list[dict[str, str]], tuple[str, ...], list[dict[str, str]], list[dict[str, str]]]:
    manifest_137 = verified_bundle(source_137, SOURCE_137_MANIFEST)
    manifest_148 = verified_bundle(source_148, SOURCE_148_GATE_A_MANIFEST)
    card = json.loads((source_137 / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_SAMPLING_FREEZE":
        raise RuntimeError("#137 is not its accepted Gate-A v2 freeze")
    part_fields, participation = read_csv(source_137 / "issue_participation_grid.csv")
    required = {"issue", "fold", "year", "issue_instance", "gate_id", "top_k_id", "selected_portfolio_ids", "selected_identity_count", "disposition", "reason"}
    if not required <= set(part_fields):
        raise RuntimeError("#137 participation schema drift")
    cohort = [row for row in participation if row["gate_id"] == "NO_GATE" and row["top_k_id"] == "K4"]
    if len(cohort) != 348 or len({issue_key(row) for row in cohort}) != 348:
        raise RuntimeError("#137 fixed candidate issue cohort drift")
    if Counter(row["disposition"] for row in cohort) != {"AVAILABLE": 339, "NO_BET": 9}:
        raise RuntimeError("#137 K4 availability drift")
    identity_fields, all_identities = read_gzip_csv(source_137 / "n7_identities.csv.gz")
    role_fields, all_roles = read_gzip_csv(source_137 / "n7_role_vectors.csv.gz")
    selected_by_issue = {issue_key(row): tuple(filter(None, row["selected_portfolio_ids"].split("|"))) for row in cohort}
    selected = {(issue, fold, year, portfolio_id) for (issue, fold, year, _), ids in selected_by_issue.items() for portfolio_id in ids}
    identities = [row for row in all_identities if row["gate_id"] == "NO_GATE" and identity_key(row) in selected]
    roles = [row for row in all_roles if row["gate_id"] == "NO_GATE" and identity_key(row) in selected]
    if len(identities) != 1_356 or len(selected) != len(identities) or len(roles) != 1_356 * 7:
        raise RuntimeError("#137 fixed K4 identity/role coverage drift")
    if set(Counter(identity_key(row) for row in roles).values()) != {7}:
        raise RuntimeError("#137 K4 role-vector cardinality drift")
    return manifest_137, manifest_148, identity_fields, identities, role_fields, roles, sorted(cohort, key=lambda row: (int(row["year"]), int(row["issue"]), row["fold"]))


def make_cohort(source_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in source_rows:
        ids = tuple(filter(None, row["selected_portfolio_ids"].split("|")))
        available = row["disposition"] == "AVAILABLE"
        if (available and len(ids) != 4) or (not available and ids):
            raise RuntimeError("fixed K4 selection membership drift")
        result.append({
            "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"],
            "gate_id": "NO_GATE", "top_k_id": "K4", "source_disposition": row["disposition"], "source_reason": row["reason"],
            "selection_status": "AVAILABLE" if available else "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES", "selected_identity_count": len(ids),
            "selected_portfolio_ids": "|".join(ids), "selected_portfolio_ids_sha256": compact_hash(ids), "full_ticket_count_per_identity": FULL_TICKETS,
            "full_issue_draw_count": len(ids) * FULL_TICKETS, "full_issue_stake_yuan": len(ids) * FULL_TICKETS * UNIT_STAKE_YUAN,
            "candidate_definition": "#137 Gate-A v2 NO_GATE/K4 selected identities; no outcome re-selection", "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
        })
    if len(result) != 348 or sum(int(row["selected_identity_count"]) for row in result) != 1_356:
        raise RuntimeError("#151 cohort denominator drift")
    return result


def make_grid() -> list[dict[str, object]]:
    return [{"grid_ordinal": ordinal, "M": value, "grid_band": band_for(value), "is_full_control": str(value == FULL_TICKETS).lower(), "WR_plan_count": 0 if value == FULL_TICKETS else len(SEEDS), "WOR_plan_count": 0 if value == FULL_TICKETS else len(SEEDS), "full_plan_count": int(value == FULL_TICKETS), "ticket_space_k": FULL_TICKETS, "outcome_boundary": "pre-outcome sampler specification only"} for ordinal, value in enumerate(M_GRID, 1)]


def make_plan(cohort: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample in cohort:
        count, available = int(sample["selected_identity_count"]), sample["selection_status"] == "AVAILABLE"
        for m_value in SAMPLED_M:
            for role, mechanism, duplicate_policy in (("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE", "EACH_INDEPENDENT_DRAW_IS_A_SEPARATE_Y2_TICKET_AND_TAX_UNIT"), ("SENSITIVITY_WOR_FIXED_CANDIDATE", "Q_INFORMED_WOR_DISTINCT", "DRAWS_ARE_DISTINCT_WITHIN_EACH_IDENTITY")):
                for seed in SEEDS:
                    rows.append({"plan_id": compact_hash([CONTRACT, sample["issue_instance"], role, m_value, seed]), "sampling_role": role, "ticket_mechanism": mechanism, "duplicate_policy": duplicate_policy, "gate_id": "NO_GATE", "top_k_id": "K4", "issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": sample["issue_instance"], "selection_status": sample["selection_status"], "reason": sample["source_reason"], "candidate_identity_count": count, "selected_portfolio_ids_sha256": sample["selected_portfolio_ids_sha256"], "M": m_value, "seed": seed, "seed_role": "PRIMARY" if seed == SEEDS[0] else "SENSITIVITY", "ticket_space_k": FULL_TICKETS, "planned_draw_count": count * m_value if available else 0, "planned_stake_yuan": count * m_value * UNIT_STAKE_YUAN if available else 0, "expected_unique_formula": "sum_t[1-(1-q(t))^M] per identity" if mechanism.endswith("DUPLICATE_STAKE") else "M distinct tickets per identity", "realized_unique_rule": "retain every independent draw including exact duplicates" if mechanism.endswith("DUPLICATE_STAKE") else "each identity has exactly M distinct tickets", "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted"})
        rows.append({"plan_id": compact_hash([CONTRACT, sample["issue_instance"], "FULL_ENUMERATED", FULL_TICKETS]), "sampling_role": "FULL_ECONOMIC_CONTROL", "ticket_mechanism": "FULL_ENUMERATED", "duplicate_policy": "ALL_2187_DISTINCT_TICKETS", "gate_id": "NO_GATE", "top_k_id": "K4", "issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": sample["issue_instance"], "selection_status": sample["selection_status"], "reason": sample["source_reason"], "candidate_identity_count": count, "selected_portfolio_ids_sha256": sample["selected_portfolio_ids_sha256"], "M": FULL_TICKETS, "seed": "NA", "seed_role": "CONTROL", "ticket_space_k": FULL_TICKETS, "planned_draw_count": count * FULL_TICKETS if available else 0, "planned_stake_yuan": count * FULL_TICKETS * UNIT_STAKE_YUAN if available else 0, "expected_unique_formula": "2187 distinct tickets per identity", "realized_unique_rule": "all tickets in each identity's 3^7 space", "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted"})
    rows.sort(key=lambda row: (int(str(row["year"])), int(str(row["issue"])), str(row["sampling_role"]), int(str(row["M"])), str(row["seed"])))
    expected = len(cohort) * (len(SAMPLED_M) * 2 * len(SEEDS) + 1)
    if len(rows) != expected or expected != 119_364 or len({str(row["plan_id"]) for row in rows}) != len(rows):
        raise RuntimeError("#151 plan denominator or identity drift")
    return rows


def freeze(output: Path, source_137: Path = SOURCE_137, source_148: Path = SOURCE_148) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj151_gate_a_", dir=output.parent))
    try:
        manifest_137, manifest_148, identity_fields, identities, role_fields, roles, source_rows = load_candidate(source_137, source_148)
        cohort, grid, plan = make_cohort(source_rows), make_grid(), None
        plan = make_plan(cohort)
        write_csv(stage / "candidate_cohort.csv", COHORT_FIELDS, cohort)
        write_csv(stage / "dense_m_grid.csv", GRID_FIELDS, grid)
        write_csv(stage / "sampling_plan.csv", PLAN_FIELDS, plan)
        write_gzip_csv(stage / "candidate_identities.csv.gz", identity_fields, identities)
        write_gzip_csv(stage / "candidate_role_vectors.csv.gz", role_fields, roles)
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj137_gate_a_preoutcome_v2", "role": "accepted fixed candidate definition: NO_GATE/K4 identities and Q vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_137_MANIFEST, "rows": len(identities), "join_status": "all 348 source K4 rows retained; nine explicit insufficient-identity no-bets preserved"},
            {"source": "bj148_gate_a_preoutcome_v1", "role": "accepted broader-pool dense-M comparator definition only; no settlement data read at Gate A", "identity": "SHA256SUMS.json", "sha256": SOURCE_148_GATE_A_MANIFEST, "rows": 58, "join_status": "identical dense M grid bound for Gate-B side-by-side reporting"},
        ])
        card = {"issue": 151, "contract": CONTRACT, "generator_version": VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_FIXED_CANDIDATE_DENSE_M_FREEZE", "sources": {"bj137_gate_a_v2": {"manifest_sha256": SOURCE_137_MANIFEST, "content_identity_sha256": manifest_137["CONTENT_IDENTITY.json"], "participation_payload_sha256": manifest_137["issue_participation_grid.csv"], "identity_payload_sha256": manifest_137["n7_identities.csv.gz"], "role_payload_sha256": manifest_137["n7_role_vectors.csv.gz"]}, "bj148_gate_a_v1": {"manifest_sha256": SOURCE_148_GATE_A_MANIFEST, "content_identity_sha256": manifest_148["CONTENT_IDENTITY.json"], "role": "broader-pool comparator definition only"}}, "fixed_candidate": {"gate_id": "NO_GATE", "top_k_id": "K4", "sampler_id": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT", "historical_reference_M": 64, "historical_reference_seeds": list(SEEDS), "identity_rule": "exact #137 Gate-A v2 selected_portfolio_ids; no outcome-directed selection, parameter scan, or candidate-pool expansion"}, "sampling_contract": {"dense_m_grid": list(M_GRID), "wr_primary": "Q_INFORMED_WR_DUPLICATE_STAKE with the fixed #137 Q_WEIGHT vector", "wor_sensitivity": "Q_INFORMED_WOR_DISTINCT with the fixed #137 Q_WEIGHT vector", "full_control": "M=2187 exact enumeration per selected identity", "seeds": list(SEEDS)}, "comparison_contract": {"broader_pool": "#148 Gate-A common-support/K_ALL definition; its settled surface is joined only at Gate B", "comparison": "report side-by-side candidate and #148 broader-pool M curves without altering the candidate's identities, vectors, seeds, or draw plan"}, "metrics_frozen_for_gate_b": ["no_tax_roi primary; tax-adjusted ROI secondary", "candidate ROI, matched K4 FULL ROI, and candidate-minus-FULL deltas", "side-by-side #148 broader-pool M curve", "three seeds, YEAR/FOLD/LOYO and issue bootstrap", "issue stake distribution, duplicate rate, unique coverage, concentration, largest-issue sensitivity"], "outcome_boundary": "No test outcome, score, final/winning SP, settlement, payout, ROI, tax realization, or post-kickoff input is read or emitted.", "gate_b_requirements": {"authorization": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE", "promotion": "No historical result authorizes purchase, production, betting, or promotion. A stable positive first requires separate strict independent EV."}, "scope": "historical paper research only; no purchase, production, betting, or promotion authority.", "denominator": {"complete_issue_rows": len(cohort), "available_issue_rows": sum(row["selection_status"] == "AVAILABLE" for row in cohort), "no_bet_issue_rows": sum(row["selection_status"] != "AVAILABLE" for row in cohort), "fixed_candidate_identities": len(identities), "fixed_candidate_role_rows": len(roles), "dense_m_points": len(M_GRID), "sampled_m_points": len(SAMPLED_M), "seed_count": len(SEEDS), "sampling_plan_rows": len(plan)}}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text("# #151 Gate A: fixed #137 candidate dense-M reproduction freeze\n\nThis immutable outcome-unexposed package contains only #137 Gate-A v2 `NO_GATE/K4` selected identities, their Q vectors, the #148-aligned M grid, and WR/WOR/FULL replay plans. It has no outcome data. Replay with `python3 freeze_runner.py --output <new-dir>`; staging is beside the requested output, never in `/tmp`.\n", encoding="utf-8")
        content = {"contract_version": CONTENT_VERSION, "gzip_payloads": {name: {"canonical_decompressed_sha256": hashlib.sha256(gzip.open(stage / name, "rb").read()).hexdigest()} for name in ("candidate_identities.csv.gz", "candidate_role_vectors.csv.gz")}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in {"candidate_identities.csv.gz", "candidate_role_vectors.csv.gz"}}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "complete_issue_rows": len(cohort), "fixed_candidate_identities": len(identities), "sampling_plan_rows": len(plan)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--source-137", type=Path, default=SOURCE_137)
    parser.add_argument("--source-148", type=Path, default=SOURCE_148)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve(), args.source_137.resolve(), args.source_148.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
