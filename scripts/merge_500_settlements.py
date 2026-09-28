#!/usr/bin/env python3
"""Merge SPF + four play types into one wide table (one row per fixture).

state is per-match (all plays share the same state), so one column suffices.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    db = args.data_root / "control" / "settlement_500" / "settlement.sqlite"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")

    if args.replace:
        con.execute("DROP TABLE IF EXISTS settlement_merged")
    con.execute("""
        CREATE TABLE IF NOT EXISTS settlement_merged (
            issue_code TEXT NOT NULL,
            issue_slot INTEGER NOT NULL,
            local_500_fid INTEGER NOT NULL,
            handicap_line INTEGER,
            home_score INTEGER,
            away_score INTEGER,
            settlement_state TEXT NOT NULL DEFAULT 'settled',
            -- SPF 让球胜平负
            result_code_spf TEXT CHECK(result_code_spf IS NULL OR result_code_spf IN ('3', '1', '0')),
            winning_option_spf TEXT,
            winning_sp_spf REAL,
            -- 总进球
            winning_option_jq TEXT,
            winning_sp_jq REAL,
            -- 上下单双
            winning_option_ds TEXT,
            winning_sp_ds REAL,
            -- 半全场
            winning_option_bq TEXT,
            winning_sp_bq REAL,
            -- 比分
            winning_option_bf TEXT,
            winning_sp_bf REAL,
            PRIMARY KEY(issue_code, issue_slot)
        )
    """)

    spf = con.execute("""
        SELECT issue_code, issue_slot, local_500_fid, handicap_line,
               home_score, away_score, result_code, winning_sp, settlement_state
        FROM raw_settlement_row
    """).fetchall()
    print(f"SPF rows: {len(spf)}")

    plays = con.execute("""
        SELECT issue_code, issue_slot, play_type, winning_option, winning_sp
        FROM raw_settlement_play_row
    """).fetchall()
    play_map: dict[tuple[str, int], dict] = {}
    for issue, slot, pt, opt, sp in plays:
        play_map.setdefault((issue, slot), {})[pt] = (opt, sp)

    merged = []
    for issue, slot, fid, handicap, hs, as_, rc, sp, state in spf:
        d = play_map.get((issue, slot), {})
        win_opt_spf = {"3": "胜", "1": "平", "0": "负"}.get(rc)
        merged.append((
            issue, slot, fid, handicap, hs, as_, state,
            rc, win_opt_spf, sp,
            d.get("jq", (None, None))[0], d.get("jq", (None, None))[1],
            d.get("ds", (None, None))[0], d.get("ds", (None, None))[1],
            d.get("bq", (None, None))[0], d.get("bq", (None, None))[1],
            d.get("bf", (None, None))[0], d.get("bf", (None, None))[1],
        ))

    con.executemany("""
        INSERT OR REPLACE INTO settlement_merged
        (issue_code, issue_slot, local_500_fid, handicap_line, home_score, away_score,
         settlement_state,
         result_code_spf, winning_option_spf, winning_sp_spf,
         winning_option_jq, winning_sp_jq,
         winning_option_ds, winning_sp_ds,
         winning_option_bq, winning_sp_bq,
         winning_option_bf, winning_sp_bf)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, merged)
    con.commit()

    total = con.execute("SELECT COUNT(*) FROM settlement_merged").fetchone()[0]
    settled = con.execute("SELECT COUNT(*) FROM settlement_merged WHERE settlement_state='settled'").fetchone()[0]
    print(f"Merged table: {total} rows, {settled} settled")
    con.close()


if __name__ == "__main__":
    main()
