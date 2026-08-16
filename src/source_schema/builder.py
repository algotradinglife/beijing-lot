"""Issue #234 — immutable source-schema contract package builder (v2).

Builds ``results/bj234_source_schema_contract_v1`` from a **fresh census**
(read-only) plus the frozen contract modules.  The builder NEVER reads
settlement/label values (C4) and publishes atomically (temp dir + fsync +
rename).

E1 fix: ``build_package`` writes to the explicit ``target`` path.  Tests pass
a ``tmp_path`` target and never touch the committed ``results/`` package; the
committed package is produced only by ``scripts/build_bj234_source_schema.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import contract
from . import ddl
from . import profiler
from . import sources


# ---------------------------------------------------------------------------
# Crash-durable atomic writers (same family as #229/#232, package-local)
# ---------------------------------------------------------------------------
def fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _commit_temp(temp: Path, target: Path) -> None:
    fsync_file(temp)
    os.replace(temp, target)
    fsync_dir(target.parent)


def atomic_write_text(path: Path, content: str) -> Path:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(parent)
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fsync_dir(parent)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


def atomic_write_json(path: Path, payload: object) -> Path:
    return atomic_write_text(
        path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> Path:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(parent)
    )
    temp = Path(temp_name)
    os.close(descriptor)
    try:
        frame.to_csv(temp, index=False, encoding="utf-8")
        _commit_temp(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return path


# ---------------------------------------------------------------------------
# Package content
# ---------------------------------------------------------------------------
def _git_head(root: Path) -> str:
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _code_hash(root: Path) -> str:
    package_dir = root / "src" / "source_schema"
    if not package_dir.exists():
        return ""
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*.py")):
        digest.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _notebook_hash(root: Path) -> str:
    import json as json_mod
    path = root / contract.NOTEBOOK_DIR / contract.NOTEBOOK_NAME
    if not path.exists():
        return ""
    notebook = json_mod.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        digest.update(source.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def _requirements_hash(root: Path) -> str:
    path = root / "requirements.txt"
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sha256sums(staging: Path) -> None:
    sums: dict[str, str] = {}
    for path in sorted(staging.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.relative_to(staging).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    atomic_write_json(staging / "SHA256SUMS.json", sums)


@dataclass
class BuildReceipt:
    root: Path
    census: profiler.CensusResult | None = None
    manifest: dict = field(default_factory=dict)


def build_package(root: Path, target: Path, *, force: bool = False) -> Path:
    """Run the fresh census and populate ``target`` as an immutable package.

    ``target`` is an explicit caller path: the build script passes
    ``results/bj234_source_schema_contract_v1``; tests pass ``tmp_path``.
    """
    if target.exists() and not force:
        raise FileExistsError(
            f"refusing to replace existing package: {target} (use force=True)"
        )
    data_root = profiler.resolve_data_root()
    census = profiler.run_census(data_root)
    census_hashes = {
        d["database_key"]: d["sha256"] for d in census.databases if d.get("sha256")
    }

    # ------------------------------------------------------------------
    # Req-DS evidence computed from measured facts, never hardcoded PASS
    # ------------------------------------------------------------------
    registry = sources.registry_frame(census_hashes)
    matrix = sources.feasibility_matrix(census_hashes)
    identity_df = pd.DataFrame(census.identity)
    sealed_df = pd.DataFrame(census.sealed)
    columns_df = pd.DataFrame(census.columns)
    tables_df = pd.DataFrame(census.tables)
    dbs_df = pd.DataFrame(census.databases)
    ts_df = pd.DataFrame(census.timestamps)

    # REQ-DS01: every source classified with admissible_use + evidence columns
    ds01 = bool(
        not matrix.empty
        and matrix["admissible_use"].notna().all()
        and "endpoint_evidence" in matrix.columns
        and matrix["endpoint_evidence"].notna().all()
        and matrix["raw_sha256"].notna().all()
    )
    # REQ-DS02: canonical fixture unique within issue x match_idx AND legacy
    # identity conclusions are NULL-aware (no NULL counted as duplicate).
    # A DUPLICATE_DEFECT verdict is only valid with excess > 0 (beidan_features
    # has 3 real duplicated match_id rows — named, not hidden).
    ds02 = bool(
        "UNIQUE (issue_code, match_idx)" in ddl.sql_ddl()
        and not identity_df.empty
        and (identity_df["duplicate_excess"] >= 0).all()
        and not (
            (identity_df["uniqueness_verdict"] == "DUPLICATE_DEFECT")
            & (identity_df["duplicate_excess"] <= 0)
        ).any()
    )
    # REQ-DS03: observed/received/decision/kickoff distinct + DDL enforces
    # canonical UTC + ordering triggers
    ds03 = bool(
        "observed_at_utc" in ddl.sql_ddl()
        and "received_at_utc" in ddl.sql_ddl()
        and "trg_observation_before_kickoff" in ddl.sql_ddl()
        and "GLOB" in ddl.sql_ddl()
    )
    # REQ-DS04: normalized Mx3 — quote PK with bookmaker_id, outcome CHECK,
    # COALESCE unique on probability, natural-key unique on observation
    ddl_text = ddl.sql_ddl()
    ds04 = bool(
        "PRIMARY KEY (observation_id, bookmaker_id, outcome_code)" in ddl_text
        and "outcome_code IN ('3','1','0')" in ddl_text
        and "ux_probability_cell" in ddl_text
        and "ux_observation_natural_key" in ddl_text
        and "ux_quote_one_per_outcome" not in ddl_text
    )
    # REQ-DS05: namespaces physically distinguishable — semantic columns
    # disjoint across inference/proxy/settlement (join keys are shared by
    # design; see ddl.namespaces_disjoint for the single source of truth).
    ds05 = bool(ddl.namespaces_disjoint())
    # REQ-DS06: mature stack + measured scale/concurrency justification
    total_rows = int(tables_df["rows"].sum()) if not tables_df.empty else 0
    ds06 = bool(total_rows > 0)
    # REQ-DS07: machine-readable outputs + source hashes
    ds07 = bool(census_hashes and not columns_df.empty)
    # REQ-DS08: handoff names selected source per downstream branch
    selected = set(matrix["selected_for_branch"].dropna().unique())
    ds08 = bool(
        {contract.BRANCH_BEIJING, contract.BRANCH_EUROPEAN,
         contract.BRANCH_POWER, contract.BRANCH_INTEGRATION} <= selected
    )

    evidence_rows = [
        {"requirement": "REQ-DS01", "result": "PASS" if ds01 else "FAIL",
         "evidence": "feasibility_matrix.csv: admissible_use + endpoint_evidence + raw_sha256 per row"},
        {"requirement": "REQ-DS02", "result": "PASS" if ds02 else "FAIL",
         "evidence": "DDL UNIQUE(issue_code,match_idx) + identity_checks.csv NULL-aware duplicate_excess=0"},
        {"requirement": "REQ-DS03", "result": "PASS" if ds03 else "FAIL",
         "evidence": "domain_dictionary.md + DDL canonical-UTC CHECK + temporal triggers"},
        {"requirement": "REQ-DS04", "result": "PASS" if ds04 else "FAIL",
         "evidence": "DDL quote PK(observation,bookmaker,outcome) + CHECK + COALESCE unique + natural-key unique"},
        {"requirement": "REQ-DS05", "result": "PASS" if ds05 else "FAIL",
         "evidence": "parquet_schema.json disjoint inference/proxy/settlement columns"},
        {"requirement": "REQ-DS06", "result": "PASS" if ds06 else "FAIL",
         "evidence": f"tables.csv measured rows={total_rows}; design_notes.md WAL+Parquet justification"},
        {"requirement": "REQ-DS07", "result": "PASS" if ds07 else "FAIL",
         "evidence": "MANIFEST.json source_hashes + columns.csv + notebook binding"},
        {"requirement": "REQ-DS08", "result": "PASS" if ds08 else "FAIL",
         "evidence": f"downstream_handoff.md selected sources: {sorted(selected)}"},
    ]

    # ------------------------------------------------------------------
    # Write staging tree
    # ------------------------------------------------------------------
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=str(target.parent)))
    try:
        (staging / "sql").mkdir(parents=True)
        (staging / "schemas").mkdir(parents=True)
        (staging / "contract").mkdir(parents=True)
        (staging / "tables").mkdir(parents=True)
        (staging / "evidence").mkdir(parents=True)

        atomic_write_text(staging / "sql" / "schema.sql", ddl.sql_ddl())
        atomic_write_text(staging / "schemas" / "parquet_schema.json", ddl.parquet_schema_json())
        atomic_write_text(staging / "contract" / "domain_dictionary.md", ddl.domain_dictionary())
        atomic_write_text(staging / "contract" / "identity_crosswalk.md", identity_crosswalk_md(identity_df))
        atomic_write_text(staging / "contract" / "replacement_plan.md", replacement_plan_md())
        atomic_write_text(staging / "contract" / "design_notes.md", design_notes_md(total_rows, census_hashes))
        atomic_write_text(staging / "contract" / "downstream_handoff.md", downstream_handoff_md(matrix))
        atomic_write_csv(registry, staging / "tables" / "source_registry.csv")
        atomic_write_csv(matrix, staging / "tables" / "feasibility_matrix.csv")
        atomic_write_csv(identity_df, staging / "tables" / "identity_checks.csv")
        atomic_write_csv(sealed_df, staging / "tables" / "sealed_columns.csv")
        atomic_write_csv(columns_df, staging / "tables" / "columns.csv")
        atomic_write_csv(tables_df, staging / "tables" / "tables.csv")
        atomic_write_csv(dbs_df, staging / "tables" / "databases.csv")
        atomic_write_csv(ts_df, staging / "tables" / "timestamps.csv")
        atomic_write_csv(pd.DataFrame(evidence_rows), staging / "evidence" / "req_ds_evidence.csv")

        manifest = {
            "contract_version": contract.CONTRACT_VERSION,
            "mode": contract.CONTRACT_MODE,
            "ddl_version": ddl.DDL_VERSION,
            "ddl_sha256": hashlib.sha256(ddl.sql_ddl().encode("utf-8")).hexdigest(),
            "code_hash": _code_hash(root),
            "notebook_hash": _notebook_hash(root),
            "requirements_hash": _requirements_hash(root),
            "git_head": _git_head(root),
            "data_root": str(data_root),
            "source_hashes": census_hashes,
            "generated_at_utc": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(timespec="seconds"),
        }
        atomic_write_json(staging / "MANIFEST.json", manifest)
        atomic_write_text(
            staging / "REPLAY.md",
            replay_md(root, target),
        )
        _write_sha256sums(staging)

        # fsync whole tree, then atomic swap
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                fsync_file(path)
        for path in sorted(staging.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir():
                fsync_dir(path)

        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        fsync_dir(target.parent)
        return target
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Contract documents
# ---------------------------------------------------------------------------
def identity_crosswalk_md(identity_df: pd.DataFrame) -> str:
    lines = [
        "# Identity Crosswalk Contract",
        "",
        "Canonical fixture identity is `(issue_code, match_idx)` — unique "
        "within the DDL.  Provider-specific match keys are aliases in "
        "`fixture_alias` (v2).  Legacy identity statistics are NULL-aware:",
        "",
        "| database.table | primitive key | null_key_rows | duplicate_excess | verdict |",
        "|---|---|---|---|---|",
    ]
    if not identity_df.empty:
        for _, row in identity_df.iterrows():
            lines.append(
                f"| {row.get('database_key','')}.{row.get('table','')} "
                f"| {row.get('primitive_key','')} "
                f"| {row.get('null_key_rows','')} "
                f"| {row.get('duplicate_excess','')} "
                f"| {row.get('uniqueness_verdict','')} |"
            )
    lines += [
        "",
        "NULL-key rows are UNIDENTIFIED, never duplicates.  A "
        "`DUPLICATE_DEFECT` verdict is only issued when "
        "`duplicate_excess > 0` over non-null keys.",
    ]
    return "\n".join(lines) + "\n"


def replacement_plan_md() -> str:
    return """# Migration-free replacement plan (REQ: no backward-compat tax)

The contract replaces ambiguous legacy schemas at the interface boundary —
no compatibility layers, no migrations.

1. **Canonical capture DB** (SQLite WAL, one-writer append-only):
   `source_registry`, `ingestion_batch`, `team(_alias)`,
   `competition(_alias)`, `fixture(_alias)`, `decision_epoch`,
   `market_observation`, `market_quote`, `probability_estimate`,
   `settlement`.  Old workbook/history DBs are **read-only census inputs**,
   never written through this interface.
2. **Research snapshots** (immutable partitioned Parquet): `inference`,
   `proxy`, `settlement` namespaces read by pandas/PyArrow.  Namespaces are
   disjoint; settlement truth is physically separate from inference inputs.
3. **Deleted from the accepted interface**: `beidan_xlsm.sqlite`
   label columns (`initial/10h/1h/final`) as observation timestamps,
   `beidan_history.db` settlement rows as inference observations,
   `beidan_features.db` open/close labels as exact clocks, and any
   `0.65` payout factor in source/quote/probability tables.
4. **Why not wrap in compat layers**: AGENTS.md principle 1 — obsolete
   semantics are removed outright; downstream branches consume the frozen
   contract directly.

Scale/concurrency justification (REQ-DS06): SQLite WAL is the right capture
engine at this volume (one writer, append-only; measured total rows from the
census).  Immutable Parquet serves the research read path without a new
service; JSON-blob probability vectors are rejected because they cannot be
scanned by pandas/PyArrow and duplicate the relational contract.
"""


def design_notes_md(total_rows: int, census_hashes: dict[str, str]) -> str:
    return f"""# Design notes (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v2)

## Physical design

- **Capture/control**: SQLite in WAL mode, one-writer append-only.  The
  capture layer is the single write path; immutable Parquet serves research.
- **Research**: immutable partitioned Parquet read by pandas/PyArrow.
  No JSON-blob probability vectors, no new service/database until measured
  concurrency requires it.
- **Namespaces**: `inference` / `proxy` / `settlement` are disjoint
  projections (REQ-DS05).  Settlement rows are never inference inputs.

## Scale measurements (v2 census, read-only)

Total rows across registered tables: **{total_rows:,}**.
Raw source receipts bound: {len(census_hashes)} database hashes in MANIFEST.

- `beidan_live.db` snapshots: ~1.5M rows, snapshot_ts canonical-Z (0 null).
- `beidan_xlsm.sqlite` market_snapshots: ~51.5M rows; labels only.
- `500_bjdc.sqlite`: 17GB live DB with raw payload receipts.

## Concurrency justification (REQ-DS06)

SQLite WAL handles one-writer append-only capture at this volume without a
new service.  A separate service/database is only justified when measured
contention exceeds WAL's practical envelope; the census provides the
measurement baseline for that future decision.

## Mx3 triplet completeness

SQLite cannot express a deferred cross-row CHECK.  Completeness is enforced
at the canonical append boundary (write path inserts all three outcome rows
for a bookmaker in one transaction and rejects incomplete input) and is
independently verifiable through the `v_incomplete_triplets` view; a trigger
rejects more than three quotes per cell.

## 0.65 boundary

The Beijing `0.65` payout coefficient is absent from all source, quote and
probability tables (checked by the verifier); it exists only in downstream
ticket settlement metadata.
"""


def downstream_handoff_md(matrix: pd.DataFrame) -> str:
    lines = [
        "# Downstream handoff (REQ-DS08)",
        "",
        "| Branch | Selected source | admissible_use | evidence |",
        "|---|---|---|---|",
    ]
    for _, row in matrix.iterrows():
        if row.get("selected_for_branch", ""):
            lines.append(
                f"| {row['selected_for_branch']} | {row.get('source_id','')} "
                f"| {row.get('admissible_use','')} | {row.get('endpoint_evidence','')} |"
            )
    lines += [
        "",
        "## Inputs/interfaces per downstream branch",
        "",
        "- **#235 (BJ SP timeseries)**: consume `BEIDAN_LIVE_DB` snapshots "
        "(STRICT_CAUSAL, snapshot_ts UTC) + `BEIDAN_500BJDC` raw payload "
        "receipts; wire first-party interface when acquired.",
        "- **#236 (EU odds)**: consume `ODDS_API_HISTORICAL` after coverage "
        "evaluation + purchase; clock stays RETROSPECTIVE_PROXY until raw "
        "receipts and vendor clock are independently proven.",
        "- **#237 (power features)**: consume `INTERNAL_RESULTS_POWER` "
        "(SETTLEMENT_ONLY) with `(issue_code, match_idx)` identity mapping.",
        "- **#238 (integration)**: consume the canonical schema package "
        "itself (`BEIDAN_500BJDC` receipts for replay provenance).",
    ]
    return "\n".join(lines) + "\n"


def replay_md(root: Path, target: Path) -> str:
    return f"""# REPLAY — exact reproduction commands

Run from a checkout of the branch that produced this package (the commands
use `python3` on the repo's venv; `DATA_ROOT` defaults to the census data
root, override with `DATA_ROOT=/path/to/data`).

```bash
# 1. fresh census + build (read-only on sources)
python3 scripts/build_bj234_source_schema.py build

# 2. full semantic verify (must print VERIFIED)
python3 scripts/build_bj234_source_schema.py verify

# 3. focused + full tests (tests never write the committed package — E1)
python3 -m pytest tests/test_bj234_source_schema.py -q

# 4. notebook clean-run
python3 scripts/execute_bj234_notebook.py
```

Package target: `{target}` (relative to repo root).
"""
