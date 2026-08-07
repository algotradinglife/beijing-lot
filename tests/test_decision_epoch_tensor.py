from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from decision_epoch_tensor.builder import (
    _assemble_frames,
    _namespace_manifest,
    DecisionEpochBuildError,
    verify_package,
    write_parquet,
)
from decision_epoch_tensor.contract import (
    ACTIVATION_UTC,
    CONTRACT_VERSION,
    OUTCOME_ORDER,
    epoch_cell_key,
    epoch_id,
    forbidden_inference_names,
)
from decision_epoch_tensor.loader import load_epoch_tensors


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/bj214_decision_epoch_tensor_v1"


def test_epoch_keys_are_stable_and_outcome_axis_is_canonical() -> None:
    identity = epoch_id("26083", "PROSPECTIVE_ACTIVATION", ACTIVATION_UTC, 7)
    assert identity == epoch_id(
        "26083", "PROSPECTIVE_ACTIVATION", ACTIVATION_UTC, 7
    )
    assert len(identity) == 64
    assert len({epoch_cell_key(identity, "26083-1", code) for code in OUTCOME_ORDER}) == 3
    with pytest.raises(ValueError, match="unsupported outcome"):
        epoch_cell_key(identity, "26083-1", "9")


def test_forbidden_inference_names_fail_closed() -> None:
    assert forbidden_inference_names(["final_score", "settlement_label"]) == [
        "final_score",
        "settlement_label",
    ]
    assert forbidden_inference_names(["predicted_final_sp"]) == []


def _positive_n7_fixture() -> dict[str, object]:
    match_indices = list(range(1, 11))
    matches = pd.DataFrame(
        {
            "match_id": [f"synthetic-{value}" for value in match_indices],
            "issue": ["99999"] * 10,
            "match_idx": match_indices,
            "year": [2026] * 10,
            "kickoff_ts_utc": [
                *[f"2026-08-07T12:{value:02d}:00Z" for value in range(1, 8)],
                "2026-08-07T12:08:00Z",
                "2026-08-07T09:34:30Z",
                "2026-08-07T12:10:00Z",
            ],
            "feature_cutoff_ts_utc": ["2026-08-07T09:30:00Z"] * 10,
            "identity_observed_ts_utc": ["2026-08-07T09:30:00Z"] * 10,
            "identity_timing_status": ["TIMESTAMPED_IDENTITY_ONLY"] * 10,
            "identity_source": ["synthetic"] * 10,
            "native_handicap_line": [0.0] * 10,
            "league_index": np.arange(10, dtype=float),
            "home_team_index": np.arange(10, dtype=float) + 10,
            "away_team_index": np.arange(10, dtype=float) + 20,
            "match_position_fraction": np.linspace(0.0, 1.0, 10),
            "cohort": ["prospective_post_activation"] * 10,
            "named_calibrated_present": [False] * 10,
            "named_euro_present": [False] * 10,
            "named_predicted_sp_present": [False] * 10,
        }
    )
    market = pd.DataFrame(
        {
            "id": match_indices,
            "match_id": matches["match_id"],
            "snapshot_ts_utc": [
                *["2026-08-07T09:34:00Z"] * 7,
                "2026-08-07T09:36:00Z",
                "2026-08-07T09:34:00Z",
                "2026-08-07T09:34:00Z",
            ],
            "sp_3": [2.10] * 10,
            "sp_1": [3.20] * 10,
            "sp_0": [3.60] * 10,
            "eu_h": [2.20] * 10,
            "eu_d": [3.30] * 10,
            "eu_a": [3.70] * 10,
            "source": ["synthetic"] * 10,
        }
    )
    eligibility = pd.DataFrame(
        {
            "issue": ["99999"] * 10,
            "match_idx": match_indices,
            "match_id": matches["match_id"],
            "fetched_at_utc": ["2026-08-07T09:34:00Z"] * 10,
            "source_updated_at_hkt": ["2026-08-07T17:33:00+08:00"] * 10,
            "source_updated_at_utc": ["2026-08-07T09:33:00Z"] * 10,
            "sale_status": [*["open"] * 9, "unknown"],
            "parlay_allowed": [*["allowed"] * 9, "unknown"],
            "capture_classification": ["synthetic"] * 10,
            "source_attribute": ["synthetic"] * 10,
            "publication_status": ["published"] * 10,
        }
    )
    windows = pd.DataFrame(
        columns=[
            "issue",
            "segment_idx",
            "freeze_at",
            "manual_frozen_at",
            "match_indices_json",
            "decision_epoch_utc",
        ]
    )
    return _assemble_frames(
        matches.iloc[0:0].copy(),
        matches,
        market,
        eligibility,
        windows,
        source_freeze_cutoff_utc="2026-08-07T10:00:00Z",
    )


def test_nonempty_n7_tensor_and_causal_rejections(tmp_path: Path) -> None:
    assembled = _positive_n7_fixture()
    diagnostics = assembled["epoch_diagnostics"]
    activation = diagnostics[
        diagnostics["epoch_rule"].eq("PROSPECTIVE_ACTIVATION")
    ].iloc[0]
    assert activation["evaluation_status"] == "EVALUATED"
    assert activation["candidate_matches"] == 9
    assert activation["causal_core_complete_matches"] == 8
    assert activation["strict_complete_eligible_matches"] == 7
    assert bool(activation["model_n7_gate_pass"])
    assert bool(activation["ticket_n7_gate_pass"])

    epoch_id_value = str(activation["epoch_id"])
    roster = assembled["roster_capability"]
    scoped = roster[roster["epoch_id"].eq(epoch_id_value)].set_index("match_idx")
    assert "CAUSAL_MARKET_SNAPSHOT_UNAVAILABLE" in scoped.loc[8, "rejection_reason"]
    assert "MATCH_ALREADY_STARTED" in scoped.loc[9, "rejection_reason"]
    assert "SALE_OPEN_NOT_VERIFIED" in scoped.loc[10, "rejection_reason"]
    assert "PARLAY_ALLOWED_NOT_VERIFIED" in scoped.loc[10, "rejection_reason"]

    inference = assembled["inference"]
    strict = inference["roster"]
    assert len(strict[strict["epoch_id"].eq(epoch_id_value)]) == 7
    identity = inference["cell_identity"]
    cells = identity[identity["epoch_id"].eq(epoch_id_value)]
    assert len(cells) == 21
    for _match, group in cells.groupby("match_id", sort=False):
        assert tuple(group["outcome_code"]) == OUTCOME_ORDER
        assert tuple(group["outcome_order"]) == (0, 1, 2)
    cell_indices = cells.index
    values = inference["feature_values"].loc[cell_indices]
    masks = inference["feature_masks"].loc[cell_indices]
    for feature in ("devig_euro_probability", "euro_1h_odds", "bj_sp_snapshot"):
        assert masks[feature].all()
        assert np.isfinite(values[feature]).all()

    namespace = tmp_path / "inference"
    namespace.mkdir()
    for name, frame in inference.items():
        write_parquet(namespace / f"{name}.parquet", frame)
    _namespace_manifest(namespace, "decision_epoch_outcome_unexposed_inference")
    tensors = load_epoch_tensors(tmp_path)
    tensor = next(value for value in tensors if value.epoch_id == epoch_id_value)
    assert tensor.match_ids == tuple(f"synthetic-{value}" for value in range(1, 8))
    assert tensor.values.shape == (7, 3, 24)
    assert tensor.masks.shape == (7, 3, 24)


def test_frozen_package_has_no_outcome_namespace_and_no_strict_false_positive() -> None:
    receipt = verify_package(PACKAGE)
    assert receipt == {
        "contract_version": CONTRACT_VERSION,
        "disposition": "BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT",
        "epochs": 2855,
        "features": 24,
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "source_manifest_sha256": (
            "f05e02404a91bb63d2a40c55bbe572964cf681057df72f7c69c6145c4c78572d"
        ),
        "status": "PASS",
        "strict_cells": 0,
        "strict_roster_rows": 0,
    }
    tensors = load_epoch_tensors(PACKAGE)
    assert len(tensors) == 2855
    assert all(tensor.values.shape == (0, 3, 24) for tensor in tensors)
    assert not (PACKAGE / "labels").exists()
    roster = pd.read_parquet(PACKAGE / "audit/roster_capability.parquet")
    assert not roster["strict_complete_eligible_match"].any()
    assert roster["sale_open_verified"].sum() == 0
    assert roster["parlay_allowed_verified"].sum() == 0
    decision = json.loads(
        (PACKAGE / "analysis/decision.json").read_text(encoding="utf-8")
    )
    assert decision["disposition"] == "BLOCKED_INSUFFICIENT_CAUSAL_SUPPORT"
    assert decision["representative_rule"]["epoch_rule"] == (
        "MEDIAN_KICKOFF_MINUS_10H"
    )
    assert decision["representative_rule"]["sensitivity_rules_do_not_vote"] is True
    assert decision["model_learning_gate_pass"] is False
    assert decision["ticket_operability_gate_pass"] is False
    activation = decision["prospective_activation_sensitivity"]
    assert activation["causal_core_complete_matches"] == 269
    assert activation["candidate_matches"] == 289
    assert activation["model_core_coverage"] == pytest.approx(269 / 289)
    assert "Sale/parlay recovery" in decision["blocking_facts"][
        "ticket_operability"
    ][1]
    coverage = pd.read_csv(PACKAGE / "audit/coverage_by_cohort_rule.csv")
    controlling = coverage[coverage["controlling_representative_rule"]]
    assert set(controlling["epoch_rule"]) == {"MEDIAN_KICKOFF_MINUS_10H"}
    assert controlling.groupby("cohort")["epochs"].sum().le(
        coverage.groupby("cohort")["issues"].max()
    ).all()


def test_verifier_rejects_manifest_only_rehash_attack(tmp_path: Path) -> None:
    attacked = tmp_path / "package"
    attacked.mkdir()
    for source in PACKAGE.iterdir():
        if source.is_dir():
            import shutil

            shutil.copytree(source, attacked / source.name)
        else:
            (attacked / source.name).write_bytes(source.read_bytes())
    decision_path = attacked / "analysis/decision.json"
    payload = json.loads(decision_path.read_text(encoding="utf-8"))
    payload["disposition"] = "READY_FOR_204"
    decision_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    sums_path = attacked / "SHA256SUMS.json"
    sums = json.loads(sums_path.read_text(encoding="utf-8"))
    from hashlib import sha256

    sums["analysis/decision.json"] = sha256(decision_path.read_bytes()).hexdigest()
    sums_path.write_text(json.dumps(sums, sort_keys=True), encoding="utf-8")
    with pytest.raises(DecisionEpochBuildError):
        verify_package(attacked)
