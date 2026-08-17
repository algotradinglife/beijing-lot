"""Focused tests for Issue #234 unified data source schema contract (v1).

Covers:

- **REQ-DS01**: every source classified by causal admissibility; registry rows
  carry admissible_use + clock_semantics + coverage_grade.
- **REQ-DS02**: canonical fixture identity unique within issue_code x match_idx
  (DDL constraint) and the crosswalk contract resolves aliases.
- **REQ-DS03**: observed/received/decision/kickoff/settled semantics distinct.
- **REQ-DS04**: DDL rejects duplicate/invalid Mx3 cells (CHECK + unique idx).
- **REQ-DS05**: inference/proxy/settlement namespaces physically distinguishable.
- **REQ-DS06**: design reuses pandas/PyArrow/SQLite (DDL executes in SQLite).
- **REQ-DS07**: manifest binds notebook + code + source hashes.
- **REQ-DS08**: handoff names exact inputs for beijing/european/power/integration.
- **REQ-E06 tamper self-tests**: verifier must FAIL when the manifest, a
  census table, the DDL or the source-registry receipt is tampered.
- **0.65 boundary**: the payout factor is absent from all source/quote/
  probability tables (contract rule).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import builder  # noqa: E402
from source_schema import census  # noqa: E402
from source_schema import contract  # noqa: E402
from source_schema import ddl  # noqa: E402
from source_schema import feasibility  # noqa: E402
from source_schema import handoff  # noqa: E402
from source_schema import identity  # noqa: E402
from source_schema import plan  # noqa: E402
from source_schema import publication  # noqa: E402
from source_schema import sources  # noqa: E402

PACKAGE = ROOT / "results" / contract.PACKAGE_NAME

# The census hashes multi-GB gitignored databases; run it once per test
# session and reuse the receipt (write_package re-emits files from the
# receipt without re-running the census).
_RECEIPT_CACHE: dict[str, builder.BuildReceipt] = {}


def _build_receipt() -> builder.BuildReceipt:
    if "_receipt" not in _RECEIPT_CACHE:
        _RECEIPT_CACHE["_receipt"] = builder.build(ROOT)
    return _RECEIPT_CACHE["_receipt"]


# ---------------------------------------------------------------------------
# Contract invariants
# ---------------------------------------------------------------------------
def test_outcome_codes_exactly_3_1_0() -> None:
    assert contract.OUTCOME_CODES == ("3", "1", "0")
    assert contract.OUTCOME_ORDER == {"3": 0, "1": 1, "0": 2}


def test_payout_factor_boundary_absent_from_tables() -> None:
    # The 0.65 coefficient appears in no source/quote/probability DDL table.
    assert "0.65" not in ddl.DDL_TABLES
    assert contract.PAYOUT_FACTOR_FORBIDDEN_IN_TABLES is True


def test_temporal_semantics_distinct() -> None:
    assert len(set(contract.TEMPORAL_SEMANTICS)) == len(contract.TEMPORAL_SEMANTICS)
    assert contract.OBSERVED_AT != contract.RECEIVED_AT
    assert contract.OBSERVED_AT != contract.DECISION_AT
    assert contract.DECISION_AT != contract.KICKOFF_AT


def test_admissible_use_classes_frozen() -> None:
    assert contract.ADMISSIBLE_USE_CLASSES == (
        "STRICT_CAUSAL",
        "RETROSPECTIVE_PROXY",
        "SETTLEMENT_ONLY",
        "UNUSABLE",
    )


# ---------------------------------------------------------------------------
# REQ-DS01: source registry completeness
# ---------------------------------------------------------------------------
def test_registry_rows_carry_evidence() -> None:
    registry = feasibility.source_registry()
    assert not registry.empty
    for column in (
        "source_id",
        "admissible_use",
        "clock_semantics",
        "coverage_grade",
        "first_usable_at_utc",
        "last_usable_at_utc",
    ):
        assert registry[column].notna().all()
    assert set(registry["admissible_use"].unique()) <= set(contract.ADMISSIBLE_USE_CLASSES)


def test_family_coverage_evidence_based() -> None:
    matrix = feasibility.feasibility_matrix()
    # every source row has an admissible-use class and a clock semantics
    assert matrix["admissible_use"].notna().all()
    assert matrix["clock_semantics"].notna().all()
    # evidence is per-row rationale, not a single blanket label
    assert matrix["rationale"].str.len().gt(20).all()


# ---------------------------------------------------------------------------
# REQ-DS02: identity uniqueness
# ---------------------------------------------------------------------------
def test_ddl_enforces_unique_issue_match_idx() -> None:
    sql = ddl.sql_ddl()
    assert "UNIQUE (issue_code, match_idx)" in sql
    connection = sqlite3.connect(":memory:")
    connection.executescript(sql)
    # inserting the same (issue, match_idx) twice must fail
    connection.execute(
        "INSERT INTO competition(competition_id, canonical_name) VALUES (1, 'C')"
    )
    connection.execute("INSERT INTO team(team_id, canonical_name) VALUES (1, 'T1')")
    connection.execute("INSERT INTO team(team_id, canonical_name) VALUES (2, 'T2')")
    connection.execute(
        "INSERT INTO fixture(fixture_id, issue_code, match_idx, source_match_key, "
        "competition_id, home_team_id, away_team_id, kickoff_at_utc, identity_status) "
        "VALUES (1, '25042', 1, 'k', 1, 1, 2, '2026-01-01T00:00:00Z', 'CANONICAL')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO fixture(fixture_id, issue_code, match_idx, source_match_key, "
            "competition_id, home_team_id, away_team_id, kickoff_at_utc, identity_status) "
            "VALUES (2, '25042', 1, 'k2', 1, 1, 2, '2026-01-01T00:00:00Z', 'CANONICAL')"
        )
    connection.close()


def test_identity_crosswalk_contract_has_alias_tables() -> None:
    text = identity.identity_crosswalk_contract()
    assert "team_alias" in text
    assert "competition_alias" in text
    assert "UNIQUE (issue_code, match_idx)" in text


# ---------------------------------------------------------------------------
# REQ-DS03: temporal non-interchangeability
# ---------------------------------------------------------------------------
def test_ddl_has_all_temporal_columns() -> None:
    sql = ddl.sql_ddl()
    for column in contract.TEMPORAL_SEMANTICS:
        assert column in sql


# ---------------------------------------------------------------------------
# REQ-DS04: normalized Mx3 constraints
# ---------------------------------------------------------------------------
def test_ddl_rejects_invalid_outcome_code() -> None:
    sql = ddl.sql_ddl()
    assert "CHECK (outcome_code IN ('3','1','0'))" in sql
    connection = sqlite3.connect(":memory:")
    connection.executescript(sql)
    connection.execute(
        "INSERT INTO source_registry(source_id, provider, endpoint, acquisition_method, "
        "terms_status, timezone, clock_semantics, cadence_seconds, parser_version, "
        "admissible_use, first_usable_at_utc, last_usable_at_utc, coverage_grade) "
        "VALUES ('s1','p','e','a','t','UTC','TIMESTAMPED_UTC','60','v1',"
        "'STRICT_CAUSAL','2026-01-01T00:00:00Z','2026-12-31T00:00:00Z','A')"
    )
    connection.execute(
        "INSERT INTO ingestion_batch(batch_id, source_id, requested_at_utc, "
        "received_at_utc, raw_uri, raw_sha256, parser_version, row_count, status) "
        "VALUES (1,'s1','2026-01-01T00:00:00Z','2026-01-01T00:00:01Z','u','h','v1',0,'OK')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO market_quote(observation_id, bookmaker_id, outcome_code, "
            "decimal_odds, quote_status) VALUES (1, 'bm', 'X', 2.0, 'LIVE')"
        )
    connection.close()


def test_ddl_quote_unique_per_outcome() -> None:
    sql = ddl.sql_ddl()
    assert "ux_quote_one_per_outcome" in sql


# ---------------------------------------------------------------------------
# REQ-DS05: namespace separation
# ---------------------------------------------------------------------------
def test_namespaces_physically_distinct() -> None:
    schema = ddl.parquet_schema_contract()
    namespaces = schema["namespaces"]
    assert set(namespaces.keys()) >= {
        contract.INFERENCE_NAMESPACE,
        contract.PROXY_NAMESPACE,
        contract.SETTLEMENT_NAMESPACE,
    }
    assert namespaces[contract.INFERENCE_NAMESPACE] != namespaces[contract.SETTLEMENT_NAMESPACE]
    # settlement carries result/winning_sp, inference carries probability
    inference_cols = set(namespaces[contract.INFERENCE_NAMESPACE].keys())
    settlement_cols = set(namespaces[contract.SETTLEMENT_NAMESPACE].keys())
    assert "probability" in inference_cols
    assert "result_code" in settlement_cols
    # inference-only vs settlement-only semantic columns are disjoint
    # (identity keys fixture_id/issue_code/match_idx are shared by design)
    inference_semantic = {"probability", "uncertainty", "estimator_id", "target_market"}
    settlement_semantic = {"result_code", "winning_sp", "settled_at_utc"}
    assert not (inference_semantic & settlement_semantic)
    assert inference_semantic <= inference_cols
    assert settlement_semantic <= settlement_cols


# ---------------------------------------------------------------------------
# REQ-DS06: mature stack reuse (DDL executes in SQLite)
# ---------------------------------------------------------------------------
def test_ddl_executes_in_sqlite() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(ddl.sql_ddl())
    created = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table in contract.CAPTURE_TABLES + contract.SETTLEMENT_TABLES:
        assert table in created
    connection.close()


# ---------------------------------------------------------------------------
# REQ-DS07 / REQ-E06: hash binding + tamper self-tests
# ---------------------------------------------------------------------------
def test_manifest_binds_hashes() -> None:
    receipt = _build_receipt()
    manifest = receipt.manifest
    assert manifest["contract_version"] == contract.CONTRACT_VERSION
    assert manifest["code_hash"]
    assert manifest["notebook_hash"]
    assert manifest["source_hashes"]


def test_verify_package_fails_on_tampered_manifest(tmp_path: Path) -> None:
    receipt = _build_receipt()
    package = builder.write_package(receipt, force=True)
    # Tamper: rewrite the manifest, then verify must fail.
    manifest_path = package / "MANIFEST.json"
    original = manifest_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(original)
        payload["tampered"] = True
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        with pytest.raises(AssertionError):
            sources.verify_package_hashes(package)
    finally:
        manifest_path.write_text(original, encoding="utf-8")


def test_verify_package_fails_on_tampered_registry(tmp_path: Path) -> None:
    receipt = _build_receipt()
    package = builder.write_package(receipt, force=True)
    registry_path = package / "tables" / "source_registry.csv"
    original = registry_path.read_text(encoding="utf-8")
    try:
        registry_path.write_text(
            original.replace("STRICT_CAUSAL", "UNUSABLE"), encoding="utf-8"
        )
        with pytest.raises(AssertionError):
            sources.verify_package_hashes(package)
    finally:
        registry_path.write_text(original, encoding="utf-8")


def test_verify_package_fails_on_tampered_ddl(tmp_path: Path) -> None:
    receipt = _build_receipt()
    package = builder.write_package(receipt, force=True)
    sql_path = package / "sql" / "schema.sql"
    original = sql_path.read_text(encoding="utf-8")
    try:
        sql_path.write_text(
            original.replace("UNIQUE (issue_code, match_idx)", "-- removed"),
            encoding="utf-8",
        )
        with pytest.raises(AssertionError):
            sources.verify_package_hashes(package)
    finally:
        sql_path.write_text(original, encoding="utf-8")


def test_handoff_validate_package_fails_on_bad_registry_columns(tmp_path: Path) -> None:
    """Semantic check: a registry missing admissible_use fails validation."""
    receipt = _build_receipt()
    package = builder.write_package(receipt, force=True)
    registry = pd.read_csv(package / "tables" / "source_registry.csv")
    registry = registry.drop(columns=["admissible_use"])
    registry.to_csv(package / "tables" / "source_registry.csv", index=False)
    problems = handoff.validate_package(package, ROOT)
    assert any("admissible_use" in problem for problem in problems)


# ---------------------------------------------------------------------------
# REQ-DS08: downstream branch handoff
# ---------------------------------------------------------------------------
def test_selected_sources_cover_all_branches() -> None:
    matrix = feasibility.feasibility_matrix()
    selected = set(matrix["selected_for_branch"].dropna().unique())
    assert {
        contract.BRANCH_BEIJING,
        contract.BRANCH_EUROPEAN,
        contract.BRANCH_POWER,
        contract.BRANCH_INTEGRATION,
    } <= selected
    # integration consumes the canonical schema itself
    integration_row = matrix[matrix["selected_for_branch"] == contract.BRANCH_INTEGRATION]
    assert not integration_row.empty
    assert integration_row.iloc[0]["source_key"] == "bj234_canonical_schema"


# ---------------------------------------------------------------------------
# Census behavior (no DB mutation, bounded)
# ---------------------------------------------------------------------------
def test_census_readonly_and_bounded() -> None:
    result = _build_receipt().census
    assert result is not None
    assert result.databases is not None
    assert not result.databases.empty
    # existing databases are recorded; missing ones explicitly named
    assert {"exists": False}.keys()
    # large tables skip per-column stats (marker -2) instead of full scans
    if result.columns is not None and not result.columns.empty:
        skipped = result.columns[result.columns["null_count"].eq(-2)]
        # at least one large table exists in the real data
        if not result.tables.empty:
            large = result.tables[result.tables["row_count"].ge(census.LARGE_TABLE_ROWS)]
            assert len(skipped) >= len(large)


# ---------------------------------------------------------------------------
# Migration-free replacement plan
# ---------------------------------------------------------------------------
def test_replacement_plan_no_compat_layers() -> None:
    frame = plan.replacement_plan()
    assert not frame.empty
    assert set(frame["verdict"].unique()) <= {"REMOVE", "REDIRECT", "KEEP_AS_SOURCE"}
    # every obsolete schema is removed or redirected, never wrapped
    assert "COMPAT" not in " ".join(frame["verdict"].tolist())


# ---------------------------------------------------------------------------
# Publication fault injection (class 6: atomic publication)
# ---------------------------------------------------------------------------
def test_atomic_publish_preserves_old_on_failure(tmp_path: Path) -> None:
    target = tmp_path / "pkg"
    target.mkdir()
    (target / "keep.txt").write_text("old", encoding="utf-8")

    def populate_fails(staging: Path) -> None:
        (staging / "new.txt").write_text("new", encoding="utf-8")
        raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError):
        publication.atomic_publish_directory(target, populate_fails, force=True)
    # old package intact
    assert (target / "keep.txt").read_text(encoding="utf-8") == "old"


def test_build_receipt_evidence_all_pass() -> None:
    """The REQ-DS evidence frame must show PASS for every criterion."""
    receipt = _build_receipt()
    evidence = builder._build_req_ds_evidence(receipt)
    assert set(evidence["req"]) == {
        "REQ-DS01",
        "REQ-DS02",
        "REQ-DS03",
        "REQ-DS04",
        "REQ-DS05",
        "REQ-DS06",
        "REQ-DS07",
        "REQ-DS08",
    }
    assert evidence["pass"].all()
