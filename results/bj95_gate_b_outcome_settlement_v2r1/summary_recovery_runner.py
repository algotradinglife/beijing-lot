#!/usr/bin/env python3
"""Non-outcome reporting recovery for #95's one-shot canonical Gate-B join.

This runner deliberately consumes only the immutable v1 settled rows.  It
does not open an outcome database or parse an outcome row: the canonical
outcome payload is copied byte-for-byte, while all summaries are recomputed
from the already-settled group/frontier ledger.  The recovery corrects the
#91 comparison's zero-K rows from a misleading SETTLED label to NO_BET.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


def repository_root(anchor: Path) -> Path:
    resolved = anchor.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"cannot locate repository root from {anchor}")


ROOT = repository_root(Path(__file__))
V1 = ROOT / "results" / "bj95_gate_b_outcome_settlement_v1"
OUT = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r1"
EXPECTED_V1_MANIFEST = "3cff428525acc36f9073a50440c9909f1ebbb0f62fa7dd894721e5a86344c865"
EXPECTED_GROUP_ROWS = 240_696
EXPECTED_GROUPS = 6_686
EXPECTED_OUTCOME_ROWS = 46_802
BJ91_SETTLEMENT = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1" / "group_arm_settlement.csv"
BJ91_ARMS = (
    "FULL_3_TO_N_ANALYTIC",
    "POINT_SP5_POSITIVE_EV",
    "CONSERVATIVE_M2_SP5_POSITIVE_EV",
)

BASE_SPEC = importlib.util.spec_from_file_location(
    "bj95_canonical_settlement", ROOT / "scripts" / "settle_bj95_n7_pruning_gate_b.py"
)
assert BASE_SPEC and BASE_SPEC.loader
BASE = importlib.util.module_from_spec(BASE_SPEC)
BASE_SPEC.loader.exec_module(BASE)

SETTLEMENT_FIELDS = (
    "cohort", "group_id", "issue", "year", "quarter", "fold", "arm", "depth", "gate_a_disposition",
    "settlement_status", "eligible_removals", "actual_removals", "removed_positions", "removed_codes",
    "portfolio_descriptor_sha256", "formula_k", "selected_sequence_count", "stake_yuan", "calibrated_mass",
    "euro_novig_mass", "truth_sequence", "final_winning_sp_product_uncapped", "winning_sp_sources", "hit",
    "gross_yuan", "net_yuan", "settlement_factor", "paid_cent_rounding_applied", "hit_break_even_threshold",
    "hit_profit_after_factor",
)


def normalise_bj91_status(k: str) -> str:
    """A K=0 #91 row is a recorded no-bet, whatever its legacy label says."""
    try:
        return "SETTLED" if int(k) > 0 else "NO_BET"
    except ValueError as error:
        raise RuntimeError(f"invalid #91 selected sequence count: {k!r}") from error


def read_exact_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        return list(reader)


def load_correct_bj91_comparison(group_ids: set[str]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    with BJ91_SETTLEMENT.open(newline="", encoding="utf-8") as handle:
        source = [
            row for row in csv.DictReader(handle)
            if row["cohort"] == "PRIMARY" and row["n"] == "7" and row["group_id"] in group_ids and row["arm"] in BJ91_ARMS
        ]
    if len(source) != len(group_ids) * len(BJ91_ARMS):
        raise RuntimeError("#91 comparison does not exactly cover all frozen #95 groups")
    rows: list[dict[str, object]] = []
    for row in source:
        rows.append({
            "arm": f"BJ91::{row['arm']}", "depth": "0", "issue": row["issue"], "year": row["year"],
            "quarter": row["quarter"], "group_id": row["group_id"],
            "settlement_status": normalise_bj91_status(row["k"]), "selected_sequence_count": row["k"],
            "stake_yuan": row["stake_yuan"], "gross_yuan": row["gross_yuan"], "net_yuan": row["net_yuan"],
            "hit": row["hit"], "calibrated_mass": row["retained_mass"], "euro_novig_mass": row["retained_mass"],
        })
    return rows, *BASE.summarise(rows)


def add_break_even_fields(summary: list[dict[str, object]], settled_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Add an explicitly realised-payout break-even diagnostic to every scope."""
    for record in summary:
        members = [
            row for row in settled_rows
            if row["arm"] == record["arm"] and int(str(row["depth"])) == int(str(record["depth"]))
        ]
        if record["scope"] == "YEAR":
            members = [row for row in members if row["year"] == record["scope_value"]]
        elif record["scope"] == "QUARTER":
            members = [row for row in members if row["quarter"] == record["scope_value"]]
        elif record["scope"] == "LEAVE_ONE_YEAR_OUT":
            members = [row for row in members if row["year"] != record["scope_value"]]
        elif record["scope"] not in ("ALL", "SAME_6686_GROUPS"):
            raise RuntimeError(f"unsupported summary scope: {record['scope']}")
        bets = [row for row in members if row["settlement_status"] == "SETTLED"]
        hits = [row for row in bets if row["hit"] == "YES"]
        if not hits:
            record["break_even_hits_at_observed_mean_hit_gross"] = ""
            record["break_even_coverage_rate_at_observed_mean_hit_gross"] = ""
            continue
        total_gross = sum((BASE.decimal(row["gross_yuan"], "gross") for row in hits), Decimal("0"))
        stake = sum((BASE.decimal(row["stake_yuan"], "stake") for row in bets), Decimal("0"))
        mean_hit_gross = total_gross / Decimal(len(hits))
        required_hits = stake / mean_hit_gross
        record["break_even_hits_at_observed_mean_hit_gross"] = BASE.ratio(required_hits)
        record["break_even_coverage_rate_at_observed_mean_hit_gross"] = BASE.ratio(required_hits / Decimal(len(bets))) if bets else ""
    return summary


def ensure_v1(source: Path) -> dict[str, str]:
    manifest = BASE.verify_manifest(source, EXPECTED_V1_MANIFEST)
    required = {
        "canonical_outcome_join.csv", "group_frontier_settlement.csv", "full_control_reconciliation_with_bj91.csv",
        "settlement_card.json", "settlement_runner.py",
    }
    if not required.issubset(manifest):
        raise RuntimeError("v1 bundle is incomplete")
    card = json.loads((source / "settlement_card.json").read_text(encoding="utf-8"))
    if card.get("stage") != "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT" or card.get("outcome_read_once") is not True:
        raise RuntimeError("v1 is not the authorized one-shot settlement")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=V1, help="immutable v1 one-shot settlement bundle")
    parser.add_argument("--output", type=Path, default=OUT, help="new immutable recovery bundle")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {output}")
    stage = Path(tempfile.mkdtemp(prefix="bj95_gate_b_recovery_", dir=output.parent))
    try:
        source_manifest = ensure_v1(source)
        settlement_rows = read_exact_csv(source / "group_frontier_settlement.csv", SETTLEMENT_FIELDS)
        if len(settlement_rows) != EXPECTED_GROUP_ROWS:
            raise RuntimeError("v1 frontier cardinality drift")
        group_ids = {row["group_id"] for row in settlement_rows}
        if len(group_ids) != EXPECTED_GROUPS:
            raise RuntimeError("v1 group cardinality drift")
        # Count raw newline-delimited payload records only.  This deliberately
        # does not parse result/SP columns or form a second outcome join.
        with (source / "canonical_outcome_join.csv").open("rb") as handle:
            outcome_count = sum(1 for _ in handle) - 1
        if outcome_count != EXPECTED_OUTCOME_ROWS:
            raise RuntimeError("v1 canonical outcome payload cardinality drift")

        overview, annual, quarterly, loyo = BASE.summarise(settlement_rows)
        for summary in (overview, annual, quarterly, loyo):
            add_break_even_fields(summary, settlement_rows)
        bj91_rows, bj91_overview, bj91_annual, bj91_quarterly, bj91_loyo = load_correct_bj91_comparison(group_ids)
        for summary in (bj91_overview, bj91_annual, bj91_quarterly, bj91_loyo):
            add_break_even_fields(summary, bj91_rows)
        decision = BASE.nomination(overview, annual, loyo)
        if decision["decision"] != "NO_PROMOTION":
            raise RuntimeError("unexpected post-outcome nomination; halt for PI review")

        # These are payload copies, not a second result/final-SP join.
        for filename in ("canonical_outcome_join.csv", "group_frontier_settlement.csv", "full_control_reconciliation_with_bj91.csv"):
            shutil.copyfile(source / filename, stage / filename)
        BASE.write_csv(stage / "frontier_overview.csv", list(overview[0]), overview)
        BASE.write_csv(stage / "annual_summary.csv", list(annual[0]), annual)
        BASE.write_csv(stage / "quarterly_summary.csv", list(quarterly[0]), quarterly)
        BASE.write_csv(stage / "leave_one_year_out_summary.csv", list(loyo[0]), loyo)
        BASE.write_csv(stage / "bj91_same_group_comparison.csv", list(bj91_overview[0]), bj91_overview)
        BASE.write_csv(stage / "bj91_same_group_annual_comparison.csv", list(bj91_annual[0]), bj91_annual)
        BASE.write_csv(stage / "bj91_same_group_quarterly_comparison.csv", list(bj91_quarterly[0]), bj91_quarterly)
        BASE.write_csv(stage / "bj91_same_group_leave_one_year_out_comparison.csv", list(bj91_loyo[0]), bj91_loyo)
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(source / "settlement_runner.py", stage / "canonical_settlement_runner.py")
        shutil.copyfile(__file__, stage / "summary_recovery_runner.py")
        card = {
            "issue": 95,
            "stage": "GATE_B_NON_OUTCOME_SUMMARY_RECOVERY_V2",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "canonical_settlement_input": "results/bj95_gate_b_outcome_settlement_v1",
            "canonical_settlement_manifest_sha256": EXPECTED_V1_MANIFEST,
            "canonical_settlement_payload_hashes": {
                name: source_manifest[name]
                for name in ("canonical_outcome_join.csv", "group_frontier_settlement.csv", "full_control_reconciliation_with_bj91.csv")
            },
            "outcome_database_read": False,
            "outcome_payload_parsed_for_join": False,
            "outcome_payload_copy_only": True,
            "recovery_scope": "Recompute summaries from already-settled v1 rows, add realised-payout break-even diagnostics to ALL/year/quarter/LOYO scopes, and correct #91 K=0 comparison rows to NO_BET. No frozen frontier, outcome, final SP, formula K, stake, payout, or #95 primary settlement row changes.",
            "supersedes": "v1 reporting summaries only; v1 canonical outcome join and group/frontier settlement payloads are byte-identical in this package.",
            "decision_rule": decision["rule"],
            "scope": "historical research only; NO_PROMOTION is not a production or purchase recommendation.",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {path.name: BASE.sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        print(json.dumps({"output": str(output), "manifest_sha256": BASE.sha256(output / "SHA256SUMS.json"), "decision": decision["decision"]}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
