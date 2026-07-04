#!/usr/bin/env python3
"""Scrape Jiebao/Nowscore per-match analysis context into SQLite.

The issue-row scraper stores links and live score state.  This companion
script fetches the single-match analysis page, recent-results JS, and 1x2 odds
JS so Match Detail can expose higher-quality LLM context without browser
automation.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scrape_nowscore_bjdc import DEFAULT_DB, DEFAULT_UA  # noqa: E402
from src.live_collector.scraper import Scraper  # noqa: E402


ANALYSIS_URL = "https://live.nowscore.com/analysis/{provider_id}cn.html"
ANALYSIS_JS_URL = "https://live.nowscore.com/analysisJs/data{provider_id}.js"
ODDS_1X2_JS_URL = "https://1x2.NowScore.com/{provider_id}.js"
REFERER = "https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5"

SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)
META_DESC_RE = re.compile(r'<meta\s+name=["\']Description["\']\s+content=["\'](.*?)["\']', re.S | re.I)
TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
TD_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.S | re.I)
TABLE_CLASS_RE = r"<table[^>]*class=['\"]{class_name}['\"][^>]*>(.*?)</table>"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip().strip("\ufeff")


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(str(value).strip())
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(str(value).strip()))
    except ValueError:
        return None


def title(text: str) -> str:
    match = TITLE_RE.search(text)
    return clean_text(match.group(1)) if match else ""


def description(text: str) -> str:
    match = META_DESC_RE.search(text)
    return clean_text(match.group(1)) if match else ""


def extract_match_meta(text: str) -> dict[str, str]:
    kickoff = ""
    kickoff_match = re.search(r"开赛时间[:：]\s*([0-9:\-\s/]+)", clean_text(text))
    if kickoff_match:
        kickoff = kickoff_match.group(1).strip()
    lgtime = re.search(r'<div class=["\']lgtime["\'][^>]*>(.*?)</div>', text, re.S | re.I)
    lg_text = clean_text(lgtime.group(1)) if lgtime else ""
    weather = ""
    if kickoff and kickoff in lg_text:
        weather = lg_text.split(kickoff, 1)[-1].strip(" ，,")
    return {"kickoff": kickoff, "venue_weather": weather, "raw": lg_text[:240]}


def table_rows(table_html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for row_html in TR_RE.findall(table_html):
        cells = [clean_text(cell) for cell in TD_RE.findall(row_html)]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(cells)
    return rows


def tables_by_class(text: str, class_name: str) -> list[list[list[str]]]:
    pattern = TABLE_CLASS_RE.format(class_name=re.escape(class_name))
    return [table_rows(match) for match in re.findall(pattern, text, re.S | re.I)]


def team_from_rows(rows: list[list[str]]) -> str:
    for row in rows:
        if row and len(row) == 1:
            return row[0]
    return ""


def row_by_first(rows: list[list[str]], label: str) -> list[str]:
    for row in rows:
        if row and row[0] == label:
            return row
    return []


def summarize_jifen(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    team = team_from_rows(rows)
    phase = next((row[0] for row in rows if row and row[0] in {"全场", "半场"}), "")
    total = row_by_first(rows, "总")
    venue = row_by_first(rows, "主") or row_by_first(rows, "客")
    recent = row_by_first(rows, "近6")
    parts: list[str] = []
    if total and len(total) >= 11:
        parts.append(f"{phase}总{total[1]}场 {total[2]}胜{total[3]}平{total[4]}负 得失{total[5]}/{total[6]} 排名{total[9]} 胜率{total[10]}")
    if venue and len(venue) >= 11:
        parts.append(f"{venue[0]}场{venue[1]}场 {venue[2]}胜{venue[3]}平{venue[4]}负 得失{venue[5]}/{venue[6]} 胜率{venue[10]}")
    if recent and len(recent) >= 10:
        parts.append(f"近6 {recent[2]}胜{recent[3]}平{recent[4]}负 得失{recent[5]}/{recent[6]} 胜率{recent[-1]}")
    return f"{team}：{'；'.join(parts)}" if parts else clean_text(" ".join(" ".join(row) for row in rows))[:260]


def summarize_panlu(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    team = team_from_rows(rows)
    phase = next((cell for row in rows for cell in row if cell in {"全场", "半场"}), "")
    total = row_by_first(rows, "总")
    venue = row_by_first(rows, "主场") or row_by_first(rows, "客场")
    parts: list[str] = []
    if total and len(total) >= 11:
        parts.append(f"{phase}让球 {total[2]}赢{total[3]}走{total[4]}输 让胜率{total[5]}")
        parts.append(f"大小 {total[7]}大({total[8]})/{total[9]}小({total[10]})")
    if venue and len(venue) >= 11:
        parts.append(f"{venue[0]}让球 {venue[2]}赢{venue[3]}走{venue[4]}输 让胜率{venue[5]}")
    return f"{team}：{'；'.join(parts)}" if parts else clean_text(" ".join(" ".join(row) for row in rows))[:260]


def js_array(js: str, name: str) -> list[list[Any]]:
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*(\[.*?\]);", js, re.S)
    if not match:
        return []
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return []
    return value if isinstance(value, list) else []


def js_int(js: str, name: str) -> int | None:
    match = re.search(rf"var\s+{re.escape(name)}\s*=\s*(\d+);", js)
    return safe_int(match.group(1)) if match else None


def score_pair(value: Any) -> tuple[int, int] | None:
    match = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(value or ""))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def summarize_records(records: list[list[Any]], team_id: int | None, *, limit: int, perspective_name: str) -> str:
    if not records or team_id is None:
        return ""
    win = draw = loss = gf = ga = half_draw = 0
    used = 0
    streak: list[str] = []
    for row in records[:limit]:
        if len(row) < 11:
            continue
        home_id = safe_int(row[4])
        away_id = safe_int(row[6])
        hg = safe_int(row[8])
        ag = safe_int(row[9])
        if home_id is None or away_id is None or hg is None or ag is None:
            continue
        if team_id == home_id:
            goals_for, goals_against = hg, ag
        elif team_id == away_id:
            goals_for, goals_against = ag, hg
        else:
            continue
        used += 1
        gf += goals_for
        ga += goals_against
        if goals_for > goals_against:
            win += 1
            streak.append("胜")
        elif goals_for < goals_against:
            loss += 1
            streak.append("负")
        else:
            draw += 1
            streak.append("平")
        half = score_pair(row[10])
        if half and half[0] == half[1]:
            half_draw += 1
    if not used:
        return ""
    return (
        f"{perspective_name}近{used}场 {win}胜{draw}平{loss}负，进失{gf}/{ga}，"
        f"半场平{half_draw}场，近5走势{'-'.join(streak[:5])}"
    )


def summarize_h2h(records: list[list[Any]], home_team_id: int | None, *, limit: int = 10) -> str:
    if not records or home_team_id is None:
        return ""
    win = draw = loss = gf = ga = used = 0
    for row in records[:limit]:
        if len(row) < 10:
            continue
        home_id = safe_int(row[4])
        away_id = safe_int(row[6])
        hg = safe_int(row[8])
        ag = safe_int(row[9])
        if home_id is None or away_id is None or hg is None or ag is None:
            continue
        if home_team_id == home_id:
            goals_for, goals_against = hg, ag
        elif home_team_id == away_id:
            goals_for, goals_against = ag, hg
        else:
            continue
        used += 1
        gf += goals_for
        ga += goals_against
        if goals_for > goals_against:
            win += 1
        elif goals_for < goals_against:
            loss += 1
        else:
            draw += 1
    return f"近{used}次交锋主队视角 {win}胜{draw}平{loss}负，进失{gf}/{ga}" if used else ""


def parse_odds_consensus(js: str) -> dict[str, Any]:
    match = re.search(r"var\s+game\s*=\s*Array\((.*?)\);", js, re.S)
    if not match:
        return {}
    entries = re.findall(r'"([^"]+)"', match.group(1))
    rows: list[dict[str, Any]] = []
    for entry in entries:
        parts = entry.split("|")
        if len(parts) < 17:
            continue
        open_home, open_draw, open_away = (safe_float(parts[3]), safe_float(parts[4]), safe_float(parts[5]))
        cur_home, cur_draw, cur_away = (safe_float(parts[10]), safe_float(parts[11]), safe_float(parts[12]))
        if not all(v and v > 0 for v in (open_home, open_draw, open_away, cur_home, cur_draw, cur_away)):
            continue
        rows.append({
            "company": parts[2],
            "open": {"home": open_home, "draw": open_draw, "away": open_away},
            "current": {"home": cur_home, "draw": cur_draw, "away": cur_away},
            "current_prob": {"home": safe_float(parts[13]), "draw": safe_float(parts[14]), "away": safe_float(parts[15])},
            "return_rate": safe_float(parts[16]),
        })
    if not rows:
        return {}

    def avg(key: str, outcome: str) -> float:
        values = [float(row[key][outcome]) for row in rows if row.get(key, {}).get(outcome)]
        return round(sum(values) / len(values), 3) if values else 0.0

    open_avg = {outcome: avg("open", outcome) for outcome in ("home", "draw", "away")}
    current_avg = {outcome: avg("current", outcome) for outcome in ("home", "draw", "away")}
    drift = {
        outcome: round(current_avg[outcome] / open_avg[outcome] - 1, 4)
        for outcome in ("home", "draw", "away")
        if open_avg[outcome] and current_avg[outcome]
    }
    key_names = ("Bet 365", "Macauslot", "William", "HK Jockey", "Crown", "Ladbrokes")
    providers = [
        row for row in rows
        if any(name.lower() in str(row["company"]).lower() for name in key_names)
    ][:8]
    return {
        "n_companies": len(rows),
        "open_avg": open_avg,
        "current_avg": current_avg,
        "drift": drift,
        "providers": providers,
    }


def drift_text(drift: dict[str, float]) -> str:
    label = {"home": "主胜", "draw": "平", "away": "客胜"}
    parts = [f"{label[key]}{value:+.1%}" for key, value in drift.items() if isinstance(value, (int, float))]
    return "欧赔均值 " + " ".join(parts) if parts else ""


def parse_detail(provider_id: str, analysis_html: str, analysis_js: str, odds_js: str) -> dict[str, Any]:
    h_jifen = tables_by_class(analysis_html, "h_jifen")
    g_jifen = tables_by_class(analysis_html, "g_jifen")
    h_panlu = tables_by_class(analysis_html, "h_panlu")
    g_panlu = tables_by_class(analysis_html, "g_panlu")
    home_team_id = js_int(analysis_js, "hometeamID") or js_int(analysis_html, "h2h_home")
    away_team_id = js_int(analysis_js, "guestteamID") or js_int(analysis_html, "h2h_away")
    home_recent = summarize_records(js_array(analysis_js, "h_data"), home_team_id, limit=10, perspective_name="主队")
    away_recent = summarize_records(js_array(analysis_js, "a_data"), away_team_id, limit=10, perspective_name="客队")
    h2h = summarize_h2h(js_array(analysis_js, "v_data"), home_team_id, limit=10)
    odds_consensus = parse_odds_consensus(odds_js)
    home_full = summarize_jifen(h_jifen[0]) if len(h_jifen) > 0 else ""
    away_full = summarize_jifen(g_jifen[0]) if len(g_jifen) > 0 else ""
    home_half = summarize_jifen(h_jifen[1]) if len(h_jifen) > 1 else ""
    away_half = summarize_jifen(g_jifen[1]) if len(g_jifen) > 1 else ""
    home_panlu = summarize_panlu(h_panlu[0]) if len(h_panlu) > 0 else ""
    away_panlu = summarize_panlu(g_panlu[0]) if len(g_panlu) > 0 else ""
    home_half_panlu = summarize_panlu(h_panlu[1]) if len(h_panlu) > 1 else ""
    away_half_panlu = summarize_panlu(g_panlu[1]) if len(g_panlu) > 1 else ""
    highlights = [
        item for item in [
            extract_match_meta(analysis_html).get("venue_weather", ""),
            home_recent,
            away_recent,
            h2h,
            drift_text(odds_consensus.get("drift", {})) if odds_consensus else "",
        ] if item
    ][:8]
    return {
        "provider_match_id": provider_id,
        "title": title(analysis_html),
        "description": description(analysis_html),
        "match_meta": extract_match_meta(analysis_html),
        "league": {
            "home_full": home_full,
            "away_full": away_full,
            "home_half": home_half,
            "away_half": away_half,
        },
        "panlu": {
            "home_full": home_panlu,
            "away_full": away_panlu,
            "home_half": home_half_panlu,
            "away_half": away_half_panlu,
        },
        "recent": {
            "home_summary": home_recent,
            "away_summary": away_recent,
            "h2h_summary": h2h,
        },
        "odds_consensus": odds_consensus,
        "highlights": highlights,
        "urls": {
            "data": ANALYSIS_URL.format(provider_id=provider_id),
            "recommendation": f"https://guess.nowscore.com/news/Recommend/{provider_id}.htm",
            "asian": f"https://live.nowscore.com/odds/match/{provider_id}.htm",
            "europe": f"https://live.nowscore.com/1x2/{provider_id}.htm",
        },
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS nowscore_match_details (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            provider_match_id TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT,
            description TEXT,
            kickoff_context TEXT,
            home_recent_summary TEXT,
            away_recent_summary TEXT,
            h2h_summary TEXT,
            league_summary TEXT,
            panlu_summary TEXT,
            market_summary TEXT,
            highlights_json TEXT,
            odds_consensus_json TEXT,
            payload_json TEXT,
            raw_sha1 TEXT,
            error TEXT,
            PRIMARY KEY(issue, match_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_nowscore_match_details_provider
          ON nowscore_match_details(provider_match_id);
        """
    )


def select_matches(conn: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    where = ["n.provider_match_id IS NOT NULL", "n.provider_match_id != ''"]
    params: list[Any] = []
    if args.issue:
        where.append("n.issue=?")
        params.append(args.issue)
    if args.match_idx:
        where.append("n.match_idx=?")
        params.append(args.match_idx)
    if args.provider_match_id:
        where.append("n.provider_match_id=?")
        params.append(str(args.provider_match_id))
    if not args.force:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=args.stale_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        where.append("(d.fetched_at IS NULL OR d.fetched_at < ?)")
        params.append(cutoff)
    sql = f"""
        SELECT
          n.issue,
          n.match_idx,
          n.provider_match_id,
          n.analysis_url,
          n.recommendation_url,
          n.asian_url,
          n.europe_url
        FROM nowscore_bjdc_matches n
        LEFT JOIN nowscore_match_details d
          ON d.issue=n.issue
         AND d.match_idx=n.match_idx
        WHERE {" AND ".join(where)}
        ORDER BY CAST(n.issue AS INTEGER) DESC, n.match_idx
        LIMIT ?
    """
    params.append(args.limit)
    return list(conn.execute(sql, params))


def upsert_detail(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    payload: dict[str, Any],
    *,
    status: str,
    raw_html: str,
    error: str = "",
) -> None:
    recent = payload.get("recent", {})
    league = payload.get("league", {})
    panlu = payload.get("panlu", {})
    odds = payload.get("odds_consensus", {})
    highlights = payload.get("highlights", [])
    conn.execute(
        """
        INSERT INTO nowscore_match_details(
            issue, match_idx, provider_match_id, fetched_at, status, title, description,
            kickoff_context, home_recent_summary, away_recent_summary, h2h_summary,
            league_summary, panlu_summary, market_summary, highlights_json,
            odds_consensus_json, payload_json, raw_sha1, error
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(issue, match_idx) DO UPDATE SET
            provider_match_id=excluded.provider_match_id,
            fetched_at=excluded.fetched_at,
            status=excluded.status,
            title=excluded.title,
            description=excluded.description,
            kickoff_context=excluded.kickoff_context,
            home_recent_summary=excluded.home_recent_summary,
            away_recent_summary=excluded.away_recent_summary,
            h2h_summary=excluded.h2h_summary,
            league_summary=excluded.league_summary,
            panlu_summary=excluded.panlu_summary,
            market_summary=excluded.market_summary,
            highlights_json=excluded.highlights_json,
            odds_consensus_json=excluded.odds_consensus_json,
            payload_json=excluded.payload_json,
            raw_sha1=excluded.raw_sha1,
            error=excluded.error
        """,
        (
            row["issue"],
            row["match_idx"],
            row["provider_match_id"],
            now_utc(),
            status,
            payload.get("title", ""),
            payload.get("description", ""),
            payload.get("match_meta", {}).get("raw", ""),
            recent.get("home_summary", ""),
            recent.get("away_summary", ""),
            recent.get("h2h_summary", ""),
            " | ".join(value for value in [
                league.get("home_full", ""),
                league.get("away_full", ""),
                league.get("home_half", ""),
                league.get("away_half", ""),
            ] if value),
            " | ".join(value for value in [
                panlu.get("home_full", ""),
                panlu.get("away_full", ""),
                panlu.get("home_half", ""),
                panlu.get("away_half", ""),
            ] if value),
            drift_text(odds.get("drift", {})) if isinstance(odds, dict) else "",
            json.dumps(highlights, ensure_ascii=False),
            json.dumps(odds, ensure_ascii=False),
            json.dumps(payload, ensure_ascii=False),
            hashlib.sha1(raw_html.encode("utf-8", errors="ignore")).hexdigest() if raw_html else "",
            error,
        ),
    )


def scrape_one(conn: sqlite3.Connection, scraper: Scraper, row: sqlite3.Row) -> bool:
    provider_id = str(row["provider_match_id"])
    analysis_url = str(row["analysis_url"] or ANALYSIS_URL.format(provider_id=provider_id))
    try:
        analysis_html = scraper.get(analysis_url, encoding="utf-8", referer=REFERER)
        analysis_js = scraper.get(ANALYSIS_JS_URL.format(provider_id=provider_id), encoding="utf-8", referer=analysis_url)
        odds_js = scraper.get(ODDS_1X2_JS_URL.format(provider_id=provider_id), encoding="utf-8", referer=analysis_url)
        if not analysis_html or "Restricted Access" in analysis_html:
            upsert_detail(conn, row, {"provider_match_id": provider_id}, status="blocked", raw_html=analysis_html, error="blocked_or_empty")
            return False
        payload = parse_detail(provider_id, analysis_html, analysis_js, odds_js)
        upsert_detail(conn, row, payload, status="ok", raw_html=analysis_html)
        return True
    except Exception as exc:
        upsert_detail(conn, row, {"provider_match_id": provider_id}, status="error", raw_html="", error=str(exc))
        return False


def scrape_issue(conn: sqlite3.Connection, issue: str, args: argparse.Namespace) -> int:
    original_issue = getattr(args, "issue", None)
    args.issue = issue
    try:
        rows = select_matches(conn, args)
    finally:
        args.issue = original_issue
    scraper = Scraper(min_interval=max(float(args.sleep), 0.0), max_retries=2, timeout=int(args.timeout))
    ok = 0
    for idx, row in enumerate(rows):
        if idx and args.sleep:
            time.sleep(float(args.sleep))
        success = scrape_one(conn, scraper, row)
        conn.commit()
        ok += int(success)
        print(
            f"[nowscore_detail] issue={row['issue']} idx={row['match_idx']} id={row['provider_match_id']} status={'ok' if success else 'failed'}",
            flush=True,
        )
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue")
    parser.add_argument("--match-idx", type=int)
    parser.add_argument("--provider-match-id")
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument("--stale-hours", type=float, default=6.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--user-agent", default=DEFAULT_UA)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        create_schema(conn)
        rows = select_matches(conn, args)
        scraper = Scraper(min_interval=max(args.sleep, 0.0), max_retries=2, timeout=args.timeout)
        ok = 0
        for idx, row in enumerate(rows):
            if idx and args.sleep:
                time.sleep(args.sleep)
            success = scrape_one(conn, scraper, row)
            conn.commit()
            ok += int(success)
            print(
                f"[nowscore_detail] issue={row['issue']} idx={row['match_idx']} id={row['provider_match_id']} status={'ok' if success else 'failed'}",
                flush=True,
            )
        print(f"[summary] rows={len(rows)} ok={ok}", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
