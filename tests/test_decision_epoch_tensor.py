from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from decision_epoch_tensor.builder import DecisionEpochBuildError, verify_package
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
