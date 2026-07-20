#!/usr/bin/env python3
"""Monitor 500.com BJDC issue changes and keep recent results updated.

This is a thin operational wrapper around ``scripts/scrape_500_bjdc.py``.  Each
cycle refreshes the 500.com issue list, scrapes the current/recent issues, and
continues refreshing local issues that still have unsettled matches.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scrape_500_bjdc import (  # noqa: E402
    DEFAULT_DB,
    DEFAULT_UA,
    create_schema,
    fetch_issue_list,
    issue_year,
    parse_playids,
    scrape_issue,
    scrape_live_sp,
)
from scrape_nowscore_bjdc import (  # noqa: E402
    create_schema as create_nowscore_schema,
    scrape_issue as scrape_nowscore_issue,
)
from scrape_nowscore_match_details import (  # noqa: E402
    create_schema as create_nowscore_detail_schema,
    scrape_issue as scrape_nowscore_detail_issue,
)
from src.sqlite_runtime import connect_sqlite  # noqa: E402


def _now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _current_issue(rows: list[dict[str, object]]) -> str:
    for row in rows:
        if int(row.get("is_current") or 0):
            return str(row["issue"])
    return str(rows[0]["issue"]) if rows else ""


def _open_local_issues(conn: sqlite3.Connection, *, min_year: int | None, limit: int) -> list[str]:
    where = ""
    params: list[object] = []
    if min_year is not None:
        where = "WHERE CAST(substr(issue, 1, 2) AS INTEGER) + 2000 >= ?"
        params.append(min_year)
    rows = conn.execute(
        f"""
        SELECT
          issue,
          COUNT(*) AS n_matches,
          SUM(CASE WHEN winning_sp IS NOT NULL THEN 1 ELSE 0 END) AS n_settled,
          MAX(fetched_at) AS fetched_at
        FROM matches
        {where}
        GROUP BY issue
        HAVING n_matches > n_settled
        ORDER BY MAX(end_time) DESC, CAST(issue AS INTEGER) DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [str(row["issue"]) for row in rows]


def _selected_issues(conn: sqlite3.Connection, rows: list[dict[str, object]], args: argparse.Namespace) -> list[str]:
    recent = [str(row["issue"]) for row in rows[: args.recent_count]]
    current = _current_issue(rows)
    current_year = issue_year(current) if current else None
    min_year = None if current_year is None else max(2000, current_year - args.open_year_lookback)
    open_issues = _open_local_issues(conn, min_year=min_year, limit=args.open_limit)
    selected: list[str] = []
    for issue in [current, *recent, *open_issues]:
        if issue and issue not in selected:
            selected.append(issue)
    return selected


def _scrape_namespace(args: argparse.Namespace, playid: int) -> SimpleNamespace:
    return SimpleNamespace(
        timeout=args.timeout,
        user_agent=args.user_agent,
        force=True,
        keep_going=True,
        live_sp=args.live_sp,
        playid=playid,
        sleep=0,
    )


def _nowscore_detail_namespace(args: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        issue=None,
        match_idx=None,
        provider_match_id=None,
        limit=args.nowscore_detail_limit,
        stale_hours=args.nowscore_detail_stale_hours,
        force=False,
        sleep=max(args.sleep, 0.0),
        timeout=args.timeout,
        user_agent=args.user_agent,
    )


def run_once(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    rows = fetch_issue_list(conn, args)
    current = _current_issue(rows)
    previous = conn.execute(
        "SELECT value FROM source_meta WHERE key='last_monitor_current_issue'"
    ).fetchone()
    previous_issue = str(previous["value"]) if previous else ""
    if current and current != previous_issue:
        print(f"[{_now_text()}] [issue_change] {previous_issue or '-'} -> {current}", flush=True)
        conn.execute(
            "INSERT OR REPLACE INTO source_meta(key, value) VALUES('last_monitor_current_issue', ?)",
            (current,),
        )
        conn.commit()

    selected = _selected_issues(conn, rows, args)
    print(f"[{_now_text()}] [monitor] current={current} selected={','.join(selected)}", flush=True)
    playids = parse_playids(args.playid)
    scrape_args = _scrape_namespace(args, playids[0])
    total_rows = 0
    for issue in selected:
        total_rows += scrape_issue(conn, issue, scrape_args)
        if args.live_sp:
            for playid in playids:
                if playid != 34 and issue != current:
                    continue
                scrape_live_sp(conn, issue, _scrape_namespace(args, playid))
        if args.nowscore:
            scrape_nowscore_issue(conn, issue, scrape_args)
        if args.sleep:
            time.sleep(args.sleep)
    if args.nowscore_details and current:
        scrape_nowscore_detail_issue(conn, current, _nowscore_detail_namespace(args))
    return total_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--interval", type=float, default=300.0, help="Seconds between cycles.")
    parser.add_argument("--once", action="store_true", help="Run one monitor cycle and exit.")
    parser.add_argument("--recent-count", type=int, default=6, help="How many newest 500 issue-list rows to refresh.")
    parser.add_argument("--open-limit", type=int, default=20, help="Max unsettled local issues to keep refreshing.")
    parser.add_argument("--open-year-lookback", type=int, default=1, help="Only monitor unsettled local issues from current year minus this value.")
    parser.add_argument("--live-sp", action="store_true", default=True)
    parser.add_argument("--no-live-sp", action="store_false", dest="live_sp")
    parser.add_argument("--nowscore", action="store_true", default=True, help="Refresh Jiebao/Nowscore scores and half-time scores.")
    parser.add_argument("--no-nowscore", action="store_false", dest="nowscore")
    parser.add_argument("--nowscore-details", action="store_true", default=True, help="Refresh current-issue Jiebao/Nowscore match analysis details.")
    parser.add_argument("--no-nowscore-details", action="store_false", dest="nowscore_details")
    parser.add_argument("--nowscore-detail-limit", type=int, default=24)
    parser.add_argument("--nowscore-detail-stale-hours", type=float, default=6.0)
    parser.add_argument(
        "--playid",
        action="append",
        help="BJDC play id or comma-separated ids; repeatable. Default: 34,40,41,42,51.",
    )
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_sqlite(args.db, row_factory=True)
    create_schema(conn)
    create_nowscore_schema(conn)
    create_nowscore_detail_schema(conn)

    while True:
        try:
            run_once(conn, args)
        except Exception as exc:
            print(f"[{_now_text()}] [monitor_error] {exc}", flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
