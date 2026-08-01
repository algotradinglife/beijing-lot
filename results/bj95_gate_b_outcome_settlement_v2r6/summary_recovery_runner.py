#!/usr/bin/env python3
"""Durable non-outcome summary recovery for #95 canonical Gate-B settlement.

The runner authenticates its source bundle before loading the archived
canonical settlement runner.  It consumes settled rows only: no outcome DB or
new outcome join is opened.  A final v2r6 bundle is self-contained and can be
replayed from itself with an explicit --source argument.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from types import ModuleType


def repository_root(anchor: Path) -> Path:
    resolved = anchor.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"cannot locate repository root from {anchor}")


ROOT = repository_root(Path(__file__))
OUT = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r6"
EXPECTED_V1_MANIFEST = "3cff428525acc36f9073a50440c9909f1ebbb0f62fa7dd894721e5a86344c865"
EXPECTED_CANONICAL_RUNNER_SHA256 = "42fc4843f6e8b2bced6b9262fed95890deaaeb9a68c793dcbe93dd3a034a1187"
EXPECTED_BJ91_MANIFEST = "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
EXPECTED_GROUP_ROWS = 240_696
EXPECTED_GROUPS = 6_686
EXPECTED_OUTCOME_ROWS = 46_802
RECOVERY_STAGE = "GATE_B_SELF_CONTAINED_NON_OUTCOME_SUMMARY_RECOVERY_V2R6"
BJ91_BUNDLE = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
BJ91_SETTLEMENT = BJ91_BUNDLE / "group_arm_settlement.csv"
BJ91_ARMS = ("FULL_3_TO_N_ANALYTIC", "POINT_SP5_POSITIVE_EV", "CONSERVATIVE_M2_SP5_POSITIVE_EV")
EXPECTED_CANONICAL_PAYLOAD_HASHES = {
    "canonical_outcome_join.csv": "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89",
    "group_frontier_settlement.csv": "03c862d78ccdd55ab2e770780ce9d108d96dc086c7381d9e8f20cf2c1f04d09f",
    "full_control_reconciliation_with_bj91.csv": "edbf2b48d62293a7f5ee925e3a93bcacbdde34618d742984ae8dd7143ee221b1",
}

SETTLEMENT_FIELDS = (
    "cohort", "group_id", "issue", "year", "quarter", "fold", "arm", "depth", "gate_a_disposition",
    "settlement_status", "eligible_removals", "actual_removals", "removed_positions", "removed_codes",
    "portfolio_descriptor_sha256", "formula_k", "selected_sequence_count", "stake_yuan", "calibrated_mass",
    "euro_novig_mass", "truth_sequence", "final_winning_sp_product_uncapped", "winning_sp_sources", "hit",
    "gross_yuan", "net_yuan", "settlement_factor", "paid_cent_rounding_applied", "hit_break_even_threshold",
    "hit_profit_after_factor",
)
BJ91_FIELDS = (
    "cohort", "n", "group_id", "source_group_id", "issue", "year", "quarter", "fold", "group_ordinal", "arm",
    "prediction_price_basis", "k", "stake_yuan", "retained_mass", "predicted_gross_yuan", "predicted_net_yuan",
    "settlement_status", "unavailable_match_ids", "unavailable_leg_count", "truth_sequence",
    "final_winning_sp_product_uncapped", "winning_sp_sources", "hit", "gross_yuan", "net_yuan",
    "predicted_winning_sp_product_uncapped", "predicted_winning_sp_product_effective_sp5",
    "final_over_predicted_winning_sp_product", "predicted_hit_gross_yuan", "settlement_factor",
    "paid_cent_rounding_applied",
)

BASE: ModuleType | None = None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def base() -> ModuleType:
    if BASE is None:
        raise RuntimeError("canonical settlement runner is not authenticated")
    return BASE


def bind_base_for_test(module: ModuleType) -> None:
    global BASE
    BASE = module


def exact_manifest(bundle: Path, expected_sha: str | None = None) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"missing manifest: {bundle}")
    if expected_sha is not None and sha256(manifest_path) != expected_sha:
        raise RuntimeError(f"unaccepted manifest identity: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest:
        raise RuntimeError(f"invalid manifest: {bundle}")
    actual = {path.name: sha256(path) for path in bundle.iterdir() if path.is_file() and path.name != manifest_path.name}
    if actual != manifest:
        raise RuntimeError(f"manifest is not exact coverage: {bundle}")
    return manifest


def normalise_bj91_status(k: str) -> str:
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


def authenticate_source(source: Path) -> tuple[dict[str, str], str, Path]:
    manifest = exact_manifest(source)
    required = {"canonical_outcome_join.csv", "group_frontier_settlement.csv", "full_control_reconciliation_with_bj91.csv", "settlement_card.json"}
    if not required.issubset(manifest):
        raise RuntimeError("settlement source bundle is incomplete")
    card = json.loads((source / "settlement_card.json").read_text(encoding="utf-8"))
    if card.get("stage") == "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT":
        runner = source / "settlement_runner.py"
        if sha256(source / "SHA256SUMS.json") != EXPECTED_V1_MANIFEST or card.get("outcome_read_once") is not True:
            raise RuntimeError("source is not the authorized one-shot settlement")
        canonical_generated_at = str(card["generated_at_utc"])
    elif card.get("stage") == RECOVERY_STAGE:
        runner = source / "canonical_settlement_runner.py"
        if card.get("canonical_settlement_manifest_sha256") != EXPECTED_V1_MANIFEST:
            raise RuntimeError("self-contained source does not bind canonical v1")
        canonical_generated_at = str(card["canonical_settlement_generated_at_utc"])
    else:
        raise RuntimeError("unrecognized settlement source stage")
    if not runner.is_file() or manifest.get(runner.name) != EXPECTED_CANONICAL_RUNNER_SHA256:
        raise RuntimeError("canonical settlement runner identity drift")
    for filename, expected in EXPECTED_CANONICAL_PAYLOAD_HASHES.items():
        if manifest.get(filename) != expected:
            raise RuntimeError(f"canonical settlement payload drift: {filename}")
    return manifest, canonical_generated_at, runner


def load_authenticated_runner(runner: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("bj95_authenticated_canonical_runner", runner)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load authenticated canonical runner")
    module = importlib.util.module_from_spec(spec)
    # The source bundle itself is immutable evidence.  Loading its archived
    # runner must not create an unmanifested __pycache__ sidecar.
    prior_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior_dont_write_bytecode
    bind_base_for_test(module)
    return module


def validate_settlement_rows(rows: list[dict[str, str]]) -> None:
    for row in rows:
        if row["settlement_status"] not in ("SETTLED", "NO_BET"):
            raise RuntimeError(f"unknown settlement status: {row['settlement_status']!r}")
        if row["hit"] not in ("YES", "NO", "NO_BET"):
            raise RuntimeError(f"unknown hit status: {row['hit']!r}")
        if row["settlement_status"] == "NO_BET" and (row["selected_sequence_count"] != "0" or row["stake_yuan"] != "0.000000"):
            raise RuntimeError("NO_BET row has selections or stake")


def aggregate(rows: list[dict[str, object]], **scope: object) -> dict[str, object]:
    runner = base()
    bet_rows = [row for row in rows if row["settlement_status"] == "SETTLED"]
    no_bet = [row for row in rows if row["settlement_status"] == "NO_BET"]
    stake = sum((runner.decimal(row["stake_yuan"], "stake") for row in bet_rows), Decimal("0"))
    gross = sum((runner.decimal(row["gross_yuan"], "gross") for row in bet_rows), Decimal("0"))
    net = gross - stake
    cumulative = peak = maximum_drawdown = Decimal("0")
    no_hit_streak = nonpositive_streak = max_no_hit = max_nonpositive = 0
    for row in runner.sorted_rows(bet_rows):
        row_net = runner.decimal(row["net_yuan"], "net")
        cumulative += row_net; peak = max(peak, cumulative); maximum_drawdown = max(maximum_drawdown, peak - cumulative)
        if row["hit"] == "YES": no_hit_streak = 0
        else: no_hit_streak += 1; max_no_hit = max(max_no_hit, no_hit_streak)
        if row_net > 0: nonpositive_streak = 0
        else: nonpositive_streak += 1; max_nonpositive = max(max_nonpositive, nonpositive_streak)
    hits = sum(row["hit"] == "YES" for row in bet_rows)
    profitable_hits = sum(row["hit"] == "YES" and runner.decimal(row["net_yuan"], "net") > 0 for row in bet_rows)
    def mean(field: str) -> Decimal | None:
        values = [runner.decimal(row[field], field) for row in bet_rows if str(row[field]) != ""]
        return sum(values, Decimal("0")) / Decimal(len(values)) if values else None
    positive = [(max(Decimal("0"), runner.decimal(row["net_yuan"], "net")), row) for row in bet_rows]
    total_positive = sum((value for value, _ in positive), Decimal("0"))
    positive_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    signed_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for value, row in positive:
        issue = str(row["issue"]); positive_by_issue[issue] += value; signed_by_issue[issue] += runner.decimal(row["net_yuan"], "net")
    best = max(bet_rows, key=lambda row: runner.decimal(row["net_yuan"], "net"), default=None)
    best_issue = max(signed_by_issue, key=signed_by_issue.get, default="")
    without_group = [row for row in bet_rows if best is None or row["group_id"] != best["group_id"]]
    without_issue = [row for row in bet_rows if row["issue"] != best_issue]
    ex_group_net, ex_group_stake = runner.net_and_stake(without_group)
    ex_issue_net, ex_issue_stake = runner.net_and_stake(without_issue)
    return {**scope, "frontier_keys": len(rows), "bet_groups": len(bet_rows), "no_bet_groups": len(no_bet),
        "coverage_hits": hits, "coverage_hit_rate": runner.ratio(Decimal(hits) / Decimal(len(bet_rows))) if bet_rows else "",
        "profitable_hits": profitable_hits, "profitable_hit_rate": runner.ratio(Decimal(profitable_hits) / Decimal(len(bet_rows))) if bet_rows else "",
        "mean_calibrated_retained_mass": runner.ratio(mean("calibrated_mass")), "mean_euro_retained_mass": runner.ratio(mean("euro_novig_mass")),
        "total_k": sum(int(str(row["selected_sequence_count"])) for row in bet_rows), "stake_yuan": runner.six(stake), "gross_yuan": runner.six(gross), "net_yuan": runner.six(net), "roi": runner.ratio(net / stake) if stake else "",
        "max_drawdown_yuan": runner.six(maximum_drawdown), "longest_no_hit_streak": max_no_hit, "longest_nonpositive_net_streak": max_nonpositive,
        "best_net_group_id": "" if best is None else str(best["group_id"]), "best_net_issue": best_issue, "best_net_yuan": "" if best is None else runner.six(runner.decimal(best["net_yuan"], "net")),
        "ex_best_group_net_yuan": runner.six(ex_group_net), "ex_best_group_roi": runner.ratio(ex_group_net / ex_group_stake) if ex_group_stake else "",
        "ex_best_issue_net_yuan": runner.six(ex_issue_net), "ex_best_issue_roi": runner.ratio(ex_issue_net / ex_issue_stake) if ex_issue_stake else "",
        "positive_net_top_group_share": runner.ratio(max((value for value, _ in positive), default=Decimal("0")) / total_positive) if total_positive else "",
        "positive_net_top_issue_share": runner.ratio(max(positive_by_issue.values(), default=Decimal("0")) / total_positive) if total_positive else ""}


def add_break_even_fields(record: dict[str, object], members: list[dict[str, object]]) -> dict[str, object]:
    runner = base(); bets = [row for row in members if row["settlement_status"] == "SETTLED"]; hits = [row for row in bets if row["hit"] == "YES"]
    if not hits:
        record["break_even_hits_at_observed_mean_hit_gross"] = ""; record["break_even_coverage_rate_at_observed_mean_hit_gross"] = ""; return record
    total_gross = sum((runner.decimal(row["gross_yuan"], "gross") for row in hits), Decimal("0")); stake = sum((runner.decimal(row["stake_yuan"], "stake") for row in bets), Decimal("0"))
    required_hits = stake / (total_gross / Decimal(len(hits)))
    record["break_even_hits_at_observed_mean_hit_gross"] = runner.ratio(required_hits); record["break_even_coverage_rate_at_observed_mean_hit_gross"] = runner.ratio(required_hits / Decimal(len(bets))) if bets else ""
    return record


def summarise_indexed(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    buckets: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in rows: buckets.setdefault((str(row["arm"]), int(str(row["depth"]))), []).append(row)
    overview: list[dict[str, object]] = []; annual: list[dict[str, object]] = []; quarterly: list[dict[str, object]] = []; loyo: list[dict[str, object]] = []
    for (arm, depth), members in sorted(buckets.items()):
        overview.append(add_break_even_fields(aggregate(members, arm=arm, depth=depth, scope="ALL"), members))
        by_year: dict[str, list[dict[str, object]]] = {}; by_quarter: dict[str, list[dict[str, object]]] = {}
        for row in members: by_year.setdefault(str(row["year"]), []).append(row); by_quarter.setdefault(str(row["quarter"]), []).append(row)
        for year, subset in sorted(by_year.items()):
            annual.append(add_break_even_fields(aggregate(subset, arm=arm, depth=depth, scope="YEAR", scope_value=year), subset)); retained = [row for row in members if row["year"] != year]; loyo.append(add_break_even_fields(aggregate(retained, arm=arm, depth=depth, scope="LEAVE_ONE_YEAR_OUT", scope_value=year), retained))
        for quarter, subset in sorted(by_quarter.items()): quarterly.append(add_break_even_fields(aggregate(subset, arm=arm, depth=depth, scope="QUARTER", scope_value=quarter), subset))
    return overview, annual, quarterly, loyo


def load_correct_bj91_comparison(
    group_ids: set[str], bundle: Path = BJ91_BUNDLE, expected_manifest: str = EXPECTED_BJ91_MANIFEST
) -> list[dict[str, object]]:
    manifest = exact_manifest(bundle, expected_manifest)
    if "group_arm_settlement.csv" not in manifest: raise RuntimeError("#91 settlement is absent from accepted manifest")
    expected_keys = {(group_id, arm) for group_id in group_ids for arm in BJ91_ARMS}; selected: dict[tuple[str, str], dict[str, str]] = {}
    with (bundle / "group_arm_settlement.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != BJ91_FIELDS: raise RuntimeError("#91 settlement schema drift")
        for row in reader:
            if row["cohort"] == "PRIMARY" and row["n"] == "7" and row["group_id"] in group_ids and row["arm"] in BJ91_ARMS:
                key = (row["group_id"], row["arm"])
                if key in selected: raise RuntimeError(f"duplicate #91 comparison key: {key}")
                selected[key] = row
    if set(selected) != expected_keys: raise RuntimeError("#91 comparison key coverage drift")
    return [{"arm": f"BJ91::{row['arm']}", "depth": "0", "issue": row["issue"], "year": row["year"], "quarter": row["quarter"], "group_id": row["group_id"], "settlement_status": normalise_bj91_status(row["k"]), "selected_sequence_count": row["k"], "stake_yuan": row["stake_yuan"], "gross_yuan": row["gross_yuan"], "net_yuan": row["net_yuan"], "hit": row["hit"], "calibrated_mass": row["retained_mass"], "euro_novig_mass": ""} for row in selected.values()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="authenticated one-shot or self-contained v2r6 bundle")
    parser.add_argument("--output", type=Path, default=OUT, help="new immutable v2r6 recovery bundle")
    args = parser.parse_args(); source, output = args.source.resolve(), args.output.resolve()
    if output.exists(): raise SystemExit(f"refusing to overwrite immutable output: {output}")
    stage = Path(tempfile.mkdtemp(prefix="bj95_gate_b_recovery_", dir=output.parent))
    try:
        _manifest, canonical_generated_at, runner_path = authenticate_source(source); runner = load_authenticated_runner(runner_path)
        settlement_rows = read_exact_csv(source / "group_frontier_settlement.csv", SETTLEMENT_FIELDS)
        if len(settlement_rows) != EXPECTED_GROUP_ROWS: raise RuntimeError("settlement frontier cardinality drift")
        validate_settlement_rows(settlement_rows); group_ids = {row["group_id"] for row in settlement_rows}
        if len(group_ids) != EXPECTED_GROUPS: raise RuntimeError("settlement group cardinality drift")
        with (source / "canonical_outcome_join.csv").open("rb") as handle: outcome_count = sum(1 for _ in handle) - 1
        if outcome_count != EXPECTED_OUTCOME_ROWS: raise RuntimeError("canonical outcome payload cardinality drift")
        overview, annual, quarterly, loyo = summarise_indexed(settlement_rows); bj91_rows = load_correct_bj91_comparison(group_ids); bj91_overview, bj91_annual, bj91_quarterly, bj91_loyo = summarise_indexed(bj91_rows)
        decision = runner.nomination(overview, annual, loyo)
        if decision["decision"] != "NO_PROMOTION": raise RuntimeError("unexpected post-outcome nomination; halt for PI review")
        # The canonical payloads are immutable and authenticated above.  Link,
        # rather than copy, so a v2r6 self-replay does not require another
        # multi-GB transient copy; Git materializes ordinary files on checkout.
        for filename in EXPECTED_CANONICAL_PAYLOAD_HASHES:
            os.link(source / filename, stage / filename)
        for filename, rows in (("frontier_overview.csv", overview), ("annual_summary.csv", annual), ("quarterly_summary.csv", quarterly), ("leave_one_year_out_summary.csv", loyo), ("bj91_same_group_comparison.csv", bj91_overview), ("bj91_same_group_annual_comparison.csv", bj91_annual), ("bj91_same_group_quarterly_comparison.csv", bj91_quarterly), ("bj91_same_group_leave_one_year_out_comparison.csv", bj91_loyo)):
            runner.write_csv(stage / filename, list(rows[0]), rows)
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(runner_path, stage / "canonical_settlement_runner.py"); shutil.copyfile(__file__, stage / "summary_recovery_runner.py")
        card = {"issue": 95, "stage": RECOVERY_STAGE, "canonical_settlement_manifest_sha256": EXPECTED_V1_MANIFEST, "canonical_settlement_generated_at_utc": canonical_generated_at, "canonical_settlement_payload_hashes": EXPECTED_CANONICAL_PAYLOAD_HASHES, "canonical_settlement_runner_sha256": EXPECTED_CANONICAL_RUNNER_SHA256, "bj91_comparison_manifest_sha256": EXPECTED_BJ91_MANIFEST, "outcome_database_read": False, "outcome_payload_parsed_for_join": False, "outcome_payload_copy_only": True, "recovery_scope": "Recompute summaries from settled rows only; use signed issue net for ex-best-issue robustness; emit #91 EURO mass unavailable; no primary settlement row changes.", "replay_contract": "Pass this complete v2r6 bundle itself as --source and a new empty directory as --output. The replay must reproduce every payload byte and SHA256SUMS.json exactly without untracked files.", "decision_rule": decision["rule"], "scope": "historical research only; NO_PROMOTION is not a production or purchase recommendation."}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}; (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output); print(json.dumps({"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "decision": decision["decision"]}, sort_keys=True)); return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


if __name__ == "__main__": raise SystemExit(main())
