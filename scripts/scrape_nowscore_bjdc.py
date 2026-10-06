#!/usr/bin/env python3
"""Scrape Jiebao/Nowscore BJDC issue rows into the live SQLite DB.

The Nowscore BJDC page has a "完场" checkbox that navigates to the same
issue with ``all=1``.  Use that URL so finished matches are included without
browser automation.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sqlite_runtime import connect_sqlite  # noqa: E402
from beidan_backend.transport import fetch_issue_page  # noqa: E402

DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
NOWSCORE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum={issue}"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "KHTML, like Gecko Chrome/126 Safari/537.36"
)

ROW_RE = re.compile(r"<tr\b(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S | re.I)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*["']([^"']*)["']""", re.S)
PROVIDER_RE = re.compile(r"Panlu\.aspx\?id=(\d+)", re.I)
HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)
SCORE_RE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")
RESULT_LABEL_BY_CODE = {"3": "胜", "1": "平", "0": "负"}


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("+", "").strip())
    except ValueError:
        return None


def absolute_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"https://cp.nowscore.com{href}"
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"https://cp.nowscore.com/{href.lstrip('/')}"


def attrs_dict(attrs: str) -> dict[str, str]:
    return {key.lower(): html.unescape(value) for key, value in ATTR_RE.findall(attrs or "")}


def score_result_code(score: str, handicap_line: float | None) -> str | None:
    match = SCORE_RE.match(score or "")
    if not match:
        return None
    home_goals = int(match.group(1))
    away_goals = int(match.group(2))
    home_effective = home_goals + int(handicap_line or 0)
    if home_effective > away_goals:
        return "3"
    if home_effective < away_goals:
        return "0"
    return "1"


def row_status(status_text: str, score: str, can_sale: str) -> str:
    text = (status_text or "").strip()
    if "完场" in status_text:
        return "finished"
    if text in {"上", "中", "下", "加", "点"} or "中场" in text or "半场" in text or "'" in text:
        return "live"
    if SCORE_RE.match(score or "") and can_sale.lower() == "false":
        return "finished"
    if can_sale.lower() == "false":
        return "closed"
    return "scheduled"


def parse_rows(issue: str, body: str, fetched_at: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for match in ROW_RE.finditer(body):
        attrs_text = match.group("attrs")
        row_body = match.group("body")
        attrs = attrs_dict(attrs_text)
        row_id = attrs.get("id", "")
        if not re.fullmatch(r"row_\d+", row_id):
            continue
        provider_match = PROVIDER_RE.search(row_body)
        if not provider_match:
            continue
        cells = [clean_text(cell) for cell in CELL_RE.findall(row_body)]
        if len(cells) < 9:
            continue
        match_idx = int(row_id.split("_", 1)[1])
        provider_match_id = provider_match.group(1)
        handicap_text = cells[5]
        handicap_line = to_float(attrs.get("polygoal")) if attrs.get("polygoal") not in (None, "") else to_float(handicap_text)
        status_text = cells[3]
        score = cells[6]
        halftime = cells[8]
        status = row_status(status_text, score, attrs.get("cansale", ""))
        urls = {
            "panlu_url": "",
            "asian_url": "",
            "europe_url": "",
            "analysis_url": "",
            "recommendation_url": "",
            "sp_url": "",
        }
        for href in HREF_RE.findall(row_body):
            abs_href = absolute_url(html.unescape(href))
            if "Panlu.aspx?id=" in href:
                urls["panlu_url"] = abs_href
            elif "/odds/match/" in href:
                urls["asian_url"] = abs_href
            elif "/1x2/" in href:
                urls["europe_url"] = abs_href
            elif "/analysis/" in href:
                urls["analysis_url"] = abs_href
            elif "/Recommend/" in href:
                urls["recommendation_url"] = abs_href
            elif "/sp/danchang/" in href:
                urls["sp_url"] = abs_href
        rows.append(
            {
                "issue": issue,
                "match_idx": match_idx,
                "provider_match_id": provider_match_id,
                "fetched_at": fetched_at,
                "schedule_date": attrs.get("name", ""),
                "league": attrs.get("gamename") or cells[1],
                "kickoff_time": cells[2],
                "status_text": status_text,
                "status": status,
                "can_sale": 1 if attrs.get("cansale", "").lower() == "true" else 0,
                "home": cells[4],
                "away": cells[7],
                "handicap_text": handicap_text,
                "handicap_line": handicap_line,
                "score": "" if score == "-" else score,
                "halftime_score": "" if halftime == "-" else halftime,
                "result_code": score_result_code(score, handicap_line) if status == "finished" else None,
                "raw_row_hash": hashlib.sha1(match.group(0).encode("utf-8", errors="ignore")).hexdigest(),
                "raw_row": match.group(0),
                **urls,
            }
        )
    rows.sort(key=lambda row: int(row["match_idx"]))
    return rows


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;

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

        CREATE TABLE IF NOT EXISTS nowscore_bjdc_matches (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            provider_match_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            schedule_date TEXT,
            league TEXT,
            kickoff_time TEXT,
            status_text TEXT,
            status TEXT,
            can_sale INTEGER,
            home TEXT,
            away TEXT,
            handicap_text TEXT,
            handicap_line REAL,
            score TEXT,
            halftime_score TEXT,
            result_code TEXT,
            panlu_url TEXT,
            asian_url TEXT,
            europe_url TEXT,
            analysis_url TEXT,
            recommendation_url TEXT,
            sp_url TEXT,
            raw_row_hash TEXT,
            raw_row TEXT,
            PRIMARY KEY(issue, match_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_nowscore_provider_match ON nowscore_bjdc_matches(provider_match_id);
        """
    )


# The Jiebao endpoints are happiest with a browser-like Accept set and no
# cache; these are passed through the shared transport rather than hand-rolled.
NOWSCORE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}


def fetch_url(url: str, timeout: int, user_agent: str) -> tuple[int, bytes, float]:
    """Fetch one page through the package transport (bounded retries + timeout)."""
    response = fetch_issue_page(
        url, timeout=timeout, user_agent=user_agent, headers=NOWSCORE_HEADERS
    )
    return response.status, response.body, response.elapsed_sec


def insert_fetch_log(
    conn: sqlite3.Connection,
    *,
    fetched_at: str,
    issue: str,
    url: str,
    status: int | None,
    ok: bool,
    elapsed_sec: float | None,
    bytes_len: int,
    rows_parsed: int,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO fetch_log(fetched_at, kind, issue, url, status, ok, elapsed_sec, bytes, rows_parsed, error)
        VALUES(?, 'nowscore_bjdc', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fetched_at, issue, url, status, int(ok), elapsed_sec, bytes_len, rows_parsed, error),
    )


def upsert_match_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO nowscore_bjdc_matches(
            issue, match_idx, provider_match_id, fetched_at, schedule_date, league,
            kickoff_time, status_text, status, can_sale, home, away,
            handicap_text, handicap_line, score, halftime_score, result_code,
            panlu_url, asian_url, europe_url, analysis_url, recommendation_url,
            sp_url, raw_row_hash, raw_row
        ) VALUES(
            :issue, :match_idx, :provider_match_id, :fetched_at, :schedule_date, :league,
            :kickoff_time, :status_text, :status, :can_sale, :home, :away,
            :handicap_text, :handicap_line, :score, :halftime_score, :result_code,
            :panlu_url, :asian_url, :europe_url, :analysis_url, :recommendation_url,
            :sp_url, :raw_row_hash, :raw_row
        )
        ON CONFLICT(issue, match_idx) DO UPDATE SET
            provider_match_id=COALESCE(NULLIF(excluded.provider_match_id, ''), provider_match_id),
            fetched_at=excluded.fetched_at,
            schedule_date=COALESCE(NULLIF(excluded.schedule_date, ''), schedule_date),
            league=COALESCE(NULLIF(excluded.league, ''), league),
            kickoff_time=COALESCE(NULLIF(excluded.kickoff_time, ''), kickoff_time),
            status_text=CASE
                WHEN status='finished' AND COALESCE(NULLIF(excluded.status_text, ''), '') NOT LIKE '%完%'
                    THEN status_text
                ELSE COALESCE(NULLIF(excluded.status_text, ''), status_text)
            END,
            status=CASE
                WHEN status='finished' AND COALESCE(NULLIF(excluded.status, ''), '') != 'finished'
                    THEN status
                ELSE COALESCE(NULLIF(excluded.status, ''), status)
            END,
            can_sale=excluded.can_sale,
            home=COALESCE(NULLIF(excluded.home, ''), home),
            away=COALESCE(NULLIF(excluded.away, ''), away),
            handicap_text=COALESCE(NULLIF(excluded.handicap_text, ''), handicap_text),
            handicap_line=COALESCE(excluded.handicap_line, handicap_line),
            score=COALESCE(NULLIF(excluded.score, ''), score),
            halftime_score=COALESCE(NULLIF(excluded.halftime_score, ''), halftime_score),
            result_code=COALESCE(NULLIF(excluded.result_code, ''), result_code),
            panlu_url=COALESCE(NULLIF(excluded.panlu_url, ''), panlu_url),
            asian_url=COALESCE(NULLIF(excluded.asian_url, ''), asian_url),
            europe_url=COALESCE(NULLIF(excluded.europe_url, ''), europe_url),
            analysis_url=COALESCE(NULLIF(excluded.analysis_url, ''), analysis_url),
            recommendation_url=COALESCE(NULLIF(excluded.recommendation_url, ''), recommendation_url),
            sp_url=COALESCE(NULLIF(excluded.sp_url, ''), sp_url),
            raw_row_hash=excluded.raw_row_hash,
            raw_row=excluded.raw_row
        """,
        rows,
    )


def reconcile_finished_settlements(conn: sqlite3.Connection, issue: str) -> int:
    """Fill missing 500 settlements from a finished Nowscore row.

    Nowscore is the score authority here; the payout remains the matching
    500.com option SP already stored on the issue row.  Do not overwrite an
    existing official settlement, and require the two sources to agree on the
    Beidan handicap before writing a result.
    """
    has_matches = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'"
    ).fetchone()
    if not has_matches:
        return 0

    rows = conn.execute(
        """
        SELECT
          m.issue,
          m.match_idx,
          m.handicap_line AS official_handicap,
          m.sp_home,
          m.sp_draw,
          m.sp_away,
          n.fetched_at,
          n.handicap_line AS nowscore_handicap,
          n.score,
          n.result_code
        FROM matches AS m
        JOIN nowscore_bjdc_matches AS n
          ON n.issue=m.issue AND n.match_idx=m.match_idx
        WHERE m.issue=?
          AND m.winning_sp IS NULL
          AND n.status='finished'
          AND n.result_code IN ('3', '1', '0')
          AND TRIM(COALESCE(n.score, ''))<>''
          AND (
            m.handicap_line IS NULL
            OR n.handicap_line IS NULL
            OR ABS(m.handicap_line - n.handicap_line) < 0.000001
          )
        """,
        (issue,),
    ).fetchall()
    updates: list[tuple[object, ...]] = []
    for row in rows:
        result_code = str(row["result_code"])
        winning_sp = {
            "3": row["sp_home"],
            "1": row["sp_draw"],
            "0": row["sp_away"],
        }[result_code]
        if winning_sp is None or float(winning_sp) <= 0:
            continue
        updates.append(
            (
                str(row["score"]),
                RESULT_LABEL_BY_CODE[result_code],
                result_code,
                float(winning_sp),
                str(row["fetched_at"]),
                str(row["issue"]),
                int(row["match_idx"]),
            )
        )
    if not updates:
        return 0
    conn.executemany(
        """
        UPDATE matches
        SET score=?, result_label=?, result_code=?, winning_sp=?, fetched_at=?
        WHERE issue=? AND match_idx=? AND winning_sp IS NULL
        """,
        updates,
    )
    return len(updates)


def scrape_issue(conn: sqlite3.Connection, issue: str, args: argparse.Namespace) -> int:
    fetched_at = now_utc()
    url = NOWSCORE_URL.format(issue=issue)
    try:
        status, payload, elapsed = fetch_url(url, args.timeout, args.user_agent)
        text = payload.decode("utf-8", errors="replace")
        rows = parse_rows(issue, text, fetched_at)
        upsert_match_rows(conn, rows)
        reconciled = reconcile_finished_settlements(conn, issue)
        insert_fetch_log(
            conn,
            fetched_at=fetched_at,
            issue=issue,
            url=url,
            status=status,
            ok=True,
            elapsed_sec=elapsed,
            bytes_len=len(payload),
            rows_parsed=len(rows),
        )
        conn.commit()
        finished = sum(1 for row in rows if row.get("status") == "finished")
        print(
            f"[nowscore] {issue}: rows={len(rows)} finished={finished} reconciled={reconciled}",
            flush=True,
        )
        return len(rows)
    except Exception as exc:
        insert_fetch_log(
            conn,
            fetched_at=fetched_at,
            issue=issue,
            url=url,
            status=getattr(exc, "status", None),
            ok=False,
            elapsed_sec=None,
            bytes_len=0,
            rows_parsed=0,
            error=str(exc),
        )
        conn.commit()
        if args.keep_going:
            print(f"[error] nowscore issue={issue}: {exc}", file=sys.stderr, flush=True)
            return 0
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", required=True, help="Issue id. May be comma-separated or repeated.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()

    issues = [part.strip() for raw in args.issue for part in raw.split(",") if part.strip()]
    conn = connect_sqlite(args.db, row_factory=True)
    try:
        create_schema(conn)
        total = 0
        for idx, issue in enumerate(issues):
            if idx and args.sleep > 0:
                time.sleep(args.sleep)
            total += scrape_issue(conn, issue, args)
        print(f"[summary] issues={len(issues)} rows={total}", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
