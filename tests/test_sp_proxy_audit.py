"""Contract tests for Issue #318 SP/proxy audit."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.sp_proxy_audit.builder import build_package
from src.sp_proxy_audit.grading import grade_vectors
from src.sp_proxy_audit.metrics import coverage_by_issue
from src.sp_proxy_audit.validate import validate_package


def _vector(**overrides: object) -> pd.DataFrame:
    rows = []
    for outcome, price in (("3", 2.0), ("1", 3.0), ("0", 4.0)):
        row = {
            "issue_code": "26001",
            "match_idx": 1,
            "source_id": "test",
            "snapshot_kind": "initial",
            "outcome_code": outcome,
            "sp_value": price,
            "fixture_identity": "bjslot:26001:001",
            "identity_consistent": True,
            "provenance_sha256": "a" * 64,
            "observed_at_utc": "2024-01-01T00:00:00Z",
            "decision_epoch_utc": "2024-01-02T00:00:00Z",
            "kickoff_utc": "2024-01-03T00:00:00Z",
            "source_semantics": "strict",
        }
        row.update(overrides)
        rows.append(row)
    return pd.DataFrame(rows)


def test_strict_vector_requires_proven_timestamp_and_identity() -> None:
    accepted = grade_vectors(_vector())
    naive = grade_vectors(_vector(observed_at_utc="2024-01-01 00:00:00"))
    mismatched = grade_vectors(_vector(identity_consistent=False))
    assert set(accepted.source_grade) == {"STRICT_PRE_EVENT"}
    assert set(naive.exclusion_reason) == {"TIMESTAMP_UNPROVEN"}
    assert set(mismatched.exclusion_reason) == {"IDENTITY_MISMATCH"}


def test_relative_proxy_is_accepted_without_inventing_an_absolute_timestamp() -> None:
    proxy = grade_vectors(
        _vector(
            source_semantics="relative_proxy",
            observed_at_utc=None,
            decision_epoch_utc=None,
        )
    )
    assert set(proxy.source_grade) == {"HISTORICAL_PROXY"}
    assert proxy.exclusion_reason.isna().all()


def test_precedence_and_atomic_triplet_fail_closed() -> None:
    post = grade_vectors(_vector(observed_at_utc="2024-01-04T00:00:00Z"))
    incomplete = grade_vectors(_vector().assign(sp_value=[2.0, None, 4.0]))
    settlement = grade_vectors(_vector(source_semantics="settlement"))
    conflicting = grade_vectors(
        pd.concat([_vector(), _vector(sp_value=7.0)], ignore_index=True)
    )
    assert set(post.exclusion_reason) == {"POST_KICKOFF"}
    assert set(incomplete.exclusion_reason) == {"INCOMPLETE_TRIPLET"}
    assert set(settlement.exclusion_reason) == {"SETTLEMENT_ONLY"}
    assert set(conflicting.exclusion_reason) == {"DUPLICATE_CONFLICT"}


def test_identical_duplicates_collapse_to_one_mx3_vector() -> None:
    graded = grade_vectors(pd.concat([_vector(), _vector()], ignore_index=True))
    assert len(graded) == 3
    assert set(graded.source_grade) == {"STRICT_PRE_EVENT"}


def test_unusable_vectors_never_count_as_feasible_n7() -> None:
    rows = []
    for match_idx in range(1, 9):
        rows.append(_vector(match_idx=match_idx, identity_consistent=False))
    graded = grade_vectors(pd.concat(rows, ignore_index=True))
    coverage = coverage_by_issue(graded)
    assert not coverage.feasible_n7.any()


def test_genuinely_missing_sources_produce_a_fail_closed_receipt(
    tmp_path: Path,
) -> None:
    output = tmp_path / "package"
    decision = build_package(tmp_path / "repo", tmp_path / "data", output)
    inventory = pd.read_csv(output / "source_inventory.csv")
    assert decision["terminal_disposition"] == "NO_CAUSAL_PRICE_SUPPORT"
    assert set(inventory.availability) == {"SOURCE_MISSING"}
    assert (
        validate_package(output, _sha256(output / "MANIFEST.json"))["verdict"] == "PASS"
    )


def test_minimal_real_source_chain_is_consumed_and_computed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    data = tmp_path / "data-root"
    output = tmp_path / "package"
    beidan = data / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
    candidate = data / "data/derived/bj268/eu_proxy_backfill_v3/candidate.sqlite"
    registry = data / "data/derived/500_bjdc/500_bjdc.sqlite"
    materializer = data / "data/derived/bj238_divergence_materializer_v4r3"
    strict = repo / "results/bj216_model_support_panel_v1"
    receipt = repo / "docs/research/evidence/bj238/SOURCE_RECEIPT.json"
    for path in (beidan, candidate, registry):
        path.parent.mkdir(parents=True, exist_ok=True)
    materializer.mkdir(parents=True)
    (materializer / "inference").mkdir()
    (strict / "sources").mkdir(parents=True)
    (strict / "inference").mkdir()
    receipt.parent.mkdir(parents=True)

    _create_beidan(beidan)
    _create_candidate(candidate)
    _create_registry(registry)
    pd.DataFrame(
        [
            {
                "issue_code": "26051",
                "match_idx": 1,
                "snapshot_kind": horizon,
                "outcome_code": outcome,
                "q_eu_raw_1x2": probability,
                "q_eu_bjline": probability,
                "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
                "mapping_accepted": True,
            }
            for horizon in ("initial", "10h", "1h")
            for outcome, probability in (("3", 0.5), ("1", 0.3), ("0", 0.2))
        ]
    ).to_parquet(materializer / "inference/relative_horizon_view.parquet", index=False)
    (materializer / "MANIFEST.json").write_text(
        '{"contract":"test"}\n', encoding="utf-8"
    )
    pd.DataFrame(
        [
            {
                "id": 1,
                "match_id": "26051_001",
                "sp_3": 2.0,
                "sp_1": 3.2,
                "sp_0": 5.1,
                "market_observed_ts_utc": "2026-05-02T01:00:00Z",
            }
        ]
    ).to_parquet(strict / "sources/selected_snapshots.parquet", index=False)
    pd.DataFrame(
        [
            {
                "match_id": "26051_001",
                "issue": "26051",
                "match_idx": 1,
                "kickoff_ts_utc": "2026-05-02T09:40:00Z",
            }
        ]
    ).to_parquet(strict / "sources/matches.parquet", index=False)
    pd.DataFrame(
        [{"issue": "26051", "decision_epoch_utc": "2026-05-02T07:30:00Z"}]
    ).to_parquet(strict / "inference/issue_epochs.parquet", index=False)
    (strict / "MANIFEST.json").write_text('{"contract":"test"}\n', encoding="utf-8")
    receipt.write_text(
        json.dumps(
            {
                "candidate_sqlite_sha256_from_accepted_268_verification": _sha256(
                    candidate
                ),
                "proxy_manifest_sha256": _sha256(materializer / "MANIFEST.json"),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    decision = build_package(repo, data, output)
    cells = pd.read_parquet(output / "graded_cells.parquet")
    overlap = pd.read_csv(output / "overlap_metrics.csv")
    assert decision["terminal_disposition"] == "NO_CAUSAL_PRICE_SUPPORT"
    assert set(
        cells.loc[cells.source_id.eq("strict_prospective_216"), "source_grade"]
    ) == {"STRICT_PRE_EVENT"}
    assert set(
        cells.loc[cells.source_id.eq("eu_consensus_fair_odds_268"), "source_grade"]
    ) == {"HISTORICAL_PROXY"}
    assert len(overlap) == 3
    assert decision["observed_metrics"]["overlap_cells"] == 9
    assert (
        validate_package(output, _sha256(output / "MANIFEST.json"))["verdict"] == "PASS"
    )


def test_remanifested_decision_tamper_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "package"
    build_package(tmp_path / "repo", tmp_path / "data", output)
    anchor = _sha256(output / "MANIFEST.json")
    decision_path = output / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["terminal_disposition"] = "STRICT_HISTORY_AVAILABLE"
    decision_path.write_text(
        json.dumps(decision, sort_keys=True) + "\n", encoding="utf-8"
    )
    _remanifest(output)
    with pytest.raises(ValueError, match="trusted manifest"):
        validate_package(output, anchor)


def _create_beidan(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE matches(issue TEXT, match_idx INTEGER, kickoff_ts TEXT, provider_match_id TEXT);
            CREATE TABLE match_features(issue TEXT, match_idx INTEGER, kickoff_ts TEXT,
              official_sp_3 REAL, official_sp_1 REAL, official_sp_0 REAL);
            CREATE TABLE official_500_settlements(issue TEXT, match_idx INTEGER,
              sp_home REAL, sp_draw REAL, sp_away REAL, imported_at TEXT);
            INSERT INTO matches VALUES ('26051',1,'2026-05-02 17:40:00','1001');
            INSERT INTO match_features VALUES ('26051',1,'2026-05-02 17:40:00',2.1,3.1,5.0);
            INSERT INTO official_500_settlements VALUES ('26051',1,2.0,3.2,5.1,'2026-05-03T00:00:00+00:00');
            """
        )


def _create_candidate(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE inventory(issue_code TEXT, match_idx INTEGER, provider_match_id TEXT,
              kickoff_ts TEXT, reconciled_source TEXT);
            CREATE TABLE resolved_quotes(issue_code TEXT, match_idx INTEGER, snapshot_kind TEXT,
              bookmaker_id TEXT, v1 REAL, v2 REAL, v3 REAL);
            CREATE TABLE duplicate_resolution_ledger(issue_code TEXT, match_idx INTEGER,
              snapshot_kind TEXT, bookmaker_id TEXT, reason TEXT);
            CREATE TABLE acquisition_receipts(source_kind TEXT, source_key TEXT);
            INSERT INTO inventory VALUES ('26051',1,'1001','2026-05-02 17:40:00','TEST');
            """
        )


def _create_registry(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE issues(
              issue TEXT, ordinal INTEGER, label TEXT, is_selected INTEGER,
              is_current INTEGER, year INTEGER, first_seen_at TEXT, last_seen_at TEXT
            );
            INSERT INTO issues VALUES ('26051',1,'test',1,0,2026,'2026-05-01','2026-05-03');
            """
        )


def _remanifest(package: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {
        relative: _sha256(package / relative) for relative in manifest["files"]
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksums = {
        path.name: _sha256(path)
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (package / "SHA256SUMS.json").write_text(
        json.dumps(checksums, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
