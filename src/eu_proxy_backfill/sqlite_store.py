"""Incremental SQLite store for the #268 historical proxy recovery.

Raw provider bytes remain the external origin evidence.  This database is the
durable, rebuildable ingestion and QA layer: every issue is committed in one
transaction, duplicate resolution happens in SQL, and downstream Parquet views
are derived from ``resolved_quotes`` rather than an in-memory union.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd


SCHEMA_VERSION = "BJ268_RECOVERY_SQLITE_V1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE inventory (
            issue_code TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            provider_match_id TEXT,
            kickoff_ts TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            native_handicap_line REAL,
            reconciled_source TEXT NOT NULL,
            PRIMARY KEY (issue_code, match_idx)
        ) WITHOUT ROWID;

        -- Compatibility surface consumed by the accepted #236 materializer.
        -- Result/score fields intentionally do not exist in this candidate.
        CREATE TABLE matches (
            match_id INTEGER PRIMARY KEY,
            sheet_row INTEGER NOT NULL UNIQUE,
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            kickoff_ts TEXT,
            league TEXT,
            home TEXT,
            away TEXT,
            handicap_line REAL,
            provider_match_id TEXT,
            handicap_line_norm REAL,
            handicap_norm_source TEXT
        );

        CREATE TABLE market_snapshots (
            match_id INTEGER NOT NULL,
            market TEXT NOT NULL,
            bookmaker TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            v1 REAL,
            v2 REAL,
            v3 REAL,
            FOREIGN KEY (match_id) REFERENCES matches(match_id)
        );

        CREATE TABLE source_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE issue_dispositions (
            issue_code TEXT PRIMARY KEY,
            disposition TEXT NOT NULL,
            done_manifest_sha256 TEXT NOT NULL
        ) WITHOUT ROWID;

        CREATE TABLE acquisition_receipts (
            source_kind TEXT NOT NULL,
            source_key TEXT NOT NULL,
            source_url TEXT NOT NULL,
            requested_at_utc TEXT NOT NULL,
            received_at_utc TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            acquisition_result TEXT NOT NULL,
            status_code INTEGER,
            payload_bytes INTEGER,
            payload_sha256 TEXT,
            error_class TEXT,
            error_detail TEXT,
            attempt_count INTEGER NOT NULL,
            PRIMARY KEY (source_kind, source_key)
        ) WITHOUT ROWID;

        CREATE TABLE fixture_horizon_dispositions (
            issue_code TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            provider_match_id TEXT,
            snapshot_kind TEXT NOT NULL CHECK (snapshot_kind IN ('initial', '10h', '1h')),
            disposition TEXT NOT NULL,
            detail TEXT NOT NULL,
            PRIMARY KEY (issue_code, match_idx, snapshot_kind)
        ) WITHOUT ROWID;

        CREATE TABLE raw_quote_observations (
            observation_id INTEGER PRIMARY KEY,
            issue_code TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            source_match_id TEXT NOT NULL,
            provider_match_id TEXT,
            snapshot_kind TEXT NOT NULL CHECK (snapshot_kind IN ('initial', '10h', '1h')),
            bookmaker_id TEXT NOT NULL,
            v1 REAL,
            v2 REAL,
            v3 REAL,
            native_handicap_line_raw TEXT,
            native_handicap_line REAL,
            handicap_norm_source TEXT,
            payload_sha256 TEXT NOT NULL,
            quote_signature TEXT NOT NULL
            ,source_lane TEXT NOT NULL
        );

        CREATE TABLE duplicate_resolution_ledger (
            issue_code TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            snapshot_kind TEXT NOT NULL,
            bookmaker_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL,
            distinct_value_count INTEGER NOT NULL,
            payload_sha256s TEXT NOT NULL,
            PRIMARY KEY (issue_code, match_idx, snapshot_kind, bookmaker_id)
        ) WITHOUT ROWID;

        CREATE TABLE resolved_quotes (
            issue_code TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            source_match_id TEXT NOT NULL,
            provider_match_id TEXT,
            snapshot_kind TEXT NOT NULL CHECK (snapshot_kind IN ('initial', '10h', '1h')),
            bookmaker_id TEXT NOT NULL,
            v1 REAL,
            v2 REAL,
            v3 REAL,
            native_handicap_line_raw TEXT,
            native_handicap_line REAL,
            handicap_norm_source TEXT,
            payload_sha256 TEXT NOT NULL,
            PRIMARY KEY (issue_code, match_idx, snapshot_kind, bookmaker_id)
        ) WITHOUT ROWID;
        """
    )


def _records(frame: pd.DataFrame, columns: list[str]) -> list[tuple[object, ...]]:
    clean = frame.reindex(columns=columns).astype(object).where(pd.notna(frame.reindex(columns=columns)), None)
    return list(clean.itertuples(index=False, name=None))


def _quote_signature(row: object) -> str:
    values = [getattr(row, name) for name in ("v1", "v2", "v3")]
    canonical = [None if pd.isna(value) else float(value) for value in values]
    return json.dumps(canonical, separators=(",", ":"), allow_nan=False)


def _insert_issue(connection: sqlite3.Connection, part: Path) -> tuple[int, int, int]:
    done_path = part / "DONE.json"
    done = json.loads(done_path.read_text(encoding="utf-8"))
    issue = str(done["issue_code"])
    declared_hashes = done.get("sha256")
    if not isinstance(declared_hashes, dict) or not declared_hashes:
        raise ValueError(f"{issue} DONE marker lacks part hashes")
    for name, expected in declared_hashes.items():
        artifact = part / str(name)
        if not artifact.is_file() or _sha256(artifact) != expected:
            raise ValueError(f"{issue} checkpoint hash mismatch: {name}")
    disposition = json.loads((part / "issue_disposition.json").read_text(encoding="utf-8"))
    receipts = pd.read_csv(part / "receipts.csv", dtype={"source_key": str})
    horizons = pd.read_parquet(part / "fixture_horizon_dispositions.parquet")
    quotes = pd.read_parquet(part / "raw_quotes.parquet")

    receipt_columns = [
        "source_kind", "source_key", "source_url", "requested_at_utc", "received_at_utc",
        "parser_version", "acquisition_result", "status_code", "payload_bytes",
        "payload_sha256", "error_class", "error_detail", "attempt_count",
    ]
    horizon_columns = [
        "issue_code", "match_idx", "provider_match_id", "snapshot_kind",
        "disposition", "detail",
    ]
    quote_columns = [
        "issue_code", "match_idx", "source_match_id", "provider_match_id",
        "snapshot_kind", "bookmaker_id", "v1", "v2", "v3",
        "native_handicap_line_raw", "native_handicap_line", "handicap_norm_source",
        "payload_sha256",
    ]
    missing = set(quote_columns) - set(quotes.columns)
    if missing:
        raise ValueError(f"{issue} raw quotes missing columns: {sorted(missing)}")
    quote_rows = [(*values, _quote_signature(row), "NOWSCORE_ISSUE_PAGE") for values, row in zip(
        _records(quotes, quote_columns), quotes.itertuples(index=False), strict=True
    )]
    with connection:
        connection.execute(
            "INSERT INTO issue_dispositions VALUES (?, ?, ?)",
            (issue, str(disposition["issue_disposition"]), _sha256(done_path)),
        )
        connection.executemany(
            f"INSERT INTO acquisition_receipts VALUES ({','.join('?' for _ in receipt_columns)})",
            _records(receipts, receipt_columns),
        )
        connection.executemany(
            f"INSERT INTO fixture_horizon_dispositions VALUES ({','.join('?' for _ in horizon_columns)})",
            _records(horizons, horizon_columns),
        )
        connection.executemany(
            f"INSERT INTO raw_quote_observations ({','.join(quote_columns)}, quote_signature, source_lane) "
            f"VALUES ({','.join('?' for _ in range(len(quote_columns) + 2))})",
            quote_rows,
        )
    return len(receipts), len(horizons), len(quotes)


def _resolve_duplicates(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX raw_quote_key_idx ON raw_quote_observations
            (issue_code, match_idx, snapshot_kind, bookmaker_id);

        CREATE TEMP TABLE quote_groups AS
        SELECT issue_code, match_idx, snapshot_kind, bookmaker_id,
               COUNT(*) AS occurrence_count,
               COUNT(DISTINCT quote_signature) AS distinct_value_count,
               MIN(payload_sha256) AS selected_payload_sha256,
               MIN(observation_id) AS first_observation_id
        FROM raw_quote_observations
        GROUP BY issue_code, match_idx, snapshot_kind, bookmaker_id;

        INSERT INTO duplicate_resolution_ledger
        SELECT issue_code, match_idx, snapshot_kind, bookmaker_id,
               CASE distinct_value_count
                   WHEN 1 THEN 'EXACT_DUPLICATE_SOURCE_QUOTE'
                   ELSE 'CONFLICTING_DUPLICATE_SOURCE_QUOTE'
               END,
               g.occurrence_count, g.distinct_value_count,
               (SELECT GROUP_CONCAT(ordered.payload_sha256, ',')
                  FROM (
                      SELECT r0.payload_sha256
                      FROM raw_quote_observations AS r0
                      WHERE r0.issue_code=g.issue_code AND r0.match_idx=g.match_idx
                        AND r0.snapshot_kind=g.snapshot_kind AND r0.bookmaker_id=g.bookmaker_id
                      ORDER BY r0.payload_sha256, r0.observation_id
                  ) AS ordered)
        FROM quote_groups AS g
        WHERE g.occurrence_count > 1;

        INSERT INTO resolved_quotes
        SELECT r.issue_code, r.match_idx, r.source_match_id, r.provider_match_id,
               r.snapshot_kind, r.bookmaker_id, r.v1, r.v2, r.v3,
               r.native_handicap_line_raw, r.native_handicap_line,
               r.handicap_norm_source, r.payload_sha256
        FROM raw_quote_observations AS r
        JOIN (
            SELECT g.issue_code, g.match_idx, g.snapshot_kind, g.bookmaker_id,
                   MIN(r2.observation_id) AS selected_observation_id
            FROM quote_groups AS g
            JOIN raw_quote_observations AS r2
              ON r2.issue_code = g.issue_code
             AND r2.match_idx = g.match_idx
             AND r2.snapshot_kind = g.snapshot_kind
             AND r2.bookmaker_id = g.bookmaker_id
             AND r2.payload_sha256 = g.selected_payload_sha256
            WHERE g.distinct_value_count = 1
            GROUP BY g.issue_code, g.match_idx, g.snapshot_kind, g.bookmaker_id
        ) AS chosen ON chosen.selected_observation_id = r.observation_id;

        CREATE INDEX resolved_quote_fixture_idx ON resolved_quotes
            (issue_code, match_idx, snapshot_kind);
        DROP TABLE quote_groups;
        """
    )


def build_recovery_sqlite(staging: Path, target: Path) -> dict[str, int | str]:
    """Build an immutable recovery database from completed issue checkpoints.

    No network or mutable live database is opened.  A temporary sibling is
    fsynced and atomically renamed only after all 73 issue transactions and the
    deterministic duplicate-resolution pass finish.
    """
    staging = staging.resolve()
    target = target.resolve()
    if target.exists():
        raise FileExistsError(target)
    parts = sorted((staging / "issue_parts").glob("*/DONE.json"), key=lambda path: int(path.parent.name))
    selected = json.loads((staging / "GATE_START.json").read_text(encoding="utf-8"))["selected_issue_codes"]
    if [path.parent.name for path in parts] != selected:
        raise ValueError("completed issue set differs from frozen selected issue set")
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        raise FileExistsError(temporary)
    connection = sqlite3.connect(temporary)
    try:
        _create_schema(connection)
        totals = {"receipt_rows": 0, "disposition_rows": 0, "raw_quote_rows": 0}
        for marker in parts:
            receipt_count, disposition_count, quote_count = _insert_issue(connection, marker.parent)
            totals["receipt_rows"] += receipt_count
            totals["disposition_rows"] += disposition_count
            totals["raw_quote_rows"] += quote_count
        _resolve_duplicates(connection)
        resolved = int(connection.execute("SELECT COUNT(*) FROM resolved_quotes").fetchone()[0])
        ledger = int(connection.execute("SELECT COUNT(*) FROM duplicate_resolution_ledger").fetchone()[0])
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
            "source_mode": "FROZEN_CHECKPOINT_ZERO_NETWORK",
            "issue_count": str(len(parts)),
            **{key: str(value) for key, value in totals.items()},
            "resolved_quote_rows": str(resolved),
            "duplicate_ledger_rows": str(ledger),
        }
        with connection:
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        connection.execute("PRAGMA optimize")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        connection.close()
        os.replace(temporary, target)
        return {
            "issue_count": len(parts),
            **totals,
            "resolved_quote_rows": resolved,
            "duplicate_ledger_rows": ledger,
            "sqlite_sha256": _sha256(target),
        }
    except BaseException:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise


def _insert_inventory(connection: sqlite3.Connection, inventory_path: Path) -> None:
    columns = [
        "issue_code", "match_idx", "provider_match_id", "kickoff_ts", "league",
        "home", "away", "native_handicap_line", "reconciled_source",
    ]
    inventory = pd.read_parquet(inventory_path).sort_values(["issue_code", "match_idx"], kind="stable")
    if len(inventory) != 213_263 or inventory.issue_code.astype(str).nunique() != 808:
        raise ValueError("candidate inventory is not the frozen 808-issue/213,263-fixture denominator")
    rows = _records(inventory, columns)
    with connection:
        connection.executemany(
            f"INSERT INTO inventory VALUES ({','.join('?' for _ in columns)})", rows
        )
        connection.executemany(
            """
            INSERT INTO matches (
                match_id, sheet_row, issue, match_idx, kickoff_ts, league, home, away,
                handicap_line, provider_match_id, handicap_line_norm, handicap_norm_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    number, number, str(row[0]), int(row[1]), row[3], row[4], row[5], row[6],
                    row[7], row[2], row[7], "bj268_frozen_inventory",
                )
                for number, row in enumerate(rows, start=1)
            ],
        )


def _ingest_sqlite_lane(
    connection: sqlite3.Connection,
    *,
    source_path: Path,
    lane: str,
    source_sha256: str,
) -> int:
    """Insert one historical source with SQL-only filtering to its frozen lane."""
    connection.execute("ATTACH DATABASE ? AS lane_source", (str(source_path.resolve()),))
    try:
        before = connection.total_changes
        connection.execute(
            """
            INSERT INTO raw_quote_observations (
                issue_code, match_idx, source_match_id, provider_match_id,
                snapshot_kind, bookmaker_id, v1, v2, v3,
                native_handicap_line_raw, native_handicap_line,
                handicap_norm_source, payload_sha256, quote_signature, source_lane
            )
            SELECT CAST(m.issue AS TEXT), m.match_idx,
                   ? || ':' || CAST(m.match_id AS TEXT), CAST(m.provider_match_id AS TEXT),
                   s.snapshot, CAST(s.bookmaker AS TEXT), s.v1, s.v2, s.v3,
                   CAST(m.handicap_line AS TEXT), m.handicap_line_norm,
                   COALESCE(m.handicap_norm_source, ''), ?,
                   (CASE WHEN s.v1 IS NULL THEN 'null' ELSE printf('%.17g', s.v1) END) || '|' ||
                   (CASE WHEN s.v2 IS NULL THEN 'null' ELSE printf('%.17g', s.v2) END) || '|' ||
                   (CASE WHEN s.v3 IS NULL THEN 'null' ELSE printf('%.17g', s.v3) END),
                   ?
            FROM lane_source.market_snapshots AS s
            JOIN lane_source.matches AS m ON m.match_id = s.match_id
            JOIN inventory AS i
              ON i.issue_code = CAST(m.issue AS TEXT) AND i.match_idx = m.match_idx
             AND i.reconciled_source = ?
            WHERE s.market = 'euro_1x2' AND s.snapshot IN ('initial', '10h', '1h')
            """,
            (lane, source_sha256, lane, lane),
        )
        connection.commit()
        return connection.total_changes - before
    finally:
        connection.execute("DETACH DATABASE lane_source")


def _copy_recovery_lane(connection: sqlite3.Connection, recovery_path: Path) -> dict[str, int]:
    connection.execute("ATTACH DATABASE ? AS recovered", (str(recovery_path.resolve()),))
    try:
        counts: dict[str, int] = {}
        for table in ("issue_dispositions", "acquisition_receipts", "fixture_horizon_dispositions"):
            before = connection.total_changes
            connection.execute(f"INSERT INTO {table} SELECT * FROM recovered.{table}")
            counts[table] = connection.total_changes - before
        before = connection.total_changes
        connection.execute(
            """
            INSERT INTO raw_quote_observations (
                issue_code, match_idx, source_match_id, provider_match_id,
                snapshot_kind, bookmaker_id, v1, v2, v3,
                native_handicap_line_raw, native_handicap_line,
                handicap_norm_source, payload_sha256, quote_signature, source_lane
            )
            SELECT issue_code, match_idx, source_match_id, provider_match_id,
                   snapshot_kind, bookmaker_id, v1, v2, v3,
                   native_handicap_line_raw, native_handicap_line,
                   handicap_norm_source, payload_sha256, quote_signature, source_lane
            FROM recovered.raw_quote_observations
            """
        )
        counts["raw_quote_observations"] = connection.total_changes - before
        connection.commit()
        return counts
    finally:
        connection.execute("DETACH DATABASE recovered")


def build_full_candidate_sqlite(
    *,
    inventory_path: Path,
    accepted_source: Path,
    extension_source: Path,
    recovery_source: Path,
    target: Path,
) -> dict[str, object]:
    """Build the complete 808-issue normalized candidate database atomically."""
    paths = [inventory_path, accepted_source, extension_source, recovery_source]
    for path in paths:
        if not path.resolve().is_file():
            raise FileNotFoundError(path)
    target = target.resolve()
    if target.exists():
        raise FileExistsError(target)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    source_hashes = {path.name: _sha256(path.resolve()) for path in paths}
    connection = sqlite3.connect(temporary)
    try:
        _create_schema(connection)
        _insert_inventory(connection, inventory_path)
        accepted_rows = _ingest_sqlite_lane(
            connection, source_path=accepted_source, lane="ACCEPTED_236",
            source_sha256=source_hashes[accepted_source.name],
        )
        extension_rows = _ingest_sqlite_lane(
            connection, source_path=extension_source, lane="AVAILABLE_EXTENSION",
            source_sha256=source_hashes[extension_source.name],
        )
        recovery_counts = _copy_recovery_lane(connection, recovery_source)
        _resolve_duplicates(connection)
        with connection:
            connection.execute(
                """
                INSERT INTO market_snapshots
                SELECT m.match_id, 'euro_1x2', r.bookmaker_id, r.snapshot_kind,
                       r.v1, r.v2, r.v3
                FROM resolved_quotes AS r
                JOIN matches AS m
                  ON m.issue = r.issue_code AND m.match_idx = r.match_idx
                ORDER BY m.match_id, r.snapshot_kind, r.bookmaker_id
                """
            )
            connection.execute("CREATE INDEX idx_matches_issue_idx ON matches(issue, match_idx)")
            connection.execute("CREATE INDEX idx_market_match ON market_snapshots(match_id)")
            connection.execute(
                "CREATE INDEX idx_market_lookup ON market_snapshots(market, bookmaker, snapshot)"
            )
            source_meta = {
                "source_path": "bj268_external_nowscore_titan.sqlite",
                "nowscore_update_last_run": "BJ268_ZERO_NETWORK_CHECKPOINT_REPLAY",
                "nowscore_update_issues": "808",
                "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
            }
            connection.executemany("INSERT INTO source_meta VALUES (?, ?)", sorted(source_meta.items()))
            metadata = {
                "schema_version": "BJ268_FULL_CANDIDATE_SQLITE_V1",
                "contract": "BJ-UNIFIED-EU-PROXY-BACKFILL-001",
                "known_issue_count": "808",
                "known_fixture_count": "213263",
                "input_sha256": json.dumps(source_hashes, sort_keys=True),
            }
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        counts = {
            "inventory_rows": connection.execute("SELECT COUNT(*) FROM inventory").fetchone()[0],
            "issue_count": connection.execute("SELECT COUNT(DISTINCT issue_code) FROM inventory").fetchone()[0],
            "raw_quote_rows": connection.execute("SELECT COUNT(*) FROM raw_quote_observations").fetchone()[0],
            "resolved_quote_rows": connection.execute("SELECT COUNT(*) FROM resolved_quotes").fetchone()[0],
            "duplicate_ledger_rows": connection.execute("SELECT COUNT(*) FROM duplicate_resolution_ledger").fetchone()[0],
            "market_snapshot_rows": connection.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0],
        }
        if counts["inventory_rows"] != 213_263 or counts["issue_count"] != 808:
            raise RuntimeError(f"full candidate denominator mismatch: {counts}")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("full candidate SQLite integrity check failed")
        connection.execute("PRAGMA optimize")
        connection.close()
        if {path.name: _sha256(path.resolve()) for path in paths} != source_hashes:
            raise RuntimeError("a consumed input changed during full candidate construction")
        os.replace(temporary, target)
        return {
            **counts,
            "lane_raw_rows": {
                "ACCEPTED_236": accepted_rows,
                "AVAILABLE_EXTENSION": extension_rows,
                "NOWSCORE_ISSUE_PAGE": recovery_counts["raw_quote_observations"],
            },
            "input_sha256": source_hashes,
            "sqlite_sha256": _sha256(target),
        }
    except BaseException:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise
