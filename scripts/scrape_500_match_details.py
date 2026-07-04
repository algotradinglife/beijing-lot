#!/usr/bin/env python3
"""Fetch 500.com per-match analysis pages into the live SQLite DB.

The live issue page links each match to:

* ``odds.500.com/fenxi/shuju-{fid}.shtml``   data analysis
* ``odds.500.com/fenxi/youliao-{fid}.shtml`` recommendation page
* ``odds.500.com/fenxi/yazhi-{fid}.shtml``  Asian odds
* ``odds.500.com/fenxi/ouzhi-{fid}.shtml``  European odds

This script stores only compact, pre-match usable summaries. It deliberately
does not feed these fields into the production selector; the API/UI can expose
them as Match Detail and LLM-input context.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
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

from src.live_collector.scraper import Scraper  # noqa: E402


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DETAIL_URL = "https://odds.500.com/fenxi/shuju-{fid}.shtml"
RECOMMEND_URL = "https://odds.500.com/fenxi/youliao-{fid}.shtml?channel=pc_score"
ASIAN_URL = "https://odds.500.com/fenxi/yazhi-{fid}.shtml"
EURO_URL = "https://odds.500.com/fenxi/ouzhi-{fid}.shtml"
REFERER = "https://live.500.com/zqdc.php"

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
META_DESC_RE = re.compile(
    r'<meta\s+name=["\']Description["\']\s+content=["\'](.*?)["\']',
    re.S | re.I,
)
TEAM_NAME_RE = re.compile(r'<strong\s+class=["\']team_name["\'][^>]*>(.*?)</strong>', re.S | re.I)
TR_RE = re.compile(r"<tr\b(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def extract_title(text: str) -> str:
    match = TITLE_RE.search(text)
    return clean_text(match.group(1)) if match else ""


def extract_description(text: str) -> str:
    match = META_DESC_RE.search(text)
    return clean_text(match.group(1)) if match else ""


def between(text: str, start: str, *ends: str) -> str:
    start_idx = text.find(start)
    if start_idx < 0:
        return ""
    end_idx = len(text)
    for marker in ends:
        idx = text.find(marker, start_idx + len(start))
        if idx >= 0:
            end_idx = min(end_idx, idx)
    return text[start_idx:end_idx]


def parse_match_cells(row_html: str) -> list[str]:
    return [clean_text(cell) for cell in TD_RE.findall(row_html)]


def count_values(rows: list[dict[str, str]], key: str, values: tuple[str, ...]) -> dict[str, int]:
    out = {value: 0 for value in values}
    for row in rows:
        value = row.get(key, "")
        if value in out:
            out[value] += 1
    return out


def format_recent_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "近期战绩缺失"
    result = count_values(rows, "result", ("胜", "平", "负"))
    handicap = count_values(rows, "handicap_result", ("赢", "走", "输"))
    total = count_values(rows, "goal_size", ("大", "小"))
    return (
        f"近{len(rows)}场 {result['胜']}胜{result['平']}平{result['负']}负；"
        f"盘路 {handicap['赢']}赢{handicap['走']}走{handicap['输']}输；"
        f"大小 {total['大']}大{total['小']}小"
    )


def parse_recent_block(block: str, *, limit: int = 10) -> dict[str, Any]:
    team_match = TEAM_NAME_RE.search(block)
    rows: list[dict[str, str]] = []
    for match in TR_RE.finditer(block):
        attrs = match.group("attrs")
        if "bmatch" in attrs or "<th" in match.group("body").lower():
            continue
        cells = parse_match_cells(match.group("body"))
        if len(cells) < 8:
            continue
        rows.append(
            {
                "league": cells[0],
                "date": cells[1],
                "match": cells[2],
                "handicap": cells[3],
                "half_score": cells[4],
                "result": cells[5],
                "handicap_result": cells[6],
                "goal_size": cells[7],
            }
        )
        if len(rows) >= limit:
            break
    return {
        "team": clean_text(team_match.group(1)) if team_match else "",
        "summary": format_recent_summary(rows),
        "rows": rows,
    }


def parse_h2h_block(block: str, *, limit: int = 10) -> dict[str, Any]:
    rows: list[dict[str, str]] = []
    for match in TR_RE.finditer(block):
        attrs = match.group("attrs")
        if "bmatch" in attrs or "<th" in match.group("body").lower():
            continue
        cells = parse_match_cells(match.group("body"))
        if len(cells) < 6:
            continue
        rows.append(
            {
                "league": cells[0],
                "date": cells[1],
                "match": cells[2],
                "half_score": cells[3] if len(cells) > 3 else "",
                "result": cells[4] if len(cells) > 4 else "",
                "odds": cells[5] if len(cells) > 5 else "",
            }
        )
        if len(rows) >= limit:
            break
    result = count_values(rows, "result", ("胜", "平", "负"))
    summary = (
        f"近{len(rows)}次交锋 {result['胜']}胜{result['平']}平{result['负']}负"
        if rows
        else "交锋数据缺失"
    )
    return {"summary": summary, "rows": rows}


def parse_league_table_text(text: str) -> str:
    block = between(text, "赛前联赛积分排名", "瓦萨VS", "交战历史", "近期战绩")
    return clean_text(block)[:700]


def parse_analysis_html(fid: int, text: str) -> dict[str, Any]:
    home_block = between(text, 'id="team_zhanji_1"', 'id="team_zhanji_0"')
    away_block = between(text, 'id="team_zhanji_0"', 'id="team_zhanji1_1"', "未来赛程")
    h2h_block = between(text, "交战历史", "近期战绩")
    return {
        "fid": fid,
        "title": extract_title(text),
        "description": extract_description(text),
        "league_table": parse_league_table_text(text),
        "home_recent": parse_recent_block(home_block),
        "away_recent": parse_recent_block(away_block),
        "h2h": parse_h2h_block(h2h_block),
        "urls": {
            "data": DETAIL_URL.format(fid=fid),
            "recommendation": RECOMMEND_URL.format(fid=fid),
            "asian": ASIAN_URL.format(fid=fid),
            "europe": EURO_URL.format(fid=fid),
        },
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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


def select_matches(conn: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    where = ["fid IS NOT NULL"]
    params: list[Any] = []
    if args.issue:
        where.append("issue=?")
        params.append(args.issue)
    if args.fid:
        where.append("fid=?")
        params.append(args.fid)
    sql = f"""
        SELECT issue, match_idx, fid, league, home, away, end_time
        FROM matches
        WHERE {" AND ".join(where)}
        ORDER BY issue DESC, match_idx
        LIMIT ?
    """
    params.append(args.limit)
    return list(conn.execute(sql, params))


def upsert_detail(conn: sqlite3.Connection, row: sqlite3.Row, payload: dict[str, Any], raw_html: str, status: str, error: str = "") -> None:
    urls = payload.get("urls", {})
    home_recent = payload.get("home_recent", {})
    away_recent = payload.get("away_recent", {})
    h2h = payload.get("h2h", {})
    conn.execute(
        """
        INSERT INTO match_details_500(
            issue, match_idx, fid, fetched_at, status, title, description,
            data_url, recommendation_url, asian_url, europe_url,
            home_recent_summary, away_recent_summary, h2h_summary,
            league_table_summary, payload_json, raw_sha1, error
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(issue, match_idx) DO UPDATE SET
            fid=excluded.fid,
            fetched_at=excluded.fetched_at,
            status=excluded.status,
            title=excluded.title,
            description=excluded.description,
            data_url=excluded.data_url,
            recommendation_url=excluded.recommendation_url,
            asian_url=excluded.asian_url,
            europe_url=excluded.europe_url,
            home_recent_summary=excluded.home_recent_summary,
            away_recent_summary=excluded.away_recent_summary,
            h2h_summary=excluded.h2h_summary,
            league_table_summary=excluded.league_table_summary,
            payload_json=excluded.payload_json,
            raw_sha1=excluded.raw_sha1,
            error=excluded.error
        """,
        (
            row["issue"],
            row["match_idx"],
            row["fid"],
            now_utc(),
            status,
            payload.get("title", ""),
            payload.get("description", ""),
            urls.get("data", DETAIL_URL.format(fid=row["fid"])),
            urls.get("recommendation", RECOMMEND_URL.format(fid=row["fid"])),
            urls.get("asian", ASIAN_URL.format(fid=row["fid"])),
            urls.get("europe", EURO_URL.format(fid=row["fid"])),
            home_recent.get("summary", ""),
            away_recent.get("summary", ""),
            h2h.get("summary", ""),
            payload.get("league_table", ""),
            json.dumps(payload, ensure_ascii=False),
            hashlib.sha1(raw_html.encode("utf-8", errors="ignore")).hexdigest() if raw_html else "",
            error,
        ),
    )


def scrape_one(conn: sqlite3.Connection, scraper: Scraper, row: sqlite3.Row) -> bool:
    fid = int(row["fid"])
    url = DETAIL_URL.format(fid=fid)
    try:
        raw = scraper.get(url, encoding="gb18030", referer=REFERER)
        if not raw or "Restricted Access" in raw or "EdgeOne" in raw:
            upsert_detail(conn, row, {"fid": fid, "urls": {
                "data": url,
                "recommendation": RECOMMEND_URL.format(fid=fid),
                "asian": ASIAN_URL.format(fid=fid),
                "europe": EURO_URL.format(fid=fid),
            }}, raw, "blocked", "blocked_or_empty")
            return False
        payload = parse_analysis_html(fid, raw)
        upsert_detail(conn, row, payload, raw, "ok")
        return True
    except Exception as exc:
        upsert_detail(conn, row, {"fid": fid, "urls": {
            "data": url,
            "recommendation": RECOMMEND_URL.format(fid=fid),
            "asian": ASIAN_URL.format(fid=fid),
            "europe": EURO_URL.format(fid=fid),
        }}, "", "error", str(exc))
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue")
    parser.add_argument("--fid", type=int)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--sleep", type=float, default=0.4)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    scraper = Scraper(min_interval=max(args.sleep, 0.0), max_retries=2, timeout=args.timeout)
    rows = select_matches(conn, args)
    ok = 0
    for row in rows:
        success = scrape_one(conn, scraper, row)
        conn.commit()
        ok += int(success)
        print(
            f"[match_detail] issue={row['issue']} idx={row['match_idx']} fid={row['fid']} status={'ok' if success else 'failed'}",
            flush=True,
        )
        if args.sleep:
            time.sleep(args.sleep)
    print(f"[summary] rows={len(rows)} ok={ok}", flush=True)


if __name__ == "__main__":
    main()
