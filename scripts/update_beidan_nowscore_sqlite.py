#!/usr/bin/env python3
"""Fetch Beidan/Nowscore market snapshots into the normalized SQLite schema.

This is a Python port of the vendor workbook's `下载()` macro.  It does not
execute Excel or Selenium.  The updater writes the same normalized tables used
by `scripts/build_beidan_modeling_tables.py`:

* matches
* market_snapshots
* issue_list

The odds source is Titan007/Nowscore.  For euro 1x2, it records initial, 10h,
1h, and final snapshots plus the corresponding Kelly values.  Asian handicap
and over/under are optional but enabled by default.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.convert_beidan_xlsm_to_sqlite import create_schema, make_indexes  # noqa: E402


BOOKS_1X2 = [
    ("皇冠", "545"),
    ("澳门", "80"),
    ("Bet365", "281"),
    ("香港马会", "432"),
    ("韦德", "81"),
    ("威廉", "115"),
    ("立博", "82"),
    ("易博胜", "90"),
    ("Interwet", "104"),
    ("Bwin", "255"),
    ("竞彩足球", "1129"),
    ("10bet", "16"),
    ("Oddset", "370"),
    ("Pinna*", "177"),
    ("18*", "976"),
]

BOOKS_ASIAN = [
    ("皇冠", 3),
    ("澳门", 1),
    ("Bet365", 8),
    ("香港马会", 48),
    ("韦德", 14),
    ("易胜博", 12),
    ("明升", 17),
    ("金宝博", 23),
    ("利*", 31),
    ("12*", 24),
    ("盈*", 35),
    ("18*", 42),
    ("平*", 47),
    ("Interwet*", 19),
    ("10*", 22),
    ("威廉", 9),
    ("Bwin", 49),
    ("立博", 4),
]

SNAPSHOTS = ("initial", "1h", "10h", "final")
RESULT_LABEL_TO_CODE = {"胜": "3", "平": "1", "负": "0"}
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


@dataclass(frozen=True)
class MatchRow:
    issue: str
    match_idx: int
    provider_match_id: str
    league: str | None
    kickoff_ts: str | None
    home_rank: str | None
    home: str | None
    score: str | None
    away: str | None
    away_rank: str | None
    handicap_line: float | None
    halftime_score: str | None
    result_label: str | None
    total_goals: int | None
    half_full: str | None
    ts_10h: str | None
    home_team_id: str | None
    away_team_id: str | None
    sclassid: str | None


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = html.unescape(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def to_float(value: object) -> float | None:
    if value in ("", None):
        return None
    try:
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def to_int(value: object) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def excel_serial(dt: datetime | None) -> float | None:
    if dt is None:
        return None
    base = datetime(1899, 12, 30)
    return (dt - base).total_seconds() / 86400.0


def dt_text(dt: datetime | None) -> str | None:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def parse_dt(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def parse_titan_match_time(raw: str) -> datetime | None:
    """Parse Titan MatchTime and convert to China/HK local time like the VBA macro."""
    if not raw:
        return None
    normalized = raw.replace("-1", "")
    parts = normalized.split(",")
    if len(parts) != 6:
        return None
    try:
        utcish = datetime(
            int(parts[0]),
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
            int(parts[4]),
            int(parts[5]),
        )
    except ValueError:
        return None
    return utcish + timedelta(hours=8)


def parse_detail_time(match_dt: datetime, time_text: str, year_text: str | None = None) -> datetime | None:
    if not time_text:
        return None
    year = to_int(year_text) or match_dt.year
    try:
        parsed = datetime.strptime(f"{year}-{time_text}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    # Keep the VBA's January/December correction for records without usable year.
    if year_text in ("", None) and parsed.month == 12 and match_dt.month == 1:
        parsed = parsed.replace(year=match_dt.year - 1)
    return parsed


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "close",
        }
    )
    return s


def http_get(
    s: requests.Session,
    url: str,
    *,
    referer: str | None = None,
    mobile: bool = False,
    no_cache: bool = True,
    timeout: int = 15,
    retries: int = 4,
    backoff: float = 0.8,
) -> str:
    headers: dict[str, str] = {}
    if no_cache:
        headers["If-Modified-Since"] = "0"
    if referer:
        headers["Referer"] = referer
    if mobile:
        headers["User-Agent"] = MOBILE_UA
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = s.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(backoff * attempt)
    assert last_exc is not None
    raise last_exc


def first_regex(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text, re.S)
    return m.group(1) if m else None


def array_items(text: str, var_name: str) -> list[str]:
    m = re.search(rf"var\s+{re.escape(var_name)}\s*=\s*Array\((.*?)\);", text, re.S)
    if not m:
        return []
    return re.findall(r'"([^"]*)"', m.group(1))


def parse_score(score: str | None) -> tuple[str | None, int | None]:
    if not score or "-" not in score:
        return None, None
    try:
        home_s, away_s = score.split("-", 1)
        home_goals = int(home_s)
        away_goals = int(away_s)
    except ValueError:
        return None, None
    if home_goals > away_goals:
        label = "胜"
    elif home_goals == away_goals:
        label = "平"
    else:
        label = "负"
    return label, home_goals + away_goals


def parse_cp_issue(s: requests.Session, issue: str) -> list[dict[str, object]]:
    url = f"https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum={issue}"
    text = http_get(s, url)
    return parse_cp_issue_html(text, issue)


def _parse_cp_issue_table(text: str, issue: str) -> list[dict[str, object]]:
    """Parse the visible table rows, which may omit settled or cancelled fixtures."""

    rows: list[dict[str, object]] = []
    for part in text.split('<tr id="')[1:]:
        row_html = '<tr id="' + part.split("</tr>", 1)[0] + "</tr>"
        soup = BeautifulSoup(row_html, "lxml")
        tr = soup.find("tr")
        if tr is None:
            continue
        provider_match_id = None
        for a in soup.find_all("a"):
            href = a.get("href") or ""
            if "Panlu.aspx?id=" in href:
                provider_match_id = href.split("Panlu.aspx?id=", 1)[1].split("&", 1)[0]
                break
        if not provider_match_id:
            continue
        home_node = soup.find(id=re.compile(r"^HomeTeam_"))
        away_node = soup.find(id=re.compile(r"^GuestTeam_"))
        cells = [clean_text(td.get_text(" ", strip=True)) or "" for td in soup.find_all("td")]
        match_idx = to_int(tr.get("matchid")) or to_int(cells[0] if cells else None)
        if match_idx is None:
            continue
        handicap_text = cells[5] if len(cells) > 5 else None
        score = cells[6] if len(cells) > 6 else None
        halftime = cells[8] if len(cells) > 8 else None
        rows.append(
            {
                "issue": str(issue),
                "match_idx": match_idx,
                "provider_match_id": str(provider_match_id),
                "league": clean_text(tr.get("gamename")) or (cells[1] if len(cells) > 1 else None),
                "home": clean_text(home_node.get_text(" ", strip=True)) if home_node else (cells[4] if len(cells) > 4 else None),
                "away": clean_text(away_node.get_text(" ", strip=True)) if away_node else (cells[7] if len(cells) > 7 else None),
                "score": score,
                "halftime_score": halftime,
                "handicap_line": to_float(tr.get("polygoal")) if tr.get("polygoal") not in ("", None) else to_float(handicap_text),
            }
        )
    rows.sort(key=lambda r: int(r["match_idx"]))
    return rows


def _parse_js_string(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        quote = value[0]
        body = value[1:-1]
        body = body.replace(r"\\", "\\")
        body = body.replace(rf"\{quote}", quote)
        return clean_text(body)
    return clean_text(value)


def _parse_js_date(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.fullmatch(
        r"new\s+Date\((\d{4}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})\)",
        value.strip(),
    )
    if not match:
        return None
    year, zero_based_month, day, hour, minute, second = map(int, match.groups())
    try:
        return datetime(year, zero_based_month + 1, day, hour, minute, second)
    except ValueError:
        return None


def _parse_cp_issue_matrix(text: str, issue: str) -> list[dict[str, object]]:
    """Parse Nowscore's complete ``M[row][field]`` issue membership matrix.

    The visible HTML table can omit already settled or cancelled fixtures. The
    embedded matrix retains their provider IDs and therefore defines the
    authoritative issue membership for historical recovery.
    """

    matrix: dict[int, dict[int, str]] = {}
    for outer, field, value in re.findall(
        r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.*?);", text, flags=re.S
    ):
        matrix.setdefault(int(outer), {})[int(field)] = value.strip()

    rows: list[dict[str, object]] = []
    seen_slots: set[int] = set()
    seen_providers: set[str] = set()
    for outer in sorted(matrix):
        fields = matrix[outer]
        match_idx = to_int(fields.get(16)) or outer
        provider_match_id = _parse_js_string(fields.get(0))
        if match_idx is None or not provider_match_id:
            continue
        if match_idx in seen_slots:
            raise ValueError(f"duplicate Nowscore issue slot {issue}/{match_idx}")
        if provider_match_id in seen_providers:
            raise ValueError(
                f"duplicate Nowscore provider id {provider_match_id} in issue {issue}"
            )
        seen_slots.add(match_idx)
        seen_providers.add(provider_match_id)
        handicap_line = to_float(fields.get(4))
        if handicap_line is not None and abs(handicap_line) >= 90:
            handicap_line = None
        rows.append(
            {
                "issue": str(issue),
                "match_idx": match_idx,
                "provider_match_id": provider_match_id,
                "league": None,
                "issue_deadline_ts": dt_text(_parse_js_date(fields.get(3))),
                "home": _parse_js_string(fields.get(17)),
                "away": _parse_js_string(fields.get(20)),
                "score": None,
                "halftime_score": None,
                "handicap_line": handicap_line,
            }
        )
    return rows


def parse_cp_issue_html(text: str, issue: str) -> list[dict[str, object]]:
    """Parse one archived Beijing issue page without performing network I/O.

    Complete membership comes from the embedded JavaScript matrix. Visible
    rows only enrich fields such as league and score. Legacy pages without an
    ``M`` matrix continue to use their visible rows.
    """

    visible_rows = _parse_cp_issue_table(text, issue)
    matrix_rows = _parse_cp_issue_matrix(text, issue)
    if not matrix_rows:
        return visible_rows

    visible_by_slot = {int(row["match_idx"]): row for row in visible_rows}
    merged: list[dict[str, object]] = []
    for matrix_row in matrix_rows:
        visible = visible_by_slot.get(int(matrix_row["match_idx"]), {})
        row = dict(matrix_row)
        for key in ("league", "home", "away", "score", "halftime_score"):
            if visible.get(key) not in (None, ""):
                row[key] = visible[key]
        if visible.get("handicap_line") is not None:
            row["handicap_line"] = visible["handicap_line"]
        merged.append(row)
    return merged


def parse_titan_1x2(s: requests.Session, provider_match_id: str) -> tuple[dict[str, object], list[tuple], list[tuple]]:
    url = f"https://1x2d.titan007.com/{provider_match_id}.js"
    text = http_get(
        s,
        url,
        referer=f"https://live.nowscore.com/1x2/{provider_match_id}.htm",
        no_cache=False,
    )
    return parse_titan_1x2_text(text)


def parse_titan_1x2_text(text: str) -> tuple[dict[str, object], list[tuple], list[tuple]]:
    """Parse a Titan Euro history payload without performing network I/O."""
    match_time_raw = first_regex(text, r'MatchTime="([^"]+)"')
    kickoff = parse_titan_match_time(match_time_raw or "")
    ts_10h = kickoff - timedelta(hours=10) if kickoff else None
    ts_1h = kickoff - timedelta(hours=1) if kickoff else None

    meta = {
        "kickoff": kickoff,
        "ts_10h": ts_10h,
        "home_rank": clean_text(first_regex(text, r'var\s+hOrder="([^"]*)"')),
        "away_rank": clean_text(first_regex(text, r'var\s+gOrder="([^"]*)"')),
        "home_team_id": first_regex(text, r"hometeamID=([^;]+);"),
        "away_team_id": first_regex(text, r"guestteamID=([^;]+);"),
        "sclassid": first_regex(text, r"sclassId=([^;]+);"),
    }

    game_by_company: dict[str, list[str]] = {}
    record_to_company: dict[str, str] = {}
    for item in array_items(text, "game"):
        fields = item.split("|")
        if len(fields) < 3:
            continue
        game_by_company[fields[0]] = fields
        record_to_company[fields[1]] = fields[0]

    detail_by_record: dict[str, list[list[str]]] = {}
    for item in array_items(text, "gameDetail"):
        if "^" not in item:
            continue
        record_id, detail = item.split("^", 1)
        records = [part.split("|") for part in detail.split(";") if part]
        detail_by_record[record_id] = records

    odds_rows: list[tuple] = []
    kelly_rows: list[tuple] = []
    for bookmaker, company_id in BOOKS_1X2:
        game_fields = game_by_company.get(company_id)
        records = detail_by_record.get(game_fields[1], []) if game_fields and len(game_fields) > 1 else []
        snapshots = select_1x2_snapshots(records, kickoff, ts_10h, ts_1h)
        for snapshot in SNAPSHOTS:
            odds = snapshots.get(snapshot)
            if odds:
                odds_rows.append((None, "euro_1x2", bookmaker, snapshot, to_float(odds[0]), to_float(odds[1]), to_float(odds[2])))
                kelly_rows.append((None, "kelly_1x2", bookmaker, snapshot, to_float(odds[4]), to_float(odds[5]), to_float(odds[6])))
            else:
                odds_rows.append((None, "euro_1x2", bookmaker, snapshot, None, None, None))
                kelly_rows.append((None, "kelly_1x2", bookmaker, snapshot, None, None, None))
    return meta, odds_rows, kelly_rows


def select_1x2_snapshots(
    records: list[list[str]],
    kickoff: datetime | None,
    ts_10h: datetime | None,
    ts_1h: datetime | None,
) -> dict[str, list[str] | None]:
    out: dict[str, list[str] | None] = {name: None for name in SNAPSHOTS}
    if not records:
        return out
    out["final"] = records[0]
    out["initial"] = records[-1]
    if not kickoff:
        return out
    for snapshot, cutoff in (("10h", ts_10h), ("1h", ts_1h)):
        if cutoff is None:
            continue
        for record in records:
            if len(record) < 8:
                continue
            record_dt = parse_detail_time(kickoff, record[3], record[7])
            if record_dt and record_dt <= cutoff:
                out[snapshot] = record
                break
    return out


def parse_line_time(value: str | None) -> datetime | None:
    if not value or len(value) < 12:
        return None
    try:
        return datetime.strptime(value[:12], "%Y%m%d%H%M")
    except ValueError:
        return None


def fetch_line_market(
    s: requests.Session,
    *,
    provider_match_id: str,
    kickoff: datetime | None,
    market: str,
    oddskind: int,
    bookmaker: str,
    company_id: int,
    delay: float,
) -> list[tuple]:
    if kickoff is None:
        return [(None, market, bookmaker, snapshot, None, None, None) for snapshot in SNAPSHOTS]
    matchtime = kickoff.strftime("%Y%m%d%H%M%S")
    url = (
        "https://m.titan007.com/HandicapDataInterface.ashx"
        f"?scheid={provider_match_id}&type=3&oddskind={oddskind}"
        f"&companyid={company_id}&matchtime={matchtime}&isHalf=0"
    )
    text = http_get(
        s,
        url,
        referer=f"https://m.titan007.com/Analy/Handicap.aspx?id={provider_match_id}",
        mobile=True,
        timeout=20,
    )
    if delay > 0:
        time.sleep(delay)
    if "访问频率" in text or "WAF" in text:
        raise RuntimeError(f"line market blocked by WAF for {provider_match_id}/{company_id}/{oddskind}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"line market returned non-JSON for {provider_match_id}/{company_id}/{oddskind}") from exc
    records = [
        rec
        for rec in data
        if isinstance(rec, dict)
        and rec.get("Score") in ("早", "", None)
        and rec.get("IsClosed") in ("", None)
        and parse_line_time(rec.get("ModifyTime")) is not None
    ]
    # Titan returns latest first; the VBA loop effectively walks oldest to latest.
    records.sort(key=lambda rec: parse_line_time(rec.get("ModifyTime")) or datetime.min)
    selected: dict[str, dict[str, object] | None] = {name: None for name in SNAPSHOTS}
    if records:
        selected["initial"] = records[0]
        selected["final"] = records[-1]
    for snapshot, cutoff in (("10h", kickoff - timedelta(hours=10)), ("1h", kickoff - timedelta(hours=1))):
        for rec in records:
            rec_dt = parse_line_time(rec.get("ModifyTime"))
            if rec_dt and rec_dt <= cutoff:
                selected[snapshot] = rec
            elif rec_dt and rec_dt > cutoff:
                break
    out: list[tuple] = []
    for snapshot in SNAPSHOTS:
        rec = selected.get(snapshot)
        if rec:
            out.append(
                (
                    None,
                    market,
                    bookmaker,
                    snapshot,
                    to_float(rec.get("HomeOdds")),
                    to_float(rec.get("PanKou")),
                    to_float(rec.get("AwayOdds")),
                )
            )
        else:
            out.append((None, market, bookmaker, snapshot, None, None, None))
    return out


def ensure_schema(conn: sqlite3.Connection) -> None:
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='matches'").fetchone()
    if table is None:
        create_schema(conn)


def delete_issue(conn: sqlite3.Connection, issue: str) -> None:
    match_ids = [row[0] for row in conn.execute("SELECT match_id FROM matches WHERE issue=?", (issue,))]
    if match_ids:
        placeholders = ",".join("?" for _ in match_ids)
        conn.execute(f"DELETE FROM market_snapshots WHERE match_id IN ({placeholders})", match_ids)
        conn.execute(f"DELETE FROM exotic_odds WHERE match_id IN ({placeholders})", match_ids)
        conn.execute(f"DELETE FROM matches WHERE match_id IN ({placeholders})", match_ids)
    conn.execute("DELETE FROM issue_list WHERE issue=?", (issue,))


def next_ids(conn: sqlite3.Connection) -> tuple[int, int]:
    match_id = conn.execute("SELECT COALESCE(MAX(match_id), 0) + 1 FROM matches").fetchone()[0]
    sheet_row = conn.execute("SELECT COALESCE(MAX(sheet_row), 2) + 1 FROM matches").fetchone()[0]
    return int(match_id), int(sheet_row)


def result_from_score(score: str | None) -> tuple[str | None, int | None]:
    label, total = parse_score(score)
    return label, total


def half_full_from_scores(halftime: str | None, fulltime: str | None) -> str | None:
    ht_label, _ = parse_score(halftime)
    ft_label, _ = parse_score(fulltime)
    if not ht_label or not ft_label:
        return None
    return ht_label + ft_label


def fetch_issue(
    conn: sqlite3.Connection,
    s: requests.Session,
    issue: str,
    *,
    replace: bool,
    skip_existing: bool,
    include_lines: bool,
    line_delay: float,
    match_delay: float,
    progress_every: int,
    max_matches: int | None,
) -> dict[str, object]:
    if replace:
        delete_issue(conn, issue)
    cp_rows = parse_cp_issue(s, issue)
    if skip_existing:
        existing = {
            int(row[0])
            for row in conn.execute("SELECT match_idx FROM matches WHERE issue=? AND match_idx IS NOT NULL", (issue,))
        }
        cp_rows = [row for row in cp_rows if int(row["match_idx"]) not in existing]
    if max_matches is not None:
        cp_rows = cp_rows[:max_matches]
    match_id, sheet_row = next_ids(conn)
    inserted_matches = 0
    inserted_markets = 0
    line_errors = 0
    conn.execute("INSERT OR IGNORE INTO issue_list(issue) VALUES (?)", (issue,))

    for cp in cp_rows:
        provider_match_id = str(cp["provider_match_id"])
        try:
            meta, odds_rows, kelly_rows = parse_titan_1x2(s, provider_match_id)
        except Exception as exc:  # noqa: BLE001 - collect and continue per match.
            print(f"[warn] issue={issue} match={provider_match_id} 1x2 failed: {exc}", file=sys.stderr)
            continue
        kickoff = meta.get("kickoff")
        if isinstance(kickoff, datetime) and kickoff < datetime(2020, 1, 1):
            continue

        score = cp.get("score")
        result_label, total_goals = result_from_score(str(score) if score else None)
        half_full = half_full_from_scores(str(cp.get("halftime_score")) if cp.get("halftime_score") else None, str(score) if score else None)
        ts_10h = meta.get("ts_10h") if isinstance(meta.get("ts_10h"), datetime) else None
        row = (
            match_id,
            sheet_row,
            issue,
            int(cp["match_idx"]),
            excel_serial(kickoff if isinstance(kickoff, datetime) else None),
            dt_text(kickoff if isinstance(kickoff, datetime) else None),
            cp.get("league"),
            meta.get("home_rank"),
            cp.get("home"),
            score,
            cp.get("away"),
            meta.get("away_rank"),
            cp.get("handicap_line"),
            cp.get("halftime_score"),
            result_label,
            total_goals,
            half_full,
            provider_match_id,
            excel_serial(ts_10h),
            dt_text(ts_10h),
            meta.get("home_team_id"),
            meta.get("away_team_id"),
            meta.get("sclassid"),
        )
        conn.execute(
            """
            INSERT INTO matches (
                match_id, sheet_row, issue, match_idx, kickoff_serial, kickoff_ts,
                league, home_rank, home, score, away, away_rank, handicap_line,
                halftime_score, result_label, total_goals, half_full,
                provider_match_id, ts_10h_serial, ts_10h, home_team_id,
                away_team_id, sclassid
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            row,
        )

        market_rows = []
        for source_rows in (odds_rows, kelly_rows):
            for _, market, bookmaker, snapshot, v1, v2, v3 in source_rows:
                market_rows.append((match_id, market, bookmaker, snapshot, v1, v2, v3))

        if include_lines:
            for bookmaker, company_id in BOOKS_ASIAN:
                for market, oddskind in (("asian_handicap", 0), ("over_under", 1)):
                    try:
                        line_rows = fetch_line_market(
                            s,
                            provider_match_id=provider_match_id,
                            kickoff=kickoff if isinstance(kickoff, datetime) else None,
                            market=market,
                            oddskind=oddskind,
                            bookmaker=bookmaker,
                            company_id=company_id,
                            delay=line_delay,
                        )
                    except Exception as exc:  # noqa: BLE001
                        line_errors += 1
                        print(
                            f"[warn] issue={issue} match={provider_match_id} {market}/{bookmaker} failed: {exc}",
                            file=sys.stderr,
                        )
                        line_rows = [(None, market, bookmaker, snapshot, None, None, None) for snapshot in SNAPSHOTS]
                    for _, market2, bookmaker2, snapshot, v1, v2, v3 in line_rows:
                        market_rows.append((match_id, market2, bookmaker2, snapshot, v1, v2, v3))

        conn.executemany(
            "INSERT INTO market_snapshots(match_id, market, bookmaker, snapshot, v1, v2, v3) VALUES (?,?,?,?,?,?,?)",
            market_rows,
        )
        inserted_markets += len(market_rows)
        inserted_matches += 1
        if progress_every > 0 and inserted_matches % progress_every == 0:
            print(
                f"[progress] issue={issue} inserted={inserted_matches}/{len(cp_rows)} "
                f"last_match_idx={cp['match_idx']}",
                flush=True,
            )
        match_id += 1
        sheet_row += 1
        if match_delay > 0:
            time.sleep(match_delay)

    return {
        "issue": issue,
        "cp_rows": len(cp_rows),
        "inserted_matches": inserted_matches,
        "inserted_market_rows": inserted_markets,
        "line_errors": line_errors,
    }


def parse_issues(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                width = max(len(start), len(end))
                out.extend(str(i).zfill(width) for i in range(int(start), int(end) + 1))
            else:
                out.append(part)
    seen: set[str] = set()
    unique: list[str] = []
    for issue in out:
        if issue not in seen:
            unique.append(issue)
            seen.add(issue)
    return unique


def update_source_meta(conn: sqlite3.Connection, *, issues: list[str], include_lines: bool) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO source_meta(key, value) VALUES (?, ?)",
        [
            ("nowscore_update_last_run", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
            ("nowscore_update_issues", ",".join(issues)),
            ("nowscore_update_include_lines", str(int(include_lines))),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", required=True, type=Path)
    parser.add_argument("--issues", nargs="+", required=True, help="Issue ids or ranges, e.g. 25042 26011-26051.")
    parser.add_argument("--replace", action="store_true", help="Delete existing rows for each issue before inserting.")
    parser.add_argument("--skip-existing", action="store_true", help="Skip issue/match_idx pairs already present in the target DB.")
    parser.add_argument("--no-lines", action="store_true", help="Skip Asian handicap and over/under markets.")
    parser.add_argument("--line-delay", type=float, default=0.0, help="Delay between line-market requests.")
    parser.add_argument("--match-delay", type=float, default=0.15, help="Delay between matches.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N inserted matches.")
    parser.add_argument("--max-matches", type=int, help="Fetch only first N matches per issue for smoke testing.")
    parser.add_argument("--skip-indexes", action="store_true", help="Do not build indexes on a newly created DB.")
    args = parser.parse_args()

    issues = parse_issues(args.issues)
    args.sqlite.parent.mkdir(parents=True, exist_ok=True)
    created = not args.sqlite.exists()
    conn = sqlite3.connect(args.sqlite)
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    ensure_schema(conn)
    s = session()

    summaries: list[dict[str, object]] = []
    started = time.time()
    for issue in issues:
        conn.execute("BEGIN")
        summary = fetch_issue(
            conn,
            s,
            issue,
            replace=args.replace,
            skip_existing=args.skip_existing,
            include_lines=not args.no_lines,
            line_delay=args.line_delay,
            match_delay=args.match_delay,
            progress_every=args.progress_every,
            max_matches=args.max_matches,
        )
        conn.execute("COMMIT")
        summaries.append(summary)
        elapsed = time.time() - started
        print(
            f"[issue] {issue} matches={summary['inserted_matches']}/{summary['cp_rows']} "
            f"markets={summary['inserted_market_rows']} line_errors={summary['line_errors']} "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )

    update_source_meta(conn, issues=issues, include_lines=not args.no_lines)
    conn.commit()
    if created and not args.skip_indexes:
        make_indexes(conn)
    conn.close()
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
