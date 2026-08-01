"""Focused accounting tests for #95's one-shot Gate-B settlement."""
from __future__ import annotations

import importlib.util
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj95_gate_b", ROOT / "scripts" / "settle_bj95_n7_pruning_gate_b.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def recovery_module():
    spec = importlib.util.spec_from_file_location(
        "bj95_gate_b_recovery", ROOT / "scripts" / "summarize_bj95_gate_b_v1_recovery.py"
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
        "arm": "CAL_MIN_P", "depth": "1", "disposition": "AVAILABLE", "formula_k": "1458",
        "selected_sequence_count": "1458", "stake_yuan": "2916", "actual_removals": "1",
        "removed_positions": "2", "removed_codes": "0", "calibrated_mass": "0.8",
    }
    row.update(overrides)
    return row


def deletion(position: str = "2", code: str = "0") -> dict[str, str]:
    return {"removal_rank": "1", "position": position, "removed_code": code}


def test_available_geometry_hits_only_when_the_frozen_removed_code_is_not_truth() -> None:
    hit, selected, stake, mass, disposition = MOD.hit_and_geometry(frontier(), {1: "3", 2: "1", 3: "0", 4: "3", 5: "1", 6: "0", 7: "3"}, [deletion()])
    assert (hit, selected, stake, mass, disposition) == ("YES", 1458, Decimal("2916"), Decimal("0.8"), "AVAILABLE")
    hit, *_ = MOD.hit_and_geometry(frontier(), {1: "3", 2: "0", 3: "0", 4: "3", 5: "1", 6: "0", 7: "3"}, [deletion()])
    assert hit == "NO"


def test_full_control_and_unavailable_depth_preserve_frozen_k_and_zero_no_bet_stake() -> None:
    control = frontier(arm=MOD.CONTROL, depth="0", formula_k="2187", selected_sequence_count="2187", stake_yuan="4374", actual_removals="0", removed_positions="", removed_codes="", calibrated_mass="1")
    assert MOD.hit_and_geometry(control, {position: "3" for position in range(1, 8)}, [])[0:3] == ("YES", 2187, Decimal("4374"))
    unavailable = frontier(arm="MODEL_MARKET_AGREE", depth="4", disposition="UNAVAILABLE_BY_RULE", formula_k="432", selected_sequence_count="0", stake_yuan="0", actual_removals="0", removed_positions="", removed_codes="")
    assert MOD.hit_and_geometry(unavailable, {position: "3" for position in range(1, 8)}, [])[0:4] == ("NO_BET", 0, Decimal("0"), Decimal("0"))


def test_settlement_factor_is_once_and_final_price_is_uncapped() -> None:
    final_product = Decimal("10")
    assert MOD.STAKE_PER_SEQUENCE * MOD.FACTOR * final_product == Decimal("13.00")
    assert MOD.FACTOR == Decimal("0.65")


def test_nomination_is_fail_closed_without_all_scope_stability() -> None:
    overview = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "0.1", "ex_best_group_roi": "0.1", "ex_best_issue_roi": "0.1"}]
    annual = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "-0.1"}]
    loyo = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "0.1"}]
    assert MOD.nomination(overview, annual, loyo)["decision"] == "NO_PROMOTION"


def test_gate_b_binds_accepted_immutable_sources() -> None:
    assert MOD.EXPECTED_GATE_A_MANIFEST == "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
    assert MOD.EXPECTED_OUTCOME_SOURCE_MANIFEST == "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
    assert MOD.EXPECTED_CANONICAL_DB_SHA256 == "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"


def test_bj91_comparison_treats_zero_k_as_a_no_bet() -> None:
    recovery = recovery_module()
    assert recovery.normalise_bj91_status("0") == "NO_BET"
    assert recovery.normalise_bj91_status("2187") == "SETTLED"


def test_break_even_diagnostic_is_derived_from_realised_hit_gross_only() -> None:
    recovery = recovery_module()
    summary = [{"arm": "A", "depth": 1, "scope": "ALL"}]
    rows = [
        {"arm": "A", "depth": "1", "year": "2020", "quarter": "2020-Q1", "settlement_status": "SETTLED", "hit": "YES", "gross_yuan": "20", "stake_yuan": "10"},
        {"arm": "A", "depth": "1", "year": "2020", "quarter": "2020-Q1", "settlement_status": "SETTLED", "hit": "NO", "gross_yuan": "0", "stake_yuan": "10"},
    ]
    recovery.add_break_even_fields(summary[0], rows)
    assert summary[0]["break_even_hits_at_observed_mean_hit_gross"] == "1.000000000000"
    assert summary[0]["break_even_coverage_rate_at_observed_mean_hit_gross"] == "0.500000000000"


def test_recovery_requires_explicit_self_contained_source() -> None:
    recovery = recovery_module()
    assert recovery.EXPECTED_V1_MANIFEST == "3cff428525acc36f9073a50440c9909f1ebbb0f62fa7dd894721e5a86344c865"
    assert recovery.EXPECTED_CANONICAL_PAYLOAD_HASHES["group_frontier_settlement.csv"] == "03c862d78ccdd55ab2e770780ce9d108d96dc086c7381d9e8f20cf2c1f04d09f"


def test_ex_best_issue_uses_signed_net_but_concentration_remains_positive_only() -> None:
    recovery = recovery_module()
    def row(group_id: str, issue: str, net: str) -> dict[str, str]:
        return {"group_id": group_id, "issue": issue, "year": "2024", "quarter": "2024-Q1", "arm": "A", "depth": "1",
                "settlement_status": "SETTLED", "hit": "YES" if Decimal(net) > 0 else "NO", "stake_yuan": "20",
                "gross_yuan": str(Decimal("20") + Decimal(net)), "net_yuan": net, "selected_sequence_count": "10",
                "calibrated_mass": "0.5", "euro_novig_mass": "0.4"}
    summary = recovery.aggregate([row("a", "190303", "10"), row("b", "190303", "-12"), row("c", "22033", "9")])
    assert summary["best_net_issue"] == "22033"
    assert summary["ex_best_issue_net_yuan"] == "-2.000000"
    assert summary["positive_net_top_issue_share"] == "0.526315789474"


def _manifest(bundle: Path) -> str:
    entries = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in bundle.iterdir() if path.name != "SHA256SUMS.json"}
    manifest = bundle / "SHA256SUMS.json"
    manifest.write_text(json.dumps(entries, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _bj91_row(group_id: str, arm: str) -> dict[str, str]:
    return {field: "" for field in recovery_module().BJ91_FIELDS} | {
        "cohort": "PRIMARY", "n": "7", "group_id": group_id, "issue": "26001", "year": "2024", "quarter": "2024-Q1",
        "fold": "F", "group_ordinal": "1", "arm": arm, "k": "0", "stake_yuan": "0", "gross_yuan": "0", "net_yuan": "0", "hit": "NO_BET",
        "retained_mass": "0.5", "settlement_status": "NO_BET",
    }


def test_bj91_recovery_rejects_manifest_schema_and_duplicate_keys() -> None:
    recovery = recovery_module()
    with tempfile.TemporaryDirectory() as directory:
        bundle = Path(directory)
        path = bundle / "group_arm_settlement.csv"
        path.write_text("wrong\\nvalue\\n", encoding="utf-8")
        good_manifest = _manifest(bundle)
        expect_runtime_error(lambda: recovery.load_correct_bj91_comparison({"g"}, bundle, "0" * 64))
        expect_runtime_error(lambda: recovery.load_correct_bj91_comparison({"g"}, bundle, good_manifest))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS); writer.writeheader()
            for arm in recovery.BJ91_ARMS:
                writer.writerow(_bj91_row("g", arm))
            writer.writerow(_bj91_row("g", recovery.BJ91_ARMS[0]))
        good_manifest = _manifest(bundle)
        expect_runtime_error(lambda: recovery.load_correct_bj91_comparison({"g"}, bundle, good_manifest))
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=recovery.BJ91_FIELDS); writer.writeheader()
            for arm in recovery.BJ91_ARMS:
                writer.writerow(_bj91_row("g", arm))
        good_manifest = _manifest(bundle)
        comparison = recovery.load_correct_bj91_comparison({"g"}, bundle, good_manifest)
        assert {row["euro_novig_mass"] for row in comparison} == {""}


def test_recovery_rejects_unknown_settlement_dispositions() -> None:
    recovery = recovery_module()
    row = {"settlement_status": "PENDING", "hit": "NO", "selected_sequence_count": "1", "stake_yuan": "2"}
    expect_runtime_error(lambda: recovery.validate_settlement_rows([row]))


def test_self_contained_v2r6_subprocess_replay_is_byte_exact() -> None:
    bundle = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r6"
    assert bundle.is_dir(), "generate the committed v2r6 bundle before running this test"
    with tempfile.TemporaryDirectory(dir=ROOT / "results") as directory:
        replay = Path(directory) / "replay"
        subprocess.run([sys.executable, str(bundle / "summary_recovery_runner.py"), "--source", str(bundle), "--output", str(replay)], check=True, cwd=ROOT)
        left = sorted(path.relative_to(bundle) for path in bundle.iterdir() if path.is_file())
        right = sorted(path.relative_to(replay) for path in replay.iterdir() if path.is_file())
        assert left == right
        for relative in left:
            assert (bundle / relative).read_bytes() == (replay / relative).read_bytes()


def test_production_settlement_payout_wiring_reproduces_the_canonical_ledger() -> None:
    canonical = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r6" / "group_frontier_settlement.csv"
    with tempfile.TemporaryDirectory(dir=ROOT / "results") as directory:
        output = Path(directory) / "production"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "settle_bj95_n7_pruning_gate_b.py"), "--output", str(output)], check=True, cwd=ROOT)
        assert (output / "group_frontier_settlement.csv").read_bytes() == canonical.read_bytes()
