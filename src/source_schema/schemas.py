"""Render the canonical contract into versioned SQL DDL and PyArrow schemas.

The DDL is the *frozen interface* for all #232 recovery branches: append-only
SQLite capture/control tables (WAL, one writer) plus immutable partitioned
Parquet for research snapshots.  No JSON-blob probability vectors, no new
service/database until measured concurrency requires it (REQ-DS06).

DDL is deterministic: given the contract module, rendering twice yields
byte-identical SQL.  Every schema artifact is hashed into the package
manifest (REQ-DS07).
"""

from __future__ import annotations

import hashlib
from typing import Optional

from . import contract

SQLITE_TYPE_MAP = {
    "TEXT": "TEXT",
    "INTEGER": "INTEGER",
    "REAL": "REAL",
    "timestamp[us, tz=UTC]": "TEXT",
}


def render_ddl(*, include_capture: bool = True,
               include_inference: bool = True,
               include_settlement: bool = True) -> str:
    """Render versioned SQLite DDL for the frozen canonical tables."""
    lines: list[str] = []
    lines.append("-- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (frozen 2026-08-16)")
    lines.append("-- Canonical source registry, identity and temporal store schema.")
    lines.append("-- Rendered deterministically from src/source_schema/contract.py.")
    lines.append("-- SQLite WAL mode; one-writer append-only capture/control tables;")
    lines.append("-- research snapshots are immutable partitioned Parquet (see PyArrow schemas).")
    lines.append("-- All timestamps are timezone-aware UTC (ISO-8601 with Z).")
    lines.append("-- outcome_code domain is exactly ('3','1','0') after explicit mapping.")
    lines.append("-- The Beijing 0.65 coefficient is ABSENT from all source/quote/probability")
    lines.append("-- tables; it exists only in downstream ticket settlement metadata.")
    lines.append("")
    lines.append("PRAGMA journal_mode = WAL;")
    lines.append("PRAGMA synchronous = NORMAL;")
    lines.append("PRAGMA foreign_keys = ON;")
    lines.append("")

    for spec in contract.table_specs():
        ns = spec["namespace"]
        if ns == "capture" and not include_capture:
            continue
        if ns == "inference" and not include_inference:
            continue
        if ns == "settlement" and not include_settlement:
            continue
        lines.append(f"-- namespace: {ns}")
        lines.append(f"CREATE TABLE IF NOT EXISTS {spec['name']} (")
        col_lines = []
        for (cname, ctype, ptype, nullable, cons) in spec["columns"]:
            sql_type = SQLITE_TYPE_MAP.get(ctype, ctype)
            parts = [f"  {cname} {sql_type}"]
            if not nullable:
                parts.append("NOT NULL")
            if "PK" in cons:
                parts.append("PRIMARY KEY")
            col_lines.append(" ".join(parts))
        if spec["pk"] and not any("PK" in c[4] for c in spec["columns"]):
            col_lines.append(f"  PRIMARY KEY ({', '.join(spec['pk'])})")
        for uq in spec["uniques"]:
            col_lines.append(f"  UNIQUE ({', '.join(uq)})")
        for fk in spec["fks"]:
            col_lines.append(f"  FOREIGN KEY ({fk[0]}) REFERENCES {fk[1]}({fk[2]})")
        for ck in spec["checks"]:
            col_lines.append(f"  CHECK ({ck})")
        lines.append(",\n".join(col_lines))
        lines.append(");")
        lines.append("")
    return "\n".join(lines)


def render_ddl_sha256() -> str:
    return hashlib.sha256(render_ddl().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# PyArrow schemas for immutable research Parquet partitions
# ---------------------------------------------------------------------------
PYARROW_TYPES = {
    "string": "pa.string()",
    "int64": "pa.int64()",
    "float64": "pa.float64()",
    "timestamp[us, tz=UTC]": "pa.timestamp('us', tz='UTC')",
}


def arrow_schema_json(table_name: str) -> dict:
    """Machine-readable PyArrow schema for one canonical table (as JSON)."""
    spec = next(s for s in contract.table_specs() if s["name"] == table_name)
    fields = []
    for (cname, ctype, ptype, nullable, cons) in spec["columns"]:
        fields.append({
            "name": cname,
            "type": ptype,
            "nullable": nullable,
            "arrow": PYARROW_TYPES[ptype],
        })
    return {"table": table_name, "namespace": spec["namespace"], "fields": fields}


def all_arrow_schemas_json() -> dict:
    return {s["name"]: arrow_schema_json(s["name"]) for s in contract.table_specs()}


def arrow_schema(table_name: str):
    """Materialize a pyarrow.Schema for the given canonical table."""
    import pyarrow as pa

    spec = next(s for s in contract.table_specs() if s["name"] == table_name)
    fields = []
    for (cname, ctype, ptype, nullable, cons) in spec["columns"]:
        pa_type = eval(PYARROW_TYPES[ptype], {"pa": pa})  # noqa: S307 — fixed whitelist
        fields.append(pa.field(cname, pa_type, nullable=nullable))
    return pa.schema(fields)


def domain_dictionary() -> list[dict]:
    """Domain dictionary rows (machine-readable; rendered to CSV by builder)."""
    rows: list[dict] = []
    for spec in contract.table_specs():
        for (cname, ctype, ptype, nullable, cons) in spec["columns"]:
            rows.append({
                "table": spec["name"],
                "column": cname,
                "sqlite_type": SQLITE_TYPE_MAP.get(ctype, ctype),
                "arrow_type": ptype,
                "nullable": str(nullable).lower(),
                "constraints": ",".join(cons) if cons else "",
                "domain_notes": _domain_notes(spec["name"], cname),
            })
    return rows


def _domain_notes(table: str, column: str) -> str:
    if table == "fixture" and column == "fixture_id":
        return "canonical identity; unique within issue_code x match_idx (REQ-DS02)"
    if table == "fixture" and column == "identity_status":
        return "CANONICAL | ALIAS_RESOLVED | UNRESOLVED"
    if table == "market_quote" and column == "outcome_code":
        return "exactly 3/1/0 after explicit mapping (REQ-DS04)"
    if table == "market_quote" and column == "decimal_odds":
        return "decimal odds > 1.0; Mx3 long form per observation"
    if table == "probability_estimate" and column == "probability":
        return "probability in [0,1]; long-form scalar keyed by outcome_code"
    if table == "market_observation" and column == "observed_at_utc":
        return "exact source observation time; NOT interchangeable with received_at (REQ-DS03)"
    if table == "market_observation" and column == "received_at_utc":
        return "trusted fetch/receive clock; NOT interchangeable with observed_at (REQ-DS03)"
    if table == "fixture" and column == "kickoff_at_utc":
        return "scheduled kickoff (UTC); NOT a decision epoch (REQ-DS03)"
    if table == "decision_epoch" and column == "decision_at_utc":
        return "decision cutoff; must be < kickoff_at_utc for causal use"
    if table == "settlement" and column == "result_code":
        return "settlement namespace only; never an inference-time input"
    return ""
