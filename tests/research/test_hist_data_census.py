from __future__ import annotations

import json
import hashlib
import sqlite3
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
from research.hist_data_census.census import (  # noqa: E402
    REQUIRED_CENSUS_ARTIFACTS,
    audit_frozen_inventory,
    create_census_package,
    verify_census_package,
    write_census_artifacts,
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


def write_sha256sums(bundle: Path) -> None:
    entries = []
    for source in sorted(item for item in bundle.rglob("*") if item.is_file() and item.name != "SHA256SUMS"):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        entries.append(f"{digest}  {source.relative_to(bundle).as_posix()}\n")
    (bundle / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")


def census_fixture(tmp_path: Path) -> Path:
    source_root = tmp_path / "repository"
    database = source_root / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE matches(
                match_id INTEGER PRIMARY KEY, issue TEXT, kickoff_ts TEXT,
                handicap_line REAL, fthg INTEGER, ftag INTEGER, result_code TEXT
            );
            CREATE TABLE exotic_odds(match_id INTEGER, market TEXT, outcome TEXT, odds REAL);
            CREATE TABLE live_market_sp_snapshots(
                issue TEXT, playid INTEGER, market_key TEXT, match_id TEXT,
                outcome_code TEXT, sp REAL, fetched_at_utc TEXT,
                capture_classification TEXT, sale_status TEXT
            );
            CREATE TABLE multimarket_settlement_truth(
                issue TEXT, match_id TEXT, market_key TEXT, fthg INTEGER, ftag INTEGER,
                outcome_code TEXT, winning_sp REAL, settlement_status TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO matches VALUES (1, '26076', '2026-07-25T12:00:00+00:00', 0.5, 2, 1, '3')"
        )
        connection.executemany(
            "INSERT INTO exotic_odds VALUES (1, 'score', ?, 2.5)",
            [("1:0",), ("2:1",)],
        )
        connection.executemany(
            "INSERT INTO live_market_sp_snapshots VALUES ('26076', 40, 'total_goals', 'm1', ?, 2.5, '2026-07-25T01:00:00Z', 'terminal_backfill_exploratory_only', 'open')",
            [("0~1",), ("2~3",)],
        )
        connection.execute(
            "INSERT INTO multimarket_settlement_truth VALUES ('26076', 'm1', 'total_goals', 2, 1, '2~3', 2.5, 'settled')"
        )
    bundle = source_root / "results" / "data_collection" / "multimarket_sp_capture_v1" / "26076" / "batch-a"
    write_bytes(
        bundle / "manifest.json",
        json.dumps(
            {
                "issue": "26076",
                "playid": 40,
                "market_key": "total_goals",
                "fetched_at_utc": "2026-07-25T01:00:00Z",
                "source_updated_at_hkt": "2026-07-25T09:00:00+08:00",
                "complete_forward_open_rows": 2,
                "terminal_rows": 0,
            }, sort_keys=True).encode("utf-8"),
    )
    write_bytes(bundle / "raw.json", b'{"not":"published"}')
    write_sha256sums(bundle)
    return source_root


def test_full_census_requires_frozen_inventory_and_keeps_terminal_values_out(tmp_path: Path) -> None:
    source_root = census_fixture(tmp_path)
    inventory = build_source_inventory(repository_root=source_root)
    inventory_paths = write_inventory_artifacts(tmp_path / "inventory-output", inventory, git_commit=COMMIT)
    inventory_package = tmp_path / "freeze" / "inventory"
    create_inventory_package(
        inventory_paths,
        output_dir=inventory_package,
        git_commit=COMMIT,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )

    artifacts = audit_frozen_inventory(
        inventory_package=inventory_package,
        repository_root=source_root,
        runtime_inputs=[],
        git_commit=COMMIT,
    )
    assert set(artifacts) == set(REQUIRED_CENSUS_ARTIFACTS)
    assert artifacts["audit_report.json"]["source_identity_verified_before_and_after"] is True
    feature = next(
        row for row in artifacts["feature_availability.csv"]
        if row["table_name"] == "matches" and row["field_name"] == "fthg"
    )
    assert feature["terminal_guard"] == "true"
    assert feature["pre_match_feature_eligible"] == "false"
    assert any(
        row["market"] == "correct_score" and row["admissible_use"] == "prohibited"
        for row in artifacts["admissible_use_matrix.csv"]
    )
    p40 = next(row for row in artifacts["model_readiness_matrix.csv"] if row["play_id"] == "40")
    assert p40["price_ready"] == "conditional_strict_forward"
    assert p40["roi_ready"] == "false"
    rendered = canonical_bytes(artifacts).decode("utf-8")
    assert str(source_root) not in rendered
    assert "not\":\"published" not in rendered

    paths = write_census_artifacts(tmp_path / "census-output", artifacts)
    package = tmp_path / "freeze" / "census"
    create_census_package(
        paths,
        output_dir=package,
        git_commit=COMMIT,
        frozen_at_utc="2026-07-26T00:01:00+00:00",
    )
    verified = verify_census_package(
        package,
        inventory_package=inventory_package,
        repository_root=source_root,
        runtime_inputs=[],
    )
    assert verified["status"] == "valid"
    assert verified["inventory_bound"] is True


def test_census_fails_closed_per_asset_when_a_live_source_drifts(tmp_path: Path) -> None:
    source_root = census_fixture(tmp_path)
    inventory = build_source_inventory(repository_root=source_root)
    inventory_paths = write_inventory_artifacts(tmp_path / "inventory-output", inventory, git_commit=COMMIT)
    inventory_package = tmp_path / "freeze" / "inventory"
    create_inventory_package(
        inventory_paths,
        output_dir=inventory_package,
        git_commit=COMMIT,
        frozen_at_utc="2026-07-26T00:00:00+00:00",
    )
    database = source_root / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO matches VALUES (2, '26077', '2026-07-26T12:00:00+00:00', 0.0, 0, 0, '1')")

    artifacts = audit_frozen_inventory(
        inventory_package=inventory_package,
        repository_root=source_root,
        runtime_inputs=[],
        git_commit=COMMIT,
    )
    report = artifacts["audit_report.json"]
    assert report["source_identity_verified_before_and_after"] is False
    assert report["source_drifted_asset_count"] == 1
    drift = next(row for row in artifacts["coverage_by_period.csv"] if row["coverage_status"] == "SOURCE_DRIFT_FAIL_CLOSED")
    assert drift["logical_asset_id"].endswith("derived-beidan-xlsm-beidan-xlsm-sqlite")
    assert not any(
        row["logical_asset_id"] == drift["logical_asset_id"]
        for row in artifacts["schema_dictionary.csv"]
    )
