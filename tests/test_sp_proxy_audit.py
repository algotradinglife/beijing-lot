"""Contract tests for Issue #318 SP/proxy audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.sp_proxy_audit.builder import build_package
from src.sp_proxy_audit.grading import grade_vectors
from src.sp_proxy_audit.validate import validate_package


def _vector(**overrides: object) -> pd.DataFrame:
    rows = []
    for outcome, price in (("3", 2.0), ("1", 3.0), ("0", 4.0)):
        row = {
            "issue_code": "26001", "match_idx": 1, "source_id": "test",
            "snapshot_kind": "initial", "outcome_code": outcome, "sp_value": price,
            "fixture_identity": "bjslot:26001:001", "provenance_sha256": "a" * 64,
            "observed_at_utc": "2024-01-01T00:00:00Z",
            "decision_epoch_utc": "2024-01-02T00:00:00Z",
            "kickoff_utc": "2024-01-03T00:00:00Z",
            "source_semantics": "strict",
        }
        row.update(overrides)
        rows.append(row)
    return pd.DataFrame(rows)


def test_strict_vector_is_only_accepted_with_proven_timestamp_before_epoch_and_kickoff() -> None:
    graded = grade_vectors(_vector())
    assert set(graded.source_grade) == {"STRICT_PRE_EVENT"}
    assert graded.exclusion_reason.isna().all()


def test_settlement_and_invented_timestamps_fail_closed() -> None:
    settlement = grade_vectors(_vector(source_semantics="settlement"))
    invented = grade_vectors(_vector(observed_at_utc=None, source_semantics="strict"))
    assert set(settlement.exclusion_reason) == {"SETTLEMENT_ONLY"}
    assert set(invented.exclusion_reason) == {"TIMESTAMP_UNPROVEN"}


def test_naive_timestamp_is_unproven_without_source_timezone_contract() -> None:
    naive = grade_vectors(_vector(observed_at_utc="2024-01-01 00:00:00"))
    assert set(naive.exclusion_reason) == {"TIMESTAMP_UNPROVEN"}


def test_post_kickoff_incomplete_and_conflicting_duplicate_fail_as_atomic_vectors() -> None:
    post = grade_vectors(_vector(observed_at_utc="2024-01-04T00:00:00Z"))
    incomplete = grade_vectors(_vector().iloc[:2])
    duplicate = pd.concat([_vector(), _vector(sp_value=7.0)], ignore_index=True)
    assert set(post.exclusion_reason) == {"POST_KICKOFF"}
    assert set(incomplete.exclusion_reason) == {"INCOMPLETE_TRIPLET"}
    assert set(grade_vectors(duplicate).exclusion_reason) == {"DUPLICATE_CONFLICT"}


def test_missing_sources_produce_a_complete_fail_closed_package(tmp_path: Path) -> None:
    package = tmp_path / "package"
    build_package(tmp_path / "no-sources", package)
    decision = json.loads((package / "decision.json").read_text(encoding="utf-8"))
    inventory = pd.read_csv(package / "source_inventory.csv")
    assert decision["terminal_disposition"] == "NO_CAUSAL_PRICE_SUPPORT"
    assert set(inventory["availability"]) == {"SOURCE_MISSING"}
    assert (package / "graded_cells.parquet").is_file()
    assert validate_package(package, expected_manifest_sha256=_sha256(package / "MANIFEST.json"))["verdict"] == "PASS"


def test_remanifested_decision_tamper_is_rejected_by_external_manifest_anchor(tmp_path: Path) -> None:
    package = tmp_path / "package"
    build_package(tmp_path / "no-sources", package)
    original_manifest = _sha256(package / "MANIFEST.json")
    decision_path = package / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["terminal_disposition"] = "STRICT_HISTORY_AVAILABLE"
    decision_path.write_text(json.dumps(decision, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["decision.json"] = _sha256(decision_path)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="trusted manifest"):
        validate_package(package, expected_manifest_sha256=original_manifest)


def test_remanifested_price_or_source_trace_tamper_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "sources"
    panel = source / "results/bj216_model_support_panel_v1"
    (panel / "sources").mkdir(parents=True)
    (panel / "inference").mkdir()
    (panel / "MANIFEST.json").write_text("{}\n", encoding="utf-8")
    pd.DataFrame([{
        "id": 1, "match_id": "26051_080", "sp_3": 2.0, "sp_1": 3.0, "sp_0": 4.0,
        "eu_h": 2.0, "eu_d": 3.0, "eu_a": 4.0, "source": "frozen",
        "market_observed_ts_utc": "2026-05-02T01:00:00Z",
    }]).to_parquet(panel / "sources/selected_snapshots.parquet", index=False)
    pd.DataFrame([{"issue": "26051", "decision_epoch_utc": "2026-05-02T07:30:00Z"}]).to_parquet(panel / "inference/issue_epochs.parquet", index=False)
    package = tmp_path / "package"
    build_package(source, package)
    original_manifest = _sha256(package / "MANIFEST.json")
    cells_path = package / "graded_cells.parquet"
    cells = pd.read_parquet(cells_path)
    cells.loc[cells.index[0], "sp_value"] = 99.0
    cells.loc[cells.index[1], "provenance_sha256"] = "b" * 64
    cells.to_parquet(cells_path, index=False)
    _remanifest(package)
    with pytest.raises(ValueError, match="trusted manifest"):
        validate_package(package, expected_manifest_sha256=original_manifest)


def test_manifest_referenced_candidate_successor_is_hashed_and_not_silently_marked_missing(tmp_path: Path) -> None:
    """A receipt-approved successor is part of the closed discovery boundary."""
    source = tmp_path / "sources"
    candidate = tmp_path / "external-candidate.sqlite"
    candidate.write_bytes(b"immutable candidate bytes")
    receipt = source / "docs/research/evidence/bj238/SOURCE_RECEIPT.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps({
            "candidate_sqlite": str(candidate),
            "candidate_sqlite_sha256_from_accepted_268_verification": _sha256(candidate),
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    package = tmp_path / "package"
    build_package(source, package)
    inventory = pd.read_csv(package / "source_inventory.csv")
    candidate_record = inventory.loc[inventory.source_id.eq("eu_proxy_backfill")].iloc[0]
    assert candidate_record.availability == "PRESENT"
    assert candidate_record.sha256 == _sha256(candidate)


def _remanifest(package: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {
        relative: _sha256(package / relative)
        for relative in manifest["files"]
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    checksums = {
        path.name: _sha256(path)
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (package / "SHA256SUMS.json").write_text(json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
