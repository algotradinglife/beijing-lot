from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from research.sp_consistency.coverage import run_g0_coverage_audit
from research.sp_consistency.mapping import (
    aggregate_complete_score_distribution,
    poisson_grid_handicap_bounds,
    score_distribution_handicap_bounds,
)
from research.sp_consistency.snapshot import create_g0_input_snapshot
from research.sp_consistency.snapshot import sha256_file
from src.research_freeze_protocol import create_freeze_package


def test_score_mapper_handles_positive_zero_negative_handicaps_and_boundaries():
    distribution = {(1, 0): 0.2, (0, 0): 0.3, (0, 1): 0.5}
    assert aggregate_complete_score_distribution(distribution, 0) == pytest.approx((0.2, 0.3, 0.5))
    assert aggregate_complete_score_distribution(distribution, 1) == pytest.approx((0.5, 0.5, 0.0))
    assert aggregate_complete_score_distribution(distribution, -1) == pytest.approx((0.0, 0.2, 0.8))


def test_score_mapper_rejects_incomplete_or_malformed_point_inputs():
    with pytest.raises(ValueError, match="sum to one"):
        score_distribution_handicap_bounds({(0, 0): 0.4}, 0)
    with pytest.raises(ValueError, match="integer"):
        aggregate_complete_score_distribution({(0, 0): 1.0}, 0.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        aggregate_complete_score_distribution({(-1, 0): 1.0}, 0)


def test_poisson_grid_reports_tail_bounds_without_renormalizing():
    bounds = poisson_grid_handicap_bounds(1.2, 0.9, 0, max_goals=1)
    assert 0 < bounds.represented_mass < 1
    assert bounds.omitted_mass == pytest.approx(1 - bounds.represented_mass)
    assert bounds.point_probabilities is None
    assert sum(bounds.lower) == pytest.approx(bounds.represented_mass)
    assert all(upper - lower == pytest.approx(bounds.omitted_mass) for lower, upper in zip(bounds.lower, bounds.upper))


def _p34_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER, kickoff_ts TEXT);
        CREATE TABLE snapshots (match_id TEXT, snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL);
        INSERT INTO matches VALUES ('m1', '26080', 1, '2026-07-25T18:00:00');
        INSERT INTO snapshots VALUES ('m1', '2026-07-25T09:50:00Z', 2.0, 3.0, 4.0);
        """
    )
    connection.close()


def _p0_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE matches (issue TEXT, match_idx INTEGER, handicap_line REAL)")
    connection.close()


def _raw_bundle_fixture(root: Path, *, invalid: str | None = None) -> str:
    bundle = root / "bundle"
    bundle.mkdir(parents=True)
    payload = bundle / "nested" / "raw.json"
    payload.parent.mkdir()
    payload.write_text('{"capture":"fixture"}\n', encoding="utf-8")
    sums = bundle / "SHA256SUMS"
    if invalid == "empty":
        sums.write_text("", encoding="utf-8")
    elif invalid == "duplicate":
        sums.write_text(
            f"{sha256_file(payload)}  nested/raw.json\n{sha256_file(payload)}  nested//raw.json\n",
            encoding="utf-8",
        )
    else:
        sums.write_text(f"{sha256_file(payload)}  nested/raw.json\n", encoding="utf-8")
    if invalid == "extra":
        (bundle / "unlisted.json").write_text('{"extra":true}\n', encoding="utf-8")
    if invalid == "symlink":
        (bundle / "payload-link").symlink_to(payload.relative_to(bundle))
    return sha256_file(sums)


def _p34_strict_provenance_fixture(path: Path, bundle_hash: str) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        f"""
        CREATE TABLE matches (match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER, kickoff_ts TEXT);
        CREATE TABLE snapshots (
            match_id TEXT, snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL,
            source_observed_at TEXT, fetched_at TEXT, raw_batch_id TEXT, bundle_sha256 TEXT
        );
        INSERT INTO matches VALUES ('m1', '26080', 1, '2026-07-25T18:00:00Z');
        INSERT INTO snapshots VALUES (
            'm1', '2026-07-25T10:00:00Z', 2.0, 3.0, 4.0,
            '2026-07-25T09:50:00Z', '2026-07-25T09:55:00Z', 'batch-1', '{bundle_hash}'
        );
        """
    )
    connection.close()


def test_g0_is_outcome_blind_and_fails_closed_without_strict_p34_provenance(tmp_path: Path):
    p34 = tmp_path / "p34.db"
    p0 = tmp_path / "p0.db"
    _p34_fixture(p34)
    _p0_fixture(p0)
    atomic = create_g0_input_snapshot(
        work_dir=tmp_path / "atomic",
        p34_db=p34,
        p0_db=p0,
        p42_freeze_root=tmp_path / "no-freezes",
        model_search_roots=[tmp_path / "no-model-assets"],
    )
    report = run_g0_coverage_audit(
        p34_db=atomic.p34_snapshot,
        p34_source_schema=atomic.p34_source_schema,
        p34_raw_bundle_root=atomic.p34_raw_bundle_root,
        p0_db=atomic.p0_snapshot,
        p42_freeze_root=atomic.p42_root,
        model_inventory=atomic.model_inventory,
        input_fingerprints=atomic.fingerprints,
        audit_at_utc="2026-07-25T10:00:00+00:00",
    )
    assert report["outcomes_loaded"] is False
    assert report["coverage"]["p34"]["clocked_pre_kickoff_match_markets"] == 1
    assert report["coverage"]["p34"]["strict_complete_match_markets"] == 0
    assert report["gate"]["status"] == "INSUFFICIENT_STRICT_DATA"
    assert report["gate"]["formal_comparison_authorized"] is False
    assert report["query_audit"]["outcome_accessed"] is False
    assert report["coverage"]["p34"]["by_issue"][0]["strict_complete_match_markets"] == 0
    assert str(tmp_path) not in str(report)


def test_g0_exports_and_evaluates_strict_p34_provenance_when_source_fields_exist(tmp_path: Path):
    p34 = tmp_path / "p34-strict.db"
    p0 = tmp_path / "p0.db"
    raw_root = tmp_path / "raw-bundles"
    _p34_strict_provenance_fixture(p34, _raw_bundle_fixture(raw_root))
    _p0_fixture(p0)
    atomic = create_g0_input_snapshot(
        work_dir=tmp_path / "atomic",
        p34_db=p34,
        p0_db=p0,
        p42_freeze_root=tmp_path / "no-freezes",
        model_search_roots=[tmp_path / "no-model-assets"],
        p34_raw_bundle_root=raw_root,
    )
    report = run_g0_coverage_audit(
        p34_db=atomic.p34_snapshot,
        p34_source_schema=atomic.p34_source_schema,
        p34_raw_bundle_root=atomic.p34_raw_bundle_root,
        p0_db=atomic.p0_snapshot,
        p42_freeze_root=atomic.p42_root,
        model_inventory=atomic.model_inventory,
        input_fingerprints=atomic.fingerprints,
        audit_at_utc="2026-07-25T10:00:00+00:00",
    )
    assert report["coverage"]["p34"]["strict_complete_match_markets"] == 1
    assert report["coverage"]["p34"]["source_schema"]["all_required_fields_present"] is True
    assert report["coverage"]["model_score"]["status"] == "UNKNOWN_NOT_EVALUATED"
    assert report["coverage"]["model_score"]["strict_complete_match_markets"] is None


@pytest.mark.parametrize("bundle_hash", ["aabbcc", "f" * 64])
def test_g0_rejects_malformed_or_unbound_immutable_bundle_hash(tmp_path: Path, bundle_hash: str):
    p34 = tmp_path / "p34-invalid-bundle.db"
    p0 = tmp_path / "p0.db"
    _p34_strict_provenance_fixture(p34, bundle_hash)
    _p0_fixture(p0)
    atomic = create_g0_input_snapshot(
        work_dir=tmp_path / "atomic",
        p34_db=p34,
        p0_db=p0,
        p42_freeze_root=tmp_path / "no-freezes",
        model_search_roots=[tmp_path / "no-model-assets"],
        p34_raw_bundle_root=tmp_path / "empty-raw-bundles",
    )
    report = run_g0_coverage_audit(
        p34_db=atomic.p34_snapshot,
        p34_source_schema=atomic.p34_source_schema,
        p34_raw_bundle_root=atomic.p34_raw_bundle_root,
        p0_db=atomic.p0_snapshot,
        p42_freeze_root=atomic.p42_root,
        model_inventory=atomic.model_inventory,
        input_fingerprints=atomic.fingerprints,
        audit_at_utc="2026-07-25T10:00:00+00:00",
    )
    assert report["coverage"]["p34"]["strict_complete_match_markets"] == 0
    assert report["coverage"]["p34"]["rejections"]["invalid_or_unbound_immutable_bundle_sha256"] == 1


@pytest.mark.parametrize("invalid", ["empty", "duplicate", "extra", "symlink"])
def test_g0_rejects_incomplete_or_ambiguous_raw_bundle_manifest(tmp_path: Path, invalid: str):
    p34 = tmp_path / "p34-invalid-manifest.db"
    p0 = tmp_path / "p0.db"
    raw_root = tmp_path / "raw-bundles"
    _p34_strict_provenance_fixture(p34, _raw_bundle_fixture(raw_root, invalid=invalid))
    _p0_fixture(p0)
    atomic = create_g0_input_snapshot(
        work_dir=tmp_path / "atomic",
        p34_db=p34,
        p0_db=p0,
        p42_freeze_root=tmp_path / "no-freezes",
        model_search_roots=[tmp_path / "no-model-assets"],
        p34_raw_bundle_root=raw_root,
    )
    report = run_g0_coverage_audit(
        p34_db=atomic.p34_snapshot,
        p34_source_schema=atomic.p34_source_schema,
        p34_raw_bundle_root=atomic.p34_raw_bundle_root,
        p0_db=atomic.p0_snapshot,
        p42_freeze_root=atomic.p42_root,
        model_inventory=atomic.model_inventory,
        input_fingerprints=atomic.fingerprints,
        audit_at_utc="2026-07-25T10:00:00+00:00",
    )
    assert report["coverage"]["p34"]["strict_complete_match_markets"] == 0
    assert report["coverage"]["p34"]["rejections"]["invalid_or_unbound_immutable_bundle_sha256"] == 1


def test_atomic_g0_inputs_rebuild_same_audit_and_freeze_identity(tmp_path: Path):
    p34 = tmp_path / "p34.db"
    p0 = tmp_path / "p0.db"
    _p34_fixture(p34)
    _p0_fixture(p0)
    snapshots = [
        create_g0_input_snapshot(
            work_dir=tmp_path / name,
            p34_db=p34,
            p0_db=p0,
            p42_freeze_root=tmp_path / "no-freezes",
            model_search_roots=[tmp_path / "no-model-assets"],
        )
        for name in ("first", "second")
    ]
    audits = []
    freezes = []
    for index, atomic in enumerate(snapshots):
        audit = run_g0_coverage_audit(
            p34_db=atomic.p34_snapshot,
            p34_source_schema=atomic.p34_source_schema,
            p34_raw_bundle_root=atomic.p34_raw_bundle_root,
            p0_db=atomic.p0_snapshot,
            p42_freeze_root=atomic.p42_root,
            model_inventory=atomic.model_inventory,
            input_fingerprints=atomic.fingerprints,
            audit_at_utc="2026-07-25T10:00:00+00:00",
        )
        audit_path = atomic.p34_snapshot.parent.parent / "coverage_audit.json"
        config_path = atomic.p34_snapshot.parent.parent / "g0_config.json"
        decision_path = atomic.p34_snapshot.parent.parent / "g0_decision.json"
        import json
        audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
        config_path.write_text('{"version":"fixture"}', encoding="utf-8")
        decision_path.write_text('{"decision":"INSUFFICIENT_STRICT_DATA"}', encoding="utf-8")
        freezes.append(create_freeze_package(
            tmp_path / f"freeze-{index}", experiment_id="SP-CONSISTENCY-001A-G0-R4",
            research_question="fixture", model_version="fixture-v1",
            input_files=[atomic.p34_snapshot, atomic.p34_source_schema, atomic.p34_raw_bundle_archive, atomic.p0_snapshot, atomic.p42_archive, atomic.model_inventory, atomic.fingerprints, audit_path],
            decision_files=[decision_path], config_file=config_path,
            git_commit="1234567", frozen_at_utc="2026-07-25T10:00:00+00:00",
        ))
        audits.append(audit)
    assert audits[0] == audits[1]
    assert freezes[0]["freeze_id"] == freezes[1]["freeze_id"]
