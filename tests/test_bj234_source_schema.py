"""Issue #234 — contract test suite (v2, EV R1 rework).

Covers EV defect classes C1..C4 and E1/E2 plus REQ-DS01..08 and REQ-E06.

Isolation rule (E1): every test that builds or tampers a package targets a
``tmp_path`` copy.  No test writes to the committed
``results/bj234_source_schema_contract_v1`` directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "results" / "bj234_source_schema_contract_v1"


@pytest.fixture(scope="session")
def package() -> Path:
    assert PKG.exists(), "run build first: scripts/build_bj234_source_schema.py build"
    return PKG


@pytest.fixture()
def pkg_copy(package: Path, tmp_path: Path) -> Path:
    target = tmp_path / "pkg"
    shutil.copytree(package, target)
    return target


# ---------------------------------------------------------------------------
# C1: identity metrics — NULL-aware, correct primitive keys
# ---------------------------------------------------------------------------
def test_identity_null_rows_never_counted_as_duplicates(package: Path):
    frame = pd.read_csv(package / "tables" / "identity_checks.csv")
    assert not frame.empty
    for _, row in frame.iterrows():
        excess = int(row["duplicate_excess"])
        verdict = row["uniqueness_verdict"]
        assert excess >= 0, f"{row['table']}: negative duplicate excess"
        if verdict == "DUPLICATE_DEFECT":
            assert excess > 0, (
                f"{row['table']}: DUPLICATE_DEFECT with excess=0 "
                "(NULL rows mis-counted as duplicates)"
            )


def test_identity_long_form_key_includes_outcome_code(package: Path):
    frame = pd.read_csv(package / "tables" / "identity_checks.csv")
    outcome = frame[frame["table"] == "outcome_features"]
    assert not outcome.empty
    assert outcome.iloc[0]["primitive_key"] == "issue|match_idx|outcome_code"


def test_identity_legacy_real_duplicate_excess_is_zero(package: Path):
    """EV independent recomputation: real non-null duplicate excess = 0
    for beidan_xlsm tables.  beidan_features.matches has 3 REAL duplicate
    match_id rows (190,743 distinct of 190,746) — named, not hidden."""
    frame = pd.read_csv(package / "tables" / "identity_checks.csv")
    xlsm = frame[frame["database_key"] == "beidan_xlsm.sqlite"]
    assert not xlsm.empty
    for _, row in xlsm.iterrows():
        assert int(row["duplicate_excess"]) == 0, (
            f"{row['table']}: real duplicate excess should be 0; "
            f"NULL-key rows are {row['null_key_rows']}"
        )
    feat = frame[(frame["database_key"] == "beidan_features.db")
                 & (frame["table"] == "matches")]
    assert not feat.empty
    assert int(feat.iloc[0]["duplicate_excess"]) == 3
    assert feat.iloc[0]["uniqueness_verdict"] == "DUPLICATE_DEFECT"


def test_identity_counts_match_ev_recalculation(package: Path):
    frame = pd.read_csv(package / "tables" / "identity_checks.csv")
    matches = frame[(frame["database_key"] == "beidan_xlsm.sqlite")
                    & (frame["table"] == "matches")]
    assert not matches.empty
    row = matches.iloc[0]
    # EV: 195,269 total; 2,560 NULL-key; 192,709 non-null distinct
    assert int(row["total_rows"]) == 195_269
    assert int(row["null_key_rows"]) == 2_560
    assert int(row["non_null_rows"]) == 192_709
    assert int(row["distinct_non_null_keys"]) == 192_709


# ---------------------------------------------------------------------------
# C2: source lineage — evidence-based, honest provider names
# ---------------------------------------------------------------------------
def test_registry_every_row_has_evidence(package: Path):
    frame = pd.read_csv(package / "tables" / "source_registry.csv")
    assert {"source_id", "provider", "endpoint", "endpoint_evidence",
            "admissible_use", "clock_semantics", "raw_sha256"} <= set(frame.columns)
    for _, row in frame.iterrows():
        assert str(row["endpoint_evidence"]).strip(), row["source_id"]
        assert str(row["raw_sha256"]).strip(), row["source_id"]


def test_registry_no_500_masquerade(package: Path):
    """EV C2: 500.com collector must not be labelled Beijing official."""
    frame = pd.read_csv(package / "tables" / "source_registry.csv")
    beijing = frame[frame["source_id"] == "BEIDAN_LIVE_DB"].iloc[0]
    assert "500.com" in beijing["provider"]
    assert "official" not in beijing["provider"].lower()
    first_party = frame[frame["source_id"] == "BJ_FIRST_PARTY_OFFICIAL"].iloc[0]
    assert first_party["admissible_use"] == "UNUSABLE"
    assert first_party["raw_sha256"] == "NO_RECEIPT"


def test_registry_strict_causal_requires_receipt(package: Path):
    frame = pd.read_csv(package / "tables" / "source_registry.csv")
    for _, row in frame.iterrows():
        if row["admissible_use"] == "STRICT_CAUSAL":
            assert row["clock_semantics"] == "TIMESTAMPED_UTC"
            raw = str(row["raw_sha256"])
            assert raw and raw not in ("NO_RECEIPT", "PENDING_CENSUS"), row["source_id"]


def test_registry_selected_source_per_branch(package: Path):
    matrix = pd.read_csv(package / "tables" / "feasibility_matrix.csv")
    selected = set(matrix["selected_for_branch"].dropna().unique())
    assert {"BJ_SP_TIMESERIES #235", "EU_ODDS #236", "POWER_FEATURES #237",
            "INTEGRATION #238"} <= selected


def test_registry_0_65_absent_from_tables(package: Path):
    """REQ-E06: 0.65 never appears in registry/quote/probability payloads."""
    frame = pd.read_csv(package / "tables" / "source_registry.csv")
    for column in frame.columns:
        assert "0.65" not in str(frame[column].tolist())
    ddl_text = (package / "sql" / "schema.sql").read_text()
    # strip comments: the DDL header states the 0.65 boundary rule as a note;
    # a literal 0.65 in any executable statement is the violation.
    ddl_no_comments = "\n".join(
        line.split("--", 1)[0] for line in ddl_text.splitlines()
    )
    assert "0.65" not in ddl_no_comments


# ---------------------------------------------------------------------------
# C3: DDL executes with real constraints (semantic, not string-presence)
# ---------------------------------------------------------------------------
@pytest.fixture()
def ddl_conn() -> sqlite3.Connection:
    from source_schema import ddl as ddl_mod
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl_mod.sql_ddl())
    yield conn
    conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO source_registry VALUES "
                 "('s1','p','e','a','t','UTC','TIMESTAMPED_UTC','60','v1',"
                 "'STRICT_CAUSAL','2026-01-01T00:00:00Z','2026-12-31T00:00:00Z','A','abc','')")
    conn.execute("INSERT INTO team VALUES (1,'T')")
    conn.execute("INSERT INTO competition VALUES (1,'C')")
    conn.execute("INSERT INTO fixture VALUES (1,'26001',1,'k',1,1,1,"
                 "'2026-05-01T01:00:00Z',0.5,NULL,'CANONICAL')")
    conn.execute("INSERT INTO ingestion_batch VALUES (1,'s1','2026-05-01T00:00:00Z',"
                 "'2026-05-01T00:01:00Z','u','h','v1',1,'OK')")


def test_ddl_fixture_alias_exists(ddl_conn):
    tables = {r[0] for r in ddl_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "fixture_alias" in tables


def test_ddl_quote_pk_includes_bookmaker(ddl_conn):
    pk = {r[1] for r in ddl_conn.execute("PRAGMA table_info(market_quote)") if r[5] > 0}
    assert pk == {"observation_id", "bookmaker_id", "outcome_code"}


def test_ddl_no_index_erases_bookmaker(ddl_conn):
    indexes = [r[0] for r in ddl_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='market_quote'")]
    for idx in indexes:
        sql_row = ddl_conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (idx,)
        ).fetchone()
        if sql_row and sql_row[0]:
            assert "bookmaker_id" in sql_row[0], f"index {idx} erases bookmaker_id"


def test_ddl_multi_bookmaker_quotes_legal(ddl_conn):
    _seed(ddl_conn)
    ddl_conn.execute("INSERT INTO market_observation VALUES (3,1,'s1','euro_1x2',NULL,"
                     "'2026-04-28T00:00:00Z','2026-04-28T00:01:00Z','initial',1)")
    ddl_conn.execute("INSERT INTO market_quote VALUES (3,'bm1','3',2.1,'LIVE')")
    ddl_conn.execute("INSERT INTO market_quote VALUES (3,'bm2','3',2.2,'LIVE')")
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_quote VALUES (3,'bm1','3',2.3,'LIVE')")


def test_ddl_duplicate_primitive_observation_rejected(ddl_conn):
    _seed(ddl_conn)
    ddl_conn.execute("INSERT INTO market_observation VALUES (1,1,'s1','euro_1x2',NULL,"
                     "'2026-04-30T00:00:00Z','2026-04-30T00:01:00Z','initial',1)")
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_observation VALUES (2,1,'s1','euro_1x2',NULL,"
                         "'2026-04-30T00:00:00Z','2026-04-30T00:01:00Z','initial',1)")


def test_ddl_null_handicap_probability_collides(ddl_conn):
    """C3: NULL handicap (euro cell) must collide under COALESCE unique."""
    _seed(ddl_conn)
    ddl_conn.execute("INSERT INTO decision_epoch VALUES (1,'26001','2026-04-29T00:00:00Z','r1','v1')")
    ddl_conn.execute("INSERT INTO probability_estimate VALUES (1,1,1,'est','euro_1x2',NULL,'3',"
                     "0.5,NULL,'2026-04-30T00:00:00Z','c1','h1')")
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO probability_estimate VALUES (2,1,1,'est','euro_1x2',NULL,'3',"
                         "0.6,NULL,'2026-04-30T00:00:00Z','c1','h2')")


def test_ddl_fk_rejects_orphan_quote(ddl_conn):
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_quote VALUES (999999,'bm','3',2.0,'LIVE')")


def test_ddl_alias_no_overlap(ddl_conn):
    _seed(ddl_conn)
    ddl_conn.execute("INSERT INTO team_alias VALUES ('s1','k',1,"
                     "'2026-01-01T00:00:00Z','2026-02-01T00:00:00Z')")
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO team_alias VALUES ('s1','k',1,"
                         "'2026-01-15T00:00:00Z',NULL)")


def test_ddl_timestamp_order_rejected(ddl_conn):
    _seed(ddl_conn)
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_observation VALUES (1,1,'s1','euro_1x2',NULL,"
                         "'2026-05-01T00:02:00Z','2026-05-01T00:01:00Z','initial',1)")


def test_ddl_observation_after_kickoff_rejected(ddl_conn):
    _seed(ddl_conn)
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_observation VALUES (1,1,'s1','euro_1x2',NULL,"
                         "'2026-05-02T00:00:00Z','2026-05-02T00:01:00Z','initial',1)")


def test_ddl_live_snapshot_kind_accepted(ddl_conn):
    """EV R1 C3-5: prospective live/instant snapshot kinds must be expressible.

    beidan_live.db / 500_bjdc live_market_sp_snapshots are the primary
    prospective causal source; the canonical schema must accept a
    snapshot_kind='live' market_observation.
    """
    _seed(ddl_conn)
    ddl_conn.execute("INSERT INTO market_observation VALUES (7,1,'s1','sp_1x2',NULL,"
                     "'2026-04-28T00:00:00Z','2026-04-28T00:01:00Z','live',1)")


def test_ddl_invalid_snapshot_kind_rejected(ddl_conn):
    _seed(ddl_conn)
    with pytest.raises(sqlite3.IntegrityError):
        ddl_conn.execute("INSERT INTO market_observation VALUES (8,1,'s1','euro_1x2',NULL,"
                         "'2026-04-28T00:00:00Z','2026-04-28T00:01:00Z','bogus',1)")


def test_ddl_incomplete_triplet_view_exists(ddl_conn):
    views = {r[0] for r in ddl_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    assert "v_incomplete_triplets" in views


# ---------------------------------------------------------------------------
# C4: label sealing — sealed values are physically unreadable
# ---------------------------------------------------------------------------
def test_sealing_guard_blocks_sealed_column():
    from source_schema import profiler
    with pytest.raises(profiler.SealedColumnError):
        profiler.assert_measurable("beidan_xlsm.sqlite", "matches", "result_label")
    with pytest.raises(profiler.SealedColumnError):
        profiler.assert_measurable("beidan_live.db", "settlements", "winning_sp")
    # allow-listed columns pass
    profiler.assert_measurable("beidan_live.db", "snapshots", "snapshot_ts")


def test_sealing_evidence_published(package: Path):
    sealed = pd.read_csv(package / "tables" / "sealed_columns.csv")
    assert not sealed.empty
    # census value stats never contain sealed columns (keyed by db+table+col)
    cols = pd.read_csv(package / "tables" / "columns.csv")
    sealed_combos = set(zip(sealed["database_key"], sealed["table"],
                           sealed.get("column", "").fillna("")))
    for _, row in cols.iterrows():
        key = (str(row.get("database_key", "")), str(row["table"]),
               str(row.get("column", "")))
        assert key not in sealed_combos


def test_sealing_settlement_table_metadata_only(package: Path):
    tables = pd.read_csv(package / "tables" / "tables.csv")
    settlements = tables[tables["table"].isin(["settlements", "official_500_settlements",
                                               "official_3sp_settlements",
                                               "multimarket_settlement_truth"])]
    for _, row in settlements.iterrows():
        assert row["sealed"] is True or str(row["sealed"]).lower() == "true"


# ---------------------------------------------------------------------------
# E1: tests must never write the committed package; build targets tmp
# ---------------------------------------------------------------------------
def test_build_to_tmp_path_never_touches_committed(package: Path, tmp_path: Path):
    committed_before = (package / "MANIFEST.json").read_bytes()
    from source_schema import builder
    target = tmp_path / "built_pkg"
    builder.build_package(ROOT, target, force=True)
    assert target.exists()
    assert (package / "MANIFEST.json").read_bytes() == committed_before
    from source_schema import verify
    verdict = verify.verify_package(target, ROOT)
    assert verdict["verified"], verdict["problems"]


def test_committed_package_verifies_clean(package: Path):
    from source_schema import verify
    verdict = verify.verify_package(package, ROOT)
    assert verdict["verified"], verdict["problems"]


# ---------------------------------------------------------------------------
# E2: semantic verifier fails closed on remanifest attacks
# ---------------------------------------------------------------------------
def _attack(pkg_copy: Path, mutate) -> None:
    mutate(pkg_copy)


def test_e2_attack_all_sources_unusable(pkg_copy: Path):
    from source_schema import verify
    path = pkg_copy / "tables" / "source_registry.csv"
    frame = pd.read_csv(path)
    frame["admissible_use"] = "UNUSABLE"
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_registry_single_source(pkg_copy: Path):
    from source_schema import verify
    path = pkg_copy / "tables" / "source_registry.csv"
    frame = pd.read_csv(path)
    frame = frame.head(1)
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_empty_raw_hashes(pkg_copy: Path):
    from source_schema import verify
    path = pkg_copy / "tables" / "source_registry.csv"
    frame = pd.read_csv(path)
    frame["raw_sha256"] = ""
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_forge_selected_sources(pkg_copy: Path):
    from source_schema import verify
    path = pkg_copy / "tables" / "source_registry.csv"
    frame = pd.read_csv(path)
    frame["selected_for_branch"] = "BJ_SP_TIMESERIES #235"
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    # forged selection must break DS08 coverage (missing branches)
    assert not verdict["verified"]


def test_e2_attack_forge_manifest_hashes(pkg_copy: Path):
    from source_schema import verify
    manifest = json.loads((pkg_copy / "MANIFEST.json").read_text())
    manifest["ddl_sha256"] = "0" * 64
    manifest["code_hash"] = "0" * 64
    (pkg_copy / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_delete_quote_unique_index(pkg_copy: Path):
    from source_schema import verify
    sql = (pkg_copy / "sql" / "schema.sql").read_text()
    # delete the quote PK constraint (bookmaker identity)
    sql = sql.replace("PRIMARY KEY (observation_id, bookmaker_id, outcome_code)",
                      "PRIMARY KEY (observation_id, outcome_code)")
    (pkg_copy / "sql" / "schema.sql").write_text(sql)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_inject_0_65(pkg_copy: Path):
    from source_schema import verify
    sql = (pkg_copy / "sql" / "schema.sql").read_text()
    sql = sql.replace("decimal_odds   REAL NOT NULL CHECK (decimal_odds > 1.0),",
                      "decimal_odds   REAL NOT NULL DEFAULT 0.65 CHECK (decimal_odds > 1.0),")
    (pkg_copy / "sql" / "schema.sql").write_text(sql)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_mix_namespace_columns(pkg_copy: Path):
    from source_schema import verify
    path = pkg_copy / "schemas" / "parquet_schema.json"
    schemas = json.loads(path.read_text())
    schemas["namespaces"]["inference"]["winning_sp"] = "double"
    path.write_text(json.dumps(schemas, indent=2))
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_remove_observed_column(pkg_copy: Path):
    from source_schema import verify
    sql = (pkg_copy / "sql" / "schema.sql").read_text()
    sql = sql.replace("observed_at_utc  TEXT NOT NULL CHECK (observed_at_utc GLOB '????-??-??T??:??:??Z'),\n", "")
    (pkg_copy / "sql" / "schema.sql").write_text(sql)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_e2_attack_duplicate_verdict_regression(pkg_copy: Path):
    """C1 regression: NULL rows reported as duplicates must fail verify."""
    from source_schema import verify
    path = pkg_copy / "tables" / "identity_checks.csv"
    frame = pd.read_csv(path)
    frame["uniqueness_verdict"] = "DUPLICATE_DEFECT"
    frame["duplicate_excess"] = 0
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


# ---------------------------------------------------------------------------
# REQ-E06 tamper self-tests (attacks against MY implementation)
# ---------------------------------------------------------------------------
def test_tamper_manifest_forge_fails(pkg_copy: Path):
    from source_schema import verify
    manifest = json.loads((pkg_copy / "MANIFEST.json").read_text())
    manifest["contract_version"] = "BJ-UNIFIED-DATA-SOURCE-SCHEMA-FORGED"
    (pkg_copy / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_tamper_byte_manifest_fails(pkg_copy: Path):
    from source_schema import verify
    sql_path = pkg_copy / "sql" / "schema.sql"
    sql_path.write_text(sql_path.read_text() + "\n-- tampered\n")
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_tamper_registry_label_future_info_fails(pkg_copy: Path):
    """Forge source trace: set future first_usable date -> STRICT_CAUSAL check
    should not pass silently (receipt required)."""
    from source_schema import verify
    path = pkg_copy / "tables" / "source_registry.csv"
    frame = pd.read_csv(path)
    frame.loc[frame["admissible_use"] == "STRICT_CAUSAL", "raw_sha256"] = "NO_RECEIPT"
    frame.to_csv(path, index=False)
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


def test_tamper_settlement_namespace_merge_fails(pkg_copy: Path):
    """REQ-DS05/DS04: settlement semantics leaking into inference must fail."""
    from source_schema import verify
    path = pkg_copy / "schemas" / "parquet_schema.json"
    schemas = json.loads(path.read_text())
    schemas["namespaces"]["inference"]["result_code"] = "string"
    path.write_text(json.dumps(schemas, indent=2))
    verdict = verify.verify_package(pkg_copy, ROOT)
    assert not verdict["verified"]


# ---------------------------------------------------------------------------
# REQ-DS07: notebook binds machine-readable outputs + source hashes
# ---------------------------------------------------------------------------
def test_notebook_committed_executed(package: Path):
    nb_path = ROOT / "notebooks" / "research" / "issue-234" / "bj234_source_schema.ipynb"
    assert nb_path.exists()
    nb = json.loads(nb_path.read_text())
    code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert code_cells
    for cell in code_cells:
        assert cell.get("execution_count") not in (None, 0), "cell not executed"


def test_manifest_binds_source_hashes(package: Path):
    manifest = json.loads((package / "MANIFEST.json").read_text())
    assert manifest["source_hashes"], "source hashes must bind reviewed assets"
    assert any(v for v in manifest["source_hashes"].values())


# ---------------------------------------------------------------------------
# REQ-DS02: canonical identity unique within issue x match_idx
# ---------------------------------------------------------------------------
def test_ddl_identity_unique(package: Path):
    sql = (package / "sql" / "schema.sql").read_text()
    assert "UNIQUE (issue_code, match_idx)" in sql
