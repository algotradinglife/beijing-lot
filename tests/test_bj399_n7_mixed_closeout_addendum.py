"""Focused + adversarial mutation tests for issue #399 close-out addendum.

Contract BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1 (parent #394).  These tests
cover:

- the two corrected statistics are semantically distinct (counterexample +
  sign-changing regression coverage drawn from the audited #394 contrasts);
- the frozen board reproduces exactly from the committed bundles (parity);
- the deprecated `matched_ex_largest_lift_cny` value equals the paired-delta
  sensitivity (its true semantics) and is NOT the armwise ex-largest;
- metadata reconciles to producer configuration;
- decision invariance;
- adversarial mutation: every verifier gate FAILS when any committed
  artifact is tampered with (corrected CSV, per-issue frame, receipt binding,
  report machine block, original #394 package, manifest).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.n7_mixed_full_history import closeout as C
from src.n7_mixed_full_history.contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    MOVING_BLOCK_LENGTH,
)
from scripts import verify_n7_mixed_closeout_addendum as V

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PKG = REPO_ROOT / C.SOURCE_PACKAGE
ADD_PKG = REPO_ROOT / C.ADDENDUM_PACKAGE

TERMINAL_VERDICT = "NO_MIXED_N7_EXTENSION_INCREMENT"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def bundles() -> pd.DataFrame:
    return pd.read_parquet(SOURCE_PKG / "bundles.parquet")


@pytest.fixture(scope="module")
def frozen() -> pd.DataFrame:
    return pd.read_csv(SOURCE_PKG / "matched_contrasts.csv")


@pytest.fixture(scope="module")
def corrected() -> pd.DataFrame:
    return pd.read_csv(ADD_PKG / "matched_contrasts_corrected.csv")


@pytest.fixture(scope="module")
def counters() -> pd.DataFrame:
    return pd.read_csv(ADD_PKG / "semantic_counterexamples.csv")


@pytest.fixture(scope="module")
def paired_frame() -> pd.DataFrame:
    return pd.read_csv(ADD_PKG / "paired_delta_frame.csv")


def _recompute_from_frame(frame: pd.DataFrame) -> dict[str, float | str | int]:
    """Inline independent recomputation (does not import producer arithmetic)."""
    pnl_a = frame["pnl_a"].to_numpy(float)
    gross_a = frame["gross_a"].to_numpy(float)
    pnl_b = frame["pnl_b"].to_numpy(float)
    gross_b = frame["gross_b"].to_numpy(float)
    issues = frame["issue"].astype(str).tolist()
    delta = pnl_a - pnl_b
    subj_idx = int(np.argmax(gross_a))
    ref_idx = int(np.argmax(gross_b))
    largest_idx = int(np.argmax(np.abs(delta)))
    return {
        "issues": int(len(frame)),
        "subject_ex_largest_pnl_cny": float(pnl_a.sum() - pnl_a[subj_idx]),
        "reference_ex_largest_pnl_cny": float(pnl_b.sum() - pnl_b[ref_idx]),
        "armwise_ex_largest_lift_cny": float(
            (pnl_a.sum() - pnl_a[subj_idx]) - (pnl_b.sum() - pnl_b[ref_idx])
        ),
        "subject_largest_payout_issue": str(issues[subj_idx]),
        "reference_largest_payout_issue": str(issues[ref_idx]),
        "largest_abs_paired_delta_signed_cny": float(delta[largest_idx]),
        "largest_abs_paired_delta_issue": str(issues[largest_idx]),
        "largest_absolute_paired_delta_sensitivity_cny": float(
            delta.sum() - delta[largest_idx]
        ),
    }


# ---------------------------------------------------------------------------
# Semantic distinction (contract requirement 5)
# ---------------------------------------------------------------------------

def test_two_statistics_are_independent_semantics(corrected, counters) -> None:
    assert {"armwise_ex_largest_lift_cny", "largest_absolute_paired_delta_sensitivity_cny"}.issubset(
        corrected.columns
    )
    # independent code paths: per-arm gross argmax removal vs paired delta argmax
    assert int(counters["differ"].sum()) >= 1
    assert int(counters["sign_change"].sum()) >= 1


def test_counterexample_and_sign_changing_regression_coverage(counters) -> None:
    """Audited #394 contrasts must contain at least one row where the two
    statistics differ and at least one where they flip sign."""
    assert (counters["role"].eq("counterexample_differ")).any()
    assert (counters["role"].eq("sign_changing_regression")).any()
    # every scope contributes at least one differing row
    for scope in ("PRE_2025", "EXTENSION_2025_2026", "ALL"):
        sub = counters[counters["scope"].eq(scope)]
        assert sub["differ"].any(), f"{scope} has no differing row"


def test_deprecated_field_value_was_paired_delta_sensitivity_not_armwise(
    frozen, corrected
) -> None:
    """The merged `matched_ex_largest_lift_cny` equals the paired-delta
    sensitivity -- NOT the armwise ex-largest. This is the semantic defect the
    addendum repairs."""
    merged = corrected.merge(
        frozen[["scope", "contrast", "matched_ex_largest_lift_cny"]],
        on=["scope", "contrast"],
        validate="one_to_one",
    )
    for row in merged.itertuples(index=False):
        assert row.matched_ex_largest_lift_cny == pytest.approx(
            row.largest_absolute_paired_delta_sensitivity_cny, rel=1e-12, abs=1e-9
        )
    # and they are NOT the same statistic: at least one row differs from
    # the armwise ex-largest with a sign change
    assert (merged["matched_ex_largest_lift_cny"] != merged["armwise_ex_largest_lift_cny"]).any()


def test_reconstruction_matches_committed(corrected, paired_frame) -> None:
    num_cols = [
        "subject_ex_largest_pnl_cny",
        "reference_ex_largest_pnl_cny",
        "armwise_ex_largest_lift_cny",
        "largest_abs_paired_delta_signed_cny",
        "largest_absolute_paired_delta_sensitivity_cny",
    ]
    str_cols = [
        "subject_largest_payout_issue",
        "reference_largest_payout_issue",
        "largest_abs_paired_delta_issue",
    ]
    expected = corrected.set_index(["scope", "contrast"])
    for (scope, contrast), grp in paired_frame.groupby(["scope", "contrast"], sort=True):
        est = _recompute_from_frame(grp.reset_index(drop=True))
        row = expected.loc[(scope, contrast)]
        assert row["subject_schedule"] == "MIXED_50_50", (scope, contrast)
        assert row["reference_schedule"] in {"R3_STANDALONE", "C1E3_STANDALONE", "R0_COMPARATOR"}, (scope, contrast)
        for col in num_cols:
            assert est[col] == pytest.approx(row[col], rel=1e-9, abs=1e-6), (scope, contrast, col)
        for col in str_cols:
            assert str(est[col]) == str(row[col]), (scope, contrast, col)


def test_frozen_board_reproduces_exactly(bundles, frozen) -> None:
    C.assert_frozen_board_parity(bundles, frozen)


def test_armwise_removes_own_largest_payout_not_paired_delta(
    corrected, counters
) -> None:
    """The armwise stat removes each arm's own largest gross-payout issue;
    in at least one audited contrast that issue differs from the largest
    absolute paired-delta issue and the two statistics are not interchangeable."""
    diff_issue = corrected[
        corrected["subject_largest_payout_issue"].ne(corrected["largest_abs_paired_delta_issue"])
    ]
    assert not diff_issue.empty
    merged = counters.set_index(["scope", "contrast"])
    for row in diff_issue.itertuples(index=False):
        assert merged.loc[(row.scope, row.contrast), "differ"], (row.scope, row.contrast)


# ---------------------------------------------------------------------------
# Metadata + decision invariance
# ---------------------------------------------------------------------------

def test_moving_block_metadata_reconciles_to_producer_config() -> None:
    meta = json.loads((ADD_PKG / "moving_block_metadata.json").read_text(encoding="utf-8"))
    assert meta["estimand"] == "paired_mean_cny_per_issue"
    assert meta["unit"] == "CNY_PER_ISSUE"
    assert meta["block_length"] == int(MOVING_BLOCK_LENGTH)
    assert meta["draw_count"] == int(BOOTSTRAP_DRAWS)
    assert meta["seed"] == int(BOOTSTRAP_SEED)
    frozen = pd.read_csv(SOURCE_PKG / "matched_contrasts.csv")
    for row in meta["rows"]:
        expected = frozen.loc[
            (frozen["scope"].eq(row["scope"])) & (frozen["contrast"].eq(row["contrast"])),
            "moving_block_p05_lift_cny",
        ]
        assert len(expected) == 1 and expected.iloc[0] == pytest.approx(
            row["moving_block_p05_lift_cny_per_issue"], rel=1e-9, abs=1e-9
        )


def test_decision_invariance() -> None:
    decision = json.loads((SOURCE_PKG / "decision.json").read_text(encoding="utf-8"))
    assert decision["verdict"] == TERMINAL_VERDICT
    assert decision.get("strategy_promoted") is False
    assert decision.get("promotion_unlock_210") is False
    assert [int(x) for x in decision.get("preserved_issues", [])] == [210, 218]
    dr = json.loads((ADD_PKG / "DECISION_RECEIPT.json").read_text(encoding="utf-8"))
    assert dr["verdict_unchanged"] == TERMINAL_VERDICT
    assert dr["strategy_promoted_unchanged"] is False


def test_addendum_receipt_binds_frozen_merge() -> None:
    receipt = json.loads((ADD_PKG / "ADDENDUM_RECEIPT.json").read_text(encoding="utf-8"))
    assert receipt["source"]["source_merge_sha"] == C.SOURCE_MERGE_SHA
    assert receipt["source"]["source_merge_pr"] == 398
    assert receipt["deprecation"]["deprecated_field"] == "matched_ex_largest_lift_cny"
    assert receipt["deprecation"]["status"] == "DEPRECATED"


def test_report_machine_block_parity() -> None:
    report = (REPO_ROOT / C.REPORT_PATH).read_text(encoding="utf-8")
    block = V._extract_machine_block(report)
    machine = (ADD_PKG / "matched_contrasts_corrected.csv").read_text(
        encoding="utf-8"
    ).rstrip("\n")
    assert block == machine


# ---------------------------------------------------------------------------
# Adversarial mutation tests (tamper self-test, REQ-E06)
# ---------------------------------------------------------------------------

def _mini_repo(tmp_path: Path) -> Path:
    """Copy the frozen source package + addendum package + report + pipeline
    source into a throwaway repo root so mutations never touch committed data."""
    root = tmp_path / "repo"
    (root / C.SOURCE_PACKAGE).parent.mkdir(parents=True, exist_ok=True)
    (root / C.ADDENDUM_PACKAGE).parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE_PKG, root / C.SOURCE_PACKAGE)
    shutil.copytree(ADD_PKG, root / C.ADDENDUM_PACKAGE)
    report = root / C.REPORT_PATH
    report.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / C.REPORT_PATH, report)
    pipe = root / "src/n7_mixed_full_history/pipeline.py"
    pipe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "src/n7_mixed_full_history/pipeline.py", pipe)
    return root


def test_verifier_passes_on_pristine_coverage_checks(tmp_path) -> None:
    root = _mini_repo(tmp_path)
    pkg = root / C.ADDENDUM_PACKAGE
    receipt = json.loads((pkg / "ADDENDUM_RECEIPT.json").read_text(encoding="utf-8"))
    V._check_e01_e02(root, receipt)
    V._check_e03_e04(root, pkg)
    V._check_e05(root, pkg)
    V._check_e06_report(root, pkg)
    V._check_e07(root, receipt, pkg)


def _mutate_and_expect_fail(tmp_path, mutate, check, *, e01=False, e07=False) -> None:
    root = _mini_repo(tmp_path)
    pkg = root / C.ADDENDUM_PACKAGE
    mutate(root, pkg)
    receipt = json.loads((pkg / "ADDENDUM_RECEIPT.json").read_text(encoding="utf-8"))
    with pytest.raises(V.VerifyError):
        if e07:
            check(root, receipt, pkg)
        elif e01:
            check(root, receipt)
        else:
            check(root, pkg)


def test_tamper_armwise_value_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = pkg / "matched_contrasts_corrected.csv"
        df = pd.read_csv(p)
        df.loc[0, "armwise_ex_largest_lift_cny"] += 100.0
        p.write_text(df.to_csv(index=False), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e03_e04)


def test_tamper_sensitivity_value_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = pkg / "matched_contrasts_corrected.csv"
        df = pd.read_csv(p)
        df.loc[0, "largest_absolute_paired_delta_sensitivity_cny"] -= 100.0
        p.write_text(df.to_csv(index=False), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e03_e04)


def test_tamper_paired_frame_row_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = pkg / "paired_delta_frame.csv"
        df = pd.read_csv(p)
        df.loc[0, "pnl_a"] += 1.0
        p.write_text(df.to_csv(index=False), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e03_e04)


def test_tamper_receipt_binding_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = pkg / "ADDENDUM_RECEIPT.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["source"]["source_merge_sha"] = "0" * 40
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e01_e02, e01=True)


def test_tamper_report_machine_block_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = root / C.REPORT_PATH
        text = p.read_text(encoding="utf-8")
        block = V._extract_machine_block(text)
        mutated = block.replace("vs_R3", "vs_R3_MUT", 1)
        assert mutated != block
        p.write_text(text.replace(block, mutated), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e06_report)


def test_tamper_original_package_file_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = root / C.SOURCE_PACKAGE / "decision.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["verdict"] = "MIXED_N7_EXTENSION_HISTORICAL_SIGNAL_NO_PROMOTION"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e01_e02, e01=True)


def test_tamper_original_manifest_hash_too_fails_verifier(tmp_path) -> None:
    """A coordinated edit of a package file + its manifest + the receipt must
    still fail: the receipt binds the ORIGINAL manifest hash as committed at
    the frozen merge SHA, which a working-tree rewrite cannot forge."""

    def mutate(root, pkg):
        src_pkg = root / C.SOURCE_PACKAGE
        # mutate a primitive file
        (src_pkg / "bundles.parquet").write_bytes(b"tampered")
        # and rewrite the manifest to claim the tampered hash, plus the receipt
        manifest = json.loads((src_pkg / "MANIFEST.json").read_text(encoding="utf-8"))
        manifest["files"]["bundles.parquet"]["sha256"] = V._sha256_file(src_pkg / "bundles.parquet")
        manifest["files"]["bundles.parquet"]["bytes"] = 8
        (src_pkg / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        receipt_path = pkg / "ADDENDUM_RECEIPT.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["source"]["original_package_manifest_sha256"] = V._sha256_file(src_pkg / "MANIFEST.json")
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")

    root = _mini_repo(tmp_path)
    pkg = root / C.ADDENDUM_PACKAGE
    mutate(root, pkg)
    receipt = json.loads((pkg / "ADDENDUM_RECEIPT.json").read_text(encoding="utf-8"))
    # the immutable anchor is the merge-commit blob hash of the ORIGINAL manifest
    anchor = V._manifest_sha_at_merge(REPO_ROOT)
    with pytest.raises(V.VerifyError):
        V._check_e01_e02(root, receipt, expected_manifest_sha=anchor)


def test_tamper_decision_receipt_fails_verifier(tmp_path) -> None:
    def mutate(root, pkg):
        p = pkg / "DECISION_RECEIPT.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["verdict_unchanged"] = "MIXED_N7_EXTENSION_HISTORICAL_SIGNAL_NO_PROMOTION"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    _mutate_and_expect_fail(tmp_path, mutate, V._check_e07, e07=True)


def test_deprecated_field_confined_to_descriptive_board() -> None:
    src = (REPO_ROOT / "src/n7_mixed_full_history/pipeline.py").read_text(encoding="utf-8")
    hits = [no for no, line in enumerate(src.splitlines(), 1) if "matched_ex_largest_lift_cny" in line]
    assert hits
    start = src.find("def _matched_contrasts_board")
    end = src.find("\ndef _correlation_board")
    start_line = src[:start].count("\n") + 1
    end_line = src[:end].count("\n") + 1
    assert all(start_line <= no <= end_line for no in hits)