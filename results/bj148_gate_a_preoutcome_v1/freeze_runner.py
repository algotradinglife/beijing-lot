#!/usr/bin/env python3
"""Freeze #148's dense N7 M-grid sampling surface without outcomes.

The package intersects the accepted #137 complete-issue NO_GATE/K_ALL
universe with #133's frozen, rank-32 candidate catalogue.  It deliberately
reads no result, final SP, payout, tax, settlement, or ROI data.  Ticket draws
are represented as a deterministic replay plan rather than materialised: Gate
B alone may consume the fixed role vectors and this plan after PI approval.
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


CONTRACT = "BJ-HIST-N7-M-GRID-001"
VERSION = "bj148-gate-a-v1"
CONTENT_VERSION = "bj148-gate-a-content-v1"
FULL_TICKETS = 3**7
UNIT_STAKE_YUAN = 2
SEEDS = ("133001", "133002", "133003")
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
SOURCE_133_MANIFEST = "1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79"


def dense_m_grid() -> tuple[int, ...]:
    """Return the exact grid written in the #148 issue contract."""
    values = tuple(range(16, 513, 16)) + tuple(range(576, 1025, 64)) + tuple(range(1088, 2113, 64)) + (FULL_TICKETS,)
    if len(values) != 58 or values[-1] != FULL_TICKETS or len(set(values)) != len(values):
        raise RuntimeError("dense M-grid contract drift")
    if any(value <= 0 or value > FULL_TICKETS for value in values):
        raise RuntimeError("M-grid outside N7 ticket space")
    return values


M_GRID = dense_m_grid()
SAMPLED_M = tuple(value for value in M_GRID if value != FULL_TICKETS)

COHORT_FIELDS = (
    "issue", "fold", "year", "issue_instance", "eligible_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "source_segment_count", "issue_disposition", "fold_integrity", "selection_scope", "gate_id", "top_k_id",
    "source_disposition", "source_reason", "candidate_identity_count", "selected_identity_count",
    "selected_portfolio_ids", "selected_portfolio_ids_sha256", "full_ticket_count_per_identity",
    "full_issue_draw_count", "full_issue_stake_yuan", "common_support_status", "common_support_reason",
    "outcome_boundary",
)
GRID_FIELDS = (
    "grid_ordinal", "M", "grid_band", "is_full_control", "WR_plan_count", "WOR_plan_count", "full_plan_count",
    "ticket_space_k", "per_identity_stake_yuan", "outcome_boundary",
)
PLAN_FIELDS = (
    "plan_id", "sampling_role", "ticket_mechanism", "duplicate_policy", "gate_id", "issue", "fold", "year",
    "issue_instance", "selection_status", "reason", "candidate_identity_count", "selected_portfolio_ids_sha256",
    "M", "seed", "seed_role", "ticket_space_k", "planned_draw_count", "planned_stake_yuan",
    "expected_unique_formula", "realized_unique_rule", "outcome_boundary",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_133 = ROOT / "results" / "bj133_gate_a_preoutcome_v1"
OUTPUT = ROOT / "results" / "bj148_gate_a_preoutcome_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def verified_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted source manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def read_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    if not fields or not rows:
        raise RuntimeError(f"empty source CSV: {path}")
    return fields, rows


def read_gzip_csv(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)
    if not fields or not rows:
        raise RuntimeError(f"empty source gzip CSV: {path}")
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


def band_for(m_value: int) -> str:
    if m_value == FULL_TICKETS:
        return "FULL"
    if m_value <= 512:
        return "DENSE_16"
    if m_value <= 1024:
        return "DENSE_64_MID"
    return "DENSE_64_HIGH"


def issue_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["issue"], row["fold"], row["year"], row["issue_instance"]


def catalogue_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["issue"], row["fold"], row["year"], row["portfolio_id"]


def assert_source_cards(source_137: Path, source_133: Path) -> None:
    card_137 = json.loads((source_137 / "gate_a_card.json").read_text(encoding="utf-8"))
    card_133 = json.loads((source_133 / "gate_a_card.json").read_text(encoding="utf-8"))
    if card_137.get("contract") != "BJ-HIST-PROB-SAMPLING-N7-001" or card_137.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_SAMPLING_FREEZE":
        raise RuntimeError("#137 source card is not the accepted outcome-unexposed sampling freeze")
    if card_133.get("contract") != "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001" or card_133.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_DIVERSIFIED_ALLOCATION_FREEZE":
        raise RuntimeError("#133 source card is not the accepted outcome-unexposed allocation freeze")


def load_common_support(source_137: Path, source_133: Path) -> tuple[
    dict[str, str], dict[str, str], tuple[str, ...], list[dict[str, str]], tuple[str, ...], list[dict[str, str]], list[dict[str, str]]
]:
    manifest_137 = verified_bundle(source_137, SOURCE_137_MANIFEST)
    manifest_133 = verified_bundle(source_133, SOURCE_133_MANIFEST)
    assert_source_cards(source_137, source_133)

    participation_fields, participation = read_csv(source_137 / "issue_participation_grid.csv")
    required_participation = {"issue", "fold", "year", "issue_instance", "gate_id", "top_k_id", "available_identity_count", "selected_identity_count", "disposition", "reason"}
    if not required_participation <= set(participation_fields):
        raise RuntimeError("#137 participation schema lacks complete-issue universe")
    universe = [row for row in participation if row["gate_id"] == "NO_GATE" and row["top_k_id"] == "K_ALL"]
    if len(universe) != 348 or len({issue_key(row) for row in universe}) != 348:
        raise RuntimeError("#137 NO_GATE/K_ALL common issue universe drift")

    identity_fields, identities_all = read_gzip_csv(source_133 / "candidate_identity_catalog.csv.gz")
    role_fields, roles_all = read_gzip_csv(source_133 / "candidate_role_vectors.csv.gz")
    required_identity = {"gate_id", "issue", "fold", "year", "portfolio_id", "candidate_rank_in_complete_issue", "selected_match_ids"}
    required_role = {"gate_id", "issue", "fold", "year", "portfolio_id", "match_id", "selection_rank", "q_weight3", "q_weight1", "q_weight0"}
    if not required_identity <= set(identity_fields) or not required_role <= set(role_fields):
        raise RuntimeError("#133 candidate source schema lacks Q-weight identity support")
    identities = [row for row in identities_all if row["gate_id"] == "NO_GATE"]
    if len(identities) != 8_550 or len({catalogue_key(row) for row in identities}) != len(identities):
        raise RuntimeError("#133 NO_GATE candidate identity cardinality drift")
    by_issue: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in identities:
        by_issue[issue_key(row)].append(row)
    for rows in by_issue.values():
        rows.sort(key=lambda row: (int(row["candidate_rank_in_complete_issue"]), row["portfolio_id"]))
        ranks = [int(row["candidate_rank_in_complete_issue"]) for row in rows]
        # #137 first ranks candidate matches before duplicate N7 identities
        # collapse.  The inherited identity ranks can therefore have gaps
        # (for example 1,8..32), but must remain strictly ordered and within
        # the frozen rank-32 search boundary.
        if ranks != sorted(set(ranks)) or not ranks or ranks[-1] > 32:
            raise RuntimeError("#133 inherited candidate-rank surface drift")
    available = [row for row in universe if row["disposition"] == "AVAILABLE"]
    if len(available) != 343 or len(by_issue) != len(available):
        raise RuntimeError("#137/#133 common-support availability drift")
    for row in universe:
        candidates = by_issue.get(issue_key(row), [])
        if row["disposition"] == "AVAILABLE":
            if len(candidates) != int(row["available_identity_count"]) or int(row["selected_identity_count"]) != len(candidates):
                raise RuntimeError("#137 K_ALL and #133 candidate pool differ")
        elif candidates or row["disposition"] != "NO_BET":
            raise RuntimeError("unexpected common-support no-bet state")
    allowed = {catalogue_key(row) for row in identities}
    roles = [row for row in roles_all if row["gate_id"] == "NO_GATE" and catalogue_key(row) in allowed]
    role_keys = {(row["issue"], row["fold"], row["year"], row["portfolio_id"]) for row in roles}
    if role_keys != allowed or len(roles) != len(identities) * 7:
        raise RuntimeError("#133 NO_GATE role coverage drift")
    for key, count in Counter((row["issue"], row["fold"], row["year"], row["portfolio_id"]) for row in roles).items():
        if count != 7:
            raise RuntimeError(f"role count drift for {key}")
    return manifest_137, manifest_133, identity_fields, identities, role_fields, roles, sorted(universe, key=lambda row: (int(row["year"]), int(row["issue"]), row["fold"]))


def make_cohort(universe: list[dict[str, str]], identities: list[dict[str, str]]) -> list[dict[str, object]]:
    by_issue: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in identities:
        by_issue[issue_key(row)].append(row)
    for rows in by_issue.values():
        rows.sort(key=lambda row: (int(row["candidate_rank_in_complete_issue"]), row["portfolio_id"]))
    output: list[dict[str, object]] = []
    for row in universe:
        candidates = by_issue.get(issue_key(row), [])
        ids = [candidate["portfolio_id"] for candidate in candidates]
        status = "AVAILABLE" if candidates else "NO_BET_SOURCE_POOL_EMPTY"
        output.append({
            "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"],
            "eligible_match_count": row["eligible_match_count"], "first_kickoff_ts": row["first_kickoff_ts"], "last_kickoff_ts": row["last_kickoff_ts"],
            "source_segment_count": row["source_segment_count"], "issue_disposition": row["issue_disposition"], "fold_integrity": row["fold_integrity"], "selection_scope": row["selection_scope"],
            "gate_id": "NO_GATE", "top_k_id": "K_ALL", "source_disposition": row["disposition"], "source_reason": row["reason"],
            "candidate_identity_count": len(ids), "selected_identity_count": len(ids), "selected_portfolio_ids": "|".join(ids),
            "selected_portfolio_ids_sha256": compact_hash(ids), "full_ticket_count_per_identity": FULL_TICKETS,
            "full_issue_draw_count": len(ids) * FULL_TICKETS, "full_issue_stake_yuan": len(ids) * FULL_TICKETS * UNIT_STAKE_YUAN,
            "common_support_status": status, "common_support_reason": "ALL_INHERITED_RANK32_IDENTITIES" if candidates else "NO_GATE_A_CANDIDATE_POOL",
            "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
        })
    if len(output) != 348 or sum(int(row["selected_identity_count"]) for row in output) != 8_550:
        raise RuntimeError("common-support cohort denominator drift")
    return output


def make_grid_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ordinal, m_value in enumerate(M_GRID, start=1):
        full = m_value == FULL_TICKETS
        rows.append({
            "grid_ordinal": ordinal, "M": m_value, "grid_band": band_for(m_value), "is_full_control": str(full).lower(),
            "WR_plan_count": 0 if full else len(SEEDS), "WOR_plan_count": 0 if full else len(SEEDS), "full_plan_count": 1 if full else 0,
            "ticket_space_k": FULL_TICKETS, "per_identity_stake_yuan": m_value * UNIT_STAKE_YUAN,
            "outcome_boundary": "pre-outcome sampler specification only",
        })
    if len(rows) != 58:
        raise RuntimeError("M-grid row count drift")
    return rows


def make_sampling_plan(cohort: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for sample in cohort:
        count = int(sample["selected_identity_count"])
        available = sample["common_support_status"] == "AVAILABLE"
        for m_value in SAMPLED_M:
            for role, mechanism, duplicate_policy in (
                ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE", "EACH_INDEPENDENT_DRAW_IS_A_SEPARATE_Y2_TICKET_AND_TAX_UNIT"),
                ("SENSITIVITY_WOR_DISTINCT", "Q_INFORMED_WOR_DISTINCT", "DRAWS_ARE_DISTINCT_WITHIN_EACH_IDENTITY"),
            ):
                for seed in SEEDS:
                    rows.append({
                        "plan_id": compact_hash([CONTRACT, sample["issue_instance"], role, m_value, seed]), "sampling_role": role,
                        "ticket_mechanism": mechanism, "duplicate_policy": duplicate_policy, "gate_id": "NO_GATE",
                        "issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": sample["issue_instance"],
                        "selection_status": "AVAILABLE" if available else "NO_BET_SOURCE_POOL_EMPTY", "reason": sample["common_support_reason"],
                        "candidate_identity_count": count, "selected_portfolio_ids_sha256": sample["selected_portfolio_ids_sha256"], "M": m_value,
                        "seed": seed, "seed_role": "PRIMARY" if seed == SEEDS[0] else "SENSITIVITY", "ticket_space_k": FULL_TICKETS,
                        "planned_draw_count": count * m_value if available else 0, "planned_stake_yuan": count * m_value * UNIT_STAKE_YUAN if available else 0,
                        "expected_unique_formula": "sum_t[1-(1-q(t))^M] per identity" if mechanism.endswith("DUPLICATE_STAKE") else "M distinct tickets per identity",
                        "realized_unique_rule": "retain every independent draw including exact duplicates" if mechanism.endswith("DUPLICATE_STAKE") else "each identity has exactly M distinct tickets",
                        "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
                    })
        rows.append({
            "plan_id": compact_hash([CONTRACT, sample["issue_instance"], "FULL_ENUMERATED", FULL_TICKETS, "NA"]), "sampling_role": "FULL_ECONOMIC_CONTROL",
            "ticket_mechanism": "FULL_ENUMERATED", "duplicate_policy": "ALL_2187_DISTINCT_TICKETS", "gate_id": "NO_GATE",
            "issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": sample["issue_instance"],
            "selection_status": "AVAILABLE" if available else "NO_BET_SOURCE_POOL_EMPTY", "reason": sample["common_support_reason"],
            "candidate_identity_count": count, "selected_portfolio_ids_sha256": sample["selected_portfolio_ids_sha256"], "M": FULL_TICKETS,
            "seed": "NA", "seed_role": "CONTROL", "ticket_space_k": FULL_TICKETS,
            "planned_draw_count": count * FULL_TICKETS if available else 0, "planned_stake_yuan": count * FULL_TICKETS * UNIT_STAKE_YUAN if available else 0,
            "expected_unique_formula": "2187 distinct tickets per identity", "realized_unique_rule": "all tickets in each identity's 3^7 space",
            "outcome_boundary": "No outcome/final-SP/payout/ROI/tax data read or emitted",
        })
    rows.sort(key=lambda row: (int(str(row["year"])), int(str(row["issue"])), str(row["sampling_role"]), int(str(row["M"])), str(row["seed"])))
    expected = len(cohort) * (len(SAMPLED_M) * 2 * len(SEEDS) + 1)
    if len(rows) != expected or expected != 119_364:
        raise RuntimeError("dense M-grid plan denominator drift")
    if len({str(row["plan_id"]) for row in rows}) != len(rows):
        raise RuntimeError("dense M-grid plan identity collision")
    return rows


def freeze(output: Path, source_137: Path = SOURCE_137, source_133: Path = SOURCE_133) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj148_gate_a_", dir=output.parent))
    try:
        manifest_137, manifest_133, identity_fields, identities, role_fields, roles, universe = load_common_support(source_137, source_133)
        cohort = make_cohort(universe, identities)
        grid_rows = make_grid_rows()
        plan = make_sampling_plan(cohort)
        write_csv(stage / "common_support_cohort.csv", COHORT_FIELDS, cohort)
        write_csv(stage / "dense_m_grid.csv", GRID_FIELDS, grid_rows)
        write_csv(stage / "sampling_plan.csv", PLAN_FIELDS, plan)
        write_gzip_csv(stage / "common_support_identities.csv.gz", identity_fields, identities)
        write_gzip_csv(stage / "common_support_role_vectors.csv.gz", role_fields, roles)
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj137_gate_a_preoutcome_v2", "role": "accepted outcome-unexposed complete-issue NO_GATE/K_ALL universe", "identity": "SHA256SUMS.json", "sha256": SOURCE_137_MANIFEST, "rows": len(universe), "join_status": "all 348 complete issues retained; five explicit source NO_BET rows preserved"},
            {"source": "bj133_gate_a_preoutcome_v1", "role": "accepted outcome-unexposed inherited rank-32 candidate identities and calibrated Q-weight role vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_133_MANIFEST, "rows": len(identities), "join_status": "NO_GATE only; all 8,550 common-support identities retained with no K or stake cap"},
        ])
        card = {
            "issue": 148,
            "contract": CONTRACT,
            "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_DENSE_M_GRID_COMMON_SUPPORT_FREEZE",
            "sources": {
                "bj137_gate_a_v2": {"manifest_sha256": SOURCE_137_MANIFEST, "content_identity_sha256": manifest_137["CONTENT_IDENTITY.json"], "issue_universe_payload_sha256": manifest_137["issue_participation_grid.csv"]},
                "bj133_gate_a_v1": {"manifest_sha256": SOURCE_133_MANIFEST, "content_identity_sha256": manifest_133["CONTENT_IDENTITY.json"], "identity_payload_sha256": manifest_133["candidate_identity_catalog.csv.gz"], "role_payload_sha256": manifest_133["candidate_role_vectors.csv.gz"]},
            },
            "complete_issue_contract": {
                "primary_unit": "complete (issue, fold) lottery issue; source segments are diagnostic-only",
                "common_support": "#137 NO_GATE/K_ALL complete-issue universe intersected with #133 NO_GATE inherited deterministic rank-32 candidate catalogue",
                "identity_inclusion": "every inherited common-support identity is included for an AVAILABLE issue; no K, allocator, or issue-stake cap is applied",
                "no_bet": "all five #137 NO_GATE/K_ALL source no-bet issues remain explicit zero-stake rows at every M and arm",
            },
            "sampling_contract": {
                "probability_vector": "frozen #133 Q_WEIGHT three-way vector per N7 leg",
                "wr_primary": "Q_INFORMED_WR_DUPLICATE_STAKE: M independent draws per identity, each draw is a separate ¥2 ticket even if duplicate",
                "wor_sensitivity": "Q_INFORMED_WOR_DISTINCT: M distinct Q-weighted tickets per identity",
                "full_control": "M=2187 is FULL_ENUMERATED exactly once per issue; it is not a with-replacement draw",
                "seeds": list(SEEDS),
                "dense_m_grid": list(M_GRID),
            },
            "metrics_frozen_for_gate_b": [
                "no_tax_roi primary and tax_adjusted_roi reference", "complete-issue hit rate and ticket coverage", "mean/P50/P90/P95/max issue stake; total stake and capital utilization",
                "duplicate ticket ratio and unique-ticket coverage", "matched deltas versus FULL for ROI/hit/stake", "YEAR/FOLD/LOYO and issue bootstrap",
                "full WR M curve is primary; WOR is a sensitivity; no single M or seed can nominate a policy",
            ],
            "outcome_boundary": "No test outcome, score, final/winning SP, settlement, payout, ROI, tax realization, or post-kickoff input is read or emitted.",
            "gate_b_requirements": {"authorization": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE", "promotion": "No historical result authorizes purchase, production, betting, or promotion. Any apparent positive region requires separate strict independent EV review and validation."},
            "scope": "historical paper research only; no purchase, production, betting, or promotion authority.",
            "denominator": {"complete_issue_rows": len(cohort), "available_issue_rows": sum(row["common_support_status"] == "AVAILABLE" for row in cohort), "no_bet_issue_rows": sum(row["common_support_status"] != "AVAILABLE" for row in cohort), "common_support_identities": len(identities), "common_support_role_rows": len(roles), "dense_m_points": len(M_GRID), "sampled_m_points": len(SAMPLED_M), "seed_count": len(SEEDS), "sampling_plan_rows": len(plan)},
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text(
            "# #148 Gate A: dense N7 M-grid common-support freeze\n\n"
            "This immutable outcome-unexposed package freezes the #137/#133 NO_GATE common-support cohort, all inherited candidate identities, calibrated Q-weight role vectors, dense M grid, and WR/WOR/FULL replay plans. "
            "It contains no settlement input and cannot report ROI. Replay with `python3 freeze_runner.py --output <new-dir>`; staging is beside the requested output, never in `/tmp`.\n",
            encoding="utf-8",
        )
        content = {
            "contract_version": CONTENT_VERSION,
            "gzip_payloads": {name: {"canonical_decompressed_sha256": hashlib.sha256(gzip.open(stage / name, "rb").read()).hexdigest()} for name in ("common_support_identities.csv.gz", "common_support_role_vectors.csv.gz")},
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in {"common_support_identities.csv.gz", "common_support_role_vectors.csv.gz"}},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "complete_issue_rows": len(cohort), "common_support_identities": len(identities), "dense_m_points": len(M_GRID), "sampling_plan_rows": len(plan)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--source-137", type=Path, default=SOURCE_137)
    parser.add_argument("--source-133", type=Path, default=SOURCE_133)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve(), args.source_137.resolve(), args.source_133.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
