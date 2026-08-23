from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.qeu_threshold_n7.contract import ISSUE_STAKE_CNY, PAYOUT_FACTOR, TICKETS
from src.qeu_threshold_n7.pipeline import (
    _activation_mask,
    arm_definitions,
    attach_pressure_z,
    construct_and_settle,
    freeze_reference,
    prepare_match_actions,
    verify_package,
)


def _cells(probability=(0.6, 0.3, 0.1), line=(0.9, 0.05, 0.05), *, year=2023, issue="23001", match=1):
    return pd.DataFrame({
        "issue": [issue] * 3,
        "issue_year": [year] * 3,
        "issue_anchor_ts": [pd.Timestamp(f"{year}-01-01", tz="UTC")] * 3,
        "match_idx": [match] * 3,
        "outcome": ["3", "1", "0"],
        "q_eu": probability,
        "q_line": line,
    })


def test_prepare_enforces_probability_domain():
    with pytest.raises(ValueError, match="non-positive"):
        prepare_match_actions(_cells(probability=(-0.1, 0.6, 0.5)))


def test_prepare_uses_contract_qline_clip_and_retains_primitives():
    frame = _cells(
        probability=(0.000001, 0.4, 0.599999),
        line=(0.00000001, 0.2, 0.79999999),
    )
    row = prepare_match_actions(frame).iloc[0]
    assert set(row.qeu_support) == {"1", "0"}
    assert set(row.baseline_support) == {"1", "0"}
    assert not row.support_changed
    assert row.q_line_3 == pytest.approx(1e-8)
    assert row.qeu_score_3 == pytest.approx(np.log(1e-6 / 1e-4))


def test_probability_tie_omits_last_outcome_order():
    row = prepare_match_actions(_cells(probability=(1 / 3, 1 / 3, 1 / 3), line=(1 / 3,) * 3)).iloc[0]
    assert row.baseline_omitted == "0"
    assert row.qeu_omitted == "0"


def test_reference_and_z_are_strictly_prior():
    parts = []
    for year in (2020, 2021, 2022):
        for index in range(50):
            line_3 = 0.75 + 0.004 * (index % 25)
            parts.append(_cells(
                line=(line_3, 0.08, 0.92 - line_3),
                year=year, issue=f"{year}{index:03d}", match=index,
            ))
    reference_actions = prepare_match_actions(pd.concat(parts, ignore_index=True))
    reference, summary = freeze_reference(reference_actions)
    evaluated = prepare_match_actions(_cells(year=2023))
    scored = attach_pressure_z(evaluated, reference, summary)
    assert pd.Timestamp(reference["reference_max_anchor"]) < scored.issue_anchor_ts.min()
    assert scored.reference_scope.iloc[0] in {"GLOBAL", "STRATUM"}


def test_arm_surface_is_frozen_and_compact():
    reference = {
        "raw_quantiles": {f"Q{q:02d}": q / 100 for q in (50, 60, 70, 75, 80, 85, 90, 95)}
    }
    arms = arm_definitions(reference)
    assert len(arms) == 16
    assert {"R0", "R3_CORRECTED", "RAW_Q50", "Z_GE_1P0", "DUAL_Q75_Z1P0"} <= set(arms.arm)


def test_fixed_r3_pressure_tie_uses_match_identity_order():
    selected = pd.DataFrame({
        "match_idx": [1, 2, 3, 4],
        "support_changed": [True] * 4,
        "support_pressure": [0.2] * 4,
        "pressure_z": [1.0] * 4,
    })
    arm = pd.Series({"kind": "fixed_rank", "raw_cutoff": np.nan, "z_cutoff": np.nan})
    mask = _activation_mask(selected, arm)
    assert mask.tolist() == [True, True, True, False]


def test_threshold_comparison_is_inclusive():
    selected = pd.DataFrame({
        "support_changed": [True, True], "support_pressure": [0.2, 0.199],
        "pressure_z": [1.0, 0.99],
    })
    raw = pd.Series({"kind": "raw", "raw_cutoff": 0.2, "z_cutoff": np.nan})
    z = pd.Series({"kind": "z", "raw_cutoff": np.nan, "z_cutoff": 1.0})
    assert _activation_mask(selected, raw).tolist() == [True, False]
    assert _activation_mask(selected, z).tolist() == [True, False]


def test_construct_enumerates_128_and_applies_point65_once():
    rows = []
    labels = []
    for match in range(1, 8):
        action = prepare_match_actions(_cells(match=match)).iloc[0].to_dict()
        action.update({
            "pressure_z": 1.0, "reference_scope": "GLOBAL", "reference_actions": 1000,
            "reference_median": 0.1, "reference_mad": 0.1,
            "reference_cutoff": pd.Timestamp("2022-12-31", tz="UTC"),
        })
        rows.append(action)
        labels.extend([
            {"issue": "23001", "match_idx": match, "result_code": "3", "winning_sp": 2.0,
             "settlement_available": True}
        ])
    actions = pd.DataFrame(rows)
    arms = pd.DataFrame([
        {"arm": "R0", "kind": "control", "raw_quantile": np.nan, "raw_cutoff": np.nan, "z_cutoff": np.nan}
    ])
    bundles, _, tickets = construct_and_settle(actions, pd.DataFrame(labels), arms)
    assert len(tickets) == TICKETS
    assert tickets.ticket_code.nunique() == TICKETS
    assert tickets.stake_cny.sum() == ISSUE_STAKE_CNY
    assert bundles.iloc[0].gross_cny == pytest.approx(8.0 * PAYOUT_FACTOR * 2.0**7)


def test_committed_result_package_is_semantically_verified():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    package = root / "results/qeu_threshold_n7"
    if not package.exists():
        pytest.skip("result package not generated")
    assert verify_package(root, package)["status"] == "PASS"


def test_verifier_rejects_remanifested_performance_mutation(tmp_path):
    from pathlib import Path
    import hashlib
    import json
    import shutil

    root = Path(__file__).resolve().parents[1]
    source = root / "results/qeu_threshold_n7"
    if not source.exists():
        pytest.skip("result package not generated")
    package = tmp_path / "qeu_threshold_n7"
    shutil.copytree(source, package)
    performance = pd.read_csv(package / "performance.csv")
    performance.loc[0, "pnl_cny"] += 1_000_000
    performance.to_csv(package / "performance.csv", index=False, lineterminator="\n", float_format="%.12g")
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/qeu_threshold_n7/performance.csv"
    manifest["files"][relative] = {
        "sha256": hashlib.sha256((package / "performance.csv").read_bytes()).hexdigest(),
        "bytes": (package / "performance.csv").stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    receipt = verify_package(root, package)
    assert receipt["status"] == "FAIL"
    assert "performance-semantics" in receipt["failures"]


def test_all_planned_absolute_thresholds_fail_development_lift():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "results/qeu_threshold_n7/performance.csv"
    if not path.exists():
        pytest.skip("result package not generated")
    performance = pd.read_csv(path)
    threshold = performance[
        performance["issue_year"].eq(2023)
        & ~performance["arm"].isin(["R0", "R3_CORRECTED"])
    ]
    assert len(threshold) == 14
    assert threshold["matched_lift_r0_cny"].lt(0).all()
    assert threshold["ex_largest_lift_r0_cny"].lt(0).all()


def test_committed_paths_and_action_counts_are_complete():
    from pathlib import Path

    package = Path(__file__).resolve().parents[1] / "results/qeu_threshold_n7"
    if not package.exists():
        pytest.skip("result package not generated")
    paths = pd.read_csv(package / "capital_paths.csv")
    time_zero = paths[paths.issue_order.eq(0)]
    assert len(time_zero) == 32
    assert time_zero.issue.eq("TIME_ZERO").all()
    assert time_zero.capital_cny.eq(100_000).all()
    counts = pd.read_csv(package / "action_count_distribution.csv")
    for _, group in counts.groupby(["arm", "issue_year"]):
        assert set(group.activated_changes) == set(range(8))


def test_threshold_verifier_boolean_guard_rejects_strings():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "src/qeu_threshold_n7/pipeline.py"
    text = source.read_text()
    assert "is_bool_dtype(parity[column])" in text
    assert ".astype(bool).all()" not in text[text.index("def verify_package"):]
