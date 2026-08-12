#!/usr/bin/env python3
"""Freeze #107's terminal all-NO_BET issue/pool gate without reading outcomes.

#106's accepted terminal card contains no promoted value strata.  This runner
does not reinterpret the atlas or substitute another signal.  It verifies the
accepted boundaries, copies #101's complete outcome-unexposed pool denominator,
and emits one explicit no-bet decision for every official issue/pool.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


ROOT = repo_root(Path(__file__))
ATLAS_GATE_A = ROOT / "results" / "bj106_gate_a_preoutcome_v2r1"
ATLAS_GATE_B = ROOT / "results" / "bj106_gate_b_outcome_settlement_v1"
CALIBRATION = ROOT / "results" / "bj89_gate_a_preoutcome_v3"
SP_PROJECTION = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
SEGMENTATION = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"
OUT = ROOT / "results" / "bj107_gate_a_preoutcome_v1"

CONTRACT = "BJ-HIST-ISSUE-VALUE-GATE-001"
EXPECTED = {
    "bj106_gate_a": "fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d",
    "bj106_gate_b": "d112cc1f1c8b538b7a36e0c4b03de70aa9532f1cd2d9f38598afbd21b7223c86",
    "bj89": "b22c33bddc71972e3c2a5e7b95955087ece2441b5728da6424d19b3de6f503e2",
    "bj90": "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2",
    "bj101": "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447",
}
POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
DENOMINATOR_FIELDS = POOL_FIELDS + (
    "accepted_value_pocket_count", "candidate_outcome_count", "candidate_match_count",
    "candidate_density_per_eligible_match", "gate_disposition", "no_bet_reason",
    "selected_match_count", "segmentation_contract_used",
)
CHRONOLOGY_FIELDS = (
    "year", "fold", "issues", "pools", "available_segmentation_pools",
    "no_bet_pools", "accepted_value_pocket_count", "candidate_outcome_count",
    "candidate_match_count", "no_bet_rate",
)
CONCENTRATION_FIELDS = (
    "grouping", "group_value", "pools", "issues", "available_segmentation_pools",
    "upstream_no_signal_pools", "other_segmentation_unavailable_pools",
    "accepted_value_pocket_count", "candidate_outcome_count", "candidate_match_count",
    "candidate_concentration_share",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_manifest(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted input manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir()
              if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"input manifest coverage drift: {path}")
    return declared


def read_exact_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        return list(reader)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_upstream() -> dict[str, object]:
    manifests = {
        "bj106_gate_a": exact_manifest(ATLAS_GATE_A, EXPECTED["bj106_gate_a"]),
        "bj106_gate_b": exact_manifest(ATLAS_GATE_B, EXPECTED["bj106_gate_b"]),
        "bj89": exact_manifest(CALIBRATION, EXPECTED["bj89"]),
        "bj90": exact_manifest(SP_PROJECTION, EXPECTED["bj90"]),
        "bj101": exact_manifest(SEGMENTATION, EXPECTED["bj101"]),
    }
    atlas_card = json.loads((ATLAS_GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    if atlas_card.get("contract") != "BJ-HIST-Q-ATLAS-001":
        raise RuntimeError("unexpected #106 Gate-A contract")
    terminal_card = json.loads((ATLAS_GATE_B / "settlement_card.json").read_text(encoding="utf-8"))
    # The terminal card is the permitted published non-signal boundary.  The
    # runner never opens #106's outcome-level settlement payload.
    if terminal_card.get("terminal_disposition") != "NO_PROMOTION" or terminal_card.get("nominated_strata") != []:
        raise RuntimeError("#106 upstream no-signal boundary contradicted")
    if terminal_card.get("gate_a_manifest_sha256") != EXPECTED["bj106_gate_a"]:
        raise RuntimeError("#106 terminal card does not bind accepted Gate-A")
    if json.loads((CALIBRATION / "experiment_card.json").read_text()).get("stage") != "GATE_A_OUTCOME_UNEXPOSED":
        raise RuntimeError("unexpected #89 boundary")
    projection = json.loads((SP_PROJECTION / "projection_card.json").read_text())
    if projection.get("stage") != "DURABLE_OUTCOME_SAFE_DOWNSTREAM_OOS_PROJECTION":
        raise RuntimeError("unexpected #90 boundary")
    segmentation_card = json.loads((SEGMENTATION / "gate_a_card.json").read_text())
    if (segmentation_card.get("issue") != 101
            or segmentation_card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COLD_PRUNING_FREEZE"):
        raise RuntimeError("unexpected #101 segmentation contract")
    return {
        "input_manifests": EXPECTED,
        "input_payloads": {
            "bj106_gate_a_card": manifests["bj106_gate_a"]["gate_a_card.json"],
            "bj106_terminal_card": manifests["bj106_gate_b"]["settlement_card.json"],
            "bj89_card": manifests["bj89"]["experiment_card.json"],
            "bj90_card": manifests["bj90"]["projection_card.json"],
            "bj101_pool_census": manifests["bj101"]["issue_pool_census.csv"],
        },
    }


def make_denominator(pools: list[dict[str, str]]) -> list[dict[str, object]]:
    if not pools:
        raise RuntimeError("empty official issue/pool denominator")
    keys = {(row["issue"], row["pool_id"]) for row in pools}
    if len(keys) != len(pools):
        raise RuntimeError("duplicate official issue/pool denominator key")
    rows: list[dict[str, object]] = []
    for pool in pools:
        rows.append({
            **pool,
            "accepted_value_pocket_count": 0,
            "candidate_outcome_count": 0,
            "candidate_match_count": 0,
            "candidate_density_per_eligible_match": "0.000000000000",
            "gate_disposition": "ALL_NO_BET_UPSTREAM_NO_SIGNAL",
            "no_bet_reason": "UPSTREAM_106_NO_PROMOTED_VALUE_POCKETS",
            "selected_match_count": 0,
            "segmentation_contract_used": "BJ101_V1R1" if pool["pool_disposition"] == "AVAILABLE" else "BJ101_V1R1_UNAVAILABLE_POOL_RETAINED",
        })
    return rows


def chronology(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["year"]), str(row["fold"]))].append(row)
    result = []
    for (year, fold), members in sorted(grouped.items()):
        result.append({
            "year": year, "fold": fold, "issues": len({str(row["issue"]) for row in members}),
            "pools": len(members),
            "available_segmentation_pools": sum(row["pool_disposition"] == "AVAILABLE" for row in members),
            "no_bet_pools": len(members), "accepted_value_pocket_count": 0,
            "candidate_outcome_count": 0, "candidate_match_count": 0,
            "no_bet_rate": "1.000000000000",
        })
    return result


def concentration(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    result = []
    for grouping, index in (("pool_disposition", "pool_disposition"), ("year", "year")):
        groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows: groups[str(row[index])].append(row)
        for value, members in sorted(groups.items()):
            result.append({
                "grouping": grouping, "group_value": value, "pools": len(members),
                "issues": len({str(row["issue"]) for row in members}),
                "available_segmentation_pools": sum(row["pool_disposition"] == "AVAILABLE" for row in members),
                "upstream_no_signal_pools": len(members),
                "other_segmentation_unavailable_pools": 0,
                "accepted_value_pocket_count": 0, "candidate_outcome_count": 0,
                "candidate_match_count": 0, "candidate_concentration_share": "",
            })
    return result


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(); OUT = args.output.resolve()
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj107_gate_a_", dir=OUT.parent))
    try:
        provenance = validate_upstream()
        pools = read_exact_csv(SEGMENTATION / "issue_pool_census.csv", POOL_FIELDS)
        rows = make_denominator(pools)
        if len(rows) != 2659 or len({row["issue"] for row in rows}) != 344:
            raise RuntimeError("official #101 denominator cardinality drift")
        write_csv(stage / "issue_pool_no_bet_denominator.csv", DENOMINATOR_FIELDS, rows)
        write_csv(stage / "chronology_summary.csv", CHRONOLOGY_FIELDS, chronology(rows))
        write_csv(stage / "missingness_and_concentration.csv", CONCENTRATION_FIELDS, concentration(rows))
        source_rows = [
            {"source": "bj106_gate_b_outcome_settlement_v1", "role": "published terminal no-signal boundary only", "manifest_sha256": EXPECTED["bj106_gate_b"], "payload": "settlement_card.json", "payload_sha256": provenance["input_payloads"]["bj106_terminal_card"], "read_status": "parsed terminal fields only; no settlement payload opened"},
            {"source": "bj106_gate_a_preoutcome_v2r1", "role": "accepted outcome-unexposed atlas contract", "manifest_sha256": EXPECTED["bj106_gate_a"], "payload": "gate_a_card.json", "payload_sha256": provenance["input_payloads"]["bj106_gate_a_card"], "read_status": "parsed contract only; atlas not re-ranked"},
            {"source": "bj89_gate_a_preoutcome_v3", "role": "accepted calibration boundary", "manifest_sha256": EXPECTED["bj89"], "payload": "experiment_card.json", "payload_sha256": provenance["input_payloads"]["bj89_card"], "read_status": "manifest/card verified only"},
            {"source": "bj90_downstream_safe_projection_v1r1", "role": "accepted outcome-safe SP projection boundary", "manifest_sha256": EXPECTED["bj90"], "payload": "projection_card.json", "payload_sha256": provenance["input_payloads"]["bj90_card"], "read_status": "manifest/card verified only"},
            {"source": "bj101_gate_a_preoutcome_v1r1", "role": "complete official issue/pool denominator and segmentation", "manifest_sha256": EXPECTED["bj101"], "payload": "issue_pool_census.csv", "payload_sha256": provenance["input_payloads"]["bj101_pool_census"], "read_status": "parsed complete denominator only"},
        ]
        write_csv(stage / "source_census.csv", ("source", "role", "manifest_sha256", "payload", "payload_sha256", "read_status"), source_rows)
        card = {
            "issue": 107, "contract": CONTRACT, "stage": "GATE_A_OUTCOME_UNEXPOSED_TERMINAL_NO_BET",
            "provenance": provenance, "denominator": {"official_issues": 344, "official_pools": 2659},
            "gate_family": [{"name": "ALL_NO_BET_UPSTREAM_NO_SIGNAL", "thresholds": "none; #106 nominated_strata is exactly empty"}],
            "fallback": "Every official issue/pool remains in the denominator; select zero matches and emit explicit NO_BET.",
            "candidate_definition": "Only #106 promoted value pockets qualify. #106 terminal nominated_strata=[]; therefore accepted pocket, candidate outcome and candidate match counts are all zero.",
            "outcome_boundary": "No outcome rows, payout, tax, ROI, result, score, winning SP, q-atlas rows, or settlement payloads are opened. The #106 terminal settlement card is read only for its published no-signal disposition and empty nominated_strata boundary.",
            "gate_b": "NOT_REQUIRED: no staked policy exists when every candidate count is zero.",
            "decision": "NO_PROMOTION", "scope": "historical paper-only research; no purchase, production or frontend authority.",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        (stage / "decision.json").write_text(json.dumps({"decision": "NO_PROMOTION", "gate": "ALL_NO_BET_UPSTREAM_NO_SIGNAL", "reason": "#106 accepted zero promoted value pockets; no substitute signal permitted."}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        (stage / "README.md").write_text("# #107 Gate A\n\nThis package is intentionally terminal: all official issue/pools are retained as explicit `ALL_NO_BET_UPSTREAM_NO_SIGNAL`. Run `python freeze_runner.py --output <empty-directory>` from a checkout with the authenticated upstream packages.\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "manifest_sha256": sha256(OUT / "SHA256SUMS.json"), "pools": len(rows), "decision": "NO_PROMOTION"}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
