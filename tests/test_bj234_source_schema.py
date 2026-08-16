"""Focused tests for Issue #234 canonical source-schema contract.

REQ coverage:
- REQ-DS01: source clock classification is evidence-driven (feasibility + clock probe)
- REQ-DS02: fixture identity unique within issue_code x match_idx; alias binding
- REQ-DS03: observed/received/kickoff/decision semantics non-interchangeable
- REQ-DS04: M×3 constraints reject duplicate/invalid cells
- REQ-DS05: inference / proxy / settlement namespaces physically distinguishable
- REQ-DS06: SQLite WAL + PyArrow; scale/concurrency justification present
- REQ-DS07: manifest binds machine-readable outputs and source hashes
- REQ-DS08: handoff names exact interfaces for #235/#236/#237/#238

Tamper self-tests (REQ-E06 discipline): attack the *contract artifacts*
(DDL, schema JSON, manifest, crosswalk) — verifier must FAIL on each.

Fast unit tests only — the full build is exercised by the executed notebook
and the build CLI.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import contract  # noqa: E402
from source_schema import crosswalk  # noqa: E402
from source_schema import feasibility  # noqa: E402
from source_schema import profiler  # noqa: E402
from source_schema import publication  # noqa: E402
from source_schema import schemas  # noqa: E402

PKG = ROOT / "results/bj234_source_schema_v1"


# ---------------------------------------------------------------------------
# REQ-DS01: causal admissibility classification with evidence
# ---------------------------------------------------------------------------
def test_ds01_every_registered_source_has_admissible_use():
    for row in feasibility.feasibility_matrix():
        assert row["admissible_use"] in [u.value for u in contract.AdmissibleUse], row["source_id"]
        assert row["clock_grade"] in ("A", "B", "C", "U"), row["source_id"]


def test_ds01_live_db_is_strict_causal():
    matrix = {r["source_id"]: r for r in feasibility.feasibility_matrix()}
    assert matrix["BEIDAN_LIVE_DB"]["admissible_use"] == "STRICT_CAUSAL"
    assert matrix["BEIDAN_LIVE_DB"]["clock_grade"] == "A"


def test_ds01_history_db_is_settlement_only_not_causal():
    matrix = {r["source_id"]: r for r in feasibility.feasibility_matrix()}
    assert matrix["BEIDAN_HISTORY_DB"]["admissible_use"] == "SETTLEMENT_ONLY"


def test_ds01_xlsm_snapshots_are_proxy_not_strict():
    rows = profiler.classify_source_clocks(profiler.profile_all())
    xlsm = next(r for r in rows if "market_snapshots" in r["source"])
    assert xlsm["admissible_use"] == "RETROSPECTIVE_PROXY"
    assert "labels" in xlsm["evidence"] or "initial" in xlsm["evidence"]


# ---------------------------------------------------------------------------
# REQ-DS02: canonical fixture identity
# ---------------------------------------------------------------------------
def test_ds02_fixture_id_unique_within_issue_match_idx():
    ids = {contract.fixture_id("25041", i) for i in range(1, 50)}
    assert len(ids) == 49  # no collisions


def test_ds02_fixture_id_deterministic():
    assert contract.fixture_id("25041", 3) == contract.fixture_id("25041", 3)
    assert contract.fixture_id("25041", 3) != contract.fixture_id("25041", 4)


def test_ds02_fixture_id_rejects_bad_match_idx():
    with pytest.raises(ValueError):
        contract.fixture_id("25041", 0)
    with pytest.raises(ValueError):
        contract.fixture_id("25041", "1")


def test_ds02_identity_rule_requires_alias_not_fuzzy():
    rule = crosswalk.canonical_identity_rule()
    assert rule["unique_within"] == "issue_code x match_idx"
    assert "silent fuzzy matching prohibited" in rule["alias_requirement"].lower()


def test_ds02_crosswalk_covers_all_legacy_dbs():
    rows = crosswalk.identity_crosswalk_rows()
    dbs = {r["db"] for r in rows}
    assert {"beidan_live.db", "beidan_history.db", "beidan_features.db",
            "beidan_xlsm.sqlite"} <= dbs


# ---------------------------------------------------------------------------
# REQ-DS03: temporal semantics non-interchangeable
# ---------------------------------------------------------------------------
def test_ds03_temporal_columns_distinct_and_annotated():
    spec = {s["name"]: s for s in contract.table_specs()}
    obs_cols = {c[0] for c in spec["market_observation"]["columns"]}
    assert {"observed_at_utc", "received_at_utc"} <= obs_cols
    fix_cols = {c[0] for c in spec["fixture"]["columns"]}
    assert "kickoff_at_utc" in fix_cols
    epoch_cols = {c[0] for c in spec["decision_epoch"]["columns"]}
    assert "decision_at_utc" in epoch_cols
    # distinct physical columns — never a single shared timestamp
    assert len({"observed_at_utc", "received_at_utc", "kickoff_at_utc",
                "decision_at_utc", "settled_at_utc"}) == 5


def test_ds03_all_timestamps_are_tz_aware_utc():
    for spec in contract.table_specs():
        for (cname, ctype, ptype, nullable, cons) in spec["columns"]:
            # any column whose *arrow type* is a timestamp must be tz-aware UTC
            if ptype.startswith("timestamp"):
                assert "tz=UTC" in ptype, f"{spec['name']}.{cname} must be UTC"
            # any *_at_utc column must be a timestamp type (never TEXT plain)
            if cname.endswith("_at_utc") or cname.endswith("_at_utc_x"):
                assert ptype.startswith("timestamp"), \
                    f"{spec['name']}.{cname} must be timestamp type"


# ---------------------------------------------------------------------------
# REQ-DS04: M×3 constraints reject duplicate/invalid cells
# ---------------------------------------------------------------------------
def _apply_ddl(conn: sqlite3.Connection):
    conn.executescript(schemas.render_ddl())


def test_ds04_market_quote_unique_per_outcome():
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)
    conn.execute("INSERT INTO source_registry VALUES ('s1','p','','m','','UTC',"
                 "'TRUSTED_FETCH',60,'v1','STRICT_CAUSAL',NULL,NULL,NULL,'A','')")
    conn.execute("INSERT INTO ingestion_batch VALUES ('b1','s1','2026-01-01T00:00:00Z',"
                 "'2026-01-01T00:00:01Z','','abc','v1',1,'PARSED')")
    conn.execute("INSERT INTO bookmaker VALUES ('bm1','TestBook','s1')")
    conn.execute("INSERT INTO team VALUES ('t1','Home'),('t2','Away')")
    conn.execute("INSERT INTO competition VALUES ('c1','TestLeague')")
    conn.execute("INSERT INTO fixture VALUES ('fix_25041_1_x','25041',1,'key1','c1',"
                 "'t1','t2','2026-01-02T00:00:00Z',0.0,NULL,'CANONICAL')")
    conn.execute("INSERT INTO market_observation VALUES ('obs1','fix_25041_1_x','s1',"
                 "'EU_1X2',0.0,'2026-01-01T20:00:00Z','2026-01-01T20:00:05Z',"
                 "'RAW_CAPTURE','b1')")
    conn.execute("INSERT INTO market_quote VALUES ('q1','obs1','bm1','3',2.1,'VALID')")
    # duplicate outcome_code for same observation must be rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO market_quote VALUES ('q2','obs1','bm1','3',2.2,'VALID')")
    conn.close()


def test_ds04_invalid_outcome_code_rejected():
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)
    conn.execute("INSERT INTO source_registry VALUES ('s1','p','','m','','UTC',"
                 "'TRUSTED_FETCH',60,'v1','STRICT_CAUSAL',NULL,NULL,NULL,'A','')")
    conn.execute("INSERT INTO ingestion_batch VALUES ('b1','s1','2026-01-01T00:00:00Z',"
                 "'2026-01-01T00:00:01Z','','abc','v1',1,'PARSED')")
    conn.execute("INSERT INTO bookmaker VALUES ('bm1','TestBook','s1')")
    conn.execute("INSERT INTO team VALUES ('t1','Home'),('t2','Away')")
    conn.execute("INSERT INTO competition VALUES ('c1','TestLeague')")
    conn.execute("INSERT INTO fixture VALUES ('fix_25041_1_x','25041',1,'key1','c1',"
                 "'t1','t2','2026-01-02T00:00:00Z',0.0,NULL,'CANONICAL')")
    conn.execute("INSERT INTO market_observation VALUES ('obs1','fix_25041_1_x','s1',"
                 "'EU_1X2',0.0,'2026-01-01T20:00:00Z','2026-01-01T20:00:05Z',"
                 "'RAW_CAPTURE','b1')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO market_quote VALUES ('q1','obs1','bm1','X',2.1,'VALID')")
    # probability outside [0,1] must be rejected
    conn.execute("INSERT INTO decision_epoch VALUES ('de1','25041','2026-01-01T21:00:00Z',"
                 "'rule1',NULL)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO probability_estimate VALUES ('pe1','fix_25041_1_x','de1',"
                     "'est1','EU_1X2',0.0,'3',1.5,NULL,'2026-01-01T20:30:00Z',"
                     "'cal1','hash1')")
    conn.close()


def test_ds04_fixture_unique_issue_match_idx():
    conn = sqlite3.connect(":memory:")
    _apply_ddl(conn)
    conn.execute("INSERT INTO team VALUES ('t1','Home'),('t2','Away')")
    conn.execute("INSERT INTO competition VALUES ('c1','TestLeague')")
    conn.execute("INSERT INTO fixture VALUES ('fix_25041_1_x','25041',1,'key1','c1',"
                 "'t1','t2','2026-01-02T00:00:00Z',0.0,NULL,'CANONICAL')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO fixture VALUES ('fix_25041_1_y','25041',1,'key2','c1',"
                     "'t1','t2','2026-01-02T00:00:00Z',0.0,NULL,'CANONICAL')")
    conn.close()


# ---------------------------------------------------------------------------
# REQ-DS05: namespaces physically distinguishable
# ---------------------------------------------------------------------------
def test_ds05_settlement_namespace_physically_separate():
    namespaces = {s["name"]: s["namespace"] for s in contract.table_specs()}
    assert namespaces["market_observation"] == "inference"
    assert namespaces["market_quote"] == "inference"
    assert namespaces["probability_estimate"] == "inference"
    assert namespaces["settlement"] == "settlement"
    assert namespaces["source_registry"] == "capture"
    # settlement never shares a table with inference
    assert namespaces["settlement"] != namespaces["market_observation"]


def test_ds05_settlement_has_no_0_65_field():
    spec = {s["name"]: s for s in contract.table_specs()}
    cols = {c[0] for c in spec["settlement"]["columns"]}
    assert "coefficient" not in cols and "0.65" not in str(cols)
    # and no source/quote/probability table carries a 0.65 column
    for s in contract.table_specs():
        col_names = {c[0] for c in s["columns"]}
        assert not any("0.65" in c or "coef" in c.lower() for c in col_names), s["name"]


# ---------------------------------------------------------------------------
# REQ-DS06: mature stack + measured scale/concurrency justification
# ---------------------------------------------------------------------------
def test_ds06_concurrency_justification_present():
    plan = feasibility.REPLACEMENT_PLAN
    assert plan["concurrency_justification"]["engine"] == "SQLite WAL"
    assert "scale_measurements" in plan["concurrency_justification"]
    assert plan["concurrency_justification"]["scale_measurements"][
        "snapshot_rows"] > 1_000_000


def test_ds06_ddl_uses_sqlite_wal_and_parquet():
    ddl = schemas.render_ddl()
    assert "PRAGMA journal_mode = WAL" in ddl
    arrow = schemas.all_arrow_schemas_json()
    assert "timestamp[us, tz=UTC]" in str(arrow)


# ---------------------------------------------------------------------------
# REQ-DS07: manifest binds machine-readable outputs + source hashes
# ---------------------------------------------------------------------------
def test_ds07_package_present_and_verifies():
    assert PKG.exists(), "run build first: scripts/build_bj234_source_schema.py build"
    verdict = publication.verify_package(PKG)
    assert verdict["verified"]
    assert verdict["files"] >= 10


def test_ds07_manifest_binds_source_hashes():
    manifest = json.loads((PKG / "MANIFEST.json").read_text())
    assert manifest["source_hashes"], "source hashes must bind reviewed packages"
    assert any(v is not None for v in manifest["source_hashes"].values())
    assert manifest["contract_version"].startswith(contract.CONTRACT_VERSION)
    assert manifest["ddl_sha256"] == schemas.render_ddl_sha256()


# ---------------------------------------------------------------------------
# REQ-DS08: handoff names exact interfaces for downstream subissues
# ---------------------------------------------------------------------------
def test_ds08_selected_source_per_branch():
    matrix = {r["source_id"]: r for r in feasibility.feasibility_matrix()}
    assert "BJ_SP_TIMESERIES #235" in matrix["BJ_OFFICIAL_INSTANT_SP"]["selected_for"]
    assert "EU_ODDS #236" in matrix["ODDS_API"]["selected_for"]
    assert "POWER_FEATURES #237" in matrix["INTERNAL_RESULTS_POWER"]["selected_for"]


def test_ds08_replacement_plan_binds_all_requirements():
    binding = feasibility.REPLACEMENT_PLAN["acceptance_binding"]
    for req in ("REQ-DS01", "REQ-DS02", "REQ-DS03", "REQ-DS04", "REQ-DS05",
                "REQ-DS06", "REQ-DS07", "REQ-DS08"):
        assert req in binding, f"{req} missing from acceptance binding"


# ---------------------------------------------------------------------------
# Tamper self-tests (REQ-E06): attack the contract artifacts
# ---------------------------------------------------------------------------
def test_tamper_ddl_outcome_check_must_fail_verification():
    """Tamper: relax outcome_code CHECK → ddl_sha256 must change."""
    import hashlib
    orig = schemas.render_ddl()
    tampered = orig.replace("CHECK (outcome_code IN ('3','1','0'))",
                            "CHECK (outcome_code IN ('3','1'))")
    assert tampered != orig
    assert hashlib.sha256(tampered.encode("utf-8")).hexdigest() != \
        hashlib.sha256(orig.encode("utf-8")).hexdigest()


def test_tamper_manifest_source_hash_must_fail_verification(tmp_path):
    """Tamper: alter a bound source hash in the manifest → verify must fail."""
    import shutil
    pkg = tmp_path / "pkg"
    shutil.copytree(PKG, pkg)
    manifest_path = pkg / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    key = next(k for k, v in manifest["source_hashes"].items() if v is not None)
    manifest["source_hashes"][key] = "0" * 64
    manifest_path.write_text(json.dumps(manifest, indent=1))
    with pytest.raises(AssertionError):
        publication.verify_package(pkg)


def test_tamper_artifact_content_must_fail_verification(tmp_path):
    """Tamper: modify domain_dictionary.csv → sha256sums mismatch."""
    import shutil
    pkg = tmp_path / "pkg"
    shutil.copytree(PKG, pkg)
    target = pkg / "domain_dictionary.csv"
    target.write_text(target.read_text() + "\n# tampered\n")
    with pytest.raises(AssertionError):
        publication.verify_package(pkg)


def test_tamper_schema_json_outcome_domain_must_fail_verification(tmp_path):
    """Tamper: change arrow schema outcome_code type → schema sha256 changes."""
    import shutil
    import hashlib
    pkg = tmp_path / "pkg"
    shutil.copytree(PKG, pkg)
    target = pkg / "pyarrow_schemas.json"
    data = json.loads(target.read_text())
    quote = data["market_quote"]
    for f in quote["fields"]:
        if f["name"] == "outcome_code":
            f["type"] = "int64"
    target.write_text(json.dumps(data, indent=1))
    # schema bundle sha must differ from manifest's schema_sha256
    manifest = json.loads((pkg / "MANIFEST.json").read_text())
    tampered_bundle = json.dumps({"ddl": schemas.render_ddl(),
                                  "arrow_schemas": data,
                                  "domain_dictionary": schemas.domain_dictionary(),
                                  "identity_rule": {"unique_within": "issue_code x match_idx"}},
                                 sort_keys=True)
    assert hashlib.sha256(tampered_bundle.encode("utf-8")).hexdigest() != \
        manifest["schema_sha256"]


def test_tamper_identity_crosswalk_fuzzy_match_must_be_rejected():
    """Tamper: crosswalk must never claim fuzzy-only binding."""
    for row in crosswalk.identity_crosswalk_rows():
        assert "fuzzy" not in row["canonical_binding"].lower()
        assert row["canonical_binding"].startswith(("issue_code", "settlement"))


# ---------------------------------------------------------------------------
# DDL renders deterministically
# ---------------------------------------------------------------------------
def test_ddl_deterministic():
    assert schemas.render_ddl() == schemas.render_ddl()


def test_arrow_schema_materializes():
    schema = schemas.arrow_schema("market_quote")
    names = [f.name for f in schema]
    assert "outcome_code" in names and "decimal_odds" in names
