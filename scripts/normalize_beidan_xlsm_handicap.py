#!/usr/bin/env python3
"""Normalize vendor XLSM handicap codes in the converted SQLite database.

The vendor workbook stores normal Beidan handicap lines as small signed values
(-3, -2, -1, 1, 2, ...), but no-handicap rows often appear as large positive
codes such as 96, 99, 105, 133. Cross-checking against the local historical
settlement database shows those large positive codes map to handicap 0.

This script preserves the raw `matches.handicap_line` value and writes:
  - matches.handicap_line_norm
  - matches.handicap_norm_source
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def ensure_columns(conn: sqlite3.Connection) -> None:
    if not column_exists(conn, "matches", "handicap_line_norm"):
        conn.execute("ALTER TABLE matches ADD COLUMN handicap_line_norm REAL")
    if not column_exists(conn, "matches", "handicap_norm_source"):
        conn.execute("ALTER TABLE matches ADD COLUMN handicap_norm_source TEXT")


def normalize(sqlite_path: Path, history_db: Path | None) -> None:
    conn = sqlite3.connect(sqlite_path)
    ensure_columns(conn)
    conn.execute("BEGIN")

    # Large positive vendor codes have been verified against local history as
    # no-handicap / draw-no-adjustment rows.
    conn.execute(
        """
        UPDATE matches
        SET handicap_line_norm = 0,
            handicap_norm_source = 'vendor_large_code_to_zero'
        WHERE handicap_line > 20
        """
    )

    # Preserve genuine small signed handicap lines. The source contains a few
    # half/quarter values; keep them rather than forcing integer Beidan lines.
    conn.execute(
        """
        UPDATE matches
        SET handicap_line_norm = handicap_line,
            handicap_norm_source = 'vendor_small_line'
        WHERE handicap_line IS NOT NULL
          AND handicap_line <= 20
          AND handicap_line >= -20
        """
    )

    conn.execute(
        """
        UPDATE matches
        SET handicap_line_norm = NULL,
            handicap_norm_source = 'missing_raw'
        WHERE handicap_line IS NULL
        """
    )

    if history_db is not None:
        conn.execute(f"ATTACH DATABASE '{history_db}' AS hist")
        conn.execute(
            """
            UPDATE matches
            SET handicap_line_norm = (
                    SELECT h.handicap_line
                    FROM hist.historical_matches h
                    WHERE h.issue = matches.issue
                      AND h.match_idx = matches.match_idx
                    LIMIT 1
                ),
                handicap_norm_source = 'history_join_missing_raw'
            WHERE handicap_line IS NULL
              AND EXISTS (
                    SELECT 1
                    FROM hist.historical_matches h
                    WHERE h.issue = matches.issue
                      AND h.match_idx = matches.match_idx
                      AND h.handicap_line IS NOT NULL
                )
            """
        )

    conn.execute("COMMIT")
    if history_db is not None:
        conn.execute("DETACH DATABASE hist")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_matches_handicap_norm ON matches(handicap_line_norm)")
    conn.commit()
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--history-db", type=Path)
    args = parser.parse_args()
    normalize(args.sqlite, args.history_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
