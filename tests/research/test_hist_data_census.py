from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.hist_data_census.audit import (  # noqa: E402
    AUDIT_ID,
    CensusError,
    build_source_inventory,
    canonical_bytes,
    create_inventory_package,
    inventory_identity,
    parse_runtime_input,
    verify_inventory_package,
    write_inventory_artifacts,
)


COMMIT = "a" * 40


def write_bytes(path: Path, value: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def fixture_root(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "repository"
    runtime = write_bytes(tmp_path / "private" / "vendor.xlsm", b"not-opened-workbook-payload")
    write_bytes(source_root / "data" / "raw" / "matches.csv", b"private,data\n")
    write_bytes(source_root / "data" / "derived" / "model.sqlite", b"SQLite format 3\x00")
    write_bytes(source_root / "data" / "derived" / "model.sqlite-wal", b"wal")
    write_bytes(source_root / "data" / "cache" / "session_token.json", b'{"secret":"must-not-hash"}')
    bundle = source_root / "results" / "data_collection" / "capture-v1" / "issue-26076" / "batch-a"
    write_bytes(bundle / "manifest.json", b'{"payload":"not-read"}')
    write_bytes(bundle / "SHA256SUMS", b"deadbeef  raw.json\n")
    write_bytes(bundle / "raw.json", b'{"private":"payload"}')
    research_bundle = source_root / "results" / "research" / "run-a"
    write_bytes(research_bundle / "manifest.json", b"{}")
    return source_root, runtime


def test_inventory_is_metadata_only_redacted_and_stable(tmp_path: Path) -> None:
    source_root, runtime = fixture_root(tmp_path)
    runtime_input = parse_runtime_input(f"historical_xlsm={runtime}")
    first = build_source_inventory(repository_root=source_root, runtime_inputs=[runtime_input])
    second = build_source_inventory(repository_root=source_root, runtime_inputs=[runtime_input])

    assert canonical_bytes(first) == canonical_bytes(second)
    assert inventory_identity(first) == inventory_identity(second)
    rendered = canonical_bytes(first).decode("utf-8")
    assert str(source_root) not in rendered
    assert str(runtime) not in rendered
    assert "private,data" not in rendered
    assert "not-opened-workbook-payload" not in rendered
    assert "not-read" not in rendered
    rows = {row["repository_locator"]: row for row in first}
    assert rows["data/raw/matches.csv"]["sha256"]
    assert rows["data/derived/model.sqlite-wal"]["asset_kind"] == "sqlite_sidecar"
    assert rows["data/cache/session_token.json"]["availability"] == "EXCLUDED_SENSITIVE"
    assert rows["data/cache/session_token.json"]["sha256"] == ""
    assert any(row["asset_kind"] == "immutable_bundle" for row in first)
    assert any(row["availability"] == "MISSING" and row["logical_source_id"] == "freeze_packages" for row in first)


def package_from_fixture(tmp_path: Path) -> tuple[Path, Path, object]:
    source_root, runtime = fixture_root(tmp_path)
    runtime_input = parse_runtime_input(f"historical_xlsm={runtime}")
    rows = build_source_inventory(repository_root=source_root, runtime_inputs=[runtime_input])
    paths = write_inventory_artifacts(
        tmp_path / "output",
        rows,
        git_commit=COMMIT,
        runtime_inputs=[runtime_input],
    )
    package = tmp_path / "freeze" / "inventory"
    create_inventory_package(
        paths,
        output_dir=package,
        git_commit=COMMIT,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    return package, source_root, runtime_input


def test_inventory_package_verifies_and_fails_closed_on_source_drift(tmp_path: Path) -> None:
    package, source_root, runtime_input = package_from_fixture(tmp_path)
    verified = verify_inventory_package(
        package,
        repository_root=source_root,
        runtime_inputs=[runtime_input],
    )
    assert verified["status"] == "valid"
    assert verified["audit_id"] == AUDIT_ID
    assert verified["git_commit"] == COMMIT
    assert verified["current_source_identity_verified"] is True

    (source_root / "data" / "raw" / "matches.csv").write_bytes(b"changed")
    with pytest.raises(CensusError, match="differs from frozen"):
        verify_inventory_package(
            package,
            repository_root=source_root,
            runtime_inputs=[runtime_input],
        )


def test_inventory_package_rejects_abbreviated_commit_and_tampering(tmp_path: Path) -> None:
    source_root, runtime = fixture_root(tmp_path)
    runtime_input = parse_runtime_input(f"historical_xlsm={runtime}")
    rows = build_source_inventory(repository_root=source_root, runtime_inputs=[runtime_input])
    with pytest.raises(CensusError, match="full 40-character"):
        write_inventory_artifacts(tmp_path / "output", rows, git_commit="a" * 7, runtime_inputs=[runtime_input])

    package, source_root, runtime_input = package_from_fixture(tmp_path / "valid")
    source_inventory = package / "inputs" / "source_inventory.csv"
    source_inventory.write_text(source_inventory.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
    with pytest.raises(CensusError, match="checksum"):
        verify_inventory_package(
            package,
            repository_root=source_root,
            runtime_inputs=[runtime_input],
        )


def test_inventory_decision_is_precoverage_only(tmp_path: Path) -> None:
    package, _, _ = package_from_fixture(tmp_path)
    decision = json.loads((package / "decision" / "inventory_freeze_decision.json").read_text(encoding="utf-8"))
    assert decision["coverage_or_schema_inspected"] is False
    assert decision["next_permitted_phase"] == "READ_ONLY_SCHEMA_AND_COVERAGE_AUDIT_AFTER_INVENTORY_VERIFICATION"
