"""Issue #234 census: profile every existing database/table/key/timestamp.

The census reads the legacy databases read-only and emits machine-readable
registry frames that the builder freezes into the package.  Every legacy table
is graded for its clock semantics and admissible-use class with evidence
(REQ-DS01, REQ-DS03), and identity uniqueness is measured per database
(REQ-DS02, REQ-DS04).

Databases are gitignored raw assets on the producer machine; the census never
mutates them (``mode=ro``) and records their existence, size and schema only.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import contract

# ---------------------------------------------------------------------------
# Database inventory (paths resolved relative to the repo root at call time)
# ---------------------------------------------------------------------------
# Rows above this threshold skip per-column NULL/DISTINCT full scans (a
# 51M-row market_snapshots table would otherwise need dozens of full scans).
# Timestamp columns still get measured — they carry the clock evidence.
LARGE_TABLE_ROWS = 1_000_000
# Each entry: key, relative path, family, description.  Paths point at the
# primary working-tree data assets; the census resolves them under the caller's
# root so the executed notebook can bind the actual file sizes and hashes.
DATABASE_INVENTORY: tuple[dict[str, str], ...] = (
    {
        "key": "beidan_xlsm",
        "path": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "description": "2014-2025 historical identity and 51.5M labelled market snapshots",
    },
    {
        "key": "beidan_features",
        "path": "data/beidan_features.db",
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "description": "2014-2025 match identities and European probability features",
    },
    {
        "key": "beidan_history",
        "path": "data/beidan_history.db",
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "description": "2024-2026 settlement/history rows",
    },
    {
        "key": "beidan_live",
        "path": "data/beidan_live.db",
        "family": contract.FAMILY_BEIJING,
        "description": "2026-05 onward timestamped Beijing SP/European snapshots (primary prospective causal source)",
    },
    {
        "key": "beidan_modeling_plus",
        "path": "data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite",
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "description": "Derived modeling tables built from the xlsm workbook",
    },
    {
        "key": "beidan_nowscore",
        "path": "data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite",
        "family": contract.FAMILY_INTERNAL_HISTORICAL,
        "description": "Derived nowscore table built from the xlsm workbook",
    },
)


@dataclass
class CensusResult:
    """All frames produced by one census pass."""

    databases: pd.DataFrame
    tables: pd.DataFrame
    columns: pd.DataFrame
    identity: pd.DataFrame
    timestamps: pd.DataFrame
    source_hashes: pd.DataFrame


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _primary_repo_root(root: Path) -> Path:
    """Resolve the primary repo root when running inside a linked worktree.

    Gitignored raw assets (``data/``) exist only in the primary checkout; a
    linked worktree has no copy.  ``git rev-parse --git-common-dir`` returns
    the shared ``.git`` directory, whose parent is the primary tree.
    """
    try:
        import subprocess

        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        )
        common = Path(result.stdout.strip()).resolve()
        if common.name == ".git":
            return common.parent
        # bare/common dir layout: <repo>/.git/worktrees/... -> <repo>/.git
        if common.parent.name == ".git" and common.parent.parent.exists():
            return common.parent.parent
        return root
    except Exception:
        return root


def _resolve_data_path(root: Path, relative: str) -> Path:
    """Resolve a repo-relative data path, preferring the primary tree."""
    candidate = root / relative
    if candidate.exists():
        return candidate
    primary = _primary_repo_root(root)
    primary_candidate = primary / relative
    if primary_candidate.exists():
        return primary_candidate
    return candidate


def _connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _list_tables(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    return [row[0] for row in rows]


def _table_rows(connection: sqlite3.Connection, table: str) -> int:
    try:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return -1


def _table_info(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return connection.execute(f'PRAGMA table_info("{table}")').fetchall()


def _table_indexes(connection: sqlite3.Connection, table: str) -> list[tuple]:
    return connection.execute(f'PRAGMA index_list("{table}")').fetchall()


def _null_counts(connection: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in columns:
        try:
            row = connection.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NULL'
            ).fetchone()
            counts[column] = int(row[0])
        except sqlite3.Error:
            counts[column] = -1
    return counts


def _distinct_counts(connection: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for column in columns[:12]:  # cap to keep the census bounded
        try:
            row = connection.execute(
                f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'
            ).fetchone()
            counts[column] = int(row[0])
        except sqlite3.Error:
            counts[column] = -1
    return counts


def _min_max(connection: sqlite3.Connection, table: str, columns: list[str]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for column in columns:
        try:
            row = connection.execute(
                f'SELECT MIN("{column}"), MAX("{column}") FROM "{table}"'
            ).fetchone()
            result[column] = (str(row[0]), str(row[1]))
        except sqlite3.Error:
            result[column] = ("", "")
    return result


def _identity_duplicates(
    connection: sqlite3.Connection, table: str, columns: tuple[str, str]
) -> tuple[int, int]:
    """Return (distinct_pairs, duplicate_pair_count) for (issue, match_idx)."""
    issue, match_idx = columns
    try:
        row = connection.execute(
            f'SELECT COUNT(*), COUNT(DISTINCT "{issue}" || "|" || "{match_idx}") '
            f'FROM "{table}"'
        ).fetchone()
        total = int(row[0])
        distinct = int(row[1])
        return distinct, total - distinct
    except sqlite3.Error:
        return -1, -1


# Clock grading maps: timestamp column name -> clock semantics.  These are the
# evidence-based adjudications (REQ-DS01/DS03); a label such as ``initial`` or
# ``10h`` is never accepted as an exact observation timestamp.
CLOCK_EVIDENCE: dict[str, dict[str, str]] = {
    "beidan_xlsm": {
        "kickoff_ts": contract.CLOCK_SCHEDULE_ONLY,
        "ts_10h": contract.CLOCK_LABEL_RELATIVE,
        "kickoff_serial": contract.CLOCK_NO_CLOCK,
        "ts_10h_serial": contract.CLOCK_NO_CLOCK,
        "fetched_at": contract.CLOCK_TIMESTAMPED_LOCAL,
        "imported_at": contract.CLOCK_TIMESTAMPED_UTC,
        "end_time": contract.CLOCK_SCHEDULE_ONLY,
        "schedule_date": contract.CLOCK_SCHEDULE_ONLY,
    },
    "beidan_features": {
        "kickoff": contract.CLOCK_SCHEDULE_ONLY,
    },
    "beidan_history": {
        "kickoff_ts": contract.CLOCK_SCHEDULE_ONLY,
        "fetched_at": contract.CLOCK_TIMESTAMPED_LOCAL,
    },
    "beidan_live": {
        "kickoff_ts": contract.CLOCK_SCHEDULE_ONLY,
        "created_ts": contract.CLOCK_TIMESTAMPED_LOCAL,
        "snapshot_ts": contract.CLOCK_TIMESTAMPED_UTC,
        "settled_ts": contract.CLOCK_TIMESTAMPED_LOCAL,
    },
}

# Which (issue, match_idx) pairs identify matches in each database.
IDENTITY_COLUMNS: dict[str, tuple[str, str]] = {
    "beidan_xlsm": ("issue", "match_idx"),
    "beidan_features": ("issue", "match_idx"),
    "beidan_history": ("issue", "match_idx"),
    "beidan_live": ("issue", "match_idx"),
}

# Timestamp columns that carry observation semantics per database (the ones the
# census must measure for nulls / ranges so the clock evidence is concrete).
TIMESTAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    "beidan_xlsm": ("kickoff_ts", "ts_10h", "fetched_at", "imported_at", "end_time"),
    "beidan_features": ("kickoff",),
    "beidan_history": ("kickoff_ts", "fetched_at"),
    "beidan_live": ("kickoff_ts", "created_ts", "snapshot_ts", "settled_ts"),
}


def run_census(root: Path) -> CensusResult:
    """Profile every registered database under ``root`` read-only.

    Databases that do not exist are recorded with ``exists=False`` so the
    frozen registry names them explicitly (UNUSABLE / missing asset) instead
    of silently omitting them.
    """
    database_rows: list[dict[str, object]] = []
    table_rows: list[dict[str, object]] = []
    column_rows: list[dict[str, object]] = []
    identity_rows: list[dict[str, object]] = []
    timestamp_rows: list[dict[str, object]] = []

    for entry in DATABASE_INVENTORY:
        key = entry["key"]
        path = _resolve_data_path(root, entry["path"])
        size = path.stat().st_size if path.exists() else -1
        clock_map = CLOCK_EVIDENCE.get(key, {})
        identity_cols = IDENTITY_COLUMNS.get(key)
        timestamp_cols = TIMESTAMP_COLUMNS.get(key, ())

        database_rows.append(
            {
                "database_key": key,
                "path": entry["path"],
                "family": entry["family"],
                "description": entry["description"],
                "exists": bool(path.exists()),
                "size_bytes": size,
                "sha256": _sha256(path) if path.exists() and size > 0 else "",
            }
        )

        if not path.exists():
            table_rows.append(
                {
                    "database_key": key,
                    "table": "(missing)",
                    "row_count": -1,
                    "column_count": 0,
                    "primary_keys": "",
                    "indexes": "",
                    "identity_unique_rows": -1,
                    "identity_duplicate_rows": -1,
                }
            )
            continue

        connection = _connect_readonly(path)
        try:
            for table in _list_tables(connection):
                rows = _table_rows(connection, table)
                info = _table_info(connection, table)
                indexes = _table_indexes(connection, table)
                columns = [row[1] for row in info]
                pk_columns = [
                    row[1] for row in info if row[5] > 0
                ]  # pragma table_info: pk ordinal
                pk_display = ",".join(pk_columns) if pk_columns else ""
                index_display = ",".join(
                    row[1] for row in indexes if not row[1].startswith("sqlite_autoindex")
                )

                # Large tables (multi-million rows) skip per-column full scans
                # except for the timestamp columns that carry clock evidence.
                # Row count + identity checks still run (cheap or absent on the
                # wide legacy tables that have no issue/match_idx columns).
                large = rows >= LARGE_TABLE_ROWS
                stats_columns = timestamp_cols if large else columns

                nulls = _null_counts(connection, table, list(stats_columns))
                distincts = _distinct_counts(connection, table, list(stats_columns))
                ranges = _min_max(connection, table, list(stats_columns))

                for column in columns:
                    if large and column not in timestamp_cols:
                        column_rows.append(
                            {
                                "database_key": key,
                                "table": table,
                                "column": column,
                                "null_count": -2,  # LARGE_SKIPPED
                                "distinct_count": -2,
                                "min_value": "",
                                "max_value": "",
                                "clock_semantics": clock_map.get(
                                    column, contract.CLOCK_NO_CLOCK
                                ),
                            }
                        )
                        continue
                    column_rows.append(
                        {
                            "database_key": key,
                            "table": table,
                            "column": column,
                            "null_count": nulls.get(column, -1),
                            "distinct_count": distincts.get(column, -1),
                            "min_value": ranges.get(column, ("", ""))[0],
                            "max_value": ranges.get(column, ("", ""))[1],
                            "clock_semantics": clock_map.get(column, contract.CLOCK_NO_CLOCK),
                        }
                    )
                    if column in timestamp_cols:
                        timestamp_rows.append(
                            {
                                "database_key": key,
                                "table": table,
                                "column": column,
                                "min_value": ranges.get(column, ("", ""))[0],
                                "max_value": ranges.get(column, ("", ""))[1],
                                "null_count": nulls.get(column, -1),
                                "clock_semantics": clock_map.get(column, contract.CLOCK_NO_CLOCK),
                            }
                        )

                identity_distinct = identity_duplicates = -1
                if (
                    identity_cols
                    and identity_cols[0] in columns
                    and identity_cols[1] in columns
                    and not large
                ):
                    identity_distinct, identity_duplicates = _identity_duplicates(
                        connection, table, identity_cols
                    )
                    identity_rows.append(
                        {
                            "database_key": key,
                            "table": table,
                            "identity_columns": f"{identity_cols[0]},{identity_cols[1]}",
                            "row_count": rows,
                            "distinct_identity": identity_distinct,
                            "duplicate_identity_rows": identity_duplicates,
                        }
                    )

                table_rows.append(
                    {
                        "database_key": key,
                        "table": table,
                        "row_count": rows,
                        "column_count": len(columns),
                        "primary_keys": pk_display,
                        "indexes": index_display,
                        "identity_unique_rows": identity_distinct,
                        "identity_duplicate_rows": identity_duplicates,
                    }
                )
        finally:
            connection.close()

    databases = pd.DataFrame(database_rows)
    tables = pd.DataFrame(table_rows)
    columns = pd.DataFrame(column_rows)
    identity = pd.DataFrame(identity_rows)
    timestamps = pd.DataFrame(timestamp_rows)

    # Source hashes: the #203/#214/#229 immutable packages and the raw asset
    # checksums captured for the registry receipt (REQ-DS07 binds them).
    source_hashes = _collect_source_hashes(root)

    return CensusResult(
        databases=databases,
        tables=tables,
        columns=columns,
        identity=identity,
        timestamps=timestamps,
        source_hashes=source_hashes,
    )


def _collect_source_hashes(root: Path) -> pd.DataFrame:
    """Hash immutable package manifests and git-tracked source files.

    Every accepted upstream package (bj203/bj214/bj229) contributes its
    MANIFEST.json content hash; git-tracked raw assets (football-data CSVs)
    contribute their file hashes.  The registry receipt therefore binds the
    exact accepted inputs rather than a reputation label.
    """
    rows: list[dict[str, str]] = []
    packages = (
        "results/bj203_causal_tensor_v2",
        "results/bj214_decision_epoch_tensor_v1",
        "results/bj229_divergence_profile_v1",
    )
    for package in packages:
        manifest_path = root / package / "MANIFEST.json"
        if manifest_path.exists():
            rows.append(
                {
                    "source_key": package.replace("results/", ""),
                    "kind": "immutable_package_manifest",
                    "path": str(manifest_path.relative_to(root)),
                    "sha256": _sha256(manifest_path),
                }
            )

    football_data_dir = _resolve_data_path(root, "data/raw/football-data")
    if football_data_dir.exists():
        for csv_path in sorted(football_data_dir.glob("*.csv")):
            rows.append(
                {
                    "source_key": f"football_data:{csv_path.name}",
                    "kind": "raw_csv",
                    "path": str(csv_path.relative_to(football_data_dir.parent.parent))
                    if str(csv_path).startswith(str(root))
                    else f"data/raw/football-data/{csv_path.name}",
                    "sha256": _sha256(csv_path),
                }
            )

    if not rows:
        return pd.DataFrame(columns=["source_key", "kind", "path", "sha256"])
    return pd.DataFrame(rows)
