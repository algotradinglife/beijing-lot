#!/usr/bin/env python3
"""Import full Beidan 3SP settlements into the converted XLSM SQLite DB."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def parse_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def parse_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def parse_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def result_code(value: object) -> str | None:
    parsed = parse_int(value)
    if parsed is None:
        return None
    text = str(parsed)
    return text if text in {"3", "1", "0"} else None


def import_csv(sqlite_path: Path, csv_path: Path, *, replace: bool) -> None:
    conn = sqlite3.connect(sqlite_path)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    if replace:
        conn.execute("DROP TABLE IF EXISTS official_3sp_settlements")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_3sp_settlements (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            kickoff_ts TEXT,
            league TEXT,
            home_rank TEXT,
            home TEXT,
            away_rank TEXT,
            away TEXT,
            handicap_line REAL,
            fthg INTEGER,
            ftag INTEGER,
            hthg INTEGER,
            htag INTEGER,
            match_uid TEXT,
            result_code TEXT,
            winning_sp REAL,
            sp_3 REAL,
            sp_1 REAL,
            sp_0 REAL,
            last_update_ts TEXT,
            source_file TEXT,
            source_row INTEGER,
            imported_at TEXT,
            PRIMARY KEY (issue, match_idx)
        )
        """
    )

    imported_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows: list[tuple[object, ...]] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for source_row, row in enumerate(reader, start=2):
            issue = parse_int(row.get("expect"))
            match_idx = parse_int(row.get("match_no"))
            if issue is None or match_idx is None:
                continue
            rows.append(
                (
                    str(issue),
                    match_idx,
                    parse_text(row.get("kickoff_ts")),
                    parse_text(row.get("league")),
                    parse_text(row.get("home_rank")),
                    parse_text(row.get("home")),
                    parse_text(row.get("away_rank")),
                    parse_text(row.get("away")),
                    parse_float(row.get("handicap")),
                    parse_int(row.get("fthg")),
                    parse_int(row.get("ftag")),
                    parse_int(row.get("hthg")),
                    parse_int(row.get("htag")),
                    parse_text(row.get("match_uid")),
                    result_code(row.get("result_code")),
                    parse_float(row.get("winning_sp")),
                    parse_float(row.get("sp_3")),
                    parse_float(row.get("sp_1")),
                    parse_float(row.get("sp_0")),
                    parse_text(row.get("last_update_ts")),
                    str(csv_path),
                    source_row,
                    imported_at,
                )
            )

    conn.executemany(
        """
        INSERT OR REPLACE INTO official_3sp_settlements (
            issue, match_idx, kickoff_ts, league, home_rank, home, away_rank, away,
            handicap_line, fthg, ftag, hthg, htag, match_uid, result_code,
            winning_sp, sp_3, sp_1, sp_0, last_update_ts, source_file,
            source_row, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_official_3sp_issue_idx
            ON official_3sp_settlements(issue, match_idx);
        CREATE INDEX IF NOT EXISTS idx_official_3sp_result
            ON official_3sp_settlements(result_code);
        CREATE INDEX IF NOT EXISTS idx_official_3sp_winning_sp
            ON official_3sp_settlements(winning_sp);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_3sp_settlements_source", str(csv_path)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_3sp_settlements_imported_at", imported_at),
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_3sp_settlements_rows", str(len(rows))),
    )
    conn.commit()

    joined = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_3sp_settlements s
        JOIN matches m
          ON m.issue = s.issue
         AND m.match_idx = s.match_idx
        """
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM official_3sp_settlements").fetchone()[0]
    with_sp = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_3sp_settlements
        WHERE winning_sp IS NOT NULL AND winning_sp > 0
        """
    ).fetchone()[0]
    print(f"Imported rows: {len(rows)}")
    print(f"Table rows: {total}")
    print(f"Rows with winning_sp: {with_sp}")
    print(f"Rows directly joinable to matches: {joined}")
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not args.sqlite.exists():
        raise SystemExit(f"SQLite not found: {args.sqlite}")
    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")
    import_csv(args.sqlite, args.csv, replace=args.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
