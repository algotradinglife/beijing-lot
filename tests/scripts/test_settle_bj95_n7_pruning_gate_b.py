"""Focused no-outcome-read accounting tests for #95 Gate-B settlement."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bj95_gate_b", ROOT / "scripts" / "settle_bj95_n7_pruning_gate_b.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def recovery_module():
    spec = importlib.util.spec_from_file_location(
        "bj95_gate_b_recovery",
        ROOT / "scripts" / "summarize_bj95_gate_b_v1_recovery.py",
    )
    assert spec and spec.loader
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    recovery.bind_base_for_test(MOD)
    return recovery


def expect_runtime_error(action) -> None:
    try:
        action()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def frontier(**overrides: str) -> dict[str, str]:
    row = {
        "arm": "CAL_MIN_P",
        "depth": "1",
        "disposition": "AVAILABLE",
        "formula_k": "1458",
        "selected_sequence_count": "1458",
        "stake_yuan": "2916",
        "actual_removals": "1",
        "removed_positions": "2",
        "removed_codes": "0",
        "calibrated_mass": "0.8",
    }
    row.update(overrides)
    return row


def deletion(position: str = "2", code: str = "0") -> dict[str, str]:
    return {"removal_rank": "1", "position": position, "removed_code": code}


def summary_row(group_id: str, issue: str, net: str) -> dict[str, str]:
    return {
        "group_id": group_id,
        "issue": issue,
        "year": "2024",
        "quarter": "2024-Q1",
        "arm": "A",
        "depth": "1",
        "settlement_status": "SETTLED",
        "hit": "YES" if Decimal(net) > 0 else "NO",
        "stake_yuan": "20",
        "gross_yuan": str(Decimal(20) + Decimal(net)),
        "net_yuan": net,
        "selected_sequence_count": "10",
        "calibrated_mass": "0.5",
        "euro_novig_mass": "0.4",
    }


def test_available_geometry_hits_only_when_removed_code_is_not_truth() -> None:
    truth = {1: "3", 2: "1", 3: "0", 4: "3", 5: "1", 6: "0", 7: "3"}
    hit, selected, stake, mass, disposition = MOD.hit_and_geometry(
        frontier(), truth, [deletion()]
    )
    assert (hit, selected, stake, mass, disposition) == (
        "YES",
        1458,
        Decimal(2916),
        Decimal("0.8"),
        "AVAILABLE",
    )
    truth[2] = "0"
    assert MOD.hit_and_geometry(frontier(), truth, [deletion()])[0] == "NO"


def test_production_rejects_unknown_gate_a_disposition() -> None:
    expect_runtime_error(
        lambda: MOD.hit_and_geometry(
            frontier(disposition="CORRUPT_STATUS"),
            {position: "3" for position in range(1, 8)},
            [deletion()],
        )
    )


def test_full_control_and_unavailable_preserve_frozen_geometry() -> None:
    control = frontier(
        arm=MOD.CONTROL,
        depth="0",
        formula_k="2187",
        selected_sequence_count="2187",
        stake_yuan="4374",
        actual_removals="0",
        removed_positions="",
        removed_codes="",
        calibrated_mass="1",
    )
    assert MOD.hit_and_geometry(control, {i: "3" for i in range(1, 8)}, [])[:3] == (
        "YES",
        2187,
        Decimal(4374),
    )
    unavailable = frontier(
        arm="MODEL_MARKET_AGREE",
        depth="4",
        disposition="UNAVAILABLE_BY_RULE",
        formula_k="432",
        selected_sequence_count="0",
        stake_yuan="0",
        actual_removals="0",
        removed_positions="",
        removed_codes="",
    )
    assert MOD.hit_and_geometry(unavailable, {i: "3" for i in range(1, 8)}, [])[:4] == (
        "NO_BET",
        0,
        Decimal(0),
        Decimal(0),
    )


def test_production_payout_is_pure_and_uses_factor_once() -> None:
    assert MOD.settled_gross_yuan("YES", Decimal(10)) == Decimal("13.00")
    assert MOD.settled_gross_yuan("NO", Decimal(10)) == Decimal(0)
    assert MOD.settled_gross_yuan("NO_BET", Decimal(10)) == Decimal(0)
    expect_runtime_error(lambda: MOD.settled_gross_yuan("UNKNOWN", Decimal(10)))
    expect_runtime_error(lambda: MOD.settled_gross_yuan("YES", Decimal(0)))


def test_nomination_is_fail_closed_without_all_scope_stability() -> None:
    overview = [
        {
            "arm": "CAL_MIN_P",
            "depth": 1,
            "roi": "0.1",
            "ex_best_group_roi": "0.1",
            "ex_best_issue_roi": "0.1",
        }
    ]
    annual = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "-0.1"}]
    loyo = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "0.1"}]
    assert MOD.nomination(overview, annual, loyo)["decision"] == "NO_PROMOTION"


def test_gate_b_binds_accepted_immutable_sources() -> None:
    assert MOD.EXPECTED_GATE_A_MANIFEST == (
        "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
    )
    assert MOD.EXPECTED_OUTCOME_SOURCE_MANIFEST == (
        "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
    )


def test_signed_best_issue_is_identical_in_production_and_recovery() -> None:
    recovery = recovery_module()
    rows = [
        summary_row("a", "190303", "10"),
        summary_row("b", "190303", "-12"),
        summary_row("c", "22033", "9"),
    ]
    for summary in (MOD.aggregate(rows), recovery.aggregate(rows)):
        assert summary["best_net_issue"] == "22033"
        assert summary["ex_best_issue_net_yuan"] == "-2.000000"
        assert summary["positive_net_top_issue_share"] == "0.526315789474"


def _write_manifest(bundle: Path) -> str:
    entries = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in bundle.iterdir()
        if path.name != "SHA256SUMS.json"
    }
    manifest = bundle / "SHA256SUMS.json"
    manifest.write_text(json.dumps(entries, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _bj91_row(recovery, group_id: str, arm: str) -> dict[str, str]:
    row = {field: "" for field in recovery.BJ91_FIELDS}
    row.update(
        {
            "cohort": "PRIMARY",
            "n": "7",
            "group_id": group_id,
            "issue": "26001",
            "year": "2024",
            "quarter": "2024-Q1",
            "fold": "F",
            "group_ordinal": "1",
            "arm": arm,
            "k": "0",
            "stake_yuan": "0",
            "gross_yuan": "0",
            "net_yuan": "0",
            "hit": "NO_BET",
            "retained_mass": "0.5",
            "settlement_status": "NO_BET",
        }
    )
    return row


def test_snapshot_rejects_unmanifested_entries_and_seals_payload() -> None:
    recovery = recovery_module()
    with tempfile.TemporaryDirectory(dir="/dev/shm") as directory:
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        payload = source / "payload.txt"
        payload.write_text("before", encoding="utf-8")
        manifest_hash = _write_manifest(source)
        snapshot = root / "snapshot"
        recovery.snapshot_bundle(source, snapshot, manifest_hash)
        payload.write_text("after", encoding="utf-8")
        assert (snapshot / "payload.txt").read_text(encoding="utf-8") == "before"
        (source / "unmanifested").mkdir()
        expect_runtime_error(lambda: recovery.exact_manifest(source, manifest_hash))


def test_bj91_recovery_rejects_schema_duplicate_and_missing_keys() -> None:
    recovery = recovery_module()
    with tempfile.TemporaryDirectory(dir="/dev/shm") as directory:
        bundle = Path(directory)
        path = bundle / "group_arm_settlement.csv"
        path.write_text("wrong\nvalue\n", encoding="utf-8")
        expect_runtime_error(
            lambda: recovery.load_correct_bj91_comparison({"g"}, bundle)
        )
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS)
            writer.writeheader()
            for arm in recovery.BJ91_ARMS:
                writer.writerow(_bj91_row(recovery, "g", arm))
        manifest_hash = _write_manifest(bundle)
        with path.open("a", encoding="utf-8") as handle:
            handle.write("tamper-after-manifest\n")
        expect_runtime_error(
            lambda: recovery.snapshot_bundle(bundle, bundle / "snapshot", manifest_hash)
        )
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS)
            writer.writeheader()
            for arm in recovery.BJ91_ARMS:
                writer.writerow(_bj91_row(recovery, "g", arm))
            writer.writerow(_bj91_row(recovery, "g", recovery.BJ91_ARMS[0]))
        expect_runtime_error(
            lambda: recovery.load_correct_bj91_comparison({"g"}, bundle)
        )
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS)
            writer.writeheader()
            writer.writerow(_bj91_row(recovery, "g", recovery.BJ91_ARMS[0]))
        expect_runtime_error(
            lambda: recovery.load_correct_bj91_comparison({"g"}, bundle)
        )


def test_bj91_comparison_marks_euro_mass_unavailable() -> None:
    recovery = recovery_module()
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory)
        path = bundle / "group_arm_settlement.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS)
            writer.writeheader()
            for arm in recovery.BJ91_ARMS:
                writer.writerow(_bj91_row(recovery, "g", arm))
        rows = recovery.load_correct_bj91_comparison({"g"}, bundle)
        assert {row["euro_novig_mass"] for row in rows} == {""}


def test_recovery_rejects_inconsistent_disposition_status_hit_k_and_stake() -> None:
    recovery = recovery_module()
    row = {
        "gate_a_disposition": "AVAILABLE",
        "settlement_status": "NO_BET",
        "hit": "NO_BET",
        "selected_sequence_count": "0",
        "stake_yuan": "0",
    }
    expect_runtime_error(lambda: recovery.validate_settlement_rows([row]))


def test_v2r7_replay_is_cross_device_inode_independent_and_source_safe() -> None:
    recovery = recovery_module()
    bundle = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r7"
    assert bundle.is_dir(), (
        "generate the committed v2r7 bundle before running this test"
    )
    source_manifest = recovery.sha256(bundle / "SHA256SUMS.json")
    with tempfile.TemporaryDirectory(dir="/dev/shm") as directory:
        replay = Path(directory) / "replay"
        subprocess.run(
            [
                sys.executable,
                str(bundle / "summary_recovery_runner.py"),
                "--source",
                str(bundle),
                "--output",
                str(replay),
            ],
            check=True,
            cwd=ROOT,
        )
        filename = "group_frontier_settlement.csv"
        assert os.stat(bundle / filename).st_ino != os.stat(replay / filename).st_ino
        assert (bundle / filename).read_bytes() == (replay / filename).read_bytes()
        with (replay / filename).open("ab") as handle:
            handle.write(b"\nmutation-only-in-replay\n")
    assert recovery.sha256(bundle / "SHA256SUMS.json") == source_manifest
    recovery.exact_manifest(bundle, source_manifest)
