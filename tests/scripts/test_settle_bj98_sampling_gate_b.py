from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj98_sampling_gate_b.py"


def load():
    spec = importlib.util.spec_from_file_location("bj98_gate_b", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def raises(callback):
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_omission_encoding_rejects_duplicate_unknown_and_partial_codes():
    mod = load()
    assert mod.omitted_codes("") == [""] * 7
    raises(lambda: mod.omitted_codes("1:3"))
    raises(lambda: mod.omitted_codes("|".join(["1:3"] * 7)))
    raises(lambda: mod.omitted_codes("|".join(f"{n}:X" for n in range(1, 8))))


def test_metrics_applies_stake_once_and_tracks_drawdown():
    mod = load()
    metrics = mod.Metrics()
    assert metrics.add("YES", Decimal(10), Decimal(20)) == Decimal(10)
    assert metrics.add("NO", Decimal(10), Decimal(0)) == Decimal(-10)
    assert metrics.max_drawdown == Decimal(10)
    assert metrics.longest_losing_streak == 1


def test_hit_gross_applies_the_65_percent_factor_exactly_once():
    mod = load()
    assert mod.hit_gross("YES", Decimal(10)) == Decimal("13.0")
    assert mod.hit_gross("NO", Decimal(10)) == 0
    raises(lambda: mod.hit_gross("NO_BET", Decimal(10)))


def test_bootstrap_sampling_is_version_independent_and_bounded():
    mod = load()
    expected = list(mod.stable_bootstrap_indices("frozen-key", 7, 8))
    assert expected == list(mod.stable_bootstrap_indices("frozen-key", 7, 8))
    assert all(0 <= index < 7 for index in expected)


def test_manifest_rejects_wrong_identity_and_extra_file(tmp_path):
    mod = load()
    (tmp_path / "SHA256SUMS.json").write_text("{}")
    raises(lambda: mod.exact_manifest(tmp_path, "0" * 64))


def test_authenticated_snapshot_survives_later_original_source_replacement(tmp_path):
    mod = load()
    original = tmp_path / "source.csv"
    private = tmp_path / "private"
    private.mkdir()
    original.write_bytes(b"accepted snapshot\n")
    accepted_hash = mod.sha256(original)
    snapshot = mod.authenticated_snapshot(private, "input.csv", original, accepted_hash)
    original.write_bytes(b"replaced after authentication\n")
    assert snapshot.read_bytes() == b"accepted snapshot\n"
    assert mod.sha256(snapshot) == accepted_hash


def test_settlement_card_binds_private_leg_hash_and_factor():
    card = json.loads(
        (
            ROOT / "results/bj98_gate_b_outcome_settlement_v3/settlement_card.json"
        ).read_text()
    )
    assert card["factor"] == "0.65"
    assert card["bj95_safe_leg_decompressed_sha256"] == load().LEG_SHA
    assert card["fold_summary"] == "empirical fold range, not a confidence interval"
    assert "no implicit credit" in card["bankroll_execution"]
    assert card["portable_replay_identity"].startswith("CONTENT_SHA256SUMS.json")
    assert card["terminal_disposition"].startswith("NO_PROMOTION")
    assert set(card["private_snapshot_sha256"]) == {
        "bj98_sampling_frontier.csv.gz",
        "bj95_safe_legs.csv.gz",
        "bj95_canonical_outcome_join.csv",
        "bj95_group_frontier_settlement.csv",
        "bj91_group_arm_settlement.csv",
    }


def test_v2_package_has_required_diagnostics_and_matched_controls():
    package = ROOT / "results/bj98_gate_b_outcome_settlement_v3"
    controls = (
        (package / "quality_matched_control_comparison.csv").read_text().splitlines()
    )
    assert len(controls) > 6
    assert all(",3900," in row for row in controls[1:])
    assert any(row.startswith("BJ98,QUALITY_WEIGHTED_OMIT,") for row in controls[1:])
    assert any(
        row.startswith("BJ91,POINT_SP5_POSITIVE_EV,CONTROL,") for row in controls[1:]
    )
    calibration = (package / "calibration_diagnostics.csv").read_text().splitlines()
    sensitivity = (
        (package / "probability_misspecification_sensitivity.csv")
        .read_text()
        .splitlines()
    )
    assert len(calibration) > 1
    assert len(sensitivity) > 1
    assert {row.split(",")[2] for row in sensitivity[1:]} == {"0.80", "1.00", "1.20"}


def test_bankroll_execution_has_no_implicit_credit_path():
    rows = (
        (ROOT / "results/bj98_gate_b_outcome_settlement_v3/bankroll_execution.csv")
        .read_text()
        .splitlines()
    )
    assert len(rows) == 1 + 130 * 3
    assert any(row.split(",")[4] != "0" for row in rows[1:])


def test_packaged_runner_replays_portably_with_explicit_authenticated_inputs():
    package = ROOT / "results/bj98_gate_b_outcome_settlement_v3"
    with tempfile.TemporaryDirectory(dir=ROOT) as temp_name:
        temp = Path(temp_name)
        runner = temp / "settlement_runner.py"
        shutil.copy2(package / "settlement_runner.py", runner)
        replay = temp / "replay"
        command = [
            sys.executable,
            str(runner),
            "--output",
            str(replay),
            "--gate-a",
            str(ROOT / "results/bj98_gate_a_preoutcome_v1"),
            "--bj95-gate-a",
            str(ROOT / "results/bj95_gate_a_preoutcome_v5"),
            "--bj95-outcome",
            str(ROOT / "results/bj95_gate_b_outcome_settlement_v2r8"),
            "--bj91-control",
            str(ROOT / "results/bj91_gate_b_outcome_settlement_v1"),
        ]
        subprocess.run(command, cwd=temp, check=True, timeout=300)
        assert (replay / "CONTENT_SHA256SUMS.json").read_bytes() == (
            package / "CONTENT_SHA256SUMS.json"
        ).read_bytes()
