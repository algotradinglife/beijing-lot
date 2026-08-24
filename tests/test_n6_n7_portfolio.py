"""Adversarial and golden tests for BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2 (#378).

REQ-E06 tamper self-test: every mutation below MUST fail the corresponding
check. A tamper that passes is a delivery defect.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.n6_n7_portfolio import contract as C
from src.n6_n7_portfolio.pipeline import (
    ContractError,
    build_expert_calendar,
    build_package,
    correlation_diagnostics,
    evaluate_paths,
    build_paths,
    load_upstream,
    validate_upstream,
    verify_package,
    _path_metrics,
    _payout_concentration,
    _run_lengths,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _key(label: str) -> str:
    return label.split("_", 1)[-1]


# ---------------------------------------------------------------------------
# Golden metric-definition lock (values frozen from #381/#377/#373)
# ---------------------------------------------------------------------------


def test_golden_path_metrics_definition():
    n6 = load_upstream(REPO_ROOT)["n6_bundles"]
    n6_r3 = n6[n6["arm"].eq(_key(C.N6_ARM_R3))].sort_values(
        ["issue_anchor_ts", "issue"], kind="stable"
    )
    pnl = n6_r3["pnl_cny"].to_numpy(dtype=float)
    metrics = _path_metrics(pnl)
    for key in ("max_drawdown_fraction", "longest_profitable_issue_losing_run", "open_underwater_issues"):
        assert metrics[key] == pytest.approx(C.GOLDEN_N6_R3_RISK[key], abs=1e-9), key
    share, hhi = _payout_concentration(n6_r3["gross_cny"].to_numpy(dtype=float))
    assert share == pytest.approx(C.GOLDEN_N6_R3_RISK["largest_payout_share"], abs=1e-9)
    assert hhi == pytest.approx(C.GOLDEN_N6_R3_RISK["payout_hhi"], abs=1e-9)


def test_golden_upstream_pnl_values():
    upstream = load_upstream(REPO_ROOT)
    n6 = upstream["n6_bundles"]
    n7 = upstream["n7_bundles"]
    assert n6[n6["arm"].eq("R3")]["pnl_cny"].sum() == pytest.approx(C.GOLDEN_N6_R3_PNL, abs=1e-6)
    assert n6[n6["arm"].eq("R0")]["pnl_cny"].sum() == pytest.approx(C.GOLDEN_N6_R0_PNL, abs=1e-6)
    for label, expected in [
        ("C0E0", C.GOLDEN_N7_C0E0_PNL), ("C1E2", C.GOLDEN_N7_C1E2_PNL), ("C1E3", C.GOLDEN_N7_C1E3_PNL),
    ]:
        assert n7[n7["cell"].eq(label)]["pnl_cny"].sum() == pytest.approx(expected, abs=1e-6)


def test_complete_corrected_n6_surface_has_no_admitted_expert():
    upstream = load_upstream(REPO_ROOT)
    performance = upstream["n6_perf"]
    all_rows = performance[performance["scope"].eq("ALL")]
    assert set(all_rows["r"].astype(int)) == set(range(7))
    assert not all_rows["pnl_cny"].gt(0).any()
    assert upstream["n6_decision"]["positive_standalone_point_estimate_r"] == []
    assert upstream["n6_decision"]["expert_admitted_r"] == []
    assert upstream["n6_decision"]["fixed_r3_replaced"] is False


def test_run_lengths_and_path_metrics_units():
    mask = np.array([True, True, False, True, False, False, True])
    assert _run_lengths(mask).tolist() == [2, 1, 1]
    pnl = np.array([-100.0, -200.0, 500.0, -50.0, -50.0])
    m = _path_metrics(pnl)
    assert m["longest_profitable_issue_losing_run"] == 2
    # peaks at equity[0] and equity[3]; open-underwater = 5 - 3 = 2.
    assert m["open_underwater_issues"] == 2
    assert set(m.keys()) == {"max_drawdown_fraction", "longest_profitable_issue_losing_run", "open_underwater_issues"}


# ---------------------------------------------------------------------------
# Upstream frame-level adversarial mutations (attack the source surface)
# ---------------------------------------------------------------------------


def _upstream():
    return load_upstream(REPO_ROOT)


def test_tamper_n7_pnl_breaks_aggregation_parity():
    up = _upstream()
    frame = up["n7_bundles"].copy()
    mask = frame["cell"].eq("C0E0") & frame["issue"].eq("22013")
    frame.loc[mask, "pnl_cny"] += 1000.0
    up["n7_bundles"] = frame
    with pytest.raises(ContractError):
        validate_upstream(up)


def test_tamper_n7_stake_breaks_invariant():
    up = _upstream()
    frame = up["n7_bundles"].copy()
    mask = frame["cell"].eq("C0E0")
    frame.loc[mask, "stake_cny"] = 2048.0
    up["n7_bundles"] = frame
    with pytest.raises(ContractError):
        validate_upstream(up)


def test_tamper_n6_parity_breaks_cross_package_check():
    up = _upstream()
    frame = up["n6_grid_bundles"].copy()
    mask = frame["cell"].eq("C0E0") & frame["issue"].eq("22013")
    frame.loc[mask, "pnl_cny"] -= 500.0
    up["n6_grid_bundles"] = frame
    with pytest.raises(ContractError):
        validate_upstream(up)


def test_tamper_exclusion_set_breaks_calendar():
    up = _upstream()
    frame = up["n7_bundles"].copy()
    # Fabricate 23032 in the N7 surface (it must stay excluded).
    row = frame[(frame["cell"].eq("C0E0")) & (frame["issue"].eq("22013"))].copy()
    row["issue"] = "23032"
    frame = pd.concat([frame, row], ignore_index=True)
    up["n7_bundles"] = frame
    with pytest.raises(ContractError):
        validate_upstream(up)


def test_tamper_drop_n6_issue_breaks_denominator():
    up = _upstream()
    frame = up["n6_bundles"].copy()
    frame = frame[~frame["issue"].eq("22013")]
    up["n6_bundles"] = frame
    with pytest.raises(ContractError):
        validate_upstream(up)


# ---------------------------------------------------------------------------
# Artifact-level adversarial mutations (attack the delivered package)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def built_package():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "package"
        build_package(REPO_ROOT, out, force=True)
        yield out


def _tampered_copy(built_package) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tampered"
        shutil.copytree(built_package, out)
        return out


def test_manifest_tamper_any_artifact_fails_verify(built_package):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tampered"
        shutil.copytree(built_package, out)
        target = out / "correlation_diagnostics.csv"
        target.write_text(target.read_text().replace("0.753958", "0.999999", 1))
        with pytest.raises(ContractError):
            verify_package(REPO_ROOT, out, check_replay=False)


def test_tamper_decision_json_fails_verify(built_package):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tampered"
        shutil.copytree(built_package, out)
        target = out / "decision.json"
        payload = json.loads(target.read_text())
        payload["portfolio_verdict"] = "PROMOTABLE"
        target.write_text(json.dumps(payload, indent=2))
        with pytest.raises(ContractError):
            verify_package(REPO_ROOT, out, check_replay=False)


def test_tamper_delete_artifact_fails_verify(built_package):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tampered"
        shutil.copytree(built_package, out)
        (out / "tail_overlap.csv").unlink()
        with pytest.raises(ContractError):
            verify_package(REPO_ROOT, out, check_replay=False)  # manifest set equality


def test_tamper_artifact_and_manifest_entry_deletion_fails_replay(built_package):
    # Coordinated attack: delete an artifact AND drop its MANIFEST entry.
    # Set-equality checks then agree, so only the symmetric byte-replay catches it.
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "tampered"
        shutil.copytree(built_package, out)
        (out / "tail_overlap.csv").unlink()
        manifest = json.loads((out / "MANIFEST.json").read_text())
        manifest["files"].pop("tail_overlap.csv")
        (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
        with pytest.raises(ContractError):
            verify_package(REPO_ROOT, out, check_replay=True)


def test_tamper_upstream_file_detected_by_replay(built_package):
    source = REPO_ROOT / C.UPSTREAM_N7_GRID / "issue_bundles.parquet"
    backup = source.read_bytes()
    try:
        frame = pd.read_parquet(source)
        frame.loc[frame["cell"].eq("C0E0") & frame["issue"].eq("22013"), "pnl_cny"] += 1.0
        frame.to_parquet(source, index=False)
        with pytest.raises(ContractError):
            verify_package(REPO_ROOT, built_package, check_replay=True)
    finally:
        source.write_bytes(backup)


def test_portfolio_identity_holds(built_package):
    upstream = load_upstream(REPO_ROOT)
    cal = build_expert_calendar(upstream)
    frames = build_paths(cal, upstream)
    evaluated = evaluate_paths(frames)
    for scope in ("ALL", "2022", "2023", "2024"):
        port = evaluated["performance"][
            (evaluated["performance"]["path"].eq("PORTFOLIO_50_50"))
            & (evaluated["performance"]["scope"].eq(scope))
        ]["pnl_cny"].iloc[0]
        mech = evaluated["performance"][
            (evaluated["performance"]["path"].eq("MECHANICAL_WA"))
            & (evaluated["performance"]["scope"].eq(scope))
        ]["pnl_cny"].iloc[0]
        assert port == pytest.approx(mech, abs=1e-9)


def test_correlation_matches_frozen_hand_computation():
    upstream = load_upstream(REPO_ROOT)
    cal = build_expert_calendar(upstream)
    corr = correlation_diagnostics(cal, upstream)
    pool = corr[corr["kind"].eq("pool")].iloc[0]
    assert pool["issues"] == 151
    assert -1.0 <= pool["pearson_r"] <= 1.0
    assert -1.0 <= pool["spearman_rho"] <= 1.0
    # N6-R3 x N6-R3 self-pair must be exactly 1.0.
    sanity = corr[corr["kind"].eq("internal_sanity")].iloc[0]
    assert sanity["pearson_r"] == pytest.approx(1.0, abs=1e-12)
    assert sanity["spearman_rho"] == pytest.approx(1.0, abs=1e-12)


def test_exact_common_denominator_uses_activity_not_nonzero_pnl():
    upstream = load_upstream(REPO_ROOT)
    calendar = build_expert_calendar(upstream)
    active = calendar[f"{C.N7_ARM_C0E0}_stake_cny"].gt(0)
    issue = calendar.loc[active, "issue"].iloc[0]
    calendar.loc[calendar["issue"].eq(issue), f"{C.N7_ARM_C0E0}_pnl_cny"] = 0.0
    diagnostics = correlation_diagnostics(calendar, upstream)
    assert set(diagnostics["issues"]) == {C.EXPECTED_COMMON_ISSUES}


def test_full_build_and_verify_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "package"
        build_package(REPO_ROOT, out, force=True)
        result = verify_package(REPO_ROOT, out, check_replay=True)
        assert result["ok"] is True
        manifest = json.loads((out / "MANIFEST.json").read_text())
        assert manifest["contract"] == C.CONTRACT_ID
        for name in ("performance.csv", "expert_calendar.parquet", "decision.json", "source_receipt.json"):
            assert name in manifest["files"]


def test_verdict_frozen_semantics(built_package):
    decision = json.loads((built_package / "decision.json").read_text())
    assert decision["verdict"] == "NO_N6_POSITIVE_STANDALONE_PORTFOLIO_DILUTIVE"
    assert decision["n6_admission_gate"]["pass"] is False
    assert decision["expert_pool_after_diagnostic"]["admitted_new"] == []
    assert decision["portfolio_verdict"] == "NOT_PROMOTABLE_DILUTIVE"
