#!/usr/bin/env python3
"""Scrape 500.com Beijing single-game football pages into SQLite.

The trade page exposes two useful data surfaces:

* Historical HTML pages, keyed by `expect`, with score, winning option, winning
  SP, handicap, teams, league, and average 1x2 odds.
* A current-period XML endpoint for live visible SP snapshots.

The script uses only stdlib modules because the project environment is kept
lean. It is intentionally conservative about request rate and stores raw row
fragments enough to audit parser drift.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sqlite_runtime import connect_sqlite  # noqa: E402
from src.adhoc_input_freshness import explicit_utc  # noqa: E402
from beidan_backend.transport import fetch_issue_page  # noqa: E402
from beidan_backend.sources.five_hundred_betting import (  # noqa: E402
    decode_html,
    issue_year,
    parse_issue_options,
    parse_issue_rows,
    parse_live_market_sp,
    parse_live_sp,
    parse_playids,
)
from src.multimarket_p0 import (  # noqa: E402
    DEFAULT_CAPTURE_ROOT,
    TARGET_PLAYIDS as P0_TARGET_PLAYIDS,
    ensure_schema as ensure_multimarket_p0_schema,
    publish_capture_batch,
)

DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
TRADE_URL = "https://trade.500.com/bjdc/index.php"
LIVE_SP_URL = "https://www.500.com/static/public/bjdc/xml/sp/just_{issue}_{playid}.xml"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)




@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    body: bytes
    elapsed_sec: float


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")










def fetch_url(url: str, *, timeout: float, user_agent: str, referer: str | None = None) -> FetchResult:
    """Fetch one page through the package transport (bounded retries + timeout)."""
    response = fetch_issue_page(url, timeout=timeout, user_agent=user_agent, referer=referer)
    return FetchResult(
        url=response.url,
        status=response.status,
        body=response.body,
        elapsed_sec=response.elapsed_sec,
    )














def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS source_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS fetch_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetched_at TEXT NOT NULL,
            kind TEXT NOT NULL,
            issue TEXT,
            url TEXT NOT NULL,
            status INTEGER,
            ok INTEGER NOT NULL,
            elapsed_sec REAL,
            bytes INTEGER,
            rows_parsed INTEGER,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS issues (
            issue TEXT PRIMARY KEY,
            ordinal INTEGER,
            label TEXT,
            is_selected INTEGER,
            is_current INTEGER,
            year INTEGER,
            first_seen_at TEXT,
            last_seen_at TEXT
        );

        CREATE TABLE IF NOT EXISTS matches (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            fid INTEGER,
            league TEXT,
            home TEXT,
            away TEXT,
            end_time TEXT,
            schedule_date TEXT,
            handicap_line REAL,
            disabled TEXT,
            home_rank INTEGER,
            away_rank INTEGER,
            bg_color TEXT,
            score TEXT,
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
            raw_value TEXT,
            raw_row_hash TEXT,
            fetched_at TEXT,
            PRIMARY KEY (issue, match_idx)
        );

        CREATE TABLE IF NOT EXISTS live_sp_snapshots (
            issue TEXT NOT NULL,
            playid INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            source_updatetime TEXT,
            row_idx INTEGER NOT NULL,
            home TEXT,
            away TEXT,
            league TEXT,
            handicap_line REAL,
            sp_home REAL,
            sp_draw REAL,
            sp_away REAL,
            raw_node TEXT,
            PRIMARY KEY (issue, playid, fetched_at, row_idx)
        );

        CREATE INDEX IF NOT EXISTS idx_issues_year ON issues(year);
        CREATE INDEX IF NOT EXISTS idx_matches_fid ON matches(fid);
        CREATE INDEX IF NOT EXISTS idx_matches_issue ON matches(issue);
        CREATE INDEX IF NOT EXISTS idx_matches_has_sp ON matches(issue, winning_sp);
        CREATE INDEX IF NOT EXISTS idx_live_sp_issue ON live_sp_snapshots(issue, playid, fetched_at);

        CREATE TABLE IF NOT EXISTS live_market_sp_snapshots (
            issue TEXT NOT NULL,
            playid INTEGER NOT NULL,
            market_key TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            source_updatetime TEXT,
            row_idx INTEGER NOT NULL,
            home TEXT,
            away TEXT,
            league TEXT,
            outcome_code TEXT NOT NULL,
            outcome_label TEXT NOT NULL,
            sp REAL,
            source_attribute TEXT NOT NULL,
            raw_node TEXT,
            PRIMARY KEY (issue, playid, fetched_at, row_idx, outcome_code)
        );
        CREATE INDEX IF NOT EXISTS idx_live_market_sp_issue
            ON live_market_sp_snapshots(issue, playid, fetched_at, row_idx);

        CREATE TABLE IF NOT EXISTS match_details_500 (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            fid INTEGER NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT,
            description TEXT,
            data_url TEXT,
            recommendation_url TEXT,
            asian_url TEXT,
            europe_url TEXT,
            home_recent_summary TEXT,
            away_recent_summary TEXT,
            h2h_summary TEXT,
            league_table_summary TEXT,
            payload_json TEXT,
            raw_sha1 TEXT,
            error TEXT,
            PRIMARY KEY(issue, match_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_match_details_500_fid ON match_details_500(fid);
        """
    )
    ensure_multimarket_p0_schema(conn)


def upsert_issues(conn: sqlite3.Connection, rows: list[dict[str, object]], fetched_at: str) -> None:
    conn.executemany(
        """
        INSERT INTO issues(issue, ordinal, label, is_selected, is_current, year, first_seen_at, last_seen_at)
        VALUES(:issue, :ordinal, :label, :is_selected, :is_current, :year, :fetched_at, :fetched_at)
        ON CONFLICT(issue) DO UPDATE SET
            ordinal=excluded.ordinal,
            label=excluded.label,
            is_selected=excluded.is_selected,
            is_current=excluded.is_current,
            year=excluded.year,
            last_seen_at=excluded.last_seen_at
        """,
        [{**row, "fetched_at": fetched_at} for row in rows],
    )


def upsert_matches(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    cols = list(rows[0])
    placeholders = ",".join(":" + c for c in cols)
    preserve_text = {
        "league",
        "home",
        "away",
        "end_time",
        "schedule_date",
        "disabled",
        "bg_color",
        "score",
        "result_label",
        "result_code",
        "asian_handicap",
    }
    preserve_numeric = {
        "fid",
        "handicap_line",
        "home_rank",
        "away_rank",
        "winning_sp",
        "sp_home",
        "sp_draw",
        "sp_away",
        "avg_odds_home",
        "avg_odds_draw",
        "avg_odds_away",
    }
    update_exprs: list[str] = []
    for col in cols:
        if col in {"issue", "match_idx"}:
            continue
        if col in preserve_text:
            update_exprs.append(f"{col}=COALESCE(NULLIF(excluded.{col}, ''), {col})")
        elif col in preserve_numeric:
            update_exprs.append(f"{col}=COALESCE(excluded.{col}, {col})")
        else:
            update_exprs.append(f"{col}=excluded.{col}")
    updates = ",".join(update_exprs)
    conn.executemany(
        f"""
        INSERT INTO matches({",".join(cols)})
        VALUES({placeholders})
        ON CONFLICT(issue, match_idx) DO UPDATE SET {updates}
        """,
        rows,
    )


def insert_fetch_log(
    conn: sqlite3.Connection,
    *,
    kind: str,
    issue: str | None,
    url: str,
    status: int | None,
    ok: bool,
    elapsed_sec: float | None,
    bytes_len: int | None,
    rows_parsed: int | None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO fetch_log(fetched_at, kind, issue, url, status, ok, elapsed_sec, bytes, rows_parsed, error)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        """,
        (now_utc(), kind, issue, url, status, int(ok), elapsed_sec, bytes_len, rows_parsed, error),
    )


def fetch_issue_list(conn: sqlite3.Connection, args: argparse.Namespace) -> list[dict[str, object]]:
    fetched_at = now_utc()
    result = fetch_url(TRADE_URL, timeout=args.timeout, user_agent=args.user_agent)
    text = decode_html(result.body)
    issues = parse_issue_options(text)
    upsert_issues(conn, issues, fetched_at)
    conn.execute("INSERT OR REPLACE INTO source_meta(key, value) VALUES('last_issue_list_fetch_at', ?)", (fetched_at,))
    insert_fetch_log(
        conn,
        kind="issue_list",
        issue=None,
        url=result.url,
        status=result.status,
        ok=True,
        elapsed_sec=result.elapsed_sec,
        bytes_len=len(result.body),
        rows_parsed=len(issues),
    )
    conn.commit()
    return issues


def select_issues(all_issues: list[dict[str, object]], args: argparse.Namespace) -> list[str]:
    if args.issue:
        selected = []
        seen = set()
        for raw in args.issue:
            for issue in re.split(r"[,，]\s*", raw):
                issue = issue.strip()
                if issue and issue not in seen:
                    selected.append(issue)
                    seen.add(issue)
    elif args.all:
        selected = [str(row["issue"]) for row in all_issues]
    else:
        selected = [str(all_issues[0]["issue"])] if all_issues else []

    if args.from_issue or args.to_issue:
        ordered = [str(row["issue"]) for row in all_issues]
        bounds = [b for b in (args.from_issue, args.to_issue) if b]
        try:
            idxs = [ordered.index(b) for b in bounds]
        except ValueError as exc:
            raise SystemExit(f"issue bound not found in 500 list: {exc}") from exc
        lo, hi = min(idxs), max(idxs)
        range_set = set(ordered[lo : hi + 1])
        selected = [issue for issue in selected if issue in range_set] if args.issue else ordered[lo : hi + 1]

    if args.year_from is not None or args.year_to is not None:
        by_issue = {str(row["issue"]): row for row in all_issues}
        out = []
        for issue in selected:
            year = by_issue.get(issue, {}).get("year", issue_year(issue))
            if year is None:
                continue
            if args.year_from is not None and int(year) < args.year_from:
                continue
            if args.year_to is not None and int(year) > args.year_to:
                continue
            out.append(issue)
        selected = out

    if args.limit:
        selected = selected[: args.limit]
    return selected


def issue_already_scraped(conn: sqlite3.Connection, issue: str) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM matches WHERE issue=?", (issue,)).fetchone()
    return bool(row and int(row[0]) > 0)


def scrape_issue(conn: sqlite3.Connection, issue: str, args: argparse.Namespace) -> int:
    if issue_already_scraped(conn, issue) and not args.force:
        print(f"[skip] issue={issue} already scraped", flush=True)
        return 0
    url = f"{TRADE_URL}?expect={issue}"
    try:
        fetched_at = now_utc()
        result = fetch_url(url, timeout=args.timeout, user_agent=args.user_agent, referer=TRADE_URL)
        rows = parse_issue_rows(issue, decode_html(result.body), fetched_at=fetched_at)
        upsert_matches(conn, rows)
        insert_fetch_log(
            conn,
            kind="issue_html",
            issue=issue,
            url=url,
            status=result.status,
            ok=True,
            elapsed_sec=result.elapsed_sec,
            bytes_len=len(result.body),
            rows_parsed=len(rows),
        )
        conn.commit()
        wins = sum(1 for row in rows if row.get("winning_sp") is not None)
        print(f"[issue] {issue}: rows={len(rows)} winning_sp={wins}", flush=True)
        return len(rows)
    except Exception as exc:
        insert_fetch_log(
            conn,
            kind="issue_html",
            issue=issue,
            url=url,
            status=getattr(exc, "status", None),
            ok=False,
            elapsed_sec=None,
            bytes_len=None,
            rows_parsed=None,
            error=str(exc),
        )
        conn.commit()
        if args.keep_going:
            print(f"[error] issue={issue}: {exc}", file=sys.stderr, flush=True)
            return 0
        raise








def scrape_live_sp(conn: sqlite3.Connection, issue: str, args: argparse.Namespace) -> int:
    url = LIVE_SP_URL.format(issue=issue, playid=args.playid)
    fetch_kind = "live_sp_xml" if args.playid == 34 else f"live_market_sp_xml_{args.playid}"
    savepoint_active = False
    try:
        fetched_at = now_utc()
        result = fetch_url(url, timeout=args.timeout, user_agent=args.user_agent, referer=f"{TRADE_URL}?expect={issue}")
        source_updatetime, rows = parse_live_sp(issue, args.playid, result.body, fetched_at)
        normalized_updatetime, market_rows = parse_live_market_sp(issue, args.playid, result.body, fetched_at)
        if source_updatetime != normalized_updatetime:
            raise ValueError("normalized market timestamp disagrees with legacy parser")
        conn.execute("SAVEPOINT scrape_live_sp")
        savepoint_active = True
        fetched_at_utc = explicit_utc(fetched_at)
        for row in market_rows:
            row.update(
                {
                    "batch_id": None,
                    "match_id": f"{issue}_{int(row['row_idx']):03d}",
                    "source_url": url,
                    "fetched_at_utc": fetched_at_utc,
                    "source_updated_at_hkt": (
                        datetime.fromisoformat(source_updatetime).replace(tzinfo=timezone(timedelta(hours=8))).isoformat()
                        if source_updatetime
                        else None
                    ),
                    "sale_status": "unknown",
                    "sale_cutoff_hkt": None,
                    "parlay_allowed": "unknown",
                    "parlay_modes_json": "[]",
                    "stake_limit_json": "{}",
                    "capture_classification": "non_target_market_unclassified",
                }
            )
        if args.playid in P0_TARGET_PLAYIDS:
            if not source_updatetime:
                raise ValueError("target-market source updatetime missing")
            batch = publish_capture_batch(
                conn,
                issue=issue,
                playid=args.playid,
                source_url=url,
                fetched_at_utc=fetched_at_utc,
                source_updated_at_hkt=source_updatetime,
                raw_payload=result.body,
                rows=market_rows,
                capture_root=Path(getattr(args, "capture_root", DEFAULT_CAPTURE_ROOT)),
            )
            market_rows = batch["rows"]
        if args.playid == 34:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_sp_snapshots(
                    issue, playid, fetched_at, source_updatetime, row_idx,
                    home, away, league, handicap_line, sp_home, sp_draw, sp_away, raw_node
                ) VALUES(
                    :issue, :playid, :fetched_at, :source_updatetime, :row_idx,
                    :home, :away, :league, :handicap_line, :sp_home, :sp_draw, :sp_away, :raw_node
                )
                """,
                rows,
            )
        conn.executemany(
            """
            INSERT OR IGNORE INTO live_market_sp_snapshots(
                issue, playid, market_key, fetched_at, source_updatetime, row_idx,
                home, away, league, outcome_code, outcome_label, sp,
                source_attribute, raw_node, match_id, batch_id, source_url, fetched_at_utc,
                source_updated_at_hkt, sale_status, sale_cutoff_hkt, parlay_allowed, parlay_modes_json,
                stake_limit_json, capture_classification
            ) VALUES(
                :issue, :playid, :market_key, :fetched_at, :source_updatetime, :row_idx,
                :home, :away, :league, :outcome_code, :outcome_label, :sp,
                :source_attribute, :raw_node, :match_id, :batch_id, :source_url, :fetched_at_utc,
                :source_updated_at_hkt, :sale_status, :sale_cutoff_hkt, :parlay_allowed, :parlay_modes_json,
                :stake_limit_json, :capture_classification
            )
            """,
            market_rows,
        )
        insert_fetch_log(
            conn,
            kind=fetch_kind,
            issue=issue,
            url=url,
            status=result.status,
            ok=True,
            elapsed_sec=result.elapsed_sec,
            bytes_len=len(result.body),
            rows_parsed=len(rows),
        )
        conn.execute("RELEASE SAVEPOINT scrape_live_sp")
        savepoint_active = False
        conn.commit()
        print(
            f"[live_sp] {issue} playid={args.playid}: rows={len(rows)} "
            f"outcomes={len(market_rows)} updatetime={source_updatetime}",
            flush=True,
        )
        return len(rows)
    except Exception as exc:
        if savepoint_active:
            conn.execute("ROLLBACK TO SAVEPOINT scrape_live_sp")
            conn.execute("RELEASE SAVEPOINT scrape_live_sp")
        insert_fetch_log(
            conn,
            kind=fetch_kind,
            issue=issue,
            url=url,
            status=getattr(exc, "status", None),
            ok=False,
            elapsed_sec=None,
            bytes_len=None,
            rows_parsed=None,
            error=str(exc),
        )
        conn.commit()
        if args.keep_going:
            print(f"[error] live_sp issue={issue}: {exc}", file=sys.stderr, flush=True)
            return 0
        raise


def print_summary(conn: sqlite3.Connection) -> None:
    issue_row = conn.execute("SELECT COUNT(*), MIN(issue), MAX(issue) FROM issues").fetchone()
    match_row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT issue), SUM(CASE WHEN winning_sp IS NOT NULL THEN 1 ELSE 0 END) FROM matches"
    ).fetchone()
    print(
        "[summary] "
        f"issues={issue_row[0]} min_issue={issue_row[1]} max_issue={issue_row[2]} "
        f"matches={match_row[0]} match_issues={match_row[1]} winning_sp_rows={match_row[2]}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", help="Issue id or comma-separated ids. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Scrape all issue ids exposed in the 500 page.")
    parser.add_argument("--from-issue", help="Inclusive issue bound using 500's issue-list order.")
    parser.add_argument("--to-issue", help="Inclusive issue bound using 500's issue-list order.")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--list-only", action="store_true", help="Only refresh the issue list.")
    parser.add_argument("--live-sp", action="store_true", help="Also fetch current live SP XML for selected issues.")
    parser.add_argument(
        "--playid",
        action="append",
        help="BJDC play id or comma-separated ids; repeatable. Default: 34,40,41,42,51.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()
    playids = parse_playids(args.playid)

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = connect_sqlite(args.db)
    create_schema(conn)
    issues = fetch_issue_list(conn, args)
    print(f"[issue_list] {len(issues)} issues; latest={issues[0]['issue'] if issues else ''}", flush=True)
    if args.list_only:
        print_summary(conn)
        return

    selected = select_issues(issues, args)
    if not selected:
        raise SystemExit("No issues selected.")
    print(f"[select] {len(selected)} issues", flush=True)
    for i, issue in enumerate(selected, start=1):
        print(f"[progress] {i}/{len(selected)} issue={issue}", flush=True)
        scrape_issue(conn, issue, args)
        if args.live_sp:
            for playid in playids:
                args.playid = playid
                scrape_live_sp(conn, issue, args)
        if args.sleep and i < len(selected):
            time.sleep(args.sleep)
    print_summary(conn)


if __name__ == "__main__":
    main()
