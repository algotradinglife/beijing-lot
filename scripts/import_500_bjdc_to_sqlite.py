#!/usr/bin/env python3
"""Import scraped 500.com BJDC settlements into the converted XLSM SQLite DB."""
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


SCORE_RE = re.compile(r"^\s*(\d+)\s*[:：]\s*(\d+)")


def parse_score(score: object, side: int) -> int | None:
    if score is None:
        return None
    match = SCORE_RE.match(str(score))
    if not match:
        return None
    return int(match.group(side))


def import_500(sqlite_path: Path, source_db: Path, *, replace: bool) -> None:
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
    conn.execute(f"ATTACH DATABASE '{source_db}' AS src500")

    if replace:
        conn.execute("DROP TABLE IF EXISTS official_500_settlements")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS official_500_settlements (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            fid INTEGER,
            league TEXT,
            home TEXT,
            away TEXT,
            end_time TEXT,
            schedule_date TEXT,
            handicap_line REAL,
            score TEXT,
            fthg INTEGER,
            ftag INTEGER,
            result_label TEXT,
            result_code TEXT,
            winning_sp REAL,
            sp_home REAL,
            sp_draw REAL,
            sp_away REAL,
            avg_odds_home REAL,
            avg_odds_draw REAL,
            avg_odds_away REAL,
            asian_handicap TEXT,
            raw_row_hash TEXT,
            fetched_at TEXT,
            source_db TEXT,
            imported_at TEXT,
            PRIMARY KEY (issue, match_idx)
        )
        """
    )

    imported_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    source_rows = conn.execute(
        """
        SELECT
            issue, match_idx, fid, league, home, away, end_time, schedule_date,
            handicap_line, score, result_label, result_code, winning_sp,
            sp_home, sp_draw, sp_away,
            avg_odds_home, avg_odds_draw, avg_odds_away,
            asian_handicap, raw_row_hash, fetched_at
        FROM src500.matches
        WHERE match_idx IS NOT NULL
        """
    ).fetchall()
    rows = [
        (
            *row[:10],
            parse_score(row[9], 1),
            parse_score(row[9], 2),
            *row[10:],
            str(source_db),
            imported_at,
        )
        for row in source_rows
    ]
    conn.executemany(
        """
        INSERT OR REPLACE INTO official_500_settlements (
            issue, match_idx, fid, league, home, away, end_time, schedule_date,
            handicap_line, score, fthg, ftag, result_label, result_code,
            winning_sp, sp_home, sp_draw, sp_away,
            avg_odds_home, avg_odds_draw, avg_odds_away,
            asian_handicap, raw_row_hash, fetched_at, source_db, imported_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_official_500_issue_idx
            ON official_500_settlements(issue, match_idx);
        CREATE INDEX IF NOT EXISTS idx_official_500_result
            ON official_500_settlements(result_code);
        CREATE INDEX IF NOT EXISTS idx_official_500_winning_sp
            ON official_500_settlements(winning_sp);
        CREATE INDEX IF NOT EXISTS idx_official_500_fid
            ON official_500_settlements(fid);
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_500_settlements_source", str(source_db)),
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_500_settlements_imported_at", imported_at),
    )
    conn.execute(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        ("official_500_settlements_rows", str(len(rows))),
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM official_500_settlements").fetchone()[0]
    with_sp = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_500_settlements
        WHERE winning_sp IS NOT NULL AND winning_sp > 0
        """
    ).fetchone()[0]
    joined = conn.execute(
        """
        SELECT COUNT(*)
        FROM official_500_settlements f
        JOIN matches m
          ON m.issue = f.issue
         AND m.match_idx = f.match_idx
        """
    ).fetchone()[0]
    has_3sp = (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='official_3sp_settlements'"
        ).fetchone()
        is not None
    )
    if has_3sp:
        supplemental = conn.execute(
            """
            SELECT COUNT(*)
            FROM official_500_settlements f
            JOIN matches m
              ON m.issue = f.issue
             AND m.match_idx = f.match_idx
            LEFT JOIN official_3sp_settlements s
              ON s.issue = f.issue
             AND s.match_idx = f.match_idx
             AND s.winning_sp IS NOT NULL
             AND s.winning_sp > 0
            WHERE f.winning_sp IS NOT NULL
              AND f.winning_sp > 0
              AND s.issue IS NULL
            """
        ).fetchone()[0]
    else:
        supplemental = None
    print(f"Imported rows: {len(rows)}")
    print(f"Table rows: {total}")
    print(f"Rows with winning_sp: {with_sp}")
    print(f"Rows directly joinable to matches: {joined}")
    if supplemental is not None:
        print(f"Joinable winning_sp rows not covered by 3SP CSV: {supplemental}")

    conn.execute("DETACH DATABASE src500")
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--source-db", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if not args.sqlite.exists():
        raise SystemExit(f"SQLite not found: {args.sqlite}")
    if not args.source_db.exists():
        raise SystemExit(f"500 source DB not found: {args.source_db}")
    import_500(args.sqlite, args.source_db, replace=args.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
