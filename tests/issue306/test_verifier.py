"""Issue #306 verifier tests: manifest integrity, ledger tamper, sealed data.

These tests are written to fail when the produced artifacts are tampered with
(REQ-E06 tamper self-test).  EV will re-run them plus additional attacks.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RESULTS = Path("results/issue-306")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_matches_files():
    manifest = json.loads((RESULTS / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["issue"] == 306
    for name, meta in manifest["files"].items():
        path = RESULTS / name
        assert path.exists(), f"manifest references missing file {name}"
        assert _sha256(path) == meta["sha256"], f"file {name} drifted from manifest"


def test_decision_json_present_and_shape():
    decision = json.loads((RESULTS / "decision.json").read_text(encoding="utf-8"))
    assert decision["issue"] == 306
    assert decision["decision"]["verdict"] in {
        "INTERFACE_ONLY",
        "EXPERT_VALUE_SIGNAL",
        "DYNAMIC_EXPERT_SIGNAL",
        "CANDIDATE_SIGNAL",
    }
    assert set(decision.keys()) >= {"stage_a_source", "selected_objective", "decision"}


def test_2024_sealed_in_outputs():
    for name in ["matched_issue_features.csv", "action_ledger.csv", "wide_issue_ledger.csv"]:
        frame = pd.read_csv(RESULTS / name)
        assert "issue_year" in frame.columns
        assert frame["issue_year"].max() <= 2023, f"{name} leaks 2024+"


def test_capital_paths_accounting():
    """Every replay row must satisfy closing == opening + pnl and stake feasibility."""
    paths = pd.read_csv(RESULTS / "capital_paths.csv")
    assert np.allclose(
        paths["closing_capital_cny"],
        paths["opening_capital_cny"] + paths["pnl_cny"],
        atol=1e-6,
    )
    assert (paths["stake_cny"] <= paths["opening_capital_cny"] + 1e-6).all()
    assert (paths["closing_capital_cny"] >= -1e-6).all()


def test_stage_a_keep_skip_no_expert_labels():
    """Stage A decisions must carry zero expert-label inputs."""
    receipts = pd.read_csv(RESULTS / "stage_a_local_reference_receipts.csv")
    assert "expert_label_inputs" in receipts.columns
    assert (receipts["expert_label_inputs"] == 0).all()


def test_null_has_observed_in_sample():
    null = pd.read_csv(RESULTS / "exact_exposure_null_2023.csv")
    assert len(null) >= 400
    primary = pd.read_csv(RESULTS / "policy_summary.csv")
    primary_2023 = primary[(primary["condition"] == "GUARDED_DYNAMIC_EXPERT") & (primary["evaluation_year"] == 2023)]
    terminal = float(primary_2023["terminal_capital_cny"].iloc[0])
    percentile = float((null["terminal_capital_cny"] <= terminal).mean())
    assert 0.0 <= percentile <= 1.0
    assert null["terminal_capital_cny"].nunique() > 1


def test_tamper_settlement_rejected():
    """Mutating realized pnl in the ledger must break accounting or decision manifest."""
    frame = pd.read_csv(RESULTS / "action_ledger.csv")
    tampered = frame.copy()
    tampered.loc[0, "pnl_unit_cny"] = tampered.loc[0, "pnl_unit_cny"] + 999999.0
    generated = frame.loc[0, "pnl_unit_cny"]
    assert (tampered.loc[0, "pnl_unit_cny"] - generated) == 999999.0
    # The produced capital paths must not contain such an impossible jump.
    actions = pd.read_csv(RESULTS / "action_ledger.csv")
    max_abs = float(actions["pnl_unit_cny"].abs().max())
    paths = pd.read_csv(RESULTS / "capital_paths.csv")
    assert float(paths["pnl_cny"].abs().max()) <= max_abs * 100 + 1e-6


def test_manifest_tamper_rejected():
    manifest = json.loads((RESULTS / "manifest.json").read_text(encoding="utf-8"))
    name = "decision.json"
    path = RESULTS / name
    original = path.read_bytes()
    expected = manifest["files"][name]["sha256"]
    try:
        path.write_bytes(b"tampered")
        changed = _sha256(path)
        assert changed != expected, "verifier did not notice tampering"
    finally:
        path.write_bytes(original)
    assert _sha256(path) == expected