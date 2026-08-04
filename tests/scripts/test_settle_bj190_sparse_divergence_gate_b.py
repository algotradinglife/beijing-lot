from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj190_sparse_divergence_gate_b.py"
SPEC = importlib.util.spec_from_file_location("bj190_gate_b", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def repo_scratch(prefix: str) -> Path:
    root = ROOT / ".scratch" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=root))


def test_frozen_contract_and_gate_a_bindings_are_exact() -> None:
    assert RUNNER.ARMS == (
        "B0_BEST_FULL",
        "D_MATCH_ONLY_FULL",
        "D_DIRECTION_ONLY",
        "D_JOINT_SPARSE",
    )
    assert RUNNER.EXPECTED_LEDGER_ROWS == 101_970
    assert RUNNER.EXPECTED_TRUSTED_ROWS == 100_906
    assert RUNNER.EXPECTED_UNAVAILABLE_ROWS == 1_064
    assert RUNNER.EXPECTED_MULTIPLICITY_VECTOR_COUNT == 3_563
    assert RUNNER.EXPECTED_IDENTITY_DISTRIBUTION == {
        3: 1,
        4: 4,
        5: 19,
        6: 211,
        7: 2_946,
    }
    assert (
        RUNNER.sha256_file(RUNNER.GATE_A / "SHA256SUMS.json")
        == RUNNER.EXPECTED_GATE_A_MANIFEST
    )
    assert (
        RUNNER.sha256_file(RUNNER.GATE_A / "CONTENT_IDENTITY.json")
        == RUNNER.EXPECTED_GATE_A_CONTENT
    )


def test_hash_bound_database_builds_exact_canonical_ledger_and_identity_census() -> (
    None
):
    scratch = repo_scratch("bj190-ledger-")
    try:
        database = RUNNER.resolve_database()
        gate = RUNNER.load_gate_a()
        ledger = scratch / "canonical_outcome_ledger.csv.gz"
        outcomes, receipt = RUNNER.build_canonical_outcome_ledger(
            database, gate["estimators"], ledger
        )
        assert receipt["eligible_match_count"] == 101_970
        assert receipt["trusted_match_count"] == 100_906
        assert receipt["unavailable_match_count"] == 1_064
        assert receipt["legacy_overlap_count"] == 46_802
        assert receipt["legacy_disagreement_count"] == 0
        assert receipt["quality_counts"] == {
            "mismatch": 6,
            "missing_sp": 1_058,
            "trusted": 100_906,
        }
        assert receipt["ledger_sha256"] == RUNNER.sha256_file(ledger)
        _, distribution = RUNNER.prepare_identity_settlements(
            gate["identities"], outcomes
        )
        assert dict(sorted(distribution.items())) == {
            3: 1,
            4: 4,
            5: 19,
            6: 211,
            7: 2_946,
        }
    finally:
        shutil.rmtree(scratch)


def test_ticket_settlement_is_per_ticket_and_unavailable_fails_closed() -> None:
    multiplicity = bytearray([1] * RUNNER.FULL_TICKETS)
    multiplicity[0] = 2
    multiplicity[1] = 0
    available = RUNNER.IdentitySettlement(7, (), 0, 12_000.0)
    settled = RUNNER.settle_ticket_vector(available, bytes(multiplicity))
    assert settled == {
        "executed_ticket_count": 2_187,
        "stake_yuan": 4_374.0,
        "gross_pre_tax_yuan": 24_000.0,
        "tax_yuan": 4_800.0,
        "hit_ticket_count": 2,
    }
    unavailable = RUNNER.IdentitySettlement(6, ("missing",), None, 0.0)
    assert RUNNER.settle_ticket_vector(unavailable, bytes(multiplicity)) == {
        "executed_ticket_count": 0,
        "stake_yuan": 0.0,
        "gross_pre_tax_yuan": 0.0,
        "tax_yuan": 0.0,
        "hit_ticket_count": 0,
    }


def test_selected_probability_union_and_agreement_are_exact() -> None:
    row = {
        "fundamental_delta_p3": "0.20",
        "fundamental_delta_p1": "-0.05",
        "fundamental_delta_p0": "-0.15",
        "calibrated_delta_p3": "0.10",
        "calibrated_delta_p1": "-0.01",
        "calibrated_delta_p0": "-0.09",
        "fundamental_p3": "0.60",
        "fundamental_p1": "0.25",
        "fundamental_p0": "0.15",
        "calibrated_p3": "0.50",
        "calibrated_p1": "0.31",
        "calibrated_p0": "0.19",
        "line_residual_mu": "0.1",
    }
    union = RUNNER.selected_probability_view(
        row, {"detector_family": "DELTA_P", "estimator_variant": "UNION"}
    )
    assert union is not None
    assert union[0] == "FUNDAMENTAL_T1_SCORE_DISTRIBUTION"
    assert union[2:] == ("3", "0", 0.2)
    agreement = RUNNER.selected_probability_view(
        row,
        {"detector_family": "DELTA_P", "estimator_variant": "MODEL_AGREEMENT"},
    )
    assert agreement is not None
    assert agreement[0] == "STRICT_AGREEMENT_WEAKER::CALIBRATED_MARKET_ESTIMATOR"
    assert agreement[2:] == ("3", "0", 0.1)
    disagreeing = dict(row)
    disagreeing["calibrated_delta_p1"] = "-0.40"
    assert (
        RUNNER.selected_probability_view(
            disagreeing,
            {
                "detector_family": "DELTA_P",
                "estimator_variant": "MODEL_AGREEMENT",
            },
        )
        is None
    )


def test_native_bootstrap_production_path_matches_python_and_blanks_zero_support() -> (
    None
):
    scratch = repo_scratch("bj190-bootstrap-")
    targets = [
        {
            "policy_id": "p1",
            "arm": "D_MATCH_ONLY_FULL",
            "issues": ["1", "2", "3"],
            "candidate_net": [100.0, -50.0, 25.0],
            "baseline_net": [0.0, -25.0, 10.0],
            "candidate_tax_net": [80.0, -50.0, 20.0],
            "baseline_tax_net": [0.0, -25.0, 8.0],
        },
        {
            "policy_id": "p0",
            "arm": "D_JOINT_SPARSE",
            "issues": [],
            "candidate_net": [],
            "baseline_net": [],
            "candidate_tax_net": [],
            "baseline_tax_net": [],
        },
    ]
    try:
        receipt = RUNNER.run_bootstrap_engine(scratch, targets, draws=64, threads=2)
        assert receipt["target_count"] == 2
        assert receipt["nonempty_target_count"] == 1
        with (scratch / "bootstrap_paired_lift_20000.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            rows = list(csv.DictReader(handle))
            assert handle.read() == ""
        assert len(rows) == 2
        assert None not in rows[0]
        zero = next(row for row in rows if row["policy_id"] == "p0")
        assert zero["common_issue_count"] == "0"
        for field in (
            "candidate_roi_mean",
            "candidate_roi_ci_low",
            "candidate_roi_ci_high",
            "lift_mean",
            "lift_ci_low",
            "lift_ci_high",
            "probability_lift_positive",
            "monte_carlo_se_lift",
            "candidate_tax_roi_mean",
            "candidate_tax_roi_ci_low",
            "candidate_tax_roi_ci_high",
            "tax_lift_mean",
            "tax_lift_ci_low",
            "tax_lift_ci_high",
        ):
            assert zero[field] == ""
    finally:
        shutil.rmtree(scratch)


def _factorial_row(net: float) -> dict[str, object]:
    return {
        "issue": "1",
        "settlement_status": "SETTLED",
        "planned_ticket_count": 50,
        "executed_ticket_count": 50,
        "planned_stake_yuan": 100.0,
        "stake_yuan": 100.0,
        "gross_pre_tax_yuan": 100.0 + net,
        "tax_yuan": 0.0,
        "pre_tax_net_yuan": net,
        "tax_adjusted_net_yuan": net,
        "hit_ticket_count": 1,
    }


def test_four_arm_factorial_interaction_is_not_pooled() -> None:
    records = {
        RUNNER.ARMS[0]: [_factorial_row(0.0)],
        RUNNER.ARMS[1]: [_factorial_row(10.0)],
        RUNNER.ARMS[2]: [_factorial_row(20.0)],
        RUNNER.ARMS[3]: [_factorial_row(35.0)],
    }
    result = RUNNER.factorial_summary("p", records)
    assert float(result["match_selection_lift"]) == pytest.approx(0.1)
    assert float(result["direction_lift"]) == pytest.approx(0.2)
    assert float(result["joint_total_lift"]) == pytest.approx(0.35)
    assert float(result["joint_interaction"]) == pytest.approx(0.05)


def test_generated_immutable_package_manifest_and_decision() -> None:
    package = ROOT / "results" / RUNNER.PACKAGE_NAME
    assert RUNNER.sha256_file(package / "SHA256SUMS.json") == (
        "642464aeb9be0a20fa37e6c5a2a01c459bbb5fe45ad330ea4dffd99aa302243b"
    )
    assert RUNNER.sha256_file(package / "CONTENT_IDENTITY.json") == (
        "b33393860827352d7f81baadb0cc7d0385383c089c4c2fe496c167130f197585"
    )
    manifest = json.loads((package / "SHA256SUMS.json").read_text())
    assert len(manifest) == 42
    assert set(manifest) == {
        path.name
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    for name, expected in manifest.items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected
    binding = json.loads(
        (package / "canonical_outcome_ledger_binding.json").read_text()
    )
    assert binding["receipt"]["trusted_match_count"] == 100_906
    assert binding["receipt"]["unavailable_match_count"] == 1_064
    assert binding["receipt"]["legacy_overlap_count"] == 46_802
    assert binding["receipt"]["legacy_disagreement_count"] == 0
    assert binding["identity_available_leg_distribution"] == {
        "3": 1,
        "4": 4,
        "5": 19,
        "6": 211,
        "7": 2_946,
    }
    decision = json.loads((package / "decision.json").read_text())
    assert decision["decision"] == "STRICT_INDEPENDENT_EV_REQUIRED"
    assert decision["positive_screen_count"] == 475
    assert decision["strict_stability_candidate_count"] == 18
    assert decision["promotion_authority"] is False
