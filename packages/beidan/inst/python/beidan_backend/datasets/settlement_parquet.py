"""Parquet dataset conversion for the persistent NAS layer.

Turns a source SQLite release into a versioned Parquet dataset with a manifest
that binds the source identity, per-file hashes and row counts. Pure and
side-effect-free at import; every path, the clock and the source connection are
explicit parameters so the conversion can be tested on a tiny fixture.

Design contract: ``config/parquet_layout.json``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..versioning import VersionError, publish_version

WRITE_COMPRESSION = "snappy"
ROW_GROUP_SIZE = 250_000
PARQUET_VERSION = "2.6"


class DatasetConversionError(RuntimeError):
    """The conversion could not produce a complete, publishable dataset."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def issue_year(issue: Any) -> int | None:
    """Two-digit issue prefix -> year, matching the existing issue_year helper."""
    text = str(issue or "")
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return 2000 + int(text[:2])


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _arrow_from_frame(frame: pd.DataFrame) -> pa.Table:
    """Build an Arrow table without forcing text columns to UTF-8.

    SQLite columns have dynamic typing and some are BLOB (for example
    ``sp_correction_batch.raw_html`` holds raw HTML bytes). Forcing an
    Arrow-backed string dtype raises on such bytes, so object columns are typed
    per column: bytes become ``binary`` and everything else becomes ``string``.
    """
    arrays = []
    fields = []
    for name in frame.columns:
        column = frame[name]
        if column.dtype == object:
            sample = column.dropna()
            if len(sample) and isinstance(sample.iloc[0], (bytes, bytearray, memoryview)):
                array = pa.array(
                    [None if value is None else bytes(value) for value in column],
                    type=pa.binary(),
                )
            else:
                array = pa.array(
                    [None if value is None else str(value) for value in column],
                    type=pa.string(),
                )
        else:
            array = pa.array(column)
        arrays.append(array)
        fields.append(pa.field(str(name), array.type))
    return pa.Table.from_arrays(arrays, schema=pa.schema(fields))


def read_table_arrow(conn: sqlite3.Connection, sql: str) -> pa.Table:
    """Materialize a query as an Arrow table, preserving nullability and bytes."""
    frame = pd.read_sql_query(sql, conn)
    return _arrow_from_frame(frame)


def table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]


def table_row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])


def table_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    return [
        (str(row[1]), str(row[2] or ""))
        for row in conn.execute(f"PRAGMA table_info({_quote(table)})")
    ]


def write_whole_table(table: pa.Table, destination: Path) -> dict[str, Any]:
    """Write one unpartitioned table and describe it for the manifest."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        destination,
        compression=WRITE_COMPRESSION,
        row_group_size=ROW_GROUP_SIZE,
        version=PARQUET_VERSION,
        use_dictionary=True,
    )
    _fsync(destination)
    return {
        "kind": "whole",
        "rows": table.num_rows,
        "files": [describe_file(destination)],
    }


def write_partitioned_table(
    table: pa.Table,
    directory: Path,
    *,
    year_column: str = "issue_year",
) -> dict[str, Any]:
    """Write one parquet file per partition year and describe them for the manifest."""
    directory.mkdir(parents=True, exist_ok=True)
    if year_column not in table.column_names:
        raise DatasetConversionError(f"partition column {year_column!r} is absent")
    years = table.column(year_column).to_pylist()
    distinct = sorted({year for year in years if year is not None})
    files: list[dict[str, Any]] = []
    total = 0
    for year in distinct:
        mask = pa.array([value == year for value in years])
        part = table.filter(mask)
        path = directory / f"part-issue-year={year}.parquet"
        pq.write_table(
            part,
            path,
            compression=WRITE_COMPRESSION,
            row_group_size=ROW_GROUP_SIZE,
            version=PARQUET_VERSION,
            use_dictionary=True,
        )
        _fsync(path)
        files.append(describe_file(path))
        total += part.num_rows
    if total != table.num_rows:
        raise DatasetConversionError(
            f"partitioned row count {total} != source {table.num_rows}"
        )
    return {"kind": "partitioned", "rows": total, "partitions": len(distinct), "files": files}


def describe_file(path: Path) -> dict[str, Any]:
    return {
        "name": path.name,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def _fsync(path: Path) -> None:
    import os

    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- #
# Settlement conversion
# --------------------------------------------------------------------------- #

# Tables whose bulk is keyed by issue are partitioned by issue_year; the rest are
# small batch/receipt tables written whole. `option_sp` reaches issue through its
# parent observation row.
SETTLEMENT_PARTITIONED_SQL = {
    "observation": "SELECT * FROM observation",
    "option_sp": (
        "SELECT o.issue AS issue, s.observation_id, s.option, s.raw_sp, s.sp, s.cell_id "
        "FROM option_sp s LEFT JOIN observation o ON o.observation_id = s.observation_id"
    ),
}


def convert_settlement(
    *,
    database: Path,
    output_root: Path,
    version: str,
    source_registry: dict[str, Any] | None = None,
    generated_at: str | None = None,
    table_row_counts: Callable[[sqlite3.Connection], dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Convert the settlement SQLite release into a versioned Parquet dataset.

    Publication goes through the shared versioning module, so the base dataset
    follows the same lifecycle as a derived artifact: written into a staging
    directory, and published under ``datasets/settlement/versions/<version>/``
    with ``datasets/settlement/current.json`` pointing at the newest version.
    A label already published with different content is refused.
    """
    database = Path(database)
    output_root = Path(output_root)
    if not database.is_file():
        raise DatasetConversionError(f"source database is absent: {database}")
    if not output_root.is_dir():
        raise DatasetConversionError(f"output root is not available: {output_root}")

    base = output_root / "datasets" / "settlement"

    def build(staging: Path) -> dict[str, Any]:
        return _convert_into(database, staging, version, source_registry, generated_at)

    try:
        published = publish_version(base, version, build)
    except VersionError as error:
        raise DatasetConversionError(str(error)) from error
    # Callers expect the manifest, which the publisher wrote into the version.
    return json.loads((base / "versions" / version / "manifest.json").read_text(encoding="utf-8"))


def _convert_into(
    database: Path,
    staging: Path,
    version: str,
    source_registry: dict[str, Any] | None,
    generated_at: str | None,
) -> dict[str, Any]:
    """Write one version's tables and manifest into ``staging``.

    @return The version record for the publisher (row counts and the manifest).
    """
    tables_dir = staging / "tables"
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        names = table_names(conn)
        counts = {name: table_row_count(conn, name) for name in names}
        described: dict[str, Any] = {}
        for name in names:
            if name in SETTLEMENT_PARTITIONED_SQL:
                table = read_table_arrow(conn, SETTLEMENT_PARTITIONED_SQL[name])
                years = [issue_year(value) for value in table.column("issue").to_pylist()]
                table = table.append_column("issue_year", pa.array(years, pa.int16()))
                table = table.drop_columns(["issue"]) if name == "option_sp" else table
                described[name] = write_partitioned_table(table, tables_dir / name)
            else:
                table = read_table_arrow(conn, f"SELECT * FROM {_quote(name)}")
                described[name] = write_whole_table(table, tables_dir / f"{name}.parquet")
            if described[name]["rows"] != counts[name]:
                raise DatasetConversionError(
                    f"{name}: wrote {described[name]['rows']} rows, source has {counts[name]}"
                )
    finally:
        conn.close()

    manifest = {
        "schema": "beijing_lot_parquet_dataset_v1",
        "dataset": "settlement",
        "version": version,
        "converted_at": generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "database": str(database),
            "sha256": sha256_file(database),
            "registry": source_registry,
        },
        "converter": {
            "module": "beidan_backend.datasets.settlement_parquet",
            "sha256": sha256_file(Path(__file__)),
            "compression": WRITE_COMPRESSION,
            "row_group_size": ROW_GROUP_SIZE,
        },
        "partition_by": "issue_year",
        "row_counts": counts,
        "tables": described,
    }
    write_json_atomically_local(manifest, staging / "manifest.json")
    return {"rows": sum(counts.values()), "tables": len(described),
            "manifest": "manifest.json", "row_counts": counts}


def write_json_atomically_local(value, path: Path) -> None:
    """Write JSON atomically; kept local so the converter has no other dependency."""
    import os

    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def verify_manifest(version_dir: Path) -> dict[str, Any]:
    """Recompute every file hash in a published version and report mismatches."""
    version_dir = Path(version_dir)
    manifest = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    mismatches: list[str] = []
    missing: list[str] = []
    for name, entry in manifest.get("tables", {}).items():
        for file in entry.get("files", []):
            path = (
                version_dir / "tables" / name / file["name"]
                if entry["kind"] == "partitioned"
                else version_dir / "tables" / file["name"]
            )
            if not path.is_file():
                missing.append(str(path))
            elif sha256_file(path) != file["sha256"]:
                mismatches.append(str(path))
    return {
        "ok": not mismatches and not missing,
        "mismatches": mismatches,
        "missing": missing,
        "tables": len(manifest.get("tables", {})),
    }
