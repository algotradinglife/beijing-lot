#!/usr/bin/env python3
"""Emit #108's compact terminal upstream-gate evaluation without outcomes.

The accepted #107 entry gate has zero accepted pools.  #108 therefore has no
legal period on which to choose N, roles, paths, tickets or stake.  This runner
authenticates terminal metadata only, preserves the complete #107 denominator,
and never opens #105's settlement payloads or any outcome/final-SP source.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


ROOT = repo_root(Path(__file__))
BJ105 = ROOT / "results" / "bj105_gate_b_outcome_settlement_v1r2"
BJ107 = ROOT / "results" / "bj107_gate_a_preoutcome_v1"
OUT = ROOT / "results" / "bj108_terminal_upstream_gate_v1"
CONTRACT = "BJ-HIST-DYNAMIC-N-PATH-001"
EXPECTED_105_MANIFEST = "0c98ec8506585988a36620a6107ca9cc63d918cf92619930225e0112e05604d1"
EXPECTED_107_MANIFEST = "bc296a7de47b6268f2ffd4fb6d644bd39860376ca0a3d33e00a96252e8bd7fd9"
INPUT_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "accepted_value_pocket_count",
    "candidate_outcome_count", "candidate_match_count", "candidate_density_per_eligible_match",
    "gate_disposition", "no_bet_reason", "selected_match_count", "segmentation_contract_used",
)
DENOMINATOR_FIELDS = INPUT_FIELDS + (
    "source_edge_gate_status", "issue_entry_gate_status", "dynamic_n_status",
    "eligible_period", "candidate_portfolio_count", "ticket_count", "stake_yuan",
    "selected_n", "role_assignment_count", "path_count", "terminal_reason",
)
CHRONOLOGY_FIELDS = (
    "year", "fold", "issues", "pools", "upstream_no_bet_pools", "eligible_periods",
    "candidate_portfolios", "tickets", "stake_yuan", "not_run_rate",
)
FAILURE_FIELDS = (
    "reason", "pools", "issues", "share_of_pools", "candidate_portfolios", "tickets", "stake_yuan",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_identity(bundle: Path, expected: str, required_payloads: tuple[str, ...]) -> dict[str, str]:
    """Authenticate a bundle without opening unneeded outcome-bearing payloads."""
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted package manifest: {bundle}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(declared, dict) or not declared:
        raise RuntimeError("invalid package manifest")
    for payload in required_payloads:
        if payload not in declared or sha256(bundle / payload) != declared[payload]:
            raise RuntimeError(f"required payload identity drift: {bundle / payload}")
    return declared


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        return list(reader)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def validate_inputs() -> dict[str, object]:
    m105 = manifest_identity(BJ105, EXPECTED_105_MANIFEST, ("decision.json",))
    m107 = manifest_identity(BJ107, EXPECTED_107_MANIFEST, ("gate_a_card.json", "decision.json", "issue_pool_no_bet_denominator.csv"))
    decision105 = json.loads((BJ105 / "decision.json").read_text(encoding="utf-8"))
    if decision105.get("decision") != "NO_PROMOTION":
        raise RuntimeError("#105 terminal decision contradicted")
    card107 = json.loads((BJ107 / "gate_a_card.json").read_text(encoding="utf-8"))
    decision107 = json.loads((BJ107 / "decision.json").read_text(encoding="utf-8"))
    if (card107.get("contract") != "BJ-HIST-ISSUE-VALUE-GATE-001"
            or card107.get("decision") != "NO_PROMOTION"
            or decision107.get("gate") != "ALL_NO_BET_UPSTREAM_NO_SIGNAL"):
        raise RuntimeError("#107 terminal no-bet boundary contradicted")
    return {"input_manifests": {"bj105": EXPECTED_105_MANIFEST, "bj107": EXPECTED_107_MANIFEST},
            "input_payloads": {"bj105_decision": m105["decision.json"], "bj107_card": m107["gate_a_card.json"],
                               "bj107_decision": m107["decision.json"], "bj107_denominator": m107["issue_pool_no_bet_denominator.csv"]}}


def make_rows(source: list[dict[str, str]]) -> list[dict[str, object]]:
    if len(source) != 2659 or len({(row["issue"], row["pool_id"]) for row in source}) != len(source):
        raise RuntimeError("#107 denominator cardinality/key drift")
    if any(row["gate_disposition"] != "ALL_NO_BET_UPSTREAM_NO_SIGNAL"
           or row["accepted_value_pocket_count"] != "0" or row["candidate_match_count"] != "0"
           or row["selected_match_count"] != "0" for row in source):
        raise RuntimeError("#107 all-no-bet prerequisite contradicted")
    return [{**row, "source_edge_gate_status": "BJ105_NO_PROMOTION", "issue_entry_gate_status": "ALL_NO_BET_UPSTREAM_NO_SIGNAL",
             "dynamic_n_status": "NOT_RUN_UPSTREAM_ALL_NO_BET", "eligible_period": "FALSE",
             "candidate_portfolio_count": 0, "ticket_count": 0, "stake_yuan": "0.000000",
             "selected_n": "", "role_assignment_count": 0, "path_count": 0,
             "terminal_reason": "UPSTREAM_107_ZERO_ACCEPTED_PERIODS"} for row in source]


def chronology(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows: groups[(str(row["year"]), str(row["fold"]))].append(row)
    return [{"year": year, "fold": fold, "issues": len({str(item["issue"]) for item in members}),
             "pools": len(members), "upstream_no_bet_pools": len(members), "eligible_periods": 0,
             "candidate_portfolios": 0, "tickets": 0, "stake_yuan": "0.000000", "not_run_rate": "1.000000000000"}
            for (year, fold), members in sorted(groups.items())]


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(); OUT = args.output.resolve()
    if OUT.exists(): raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj108_terminal_", dir=OUT.parent))
    try:
        provenance = validate_inputs()
        source = read_csv(BJ107 / "issue_pool_no_bet_denominator.csv", INPUT_FIELDS)
        rows = make_rows(source)
        if len({row["issue"] for row in rows}) != 344: raise RuntimeError("#107 issue denominator drift")
        write_csv(stage / "issue_pool_not_run_denominator.csv", DENOMINATOR_FIELDS, rows)
        write_csv(stage / "chronology_summary.csv", CHRONOLOGY_FIELDS, chronology(rows))
        write_csv(stage / "failure_reason_reconciliation.csv", FAILURE_FIELDS, [{
            "reason": "UPSTREAM_107_ZERO_ACCEPTED_PERIODS", "pools": len(rows), "issues": len({row["issue"] for row in rows}),
            "share_of_pools": "1.000000000000", "candidate_portfolios": 0, "tickets": 0, "stake_yuan": "0.000000",
        }])
        sources = [
            {"source": "bj105_gate_b_outcome_settlement_v1r2", "role": "terminal source-of-edge gate decision", "manifest_sha256": EXPECTED_105_MANIFEST, "payload": "decision.json", "payload_sha256": provenance["input_payloads"]["bj105_decision"], "read_status": "decision only; no settlement payload opened"},
            {"source": "bj107_gate_a_preoutcome_v1", "role": "terminal issue-entry gate and complete denominator", "manifest_sha256": EXPECTED_107_MANIFEST, "payload": "gate_a_card.json + decision.json + issue_pool_no_bet_denominator.csv", "payload_sha256": provenance["input_payloads"]["bj107_denominator"], "read_status": "terminal metadata and full no-bet denominator parsed"},
        ]
        write_csv(stage / "source_census.csv", ("source", "role", "manifest_sha256", "payload", "payload_sha256", "read_status"), sources)
        card = {"issue": 108, "contract": CONTRACT, "stage": "TERMINAL_UPSTREAM_GATE_EVALUATION",
                "provenance": provenance, "denominator": {"official_issues": 344, "official_pools": 2659, "accepted_periods": 0},
                "prerequisite_rule": "Dynamic-N/path optimization operates only where both source-of-edge and issue-entry gates accept a period.",
                "upstream_status": {"bj105": "NO_PROMOTION", "bj107": "ALL_NO_BET_UPSTREAM_NO_SIGNAL for every pool"},
                "not_run": {"gate_a_n_role_path_optimization": "NOT_REQUIRED", "gate_b_outcome_settlement": "NOT_REQUIRED", "candidate_portfolios": 0, "tickets": 0, "stake_yuan": "0.000000"},
                "outcome_boundary": "No outcomes, final SP, payouts, tax, ROI, #105 settlement rows, or optimizer are opened/run. Only exact package manifests and terminal decision metadata are authenticated.",
                "decision": "NO_PROMOTION", "scope": "historical paper-only research; no purchase, production, frontend or prospective promotion."}
        (stage / "terminal_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        (stage / "decision.json").write_text(json.dumps({"decision": "NO_PROMOTION", "status": "NOT_RUN_UPSTREAM_ALL_NO_BET", "reason": "#107 accepted periods=0; dynamic-N optimization and outcome settlement are not required."}, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        (stage / "README.md").write_text("# #108 terminal upstream-gate evaluation\n\nEvery official #107 pool remains `NOT_RUN_UPSTREAM_ALL_NO_BET`; no optimizer or settlement is legal. Run `python terminal_runner.py --output <empty-directory>` from a checkout with the authenticated #105/#107 packages.\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "terminal_runner.py")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "manifest_sha256": sha256(OUT / "SHA256SUMS.json"), "pools": len(rows), "decision": "NO_PROMOTION"}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


if __name__ == "__main__": raise SystemExit(main())
