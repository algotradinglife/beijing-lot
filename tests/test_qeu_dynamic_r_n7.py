from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil

import pandas as pd
import pytest

from src.qeu_dynamic_r_n7.contract import (
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    TICKETS,
)
from src.qeu_dynamic_r_n7.pipeline import (
    FEATURE_COLUMNS,
    _strict_bool_column,
    attach_expanding_reference,
    build_issue_action_features,
    construct_fixed_arms,
    learn_dynamic_r,
    verify_package,
)
from src.qeu_threshold_n7.pipeline import prepare_match_actions


def _cells(
    probability=(0.6, 0.3, 0.1),
    line=(0.9, 0.05, 0.05),
    *,
    year=2023,
    issue="23001",
    match=1,
    anchor=None,
):
    return pd.DataFrame({
        "issue": [issue] * 3,
        "issue_year": [year] * 3,
        "issue_anchor_ts": [
            pd.Timestamp(anchor or f"{year}-01-01", tz="UTC")
        ] * 3,
        "match_idx": [match] * 3,
        "outcome": ["3", "1", "0"],
        "q_eu": probability,
        "q_line": line,
    })


def test_probability_normalization_uses_zero_relative_tolerance():
    with pytest.raises(ValueError, match="q_eu triplets"):
        prepare_match_actions(_cells(probability=(0.6, 0.3, 0.100005)))


def test_expanding_reference_is_strictly_prior():
    parts = []
    for index in range(120):
        line_3 = 0.70 + (index % 20) * 0.005
        parts.append(_cells(
            line=(line_3, 0.08, 0.92 - line_3),
            year=2022,
            issue=f"22{index:03d}",
            match=index,
            anchor=f"2022-01-{1 + index // 20:02d}",
        ))
    parts.append(_cells(year=2023, issue="23001", match=999))
    actions = prepare_match_actions(pd.concat(parts, ignore_index=True))
    scored = attach_expanding_reference(actions)
    evaluated = scored[(scored.issue == "23001") & scored.support_changed]
    assert not evaluated.empty
    assert (evaluated.reference_cutoff < evaluated.issue_anchor_ts).all()
    assert evaluated.reference_actions.gt(0).all()


def _selected_matches() -> pd.DataFrame:
    rows = []
    for match in range(1, 8):
        row = prepare_match_actions(_cells(match=match)).iloc[0].to_dict()
        row.update({
            "pressure_z": float(match) / 10,
            "reference_scope": "GLOBAL",
            "reference_actions": 1000,
            "reference_median": 0.1,
            "reference_mad": 0.05,
            "reference_cutoff": pd.Timestamp("2022-12-31", tz="UTC"),
            "pressure_rank": match,
            "result_code": "3",
            "winning_sp": 2.0,
            "settlement_available": True,
        })
        rows.append(row)
    return pd.DataFrame(rows)


def test_fixed_r_curve_has_all_arms_and_ticket_level_point65():
    bundles, attribution, tickets = construct_fixed_arms(_selected_matches())
    assert set(bundles.r) == set(range(8))
    assert bundles.arm.nunique() == 8
    assert len(tickets) == 8 * TICKETS
    receipt = tickets.groupby("arm").agg(
        rows=("ticket_code", "size"), unique=("ticket_code", "nunique"),
        stake=("stake_cny", "sum"),
    )
    assert receipt.rows.eq(TICKETS).all()
    assert receipt.unique.eq(TICKETS).all()
    assert receipt.stake.eq(ISSUE_STAKE_CNY).all()
    r0 = bundles[bundles.r.eq(0)].iloc[0]
    assert r0.gross_cny == pytest.approx(8.0 * PAYOUT_FACTOR * 2.0**7)
    assert len(attribution) == 8 * 7


def test_issue_action_table_has_one_weightable_row_per_r():
    selected = _selected_matches()
    bundles, _, _ = construct_fixed_arms(selected)
    features = build_issue_action_features(selected, bundles)
    assert len(features) == 8
    assert set(features.candidate_r) == set(range(8))
    assert set(FEATURE_COLUMNS) <= set(features.columns)
    assert features.groupby("issue").size().eq(8).all()


def test_dynamic_model_never_uses_current_or_future_issue(monkeypatch):
    import src.qeu_dynamic_r_n7.pipeline as pipeline

    monkeypatch.setattr(pipeline, "MIN_TRAIN_ISSUES", 2)
    monkeypatch.setattr(pipeline, "MODEL_SEEDS", (11, 29))
    monkeypatch.setattr(pipeline, "MODEL_TREES", 8)
    monkeypatch.setattr(pipeline, "MODEL_MIN_SAMPLES_LEAF", 2)
    rows = []
    for issue_index in range(5):
        anchor = pd.Timestamp("2023-01-01", tz="UTC") + pd.Timedelta(days=issue_index)
        for r in range(8):
            row = {column: float(r + issue_index / 10) for column in FEATURE_COLUMNS}
            row.update({
                "issue": f"23{issue_index:03d}", "issue_year": 2023,
                "issue_anchor_ts": anchor, "candidate_r": r,
                "target_pnl_cny": float(-1024 + (r == issue_index % 8) * 5000),
                "target_gross_cny": float((r == issue_index % 8) * 5000),
                "target_hit": bool(r == issue_index % 8),
            })
            rows.append(row)
    predictions, selections, _ = learn_dynamic_r(pd.DataFrame(rows))
    learned = predictions[~predictions.cold_start]
    assert (learned.training_max_anchor < learned.issue_anchor_ts).all()
    assert predictions.groupby(["issue", "policy_arm"]).selected.sum().eq(1).all()
    assert selections.groupby(["issue", "policy_arm"]).size().eq(1).all()


def test_strict_boolean_validation_rejects_string_values():
    assert _strict_bool_column(pd.DataFrame({"flag": [True, False]}), "flag")
    assert not _strict_bool_column(
        pd.DataFrame({"flag": ["True", "FORGED_FALSE"]}), "flag"
    )


def test_committed_package_is_semantically_verified():
    root = Path(__file__).resolve().parents[1]
    package = root / "results/qeu_dynamic_r_n7"
    if not (package / "MANIFEST.json").exists():
        pytest.skip("result package not generated")
    assert verify_package(root, package)["status"] == "PASS"


def test_verifier_rejects_remanifested_string_boolean(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = root / "results/qeu_dynamic_r_n7"
    if not (source / "MANIFEST.json").exists():
        pytest.skip("result package not generated")
    package = tmp_path / "qeu_dynamic_r_n7"
    shutil.copytree(source, package)
    parity = pd.read_csv(package / "baseline_parity.csv")
    parity["match_identity_parity"] = "True"
    parity.loc[0, "match_identity_parity"] = "FORGED_FALSE"
    parity.to_csv(package / "baseline_parity.csv", index=False, lineterminator="\n")
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    relative = "results/qeu_dynamic_r_n7/baseline_parity.csv"
    manifest["files"][relative] = {
        "sha256": hashlib.sha256((package / "baseline_parity.csv").read_bytes()).hexdigest(),
        "bytes": (package / "baseline_parity.csv").stat().st_size,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    receipt = verify_package(root, package)
    assert receipt["status"] == "FAIL"
    assert "parity:match_identity_parity" in receipt["failures"]
