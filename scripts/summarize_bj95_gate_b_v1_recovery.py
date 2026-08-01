#!/usr/bin/env python3
"""Durable non-outcome summary recovery for #95 canonical Gate-B settlement.

The runner authenticates and snapshots every input bundle before parsing it.
It never opens an outcome database or recomputes an outcome join.  Its output
is inode-independent and may be replayed to any writable filesystem.
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
from decimal import Decimal
from pathlib import Path
from types import ModuleType

LAUNCH_DIRECTORY = Path(__file__).resolve().parent
ROOT = LAUNCH_DIRECTORY.parent
OUT = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
EXECUTING_RECOVERY_SOURCE_BYTES = Path(__file__).read_bytes()
EXPECTED_V1_MANIFEST = (
    "3cff428525acc36f9073a50440c9909f1ebbb0f62fa7dd894721e5a86344c865"
)
EXPECTED_CANONICAL_RUNNER_SHA256 = (
    "42fc4843f6e8b2bced6b9262fed95890deaaeb9a68c793dcbe93dd3a034a1187"
)
EXPECTED_BJ91_MANIFEST = (
    "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
)
EXPECTED_BJ91_GROUP_ARM_SHA256 = (
    "cc2504f4e7809cac5e2111edfdb3ddbed1e62c31c9370cc76d0486431120a023"
)
EXPECTED_GROUP_ROWS = 240_696
EXPECTED_GROUPS = 6_686
RECOVERY_STAGE = "GATE_B_SELF_CONTAINED_NON_OUTCOME_SUMMARY_RECOVERY_V2R8"
SUPPORTED_RECOVERY_STAGES = (
    "GATE_B_SELF_CONTAINED_NON_OUTCOME_SUMMARY_RECOVERY_V2R6",
    "GATE_B_SELF_CONTAINED_NON_OUTCOME_SUMMARY_RECOVERY_V2R7",
    RECOVERY_STAGE,
)
BJ91_BUNDLE = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
BJ91_ARMS = (
    "FULL_3_TO_N_ANALYTIC",
    "POINT_SP5_POSITIVE_EV",
    "CONSERVATIVE_M2_SP5_POSITIVE_EV",
)
EXPECTED_CANONICAL_PAYLOAD_HASHES = {
    "canonical_outcome_join.csv": "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89",
    "group_frontier_settlement.csv": "03c862d78ccdd55ab2e770780ce9d108d96dc086c7381d9e8f20cf2c1f04d09f",
    "full_control_reconciliation_with_bj91.csv": "edbf2b48d62293a7f5ee925e3a93bcacbdde34618d742984ae8dd7143ee221b1",
}

SETTLEMENT_FIELDS = (
    "cohort",
    "group_id",
    "issue",
    "year",
    "quarter",
    "fold",
    "arm",
    "depth",
    "gate_a_disposition",
    "settlement_status",
    "eligible_removals",
    "actual_removals",
    "removed_positions",
    "removed_codes",
    "portfolio_descriptor_sha256",
    "formula_k",
    "selected_sequence_count",
    "stake_yuan",
    "calibrated_mass",
    "euro_novig_mass",
    "truth_sequence",
    "final_winning_sp_product_uncapped",
    "winning_sp_sources",
    "hit",
    "gross_yuan",
    "net_yuan",
    "settlement_factor",
    "paid_cent_rounding_applied",
    "hit_break_even_threshold",
    "hit_profit_after_factor",
)
SUMMARY_SETTLEMENT_FIELDS = (
    "group_id",
    "issue",
    "year",
    "quarter",
    "arm",
    "depth",
    "gate_a_disposition",
    "settlement_status",
    "selected_sequence_count",
    "stake_yuan",
    "calibrated_mass",
    "euro_novig_mass",
    "hit",
    "gross_yuan",
    "net_yuan",
)
BJ91_FIELDS = (
    "cohort",
    "n",
    "group_id",
    "source_group_id",
    "issue",
    "year",
    "quarter",
    "fold",
    "group_ordinal",
    "arm",
    "prediction_price_basis",
    "k",
    "stake_yuan",
    "retained_mass",
    "predicted_gross_yuan",
    "predicted_net_yuan",
    "settlement_status",
    "unavailable_match_ids",
    "unavailable_leg_count",
    "truth_sequence",
    "final_winning_sp_product_uncapped",
    "winning_sp_sources",
    "hit",
    "gross_yuan",
    "net_yuan",
    "predicted_winning_sp_product_uncapped",
    "predicted_winning_sp_product_effective_sp5",
    "final_over_predicted_winning_sp_product",
    "predicted_hit_gross_yuan",
    "settlement_factor",
    "paid_cent_rounding_applied",
)

BASE: ModuleType | None = None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


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
    """Validate exact top-level file coverage; directories are prohibited."""
    manifest_path = bundle / "SHA256SUMS.json"
    entries = list(bundle.iterdir()) if bundle.is_dir() else []
    if not manifest_path.is_file() or any(not path.is_file() for path in entries):
        raise RuntimeError(
            f"bundle must contain only manifested top-level files: {bundle}"
        )
    manifest_hash = sha256(manifest_path)
    if expected_sha is not None and manifest_hash != expected_sha:
        raise RuntimeError(f"unaccepted manifest identity: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not manifest:
        raise RuntimeError(f"invalid manifest: {bundle}")
    if any(Path(name).name != name or name == "SHA256SUMS.json" for name in manifest):
        raise RuntimeError(f"invalid manifest filename: {bundle}")
    actual = {
        path.name: sha256(path) for path in entries if path.name != manifest_path.name
    }
    if actual != manifest:
        raise RuntimeError(f"manifest is not exact coverage: {bundle}")
    return manifest


def snapshot_bundle(
    source: Path,
    destination: Path,
    expected_manifest_sha: str | None = None,
) -> tuple[dict[str, str], str]:
    """Copy an authenticated bundle, then parse only the private copy."""
    manifest = exact_manifest(source, expected_manifest_sha)
    source_manifest_hash = sha256(source / "SHA256SUMS.json")
    destination.mkdir()
    for filename in sorted(manifest):
        shutil.copyfile(source / filename, destination / filename)
    shutil.copyfile(source / "SHA256SUMS.json", destination / "SHA256SUMS.json")
    copied = exact_manifest(destination, source_manifest_hash)
    if copied != manifest:
        raise RuntimeError("authenticated bundle snapshot drift")
    return copied, source_manifest_hash


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


def authenticate_source(
    source: Path, manifest: dict[str, str]
) -> tuple[str, Path, str]:
    required = {
        "canonical_outcome_join.csv",
        "group_frontier_settlement.csv",
        "full_control_reconciliation_with_bj91.csv",
        "settlement_card.json",
    }
    if not required.issubset(manifest):
        raise RuntimeError("settlement source bundle is incomplete")
    card = json.loads((source / "settlement_card.json").read_text(encoding="utf-8"))
    stage = card.get("stage")
    if stage == "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT":
        if sha256(source / "SHA256SUMS.json") != EXPECTED_V1_MANIFEST:
            raise RuntimeError("source is not the authorized one-shot settlement")
        if card.get("outcome_read_once") is not True:
            raise RuntimeError("source does not attest to one outcome read")
        runner = source / "settlement_runner.py"
        generated_at = str(card["generated_at_utc"])
    elif stage in SUPPORTED_RECOVERY_STAGES:
        if card.get("canonical_settlement_manifest_sha256") != EXPECTED_V1_MANIFEST:
            raise RuntimeError("self-contained source does not bind canonical v1")
        runner = source / "canonical_settlement_runner.py"
        generated_at = str(card["canonical_settlement_generated_at_utc"])
    else:
        raise RuntimeError("unrecognized settlement source stage")
    if manifest.get(runner.name) != EXPECTED_CANONICAL_RUNNER_SHA256:
        raise RuntimeError("canonical settlement runner identity drift")
    for filename, expected in EXPECTED_CANONICAL_PAYLOAD_HASHES.items():
        if manifest.get(filename) != expected:
            raise RuntimeError(f"canonical settlement payload drift: {filename}")
    return generated_at, runner, str(stage)


def load_authenticated_runner(runner: Path, work: Path) -> ModuleType:
    """Execute exactly the runner source bytes that were hashed in the manifest."""
    source_bytes = runner.read_bytes()
    if sha256_bytes(source_bytes) != EXPECTED_CANONICAL_RUNNER_SHA256:
        raise RuntimeError("canonical settlement runner changed after authentication")
    module = ModuleType("bj95_authenticated_canonical_runner")
    # The archived runner only needs its project root while importing constants.
    # Give it a private shim root so replay does not require a Git checkout;
    # the compiled bytes remain the authenticated snapshot bytes above.
    shim_root = work / "canonical_runner_shim"
    (shim_root / ".git").mkdir(parents=True)
    execution_filename = shim_root / runner.name
    module.__file__ = str(execution_filename)
    exec(  # noqa: S102 - source bytes are authenticated immediately above.
        compile(source_bytes, str(execution_filename), "exec"), module.__dict__
    )
    bind_base_for_test(module)
    return module


def validate_settlement_rows(rows: list[dict[str, str]]) -> None:
    for row in rows:
        disposition = row["gate_a_disposition"]
        settlement_status = row["settlement_status"]
        hit = row["hit"]
        selected = row["selected_sequence_count"]
        stake = row["stake_yuan"]
        if disposition == "AVAILABLE":
            if settlement_status != "SETTLED" or hit not in ("YES", "NO"):
                raise RuntimeError("AVAILABLE row has inconsistent settlement status")
            if int(selected) <= 0 or Decimal(stake) <= 0:
                raise RuntimeError("AVAILABLE row has no selections or stake")
        elif disposition == "UNAVAILABLE_BY_RULE":
            if settlement_status != "NO_BET" or hit != "NO_BET":
                raise RuntimeError("unavailable row has inconsistent settlement status")
            if selected != "0" or Decimal(stake) != 0:
                raise RuntimeError("NO_BET row has selections or stake")
        else:
            raise RuntimeError(f"unknown Gate-A disposition: {disposition!r}")


def read_compact_settlement_rows(path: Path) -> list[dict[str, str]]:
    compact_rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SETTLEMENT_FIELDS:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        for row in reader:
            validate_settlement_rows([row])
            compact_rows.append(
                {field: row[field] for field in SUMMARY_SETTLEMENT_FIELDS}
            )
    return compact_rows


def aggregate(rows: list[dict[str, object]], **scope: object) -> dict[str, object]:
    runner = base()
    bet_rows = [row for row in rows if row["settlement_status"] == "SETTLED"]
    no_bet = [row for row in rows if row["settlement_status"] == "NO_BET"]
    stake = sum(
        (runner.decimal(row["stake_yuan"], "stake") for row in bet_rows), Decimal(0)
    )
    gross = sum(
        (runner.decimal(row["gross_yuan"], "gross") for row in bet_rows), Decimal(0)
    )
    net = gross - stake
    cumulative = peak = maximum_drawdown = Decimal(0)
    no_hit_streak = nonpositive_streak = max_no_hit = max_nonpositive = 0
    for row in runner.sorted_rows(bet_rows):
        row_net = runner.decimal(row["net_yuan"], "net")
        cumulative += row_net
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
        if row["hit"] == "YES":
            no_hit_streak = 0
        else:
            no_hit_streak += 1
            max_no_hit = max(max_no_hit, no_hit_streak)
        if row_net > 0:
            nonpositive_streak = 0
        else:
            nonpositive_streak += 1
            max_nonpositive = max(max_nonpositive, nonpositive_streak)
    hits = sum(row["hit"] == "YES" for row in bet_rows)
    profitable_hits = sum(
        row["hit"] == "YES" and runner.decimal(row["net_yuan"], "net") > 0
        for row in bet_rows
    )

    def mean(field: str) -> Decimal | None:
        values = [
            runner.decimal(row[field], field)
            for row in bet_rows
            if str(row[field]) != ""
        ]
        return sum(values, Decimal(0)) / Decimal(len(values)) if values else None

    positive = [
        (max(Decimal(0), runner.decimal(row["net_yuan"], "net")), row)
        for row in bet_rows
    ]
    total_positive = sum((value for value, _ in positive), Decimal(0))
    positive_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    signed_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for positive_net, row in positive:
        issue = str(row["issue"])
        positive_by_issue[issue] += positive_net
        signed_by_issue[issue] += runner.decimal(row["net_yuan"], "net")
    best = max(
        bet_rows,
        key=lambda row: runner.decimal(row["net_yuan"], "net"),
        default=None,
    )
    best_issue = max(signed_by_issue, key=signed_by_issue.get, default="")
    without_group = [
        row for row in bet_rows if best is None or row["group_id"] != best["group_id"]
    ]
    without_issue = [row for row in bet_rows if row["issue"] != best_issue]
    ex_group_net, ex_group_stake = runner.net_and_stake(without_group)
    ex_issue_net, ex_issue_stake = runner.net_and_stake(without_issue)
    return {
        **scope,
        "frontier_keys": len(rows),
        "bet_groups": len(bet_rows),
        "no_bet_groups": len(no_bet),
        "coverage_hits": hits,
        "coverage_hit_rate": runner.ratio(Decimal(hits) / Decimal(len(bet_rows)))
        if bet_rows
        else "",
        "profitable_hits": profitable_hits,
        "profitable_hit_rate": runner.ratio(
            Decimal(profitable_hits) / Decimal(len(bet_rows))
        )
        if bet_rows
        else "",
        "mean_calibrated_retained_mass": runner.ratio(mean("calibrated_mass")),
        "mean_euro_retained_mass": runner.ratio(mean("euro_novig_mass")),
        "total_k": sum(int(str(row["selected_sequence_count"])) for row in bet_rows),
        "stake_yuan": runner.six(stake),
        "gross_yuan": runner.six(gross),
        "net_yuan": runner.six(net),
        "roi": runner.ratio(net / stake) if stake else "",
        "max_drawdown_yuan": runner.six(maximum_drawdown),
        "longest_no_hit_streak": max_no_hit,
        "longest_nonpositive_net_streak": max_nonpositive,
        "best_net_group_id": "" if best is None else str(best["group_id"]),
        "best_net_issue": best_issue,
        "best_net_yuan": ""
        if best is None
        else runner.six(runner.decimal(best["net_yuan"], "net")),
        "ex_best_group_net_yuan": runner.six(ex_group_net),
        "ex_best_group_roi": runner.ratio(ex_group_net / ex_group_stake)
        if ex_group_stake
        else "",
        "ex_best_issue_net_yuan": runner.six(ex_issue_net),
        "ex_best_issue_roi": runner.ratio(ex_issue_net / ex_issue_stake)
        if ex_issue_stake
        else "",
        "positive_net_top_group_share": runner.ratio(
            max((value for value, _ in positive), default=Decimal(0)) / total_positive
        )
        if total_positive
        else "",
        "positive_net_top_issue_share": runner.ratio(
            max(positive_by_issue.values(), default=Decimal(0)) / total_positive
        )
        if total_positive
        else "",
    }


def add_break_even_fields(
    record: dict[str, object], members: list[dict[str, object]]
) -> dict[str, object]:
    runner = base()
    bets = [row for row in members if row["settlement_status"] == "SETTLED"]
    hits = [row for row in bets if row["hit"] == "YES"]
    if not hits:
        record["break_even_hits_at_observed_mean_hit_gross"] = ""
        record["break_even_coverage_rate_at_observed_mean_hit_gross"] = ""
        return record
    total_gross = sum(
        (runner.decimal(row["gross_yuan"], "gross") for row in hits), Decimal(0)
    )
    stake = sum(
        (runner.decimal(row["stake_yuan"], "stake") for row in bets), Decimal(0)
    )
    required_hits = stake / (total_gross / Decimal(len(hits)))
    record["break_even_hits_at_observed_mean_hit_gross"] = runner.ratio(required_hits)
    record["break_even_coverage_rate_at_observed_mean_hit_gross"] = runner.ratio(
        required_hits / Decimal(len(bets))
    )
    return record


def summarise_indexed(
    rows: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    buckets: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in rows:
        buckets.setdefault((str(row["arm"]), int(str(row["depth"]))), []).append(row)
    overview: list[dict[str, object]] = []
    annual: list[dict[str, object]] = []
    quarterly: list[dict[str, object]] = []
    loyo: list[dict[str, object]] = []
    for (arm, depth), members in sorted(buckets.items()):
        overview.append(
            add_break_even_fields(
                aggregate(members, arm=arm, depth=depth, scope="ALL"), members
            )
        )
        by_year: dict[str, list[dict[str, object]]] = defaultdict(list)
        by_quarter: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in members:
            by_year[str(row["year"])].append(row)
            by_quarter[str(row["quarter"])].append(row)
        for year, subset in sorted(by_year.items()):
            annual.append(
                add_break_even_fields(
                    aggregate(
                        subset,
                        arm=arm,
                        depth=depth,
                        scope="YEAR",
                        scope_value=year,
                    ),
                    subset,
                )
            )
            retained = [row for row in members if row["year"] != year]
            loyo.append(
                add_break_even_fields(
                    aggregate(
                        retained,
                        arm=arm,
                        depth=depth,
                        scope="LEAVE_ONE_YEAR_OUT",
                        scope_value=year,
                    ),
                    retained,
                )
            )
        for quarter, subset in sorted(by_quarter.items()):
            quarterly.append(
                add_break_even_fields(
                    aggregate(
                        subset,
                        arm=arm,
                        depth=depth,
                        scope="QUARTER",
                        scope_value=quarter,
                    ),
                    subset,
                )
            )
    return overview, annual, quarterly, loyo


def load_correct_bj91_comparison(
    group_ids: set[str],
    bundle: Path,
) -> list[dict[str, object]]:
    if not (bundle / "group_arm_settlement.csv").is_file():
        raise RuntimeError("#91 settlement is absent from accepted manifest")
    expected_keys = {(group_id, arm) for group_id in group_ids for arm in BJ91_ARMS}
    selected: dict[tuple[str, str], dict[str, str]] = {}
    with (bundle / "group_arm_settlement.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != BJ91_FIELDS:
            raise RuntimeError("#91 settlement schema drift")
        for row in reader:
            if (
                row["cohort"] == "PRIMARY"
                and row["n"] == "7"
                and row["group_id"] in group_ids
                and row["arm"] in BJ91_ARMS
            ):
                key = (row["group_id"], row["arm"])
                if key in selected:
                    raise RuntimeError(f"duplicate #91 comparison key: {key}")
                selected[key] = row
    if set(selected) != expected_keys:
        raise RuntimeError("#91 comparison key coverage drift")
    return [
        {
            "arm": f"BJ91::{row['arm']}",
            "depth": "0",
            "issue": row["issue"],
            "year": row["year"],
            "quarter": row["quarter"],
            "group_id": row["group_id"],
            "settlement_status": normalise_bj91_status(row["k"]),
            "selected_sequence_count": row["k"],
            "stake_yuan": row["stake_yuan"],
            "gross_yuan": row["gross_yuan"],
            "net_yuan": row["net_yuan"],
            "hit": row["hit"],
            "calibrated_mass": row["retained_mass"],
            "euro_novig_mass": "",
        }
        for row in selected.values()
    ]


def snapshot_bj91_comparison_input(
    source: Path,
    source_manifest: dict[str, str],
    stage_name: str,
    work: Path,
) -> Path:
    """Provide the exact #91 comparison payload from package or accepted source."""
    snapshot = work / "bj91_snapshot"
    snapshot.mkdir()
    embedded = source / "bj91_group_arm_settlement.csv"
    if stage_name == RECOVERY_STAGE:
        if source_manifest.get(embedded.name) != EXPECTED_BJ91_GROUP_ARM_SHA256:
            raise RuntimeError("embedded #91 comparison payload identity drift")
        shutil.copyfile(embedded, snapshot / "group_arm_settlement.csv")
    else:
        external = work / "bj91_external"
        manifest, _ = snapshot_bundle(BJ91_BUNDLE, external, EXPECTED_BJ91_MANIFEST)
        if manifest.get("group_arm_settlement.csv") != EXPECTED_BJ91_GROUP_ARM_SHA256:
            raise RuntimeError("accepted #91 comparison payload identity drift")
        shutil.copyfile(
            external / "group_arm_settlement.csv",
            snapshot / "group_arm_settlement.csv",
        )
    if sha256(snapshot / "group_arm_settlement.csv") != EXPECTED_BJ91_GROUP_ARM_SHA256:
        raise RuntimeError("#91 comparison payload changed after authentication")
    return snapshot


def write_rows(
    runner: ModuleType, stage: Path, rows: dict[str, list[dict[str, object]]]
) -> None:
    for filename, payload in rows.items():
        if not payload:
            raise RuntimeError(f"empty summary payload: {filename}")
        runner.write_csv(stage / filename, list(payload[0]), payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="authenticated one-shot or self-contained Gate-B bundle",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT,
        help="new immutable v2r8 recovery bundle",
    )
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {output}")
    work = Path(tempfile.mkdtemp(prefix="bj95_gate_b_recovery_", dir=output.parent))
    stage = work / "output"
    try:
        source_snapshot = work / "source_snapshot"
        source_manifest, _ = snapshot_bundle(source, source_snapshot)
        canonical_generated_at, runner_path, source_stage = authenticate_source(
            source_snapshot, source_manifest
        )
        runner = load_authenticated_runner(runner_path, work)
        bj91_snapshot = snapshot_bj91_comparison_input(
            source_snapshot, source_manifest, source_stage, work
        )
        settlement_rows = read_compact_settlement_rows(
            source_snapshot / "group_frontier_settlement.csv"
        )
        if len(settlement_rows) != EXPECTED_GROUP_ROWS:
            raise RuntimeError("settlement frontier cardinality drift")
        group_ids = {row["group_id"] for row in settlement_rows}
        if len(group_ids) != EXPECTED_GROUPS:
            raise RuntimeError("settlement group cardinality drift")
        overview, annual, quarterly, loyo = summarise_indexed(settlement_rows)
        bj91_rows = load_correct_bj91_comparison(group_ids, bj91_snapshot)
        bj91_overview, bj91_annual, bj91_quarterly, bj91_loyo = summarise_indexed(
            bj91_rows
        )
        decision = runner.nomination(overview, annual, loyo)
        if decision["decision"] != "NO_PROMOTION":
            raise RuntimeError("unexpected post-outcome nomination; halt for PI review")
        stage.mkdir()
        for filename in EXPECTED_CANONICAL_PAYLOAD_HASHES:
            shutil.copyfile(source_snapshot / filename, stage / filename)
        shutil.copyfile(
            bj91_snapshot / "group_arm_settlement.csv",
            stage / "bj91_group_arm_settlement.csv",
        )
        write_rows(
            runner,
            stage,
            {
                "frontier_overview.csv": overview,
                "annual_summary.csv": annual,
                "quarterly_summary.csv": quarterly,
                "leave_one_year_out_summary.csv": loyo,
                "bj91_same_group_comparison.csv": bj91_overview,
                "bj91_same_group_annual_comparison.csv": bj91_annual,
                "bj91_same_group_quarterly_comparison.csv": bj91_quarterly,
                "bj91_same_group_leave_one_year_out_comparison.csv": bj91_loyo,
            },
        )
        (stage / "decision.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        shutil.copyfile(runner_path, stage / "canonical_settlement_runner.py")
        (stage / "summary_recovery_runner.py").write_bytes(
            EXECUTING_RECOVERY_SOURCE_BYTES
        )
        card = {
            "issue": 95,
            "stage": RECOVERY_STAGE,
            "canonical_settlement_manifest_sha256": EXPECTED_V1_MANIFEST,
            "canonical_settlement_generated_at_utc": canonical_generated_at,
            "canonical_settlement_payload_hashes": EXPECTED_CANONICAL_PAYLOAD_HASHES,
            "canonical_settlement_runner_sha256": EXPECTED_CANONICAL_RUNNER_SHA256,
            "bj91_comparison_manifest_sha256": EXPECTED_BJ91_MANIFEST,
            "bj91_group_arm_settlement_sha256": EXPECTED_BJ91_GROUP_ARM_SHA256,
            "recovery_runner_sha256": sha256_bytes(EXECUTING_RECOVERY_SOURCE_BYTES),
            "outcome_database_read": False,
            "outcome_payload_parsed_for_join": False,
            "outcome_payload_copy_only": True,
            "recovery_scope": (
                "Snapshot authenticated settled rows only; use signed issue net for "
                "ex-best-issue robustness; emit #91 EURO mass unavailable; make no "
                "primary settlement row changes."
            ),
            "replay_contract": (
                "Replay this complete v2r8 package from any location to any writable "
                "filesystem. The #91 comparison payload is embedded and authenticated; "
                "output copies are inode-independent and leave the source unchanged."
            ),
            "decision_rule": decision["rule"],
            "scope": "historical research only; NO_PROMOTION is not a production or purchase recommendation.",
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest = {
            path.name: sha256(path)
            for path in sorted(stage.iterdir())
            if path.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(stage, output)
        print(
            json.dumps(
                {
                    "output": str(output),
                    "manifest_sha256": sha256(output / "SHA256SUMS.json"),
                    "decision": decision["decision"],
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
