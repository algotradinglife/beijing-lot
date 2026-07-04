#!/usr/bin/env python3
"""Backfill Asian handicap / over-under snapshots for an existing Nowscore DB.

`update_beidan_nowscore_sqlite.py --skip-existing` skips matches that already
exist, so it cannot be used to add line markets to an already populated DB.
This script reads existing `matches` rows and inserts only line-market rows into
`market_snapshots`.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_beidan_nowscore_sqlite import (  # noqa: E402
    BOOKS_ASIAN,
    SNAPSHOTS,
    fetch_line_market,
    parse_dt,
    parse_issues,
    session,
)


def parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        is not None
    )


def selected_books(raw: str) -> list[tuple[str, int]]:
    if raw.strip().lower() in {"", "all", "*"}:
        return BOOKS_ASIAN
    wanted = set(parse_csv(raw))
    out = [(name, company_id) for name, company_id in BOOKS_ASIAN if name in wanted or str(company_id) in wanted]
    missing = sorted(wanted - {name for name, _ in out} - {str(company_id) for _, company_id in out})
    if missing:
        raise SystemExit(f"unknown bookmakers/company ids: {','.join(missing)}")
    return out


def selected_markets(raw: str) -> list[tuple[str, int]]:
    mapping = {"asian_handicap": 0, "over_under": 1}
    markets = parse_csv(raw)
    bad = [market for market in markets if market not in mapping]
    if bad:
        raise SystemExit(f"unknown markets: {','.join(bad)}")
    return [(market, mapping[market]) for market in markets]


def issue_clause(issues: Iterable[str]) -> tuple[str, list[object]]:
    vals = list(issues)
    if not vals:
        return "", []
    placeholders = ",".join("?" for _ in vals)
    return f" AND issue IN ({placeholders})", vals


def load_matches(
    conn: sqlite3.Connection,
    *,
    issues: list[str],
    min_match_id: int | None,
    max_match_id: int | None,
    limit: int | None,
) -> list[sqlite3.Row]:
    clause, params = issue_clause(issues)
    extra = ""
    if min_match_id is not None:
        extra += " AND match_id >= ?"
        params.append(min_match_id)
    if max_match_id is not None:
        extra += " AND match_id <= ?"
        params.append(max_match_id)
    sql = f"""
        SELECT match_id, issue, match_idx, provider_match_id, kickoff_ts, home, away
        FROM matches
        WHERE provider_match_id IS NOT NULL
          AND kickoff_ts IS NOT NULL
          {clause}
          {extra}
        ORDER BY match_id
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params))


def existing_count(conn: sqlite3.Connection, match_id: int, markets: list[tuple[str, int]]) -> int:
    names = [market for market, _ in markets]
    placeholders = ",".join("?" for _ in names)
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM market_snapshots WHERE match_id=? AND market IN ({placeholders})",
            [match_id, *names],
        ).fetchone()[0]
    )


def delete_lines(conn: sqlite3.Connection, match_id: int, markets: list[tuple[str, int]]) -> None:
    names = [market for market, _ in markets]
    placeholders = ",".join("?" for _ in names)
    conn.execute(
        f"DELETE FROM market_snapshots WHERE match_id=? AND market IN ({placeholders})",
        [match_id, *names],
    )


def source_meta_upsert(conn: sqlite3.Connection, key: str, value: str) -> None:
    if not table_exists(conn, "source_meta"):
        conn.execute("CREATE TABLE source_meta(key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)", (key, value))


def backfill(args: argparse.Namespace) -> dict[str, object]:
    markets = selected_markets(args.markets)
    books = selected_books(args.bookmakers)
    expected_per_match = len(markets) * len(books) * len(SNAPSHOTS)
    issues = parse_issues(args.issues or [])

    conn = sqlite3.connect(args.sqlite)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    rows = load_matches(
        conn,
        issues=issues,
        min_match_id=args.min_match_id,
        max_match_id=args.max_match_id,
        limit=args.max_matches,
    )
    s = session()
    started = time.time()
    attempted = 0
    skipped = 0
    inserted_rows = 0
    errors = 0

    for idx, row in enumerate(rows, start=1):
        match_id = int(row["match_id"])
        if not args.replace_lines and existing_count(conn, match_id, markets) >= expected_per_match:
            skipped += 1
            continue
        if args.replace_lines:
            delete_lines(conn, match_id, markets)

        kickoff = parse_dt(str(row["kickoff_ts"]))
        if kickoff is None:
            errors += 1
            continue
        attempted += 1
        batch: list[tuple[object, ...]] = []
        for market, oddskind in markets:
            for bookmaker, company_id in books:
                try:
                    line_rows = fetch_line_market(
                        s,
                        provider_match_id=str(row["provider_match_id"]),
                        kickoff=kickoff,
                        market=market,
                        oddskind=oddskind,
                        bookmaker=bookmaker,
                        company_id=company_id,
                        delay=args.line_delay,
                    )
                except Exception as exc:  # noqa: BLE001 - keep resumable.
                    errors += 1
                    print(
                        f"[warn] match_id={match_id} issue={row['issue']} "
                        f"match_idx={row['match_idx']} {market}/{bookmaker} failed: {exc}",
                        file=sys.stderr,
                    )
                    line_rows = [(None, market, bookmaker, snapshot, None, None, None) for snapshot in SNAPSHOTS]
                for _, market2, bookmaker2, snapshot, v1, v2, v3 in line_rows:
                    batch.append((match_id, market2, bookmaker2, snapshot, v1, v2, v3))

        conn.executemany(
            "INSERT INTO market_snapshots(match_id, market, bookmaker, snapshot, v1, v2, v3) VALUES (?,?,?,?,?,?,?)",
            batch,
        )
        inserted_rows += len(batch)
        if args.match_delay > 0:
            time.sleep(args.match_delay)
        if args.commit_every > 0 and attempted % args.commit_every == 0:
            conn.commit()
        if args.progress_every > 0 and (attempted % args.progress_every == 0 or idx == len(rows)):
            elapsed = time.time() - started
            print(
                f"[progress] attempted={attempted} skipped={skipped} rows={inserted_rows} "
                f"errors={errors} last_match_id={match_id} elapsed={elapsed:.1f}s",
                flush=True,
            )

    source_meta_upsert(conn, "nowscore_line_backfill_last_run", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    source_meta_upsert(conn, "nowscore_line_backfill_markets", ",".join(market for market, _ in markets))
    source_meta_upsert(conn, "nowscore_line_backfill_bookmakers", ",".join(name for name, _ in books))
    conn.commit()
    conn.close()
    return {
        "matches_selected": len(rows),
        "matches_attempted": attempted,
        "matches_skipped_complete": skipped,
        "inserted_market_rows": inserted_rows,
        "line_errors": errors,
        "expected_rows_per_match": expected_per_match,
        "elapsed_sec": round(time.time() - started, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--issues", nargs="*", help="Issue ids or ranges, e.g. 26011-26051.")
    parser.add_argument("--markets", default="asian_handicap,over_under")
    parser.add_argument("--bookmakers", default="all", help="Comma-separated bookmaker names/company ids, or all.")
    parser.add_argument("--replace-lines", action="store_true", help="Delete selected line markets before refetching.")
    parser.add_argument("--line-delay", type=float, default=0.05)
    parser.add_argument("--match-delay", type=float, default=0.0)
    parser.add_argument("--commit-every", type=int, default=20)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--max-matches", type=int)
    parser.add_argument("--min-match-id", type=int)
    parser.add_argument("--max-match-id", type=int)
    args = parser.parse_args()
    print(json.dumps(backfill(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
