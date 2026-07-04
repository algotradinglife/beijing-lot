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
import hashlib
import html
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
TRADE_URL = "https://trade.500.com/bjdc/index.php"
LIVE_SP_URL = "https://www.500.com/static/public/bjdc/xml/sp/just_{issue}_{playid}.xml"
DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

EXPECT_SELECT_RE = re.compile(r'<select[^>]+id="expect_select"[^>]*>(?P<body>.*?)</select>', re.S | re.I)
OPTION_RE = re.compile(r'<option\s+value="(?P<issue>\d+)"(?P<attrs>[^>]*)>(?P<label>.*?)</option>', re.S | re.I)
ROW_RE = re.compile(
    r'<tr\s+class="(?P<class>[^"]*\bvs_lines\b[^"]*)"[^>]*?'
    r'value="(?P<value>\{.*?\})"\s+fid="(?P<fid>\d+)"[^>]*>'
    r'(?P<body>.*?)</tr>',
    re.S | re.I,
)
VALUE_PAIR_RE = re.compile(r"(\w+):(?:'([^']*)'|([^,}]+))")
SCORE_RE = re.compile(r'class="[^"]*\bred\b[^"]*\beng\b[^"]*"[^>]*>\s*([^<]+?)\s*</a>', re.S | re.I)
PJOZ_RE = re.compile(r'<span\s+class="[^"]*\bpjoz\b[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.S | re.I)
ASIAN_RE = re.compile(r'<span\s+class="asianhand"[^>]*>\s*([^<]*?)\s*</span>', re.S | re.I)
LABEL_BLOCK_RE = re.compile(
    r'value="(?P<label>胜|平|负)"(?P<block>.*?</label>)',
    re.S | re.I,
)
SP_VALUE_RE = re.compile(r'<span\s+class="[^"]*\bsp_value\b[^"]*"[^>]*>\s*([0-9.]+)\s*</span>', re.S | re.I)

RESULT_CODE_BY_LABEL = {"胜": "3", "平": "1", "负": "0"}
SCORE_PARTS_RE = re.compile(r"^\s*(\d+)\s*[:：]\s*(\d+)\s*$")


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    body: bytes
    elapsed_sec: float


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean_text(raw: str | None) -> str:
    if raw is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def as_float(raw: object) -> float | None:
    if raw is None:
        return None
    text = clean_text(str(raw))
    if not text or text == "--":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def as_int(raw: object) -> int | None:
    if raw is None:
        return None
    text = clean_text(str(raw))
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def decode_html(data: bytes) -> str:
    return data.decode("gb18030", errors="ignore")


def fetch_url(url: str, *, timeout: float, user_agent: str, referer: str | None = None) -> FetchResult:
    headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    started = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        status = getattr(resp, "status", 200)
    return FetchResult(url=url, status=int(status), body=body, elapsed_sec=time.time() - started)


def issue_year(issue: str) -> int | None:
    if len(issue) < 2 or not issue[:2].isdigit():
        return None
    return 2000 + int(issue[:2])


def parse_issue_options(text: str) -> list[dict[str, object]]:
    m = EXPECT_SELECT_RE.search(text)
    if not m:
        return []
    out: list[dict[str, object]] = []
    for idx, opt in enumerate(OPTION_RE.finditer(m.group("body"))):
        issue = opt.group("issue")
        if len(issue) < 5:
            continue
        attrs = opt.group("attrs")
        label = clean_text(re.sub(r"<.*?>", "", opt.group("label")))
        out.append(
            {
                "issue": issue,
                "ordinal": idx,
                "label": label,
                "is_selected": 1 if "selected" in attrs.lower() else 0,
                "is_current": 1 if "当前期" in label else 0,
                "year": issue_year(issue),
            }
        )
    return out


def parse_value_object(raw: str) -> dict[str, str]:
    raw = html.unescape(raw)
    out: dict[str, str] = {}
    for key, quoted, bare in VALUE_PAIR_RE.findall(raw):
        out[key] = clean_text(quoted if quoted != "" else bare)
    return out


def parse_label_sp(body: str) -> dict[str, float | None]:
    out = {"胜": None, "平": None, "负": None}
    for m in LABEL_BLOCK_RE.finditer(body):
        sp_m = SP_VALUE_RE.search(m.group("block"))
        out[m.group("label")] = as_float(sp_m.group(1)) if sp_m else None
    return out


def infer_result_label(score: str, handicap_line: float | None) -> str | None:
    if handicap_line is None:
        return None
    m = SCORE_PARTS_RE.match(score)
    if not m:
        return None
    home_goals = int(m.group(1))
    away_goals = int(m.group(2))
    adjusted_home = home_goals + handicap_line
    if adjusted_home > away_goals:
        return "胜"
    if adjusted_home < away_goals:
        return "负"
    return "平"


def parse_issue_rows(issue: str, text: str, *, fetched_at: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for m in ROW_RE.finditer(text):
        raw_value = html.unescape(m.group("value"))
        info = parse_value_object(raw_value)
        body = m.group("body")
        pjoz = [as_float(x) for x in PJOZ_RE.findall(body)]
        pjoz = (pjoz + [None, None, None])[:3]
        asian = ASIAN_RE.search(body)
        score_m = SCORE_RE.search(body)
        score = clean_text(score_m.group(1)) if score_m else ""
        label_sp = parse_label_sp(body)
        visible_sp = [label_sp["胜"], label_sp["平"], label_sp["负"]]
        winning_labels = [label for label, sp in label_sp.items() if sp is not None]
        handicap_line = as_float(info.get("rangqiuNum"))
        inferred_label = infer_result_label(score, handicap_line)
        result_label = winning_labels[0] if score and len(winning_labels) == 1 else inferred_label
        winning_sp = label_sp[result_label] if result_label else None
        raw_row = m.group(0)
        rows.append(
            {
                "issue": issue,
                "match_idx": as_int(info.get("index")),
                "fid": as_int(m.group("fid")),
                "league": info.get("leagueName", ""),
                "home": info.get("homeTeam", ""),
                "away": info.get("guestTeam", ""),
                "end_time": info.get("endTime", ""),
                "schedule_date": info.get("scheduleDate", ""),
                "handicap_line": handicap_line,
                "disabled": info.get("disabled", ""),
                "home_rank": as_int(info.get("homeTeamRank")),
                "away_rank": as_int(info.get("guestTeamRank")),
                "bg_color": info.get("bgColor", ""),
                "score": score,
                "result_label": result_label,
                "result_code": RESULT_CODE_BY_LABEL.get(result_label or ""),
                "winning_sp": winning_sp,
                "sp_home": visible_sp[0],
                "sp_draw": visible_sp[1],
                "sp_away": visible_sp[2],
                "avg_odds_home": pjoz[0],
                "avg_odds_draw": pjoz[1],
                "avg_odds_away": pjoz[2],
                "asian_handicap": clean_text(asian.group(1)) if asian else "",
                "raw_value": raw_value,
                "raw_row_hash": hashlib.sha1(raw_row.encode("utf-8", errors="ignore")).hexdigest(),
                "fetched_at": fetched_at,
            }
        )
    return rows


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
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in {"issue", "match_idx"})
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
            status=getattr(exc, "code", None),
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


def parse_live_sp(issue: str, playid: int, data: bytes, fetched_at: str) -> tuple[str | None, list[dict[str, object]]]:
    root = ET.fromstring(decode_html(data))
    source_updatetime = root.attrib.get("updatetime")
    rows: list[dict[str, object]] = []
    for child in list(root):
        name = child.tag
        if not name.startswith("w"):
            continue
        try:
            row_idx = int(name[1:])
        except ValueError:
            continue
        raw_node = ET.tostring(child, encoding="unicode")
        rows.append(
            {
                "issue": issue,
                "playid": playid,
                "fetched_at": fetched_at,
                "source_updatetime": source_updatetime,
                "row_idx": row_idx,
                "home": child.attrib.get("h", ""),
                "away": child.attrib.get("a", ""),
                "league": child.attrib.get("gn", ""),
                "handicap_line": as_float(child.attrib.get("r")),
                "sp_home": as_float(child.attrib.get("c1")),
                "sp_draw": as_float(child.attrib.get("c3")),
                "sp_away": as_float(child.attrib.get("c5")),
                "raw_node": raw_node,
            }
        )
    return source_updatetime, rows


def scrape_live_sp(conn: sqlite3.Connection, issue: str, args: argparse.Namespace) -> int:
    url = LIVE_SP_URL.format(issue=issue, playid=args.playid)
    try:
        fetched_at = now_utc()
        result = fetch_url(url, timeout=args.timeout, user_agent=args.user_agent, referer=f"{TRADE_URL}?expect={issue}")
        source_updatetime, rows = parse_live_sp(issue, args.playid, result.body, fetched_at)
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
        insert_fetch_log(
            conn,
            kind="live_sp_xml",
            issue=issue,
            url=url,
            status=result.status,
            ok=True,
            elapsed_sec=result.elapsed_sec,
            bytes_len=len(result.body),
            rows_parsed=len(rows),
        )
        conn.commit()
        print(f"[live_sp] {issue}: rows={len(rows)} updatetime={source_updatetime}", flush=True)
        return len(rows)
    except Exception as exc:
        insert_fetch_log(
            conn,
            kind="live_sp_xml",
            issue=issue,
            url=url,
            status=getattr(exc, "code", None),
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
    parser.add_argument("--playid", type=int, default=34, help="500 play id; 34 is BJDC rqspf.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA foreign_keys=ON")
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
            scrape_live_sp(conn, issue, args)
        if args.sleep and i < len(selected):
            time.sleep(args.sleep)
    print_summary(conn)


if __name__ == "__main__":
    main()
