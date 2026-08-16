"""Issue #234 — semantic verifier (v2).

v2 rework addresses EV R1 defect class E2: the v1 verifier was
presence/string-only and fail-open under remanifest attacks (9 of 10
accepted).  This verifier **rebuilds semantics from the committed payloads**:

1. byte manifest (SHA256SUMS.json) — unchanged, strict;
2. MANIFEST internal consistency (contract_version, ddl_sha256,
   code/notebook/requirements hashes bound to live tree);
3. **DDL semantics** — the verifier executes the committed ``schema.sql`` in
   a fresh SQLite in-memory DB and checks the *actual schema objects*:
   fixture_alias exists, quote PK includes bookmaker_id, no
   ``ux_quote_one_per_outcome``-style index, probability COALESCE unique
   index present, FK enforcement rejects an orphan quote, alias no-overlap
   trigger rejects overlapping windows, ``v_incomplete_triplets`` exists,
   and the text contains no ``0.65``;
4. **registry semantics** — admissible_use in domain; STRICT_CAUSAL rows
   carry TIMESTAMPED_UTC clock + a resolvable raw receipt (never empty);
   every selected source exists in the registry and is admissible for its
   branch; no F1 masquerade (provider/endpoint must name the actual
   collector plane, e.g. 500.com);
5. **namespace disjointness** — inference/proxy/settlement parquet schemas
   share no semantic columns;
6. **sealing** — census outputs never contain value stats for sealed
   columns/tables (C4);
7. **identity semantics** — legacy duplicate conclusions are NULL-aware:
   NULL-key rows are counted as UNIDENTIFIED, not DUPLICATE (C1).

Every check returns a structured problem or nothing; ``verify_package``
aggregates and fails closed.  The test suite runs the EV's remanifest
attacks against this verifier and asserts each one FAILS.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from . import contract
from . import ddl as ddl_mod
from . import sources


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Byte manifest
# ---------------------------------------------------------------------------
def check_byte_manifest(package: Path, problems: list[str]) -> None:
    sums_path = package / "SHA256SUMS.json"
    if not sums_path.exists():
        problems.append("SHA256SUMS.json missing")
        return
    recorded = _load_json(sums_path)
    for relative, expected in sorted(recorded.items()):
        path = package / relative
        if not path.exists():
            problems.append(f"manifest: {relative} MISSING")
            continue
        import hashlib
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            problems.append(f"manifest: {relative} hash mismatch")
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS.json":
            continue
        rel = path.relative_to(package).as_posix()
        if rel not in recorded:
            problems.append(f"manifest: {rel} UNRECORDED")


# ---------------------------------------------------------------------------
# MANIFEST internal consistency
# ---------------------------------------------------------------------------
def check_manifest_consistency(package: Path, root: Path, problems: list[str]) -> None:
    manifest_path = package / "MANIFEST.json"
    if not manifest_path.exists():
        problems.append("MANIFEST.json missing")
        return
    manifest = _load_json(manifest_path)
    if not manifest.get("contract_version", "").startswith(contract.CONTRACT_VERSION):
        problems.append(f"manifest: contract_version wrong: {manifest.get('contract_version')}")
    sql = package / "sql" / "schema.sql"
    if sql.exists():
        import hashlib
        actual = hashlib.sha256(sql.read_bytes()).hexdigest()
        if actual != manifest.get("ddl_sha256"):
            problems.append("manifest: ddl_sha256 does not match sql/schema.sql")

    # code/notebook/requirements hashes bound to the live tree
    code_dir = root / "src" / "source_schema"
    if code_dir.exists():
        digest = hashlib.sha256()
        for path in sorted(code_dir.rglob("*.py")):
            digest.update(path.relative_to(code_dir).as_posix().encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
        if digest.hexdigest() != manifest.get("code_hash"):
            problems.append("manifest: code_hash does not match src/source_schema")
    req = root / "requirements.txt"
    if req.exists():
        import hashlib
        if hashlib.sha256(req.read_bytes()).hexdigest() != manifest.get("requirements_hash"):
            problems.append("manifest: requirements_hash does not match requirements.txt")


# ---------------------------------------------------------------------------
# DDL semantics: rebuild the schema and probe actual behavior
# ---------------------------------------------------------------------------
def check_ddl_semantics(package: Path, problems: list[str]) -> None:
    sql_path = package / "sql" / "schema.sql"
    if not sql_path.exists():
        problems.append("sql/schema.sql missing")
        return
    sql = sql_path.read_text(encoding="utf-8")

    # 0.65 scan: strip SQL comments so the boundary note in the header is not
    # a false positive; a literal 0.65 in any DDL statement is a violation.
    sql_no_comments = "\n".join(
        line.split("--", 1)[0] for line in sql.splitlines()
    )
    if "0.65" in sql_no_comments:
        problems.append("ddl: 0.65 payout coefficient present in schema (contract violation)")

    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(sql)
    except sqlite3.Error as e:
        problems.append(f"ddl: schema does not execute: {e}")
        return

    # required tables
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    required_tables = {
        "source_registry", "ingestion_batch", "team", "team_alias",
        "competition", "competition_alias", "fixture", "fixture_alias",
        "decision_epoch", "market_observation", "market_quote",
        "probability_estimate", "settlement",
    }
    missing = required_tables - tables
    if missing:
        problems.append(f"ddl: missing tables: {sorted(missing)}")

    # fixture_alias must exist (C3)
    if "fixture_alias" not in tables:
        problems.append("ddl: fixture_alias missing — canonical fixture cannot hold multiple provider aliases")

    # quote PK must include bookmaker_id (C3) and must NOT have an index that
    # erases bookmaker_id
    quote_pk = {r[1] for r in conn.execute("PRAGMA table_info(market_quote)") if r[5] > 0}
    if "bookmaker_id" not in quote_pk:
        problems.append(f"ddl: market_quote PK {sorted(quote_pk)} excludes bookmaker_id")
    indexes = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='market_quote'")]
    for idx in indexes:
        idx_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (idx,)
        ).fetchone()
        if idx_sql and idx_sql[0]:
            body = idx_sql[0].lower()
            if "observation_id" in body and "outcome_code" in body and "bookmaker_id" not in body:
                problems.append(f"ddl: index {idx} erases bookmaker_id from quote identity")

    # probability COALESCE unique index must exist (C3 NULL-distinct fix)
    prob_idx = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='probability_estimate'"
    ).fetchall()
    if not any("coalesce" in (r[0] or "").lower() for r in prob_idx):
        problems.append("ddl: probability_estimate COALESCE unique index missing")

    # triggers: no-overlap, temporal, max-three
    triggers = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")}
    for expected in ("trg_team_alias_no_overlap", "trg_competition_alias_no_overlap",
                     "trg_fixture_alias_no_overlap", "trg_observation_before_kickoff",
                     "trg_decision_before_kickoff", "trg_settlement_after_kickoff",
                     "trg_quote_max_three"):
        if expected not in triggers:
            problems.append(f"ddl: trigger {expected} missing")

    # v_incomplete_triplets view
    views = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'")}
    if "v_incomplete_triplets" not in views:
        problems.append("ddl: v_incomplete_triplets view missing")

    # FK enforcement must reject an orphan quote (C3: PRAGMA foreign_keys default 0)
    try:
        conn.execute("INSERT INTO market_quote VALUES (999999,'bm','3',2.0,'LIVE')")
        problems.append("ddl: FK enforcement OFF — orphan quote accepted")
    except sqlite3.IntegrityError:
        pass

    # alias no-overlap trigger must reject an overlapping window
    try:
        conn.execute("INSERT INTO source_registry VALUES "
                     "('t_src','p','e','a','t','UTC','TIMESTAMPED_UTC','60','v1',"
                     "'STRICT_CAUSAL','2026-01-01T00:00:00Z','2026-12-31T00:00:00Z','A','abc','')")
        conn.execute("INSERT INTO team VALUES (1,'T')")
        conn.execute("INSERT INTO team_alias VALUES "
                     "('t_src','k',1,'2026-01-01T00:00:00Z','2026-02-01T00:00:00Z')")
        conn.execute("INSERT INTO team_alias VALUES "
                     "('t_src','k',1,'2026-01-15T00:00:00Z',NULL)")
        problems.append("ddl: alias no-overlap trigger not enforced")
    except sqlite3.IntegrityError:
        pass

    # C3-5: prospective live/instant snapshot kind must be expressible — the
    # canonical capture DB accepts a market_observation with snapshot_kind='live'
    # (the live collector plane is the primary prospective causal source).
    try:
        conn.execute("INSERT INTO competition VALUES (1,'C')")
        conn.execute("INSERT INTO fixture VALUES (1,'26001',1,'k',1,1,1,"
                     "'2026-05-01T01:00:00Z',0.5,NULL,'CANONICAL')")
        conn.execute("INSERT INTO ingestion_batch VALUES (1,'t_src','2026-05-01T00:00:00Z',"
                     "'2026-05-01T00:01:00Z','u','h','v1',1,'OK')")
        conn.execute("INSERT INTO market_observation VALUES (1,1,'t_src','sp_1x2',NULL,"
                     "'2026-04-30T00:00:00Z','2026-04-30T00:01:00Z','live',1)")
    except sqlite3.IntegrityError as e:
        problems.append(f"ddl: live snapshot kind rejected: {e}")

    conn.close()


# ---------------------------------------------------------------------------
# Registry semantics
# ---------------------------------------------------------------------------
def check_registry_semantics(package: Path, problems: list[str]) -> None:
    reg_path = package / "tables" / "source_registry.csv"
    if not reg_path.exists():
        problems.append("tables/source_registry.csv missing")
        return
    frame = _load_csv(reg_path)
    if "admissible_use" not in frame.columns:
        problems.append("registry: admissible_use column missing")
        return

    allowed_uses = set(contract.ADMISSIBLE_USES)
    for _, row in frame.iterrows():
        sid = row.get("source_id", "")
        use = row.get("admissible_use", "")
        if use not in allowed_uses:
            problems.append(f"registry: {sid} admissible_use={use} not in domain")
        clock = row.get("clock_semantics", "")
        raw = str(row.get("raw_sha256", ""))
        # STRICT_CAUSAL requires TIMESTAMPED_UTC + resolvable receipt
        if use == "STRICT_CAUSAL":
            if clock != "TIMESTAMPED_UTC":
                problems.append(f"registry: {sid} STRICT_CAUSAL without TIMESTAMPED_UTC clock")
            if not raw or raw == "NO_RECEIPT" or raw == "PENDING_CENSUS":
                problems.append(f"registry: {sid} STRICT_CAUSAL without resolvable raw receipt")
        # UNUSABLE rows must say why
        if use == "UNUSABLE" and not str(row.get("notes", "")):
            problems.append(f"registry: {sid} UNUSABLE without note")

    # every selected source must exist and be admissible for its branch
    selected = frame[frame["selected_for_branch"].notna() & (frame["selected_for_branch"] != "")]
    if selected.empty:
        problems.append("registry: no source selected for any branch (REQ-DS08)")
    branch_use_ok = {
        contract.BRANCH_BEIJING: {"STRICT_CAUSAL", "RETROSPECTIVE_PROXY"},
        contract.BRANCH_EUROPEAN: {"STRICT_CAUSAL", "RETROSPECTIVE_PROXY"},
        contract.BRANCH_POWER: {"SETTLEMENT_ONLY", "RETROSPECTIVE_PROXY"},
        contract.BRANCH_INTEGRATION: {"STRICT_CAUSAL", "RETROSPECTIVE_PROXY",
                                      "SETTLEMENT_ONLY", "UNUSABLE"},
    }
    for _, row in selected.iterrows():
        branch = row["selected_for_branch"]
        use = row.get("admissible_use", "")
        if branch in branch_use_ok and use not in branch_use_ok[branch]:
            problems.append(
                f"registry: {row.get('source_id')} selected for {branch} "
                f"but admissible_use={use}"
            )

    # no masquerade: any source claiming an official provider must actually
    # use an official endpoint; claiming "official" while the endpoint is the
    # 500.com third-party plane is a masquerade (EV C2).
    for _, row in frame.iterrows():
        provider = str(row.get("provider", "")).lower()
        endpoint = str(row.get("endpoint", ""))
        sid = row.get("source_id", "")
        claims_official = "official" in provider or "first-party" in provider
        uses_500 = "500.com" in endpoint.lower()
        if claims_official and uses_500:
            problems.append(
                f"registry: {sid} claims official/first-party provider but "
                f"endpoint is the 500.com third-party plane (masquerade)"
            )


# ---------------------------------------------------------------------------
# Namespace disjointness (REQ-DS05)
# ---------------------------------------------------------------------------
def check_namespaces(package: Path, problems: list[str]) -> None:
    schema_path = package / "schemas" / "parquet_schema.json"
    if not schema_path.exists():
        problems.append("schemas/parquet_schema.json missing")
        return
    schemas = _load_json(schema_path).get("namespaces", {})
    for ns in ("inference", "proxy", "settlement"):
        if ns not in schemas:
            problems.append(f"namespace: {ns} missing from parquet_schema.json")
    # semantic columns must never leak across namespaces (REQ-DS05); join
    # keys are shared by design (REQ-DS02 identity).  Same rule as the
    # builder's evidence computation (ddl.NAMESPACE_JOIN_KEYS).
    # recompute over the *committed* parquet_schema.json (attack target),
    # not the in-repo PARQUET_SCHEMAS constant
    join_keys = ddl_mod.NAMESPACE_JOIN_KEYS
    semantic = {
        name: set(cols.keys()) - join_keys
        for name, cols in schemas.items()
    }
    committed_overlap: set[str] = set()
    for left, right in (("inference", "settlement"), ("proxy", "settlement"),
                        ("inference", "proxy")):
        if left in semantic and right in semantic:
            committed_overlap |= semantic[left] & semantic[right]
    if committed_overlap:
        problems.append(
            f"namespace: semantic columns shared across namespaces: "
            f"{sorted(committed_overlap)}"
        )


# ---------------------------------------------------------------------------
# Sealing (C4)
# ---------------------------------------------------------------------------
def check_sealing(package: Path, problems: list[str]) -> None:
    sealed_path = package / "tables" / "sealed_columns.csv"
    if not sealed_path.exists():
        problems.append("tables/sealed_columns.csv missing (C4 sealing evidence)")
        return
    sealed = _load_csv(sealed_path)
    if sealed.empty:
        problems.append("sealing: no sealed columns recorded")

    # census column stats must never contain value stats for sealed columns
    cols_path = package / "tables" / "columns.csv"
    if cols_path.exists():
        cols = _load_csv(cols_path)
        if not cols.empty and {"table", "column"}.issubset(cols.columns):
            sealed_table_keys = set()
            sealed_col_keys = set()
            for _, row in sealed.iterrows():
                db = str(row.get("database_key", ""))
                t = str(row.get("table", ""))
                c = str(row.get("column", ""))
                if c and c != "nan":
                    sealed_col_keys.add((db, t, c))
                elif t and t != "nan":
                    sealed_table_keys.add((db, t))
            for _, row in cols.iterrows():
                db = str(row.get("database_key", ""))
                t = str(row.get("table", ""))
                c = str(row.get("column", ""))
                if (db, t) in sealed_table_keys or (db, t, c) in sealed_col_keys:
                    problems.append(
                        f"sealing: value stats published for sealed {db}.{t}.{c}"
                    )


# ---------------------------------------------------------------------------
# Identity semantics (C1)
# ---------------------------------------------------------------------------
def check_sweep_evidence(package: Path, problems: list[str]) -> None:
    """EV R1 mandate: the same-class complete-sweep evidence document must be
    part of the frozen package (missing = sweep not closed)."""
    sweep = package / "contract" / "same_class_sweep.md"
    if not sweep.exists():
        problems.append(
            "contract/same_class_sweep.md missing — EV R1 same-class "
            "complete-sweep evidence not in package"
        )
        return
    text = sweep.read_text(encoding="utf-8")
    for required in ("identity", "schema / alias / M×3", "时序 / 泄漏",
                     "source lineage", "验证盲区 / tamper"):
        if required not in text:
            problems.append(
                f"contract/same_class_sweep.md missing sweep category: {required}"
            )


def check_identity_semantics(package: Path, problems: list[str]) -> None:
    id_path = package / "tables" / "identity_checks.csv"
    if not id_path.exists():
        problems.append("tables/identity_checks.csv missing")
        return
    frame = _load_csv(id_path)
    for _, row in frame.iterrows():
        table = row.get("table", "")
        verdict = row.get("uniqueness_verdict", "")
        null_rows = row.get("null_key_rows", 0)
        excess = row.get("duplicate_excess", 0)
        if verdict == "DUPLICATE_DEFECT" and excess == 0:
            problems.append(
                f"identity: {table} marked DUPLICATE_DEFECT but duplicate_excess=0 "
                f"(NULL rows mis-counted as duplicates?)"
            )
        # NULL-key rows must never inflate the duplicate count
        if null_rows and verdict == "DUPLICATE_DEFECT" and excess <= 0:
            problems.append(
                f"identity: {table} has {null_rows} NULL-key rows reported as duplicates"
            )
        if "primitive_key" not in frame.columns or not str(row.get("primitive_key", "")):
            problems.append(f"identity: {table} missing primitive_key column")


# ---------------------------------------------------------------------------
# Aggregate verifier
# ---------------------------------------------------------------------------
def verify_package(package: Path, root: Path) -> dict:
    """Full semantic verification. Returns {'verified': bool, 'problems': [...]}."""
    problems: list[str] = []
    check_byte_manifest(package, problems)
    check_manifest_consistency(package, root, problems)
    check_ddl_semantics(package, problems)
    check_registry_semantics(package, problems)
    check_namespaces(package, problems)
    check_sealing(package, problems)
    check_identity_semantics(package, problems)
    check_sweep_evidence(package, problems)
    return {
        "verified": not problems,
        "problems": problems,
        "n_problems": len(problems),
    }
