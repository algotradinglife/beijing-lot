"""Acceptance tests for #236 historical European market proxy recovery."""
from __future__ import annotations

import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from eu_odds_timeseries.core import (  # noqa: E402
    derive_proxy_probabilities,
    translation_readiness,
)
from eu_odds_timeseries.source import load_workbook_proxy  # noqa: E402
from eu_odds_timeseries.package import (  # noqa: E402
    build_proxy_package,
    rebuild_manifest,
    verify_proxy_package,
)
from eu_odds_timeseries.materialize import materialize_proxy_view  # noqa: E402
from eu_odds_timeseries.profiling import build_profiles  # noqa: E402


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # valid bookmaker triplet, canonical issue-slot identity
            {"issue_code": "25042", "match_idx": 1, "source_match_id": 7,
             "snapshot_kind": "initial", "bookmaker_id": "A", "v1": 2.0, "v2": 3.0, "v3": 6.0,
             "native_handicap_line_raw": 99.0, "native_handicap_line": 0.0,
             "handicap_norm_source": "vendor_large_code_to_zero"},
            # invalid decimal odds remains in the exclusion ledger; it cannot feed consensus
            {"issue_code": "25042", "match_idx": 1, "source_match_id": 7,
             "snapshot_kind": "initial", "bookmaker_id": "B", "v1": 1.0, "v2": 3.1, "v3": 5.5,
             "native_handicap_line_raw": 99.0, "native_handicap_line": 0.0,
             "handicap_norm_source": "vendor_large_code_to_zero"},
            # a non-zero native line cannot be inferred from a straight-1X2 triplet
            {"issue_code": "25042", "match_idx": 2, "source_match_id": 8,
             "snapshot_kind": "10h", "bookmaker_id": "A", "v1": 2.5, "v2": 3.2, "v3": 3.0,
             "native_handicap_line_raw": -1.0, "native_handicap_line": -1.0,
             "handicap_norm_source": "vendor_small_line"},
        ]
    )


def test_proxy_de_vig_preserves_raw_trace_and_masks_invalid_quotes() -> None:
    probabilities, raw_quotes, ledger = derive_proxy_probabilities(_quotes())

    assert set(raw_quotes["market_type"]) == {"euro_1x2"}
    assert set(raw_quotes["causal_grade"]) == {"RETROSPECTIVE_RELATIVE_PROXY"}
    assert raw_quotes.loc[raw_quotes["bookmaker_id"].eq("B"), "quote_status"].eq("INVALID").all()
    assert "INVALID_DECIMAL_ODDS" in set(ledger["reason"])

    first = probabilities.loc[
        probabilities["canonical_fixture_key"].eq("bjslot:25042:001")
    ].sort_values("outcome_code")
    assert first["outcome_code"].tolist() == ["0", "1", "3"]
    assert first["raw_group_sha256"].notna().all()
    assert first["n_available_books"].tolist() == [1, 1, 1]
    assert math.isclose(float(first["probability"].sum()), 1.0, abs_tol=1e-12)


def test_translation_declares_zero_line_identity_and_nonzero_unavailable() -> None:
    probabilities, _, _ = derive_proxy_probabilities(_quotes())
    readiness = translation_readiness(probabilities, _quotes())

    zero = readiness.loc[readiness["canonical_fixture_key"].eq("bjslot:25042:001")].iloc[0]
    assert zero["translation_status"] == "AVAILABLE_ZERO_LINE_IDENTITY"
    assert zero["translation_probability_json"]
    assert zero["native_handicap_line_raw"] == 99.0
    assert zero["native_handicap_line"] == 0.0
    assert zero["handicap_norm_source"] == "vendor_large_code_to_zero"

    nonzero = readiness.loc[readiness["canonical_fixture_key"].eq("bjslot:25042:002")].iloc[0]
    assert nonzero["translation_status"] == "UNAVAILABLE_NONZERO_LINE_REQUIRES_GOAL_DIFFERENCE"
    assert pd.isna(nonzero["translation_probability_json"])


def test_workbook_reader_uses_only_euro_rows_and_quarantines_duplicate_issue_slot(tmp_path: Path) -> None:
    path = tmp_path / "workbook.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE matches (match_id INTEGER, issue TEXT, match_idx INTEGER, "
        "handicap_line REAL, handicap_line_norm REAL, handicap_norm_source TEXT)"
    )
    con.execute("CREATE TABLE market_snapshots (match_id INTEGER, market TEXT, bookmaker TEXT, snapshot TEXT, v1 REAL, v2 REAL, v3 REAL)")
    con.execute("CREATE TABLE source_meta (key TEXT, value TEXT)")
    con.execute("INSERT INTO source_meta VALUES ('source_path', 'C:/archive/beidan.xlsm')")
    con.executemany("INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?)", [
        (1, "25042", 1, 99.0, 0.0, "vendor_large_code_to_zero"),
        (2, "25042", 2, -1.0, -1.0, "vendor_small_line"),
        (3, "25042", 2, -1.0, -1.0, "vendor_small_line"),  # ambiguous canonical slot
    ])
    con.executemany("INSERT INTO market_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)", [
        (1, "euro_1x2", "A", "initial", 2.0, 3.0, 6.0),
        (1, "asian_handicap", "A", "initial", 1.8, 3.0, 2.0),  # excluded market
        (2, "euro_1x2", "A", "10h", 2.2, 3.1, 4.0),
        (3, "euro_1x2", "A", "10h", 2.3, 3.1, 3.9),
    ])
    con.commit()
    con.close()

    rows, ledger = load_workbook_proxy(path)
    assert rows[["source_match_id", "snapshot_kind"]].to_dict("records") == [
        {"source_match_id": 1, "snapshot_kind": "initial"}
    ]
    assert ledger.to_dict("records") == [{
        "issue_code": "25042", "match_idx": 2,
        "reason": "DUPLICATE_ISSUE_SLOT", "source_match_ids": "2,3",
    }]


def test_package_verifier_rejects_remanifested_probability_manifest_and_label_tamper(tmp_path: Path) -> None:
    package = build_proxy_package(tmp_path / "package", _quotes(), source_sha256="a" * 64)
    verify_proxy_package(package, expected_source_sha256="a" * 64)

    probabilities = package / "tables" / "probabilities.parquet"
    changed = pd.read_parquet(probabilities)
    changed.loc[0, "probability"] = 0.99
    changed.to_parquet(probabilities, index=False)
    rebuild_manifest(package)
    with pytest.raises(AssertionError, match="probabilities"):
        verify_proxy_package(package, expected_source_sha256="a" * 64)

    package = build_proxy_package(tmp_path / "package2", _quotes(), source_sha256="a" * 64)
    manifest_path = package / "MANIFEST.json"
    manifest = __import__("json").loads(manifest_path.read_text())
    manifest["source_sha256"] = "0" * 64
    manifest_path.write_text(__import__("json").dumps(manifest), encoding="utf-8")
    rebuild_manifest(package)
    with pytest.raises(AssertionError, match="source hash"):
        verify_proxy_package(package, expected_source_sha256="a" * 64)

    package = build_proxy_package(tmp_path / "package3", _quotes(), source_sha256="a" * 64)
    label = package / "tables" / "raw_quotes.parquet"
    changed = pd.read_parquet(label)
    changed.loc[0, "market_type"] = "sp_1x2"
    changed.to_parquet(label, index=False)
    rebuild_manifest(package)
    with pytest.raises(AssertionError, match="semantic"):
        verify_proxy_package(package, expected_source_sha256="a" * 64)

    package = build_proxy_package(tmp_path / "package4", _quotes(), source_sha256="a" * 64)
    ledger = package / "tables" / "exclusion_ledger.parquet"
    changed = pd.read_parquet(ledger)
    changed.loc[0, "reason"] = "ACCOUNTING_STILL_BALANCES_BUT_IS_FALSE"
    changed.to_parquet(ledger, index=False)
    rebuild_manifest(package)
    with pytest.raises(AssertionError, match="ledger semantic"):
        verify_proxy_package(package, expected_source_sha256="a" * 64)


def test_package_verifier_preserves_missing_normalized_line_metadata(tmp_path: Path) -> None:
    raw = _quotes().iloc[[2]].copy()
    raw["native_handicap_line_raw"] = None
    raw["native_handicap_line"] = None
    raw["handicap_norm_source"] = "missing_raw"

    package = build_proxy_package(tmp_path / "missing-line", raw, source_sha256="b" * 64)
    verify_proxy_package(package, expected_source_sha256="b" * 64)
    readiness = pd.read_parquet(package / "tables" / "translation_readiness.parquet")
    assert readiness.loc[0, "translation_status"] == "UNAVAILABLE_MISSING_OR_CONFLICTING_NATIVE_LINE"
    assert pd.isna(readiness.loc[0, "native_handicap_line"])


def test_streamed_materializer_writes_external_rebuildable_views(tmp_path: Path) -> None:
    workbook = tmp_path / "workbook.sqlite"
    con = sqlite3.connect(workbook)
    con.execute(
        "CREATE TABLE matches (match_id INTEGER, issue TEXT, match_idx INTEGER, "
        "handicap_line REAL, handicap_line_norm REAL, handicap_norm_source TEXT, kickoff_ts TEXT)"
    )
    con.execute("CREATE TABLE market_snapshots (match_id INTEGER, market TEXT, bookmaker TEXT, snapshot TEXT, v1 REAL, v2 REAL, v3 REAL)")
    con.execute("CREATE TABLE source_meta (key TEXT, value TEXT)")
    con.execute("INSERT INTO source_meta VALUES ('source_path', 'C:/archive/beidan.xlsm')")
    con.execute(
        "INSERT INTO matches VALUES (1, '25042', 1, 99.0, 0.0, "
        "'vendor_large_code_to_zero', '2025-07-01 10:00:00')"
    )
    con.executemany(
        "INSERT INTO market_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "euro_1x2", "A", "initial", 2.0, 3.0, 6.0),
            (1, "euro_1x2", "B", "initial", 1.0, 3.0, 6.0),
            (1, "asian_handicap", "A", "initial", 0.9, -0.5, 0.9),
            (1, "over_under", "A", "initial", 0.9, 2.5, 0.9),
        ],
    )
    con.commit()
    con.close()

    source_hash = __import__("hashlib").sha256(workbook.read_bytes()).hexdigest()
    result = materialize_proxy_view(workbook, tmp_path / "view", source_sha256=source_hash, chunksize=1)
    assert result["matched_fixture_count"] == 1
    assert (tmp_path / "view" / "MANIFEST.json").is_file()
    assert (tmp_path / "view" / "probabilities" / "part-00000.parquet").is_file()
    assert (tmp_path / "view" / "source_trace" / "part-00000.parquet").is_file()
    readiness = pd.read_parquet(tmp_path / "view" / "translation_readiness" / "part-00000.parquet")
    assert readiness.loc[0, "translation_status"] == "AVAILABLE_ZERO_LINE_IDENTITY"
    assert readiness.loc[0, "native_handicap_line_raw"] == 99.0
    assert readiness.loc[0, "native_handicap_line"] == 0.0
    ledger = pd.read_parquet(tmp_path / "view" / "exclusion_ledger" / "part-00000.parquet")
    assert "INVALID_DECIMAL_ODDS" in set(ledger["reason"])
    raw, _ = load_workbook_proxy(workbook)
    expected, _, _ = derive_proxy_probabilities(raw)
    actual = pd.read_parquet(tmp_path / "view" / "probabilities" / "part-00000.parquet")
    pd.testing.assert_frame_equal(
        actual[["canonical_fixture_key", "snapshot_kind", "outcome_code", "probability"]]
        .sort_values("outcome_code")
        .reset_index(drop=True),
        expected[["canonical_fixture_key", "snapshot_kind", "outcome_code", "probability"]]
        .sort_values("outcome_code")
        .reset_index(drop=True),
    )
    profiles = build_profiles(workbook, tmp_path / "view")
    assert profiles["summary"]["eligible_unique_issue_slots"] == 1
    auxiliary = profiles["auxiliary_market_support"]
    assert set(auxiliary["market_type"]) == {"asian_handicap", "over_under"}
    assert auxiliary["valid_native_fixture_rate"].eq(1.0).all()
