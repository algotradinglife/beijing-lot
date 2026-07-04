#!/usr/bin/env python3
"""Collect per-match intelligence into SQLite.

This is intentionally separate from the market/detail scrapers.  It fetches
editorial/context sources, stores raw compact source payloads, and writes a
short digest that the decision dashboard can show without exposing noisy pages.
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
MOBILE_URL = "https://app-live-m.500.com/detail/football/{fid}/analysis/zj"
REFERER = "https://live.500.com/zqdc.php"

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
PC_STAGE_RE = re.compile(
    r'<div class="odds_hd_ls">\s*<a[^>]*class="hd_name"[^>]*>(.*?)</a>',
    re.S | re.I,
)

KEYWORDS = (
    "出线",
    "晋级",
    "淘汰",
    "战意",
    "轮换",
    "体能",
    "伤",
    "防线",
    "状态",
    "锁定",
    "头名",
    "小组",
    "分组",
    "决赛",
)


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


def text_lines(raw: str) -> list[str]:
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = TAG_RE.sub("\n", text)
    text = html.unescape(text)
    return [line.strip() for line in re.split(r"\s*\n+\s*", text) if line.strip()]


def first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def shorten(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，。；、 ") + "…"


def sha1_text(*parts: str) -> str:
    h = hashlib.sha1()
    for part in parts:
        h.update(part.encode("utf-8", errors="ignore"))
    return h.hexdigest()


def parse_pc_stage(text: str) -> str:
    match = PC_STAGE_RE.search(text)
    return clean_text(match.group(1)) if match else ""


def parse_macau_recommendation(text: str) -> dict[str, Any]:
    lines = text_lines(text)
    start = next((idx for idx, line in enumerate(lines) if "澳门心水推荐" in line), -1)
    if start < 0:
        return {"pick": "", "record": "", "comment": ""}
    tail = lines[start : start + 80]
    pick = ""
    record = ""
    comments: list[str] = []
    for idx, line in enumerate(tail):
        if line.startswith("推介"):
            pick = first_nonempty(line.replace("推介", "").replace("-", "").strip(), tail[idx + 1] if idx + 1 < len(tail) else "")
            continue
        if line.startswith("对赛成绩"):
            record = line
            continue
        if line.startswith(("提醒：", "500网仅提供")):
            break
        if line in {"W", "D", "L", "胜", "和", "负", "(", ")", "、", "="}:
            continue
        if len(line) >= 16 and not line.endswith("推荐") and "澳门心水" not in line:
            comments.append(line)
    # The useful editorial sentence is usually the longest natural-language line.
    comments = sorted(set(comments), key=len, reverse=True)
    return {
        "pick": shorten(pick, 80),
        "record": shorten(record, 120),
        "comment": shorten(comments[0], 260) if comments else "",
    }


def parse_initial_state(text: str) -> dict[str, Any]:
    marker = "window.__INITIAL_STATE__="
    idx = text.find(marker)
    if idx < 0:
        return {}
    try:
        state, _ = json.JSONDecoder().raw_decode(text[idx + len(marker) :])
    except json.JSONDecodeError:
        return {}
    return state if isinstance(state, dict) else {}


def compact_mobile_state(state: dict[str, Any]) -> dict[str, Any]:
    detail = state.get("zqdetail") if isinstance(state.get("zqdetail"), dict) else {}
    base = detail.get("baseInfo") if isinstance(detail.get("baseInfo"), dict) else {}
    analysis = detail.get("analysisNew") if isinstance(detail.get("analysisNew"), dict) else {}
    compact: dict[str, Any] = {
        "base_info": {
            key: base.get(key)
            for key in (
                "simpleleague",
                "seasonyear",
                "stagename",
                "stagemode",
                "stageid",
                "matchgroup",
                "matchgroupname",
                "matchround",
                "homestanding",
                "awaystanding",
                "hstr",
                "astr",
                "is_zhongli",
                "venuename",
                "weather",
                "temperature",
                "status_desc",
            )
        },
        "cup_rank": analysis.get("cupRank") if isinstance(analysis.get("cupRank"), dict) else {},
        "league_rank": analysis.get("leagueRank") if isinstance(analysis.get("leagueRank"), dict) else {},
        "future_match": analysis.get("futureMatch") if isinstance(analysis.get("futureMatch"), dict) else {},
    }
    return compact


def source_status(payload: dict[str, Any]) -> str:
    return "ok" if payload else "missing"


def classify_stage(stage_name: str, competition_label: str) -> str:
    text = f"{stage_name} {competition_label}"
    if any(token in text for token in ("小组", "分组", "Group")):
        return "group"
    if re.search(r"第\d+轮", text) or "联赛" in text:
        return "league_round"
    if any(token in text for token in ("决赛", "强", "淘汰", "准决", "半准")):
        return "knockout"
    return "unknown"


def rank_line(cup_rank: dict[str, Any], group_name: str) -> str:
    group_key = group_name.replace("组", "")
    rows = cup_rank.get(group_key) or cup_rank.get(group_name)
    if not isinstance(rows, list) or not rows:
        return ""
    pieces = []
    for row in rows[:4]:
        if not isinstance(row, dict):
            continue
        pieces.append(
            f"{row.get('teamname') or row.get('sxname')} {row.get('score')}分 第{row.get('standing')}"
        )
    return f"{group_name or group_key + '组'}：" + "；".join(piece for piece in pieces if piece)


def compact_headline(competition_label: str, stage_text: str, fallback: str) -> str:
    if not competition_label and not stage_text:
        return fallback
    if competition_label and stage_text and stage_text not in competition_label:
        return f"{competition_label} · {stage_text}"
    return competition_label or stage_text


def expert_titles_from_text(text: str, home: str, away: str, limit: int = 6) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in text_lines(text):
        if any(token in line for token in ("推荐汇总", "剩余预测次数", "设置为重点预测", "发布预测", "体育场", "℃")):
            continue
        if len(line) < 10 or len(line) > 80:
            continue
        has_team = home in line or away in line
        has_keyword = any(keyword in line for keyword in KEYWORDS)
        if not (has_team or has_keyword):
            continue
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        if len(out) >= limit:
            break
    return out


def build_digest(row: sqlite3.Row, sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pc = sources.get("500_pc", {})
    mobile = sources.get("500_mobile", {})
    experts = sources.get("nowscore_expert_titles", {})
    base = mobile.get("base_info", {}) if isinstance(mobile.get("base_info"), dict) else {}
    competition_label = first_nonempty(pc.get("competition_label"), base.get("simpleleague"), row["league"])
    stage_name = first_nonempty(base.get("stagename"))
    group_name = first_nonempty(base.get("matchgroupname"))
    match_round = first_nonempty(base.get("matchround"))
    stage_type = classify_stage(stage_name, competition_label)
    stage_text = " ".join(part for part in (stage_name, group_name, f"第{match_round}轮" if match_round and match_round != "0" else "") if part)

    points: list[str] = []
    standings = []
    if base.get("homestanding"):
        standings.append(f"{row['home']}第{base.get('homestanding')}")
    if base.get("awaystanding"):
        standings.append(f"{row['away']}第{base.get('awaystanding')}")
    if standings:
        points.append("排名：" + "，".join(standings))
    cup_rank_line = rank_line(mobile.get("cup_rank", {}) if isinstance(mobile.get("cup_rank"), dict) else {}, group_name)
    if cup_rank_line:
        points.append(shorten(cup_rank_line, 160))
    macau = pc.get("macau") if isinstance(pc.get("macau"), dict) else {}
    if macau.get("comment"):
        points.append("资料观点：" + shorten(str(macau["comment"]), 180))
    expert_titles = experts.get("titles") if isinstance(experts.get("titles"), list) else []
    if expert_titles:
        points.append("观点索引：" + "；".join(shorten(str(title), 48) for title in expert_titles[:3]))

    tags: list[str] = []
    if macau.get("comment"):
        tags.append("500资料观点")
    if expert_titles:
        tags.append("专家标题池")
    if base.get("is_zhongli") == "1":
        tags.append("中立场")
    headline = compact_headline(competition_label, stage_text, f"{row['league']} {row['home']} vs {row['away']}")
    return {
        "status": "ok" if points else "missing",
        "headline": shorten(headline, 120),
        "points": points[:6],
        "tags": [tag for tag in tags if tag and tag != "unknown"],
        "stage": {
            "competition_label": competition_label,
            "stage_name": stage_name,
            "stage_type": stage_type,
            "group": group_name,
            "round": match_round,
            "home_standing": first_nonempty(base.get("homestanding")),
            "away_standing": first_nonempty(base.get("awaystanding")),
        },
        "source_count": len([payload for payload in sources.values() if payload]),
        "source_names": [name for name, payload in sources.items() if payload],
    }


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS match_intel_sources (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            fid INTEGER,
            source TEXT NOT NULL,
            source_tier TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            title TEXT,
            url TEXT,
            text TEXT,
            payload_json TEXT,
            raw_sha1 TEXT,
            error TEXT,
            PRIMARY KEY(issue, match_idx, source)
        );
        CREATE INDEX IF NOT EXISTS idx_match_intel_sources_fid ON match_intel_sources(fid);

        CREATE TABLE IF NOT EXISTS match_intel_digest (
            issue TEXT NOT NULL,
            match_idx INTEGER NOT NULL,
            fid INTEGER,
            fetched_at TEXT NOT NULL,
            status TEXT NOT NULL,
            headline TEXT,
            summary TEXT,
            digest_json TEXT,
            source_count INTEGER,
            error TEXT,
            PRIMARY KEY(issue, match_idx)
        );
        CREATE INDEX IF NOT EXISTS idx_match_intel_digest_fid ON match_intel_digest(fid);
        """
    )


def resolve_issue(conn: sqlite3.Connection, issue: str | None) -> str | None:
    if not issue:
        return None
    if issue not in {"current", "latest"}:
        return issue
    row = conn.execute(
        "SELECT issue FROM issues WHERE is_current=1 ORDER BY ordinal ASC, last_seen_at DESC LIMIT 1"
    ).fetchone()
    if row:
        return str(row["issue"])
    row = conn.execute("SELECT issue FROM issues ORDER BY last_seen_at DESC, ordinal ASC LIMIT 1").fetchone()
    return str(row["issue"]) if row else None


def select_matches(conn: sqlite3.Connection, args: argparse.Namespace) -> list[sqlite3.Row]:
    issue = resolve_issue(conn, args.issue)
    has_nowscore = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='nowscore_bjdc_matches' LIMIT 1"
    ).fetchone()
    nowscore_cols = (
        "n.provider_match_id AS nowscore_provider_match_id, n.recommendation_url AS nowscore_recommendation_url"
        if has_nowscore
        else "NULL AS nowscore_provider_match_id, NULL AS nowscore_recommendation_url"
    )
    nowscore_join = (
        "LEFT JOIN nowscore_bjdc_matches n ON n.issue=m.issue AND n.match_idx=m.match_idx"
        if has_nowscore
        else ""
    )
    where = ["m.fid IS NOT NULL"]
    params: list[Any] = []
    if issue:
        where.append("m.issue=?")
        params.append(issue)
    if args.fid:
        where.append("m.fid=?")
        params.append(args.fid)
    sql = f"""
        SELECT m.issue, m.match_idx, m.fid, m.league, m.home, m.away, m.end_time,
               {nowscore_cols}
        FROM matches m
        {nowscore_join}
        WHERE {" AND ".join(where)}
        ORDER BY m.issue DESC, m.match_idx
        LIMIT ?
    """
    params.append(args.limit)
    return list(conn.execute(sql, params))


def upsert_source(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    source: str,
    source_tier: str,
    status: str,
    title: str,
    url: str,
    text: str,
    payload: dict[str, Any],
    raw: str,
    error: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO match_intel_sources(
            issue, match_idx, fid, source, source_tier, fetched_at, status,
            title, url, text, payload_json, raw_sha1, error
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(issue, match_idx, source) DO UPDATE SET
            fid=excluded.fid,
            source_tier=excluded.source_tier,
            fetched_at=excluded.fetched_at,
            status=excluded.status,
            title=excluded.title,
            url=excluded.url,
            text=excluded.text,
            payload_json=excluded.payload_json,
            raw_sha1=excluded.raw_sha1,
            error=excluded.error
        """,
        (
            row["issue"],
            row["match_idx"],
            row["fid"],
            source,
            source_tier,
            now_utc(),
            status,
            title,
            url,
            text,
            json.dumps(payload, ensure_ascii=False),
            sha1_text(raw, json.dumps(payload, ensure_ascii=False)),
            error,
        ),
    )


def upsert_digest(conn: sqlite3.Connection, row: sqlite3.Row, digest: dict[str, Any], error: str = "") -> None:
    points = digest.get("points") if isinstance(digest.get("points"), list) else []
    summary = "；".join(str(point) for point in points[:4])
    conn.execute(
        """
        INSERT INTO match_intel_digest(
            issue, match_idx, fid, fetched_at, status, headline, summary,
            digest_json, source_count, error
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(issue, match_idx) DO UPDATE SET
            fid=excluded.fid,
            fetched_at=excluded.fetched_at,
            status=excluded.status,
            headline=excluded.headline,
            summary=excluded.summary,
            digest_json=excluded.digest_json,
            source_count=excluded.source_count,
            error=excluded.error
        """,
        (
            row["issue"],
            row["match_idx"],
            row["fid"],
            now_utc(),
            digest.get("status", "missing"),
            digest.get("headline", ""),
            summary,
            json.dumps(digest, ensure_ascii=False),
            int(digest.get("source_count") or 0),
            error,
        ),
    )


def collect_one(conn: sqlite3.Connection, scraper: Scraper, row: sqlite3.Row) -> bool:
    fid = int(row["fid"])
    sources: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    pc_url = DETAIL_URL.format(fid=fid)
    pc_raw = scraper.get(pc_url, encoding="gb18030", referer=REFERER)
    if pc_raw:
        macau = parse_macau_recommendation(pc_raw)
        pc_payload = {
            "competition_label": parse_pc_stage(pc_raw),
            "macau": macau,
        }
        sources["500_pc"] = pc_payload
        upsert_source(
            conn,
            row,
            source="500_pc_shuju_macau",
            source_tier="editorial",
            status=source_status(pc_payload),
            title=pc_payload.get("competition_label", ""),
            url=pc_url,
            text=macau.get("comment", ""),
            payload=pc_payload,
            raw=pc_raw,
        )
    else:
        errors.append("500_pc_empty")
        upsert_source(conn, row, source="500_pc_shuju_macau", source_tier="editorial", status="missing", title="", url=pc_url, text="", payload={}, raw="", error="empty")

    mobile_url = MOBILE_URL.format(fid=fid)
    mobile_raw = scraper.get(mobile_url, encoding="utf-8", referer=REFERER)
    mobile_state = compact_mobile_state(parse_initial_state(mobile_raw)) if mobile_raw else {}
    if mobile_state:
        sources["500_mobile"] = mobile_state
    else:
        errors.append("500_mobile_state_missing")
    upsert_source(
        conn,
        row,
        source="500_mobile_state",
        source_tier="raw_data",
        status=source_status(mobile_state),
        title=first_nonempty(mobile_state.get("base_info", {}).get("stagename") if isinstance(mobile_state.get("base_info"), dict) else ""),
        url=mobile_url,
        text="",
        payload=mobile_state,
        raw=mobile_raw,
        error="" if mobile_state else "state_missing",
    )

    rec_url = str(row["nowscore_recommendation_url"] or "")
    if rec_url:
        rec_raw = scraper.get(rec_url, encoding="utf-8", referer=str(row["nowscore_recommendation_url"] or REFERER))
        titles = expert_titles_from_text(rec_raw, str(row["home"] or ""), str(row["away"] or "")) if rec_raw else []
        rec_payload = {"titles": titles}
        if titles:
            sources["nowscore_expert_titles"] = rec_payload
        upsert_source(
            conn,
            row,
            source="nowscore_expert_titles",
            source_tier="expert_pool",
            status="ok" if titles else "missing",
            title="; ".join(titles[:3]),
            url=rec_url,
            text="; ".join(titles[:6]),
            payload=rec_payload,
            raw=rec_raw,
            error="" if titles else "no_titles",
        )

    digest = build_digest(row, sources)
    upsert_digest(conn, row, digest, ";".join(errors))
    return digest.get("status") == "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", default="current")
    parser.add_argument("--fid", type=int)
    parser.add_argument("--limit", type=int, default=64)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    scraper = Scraper(min_interval=max(args.sleep, 0.0), max_retries=2, timeout=args.timeout)
    rows = select_matches(conn, args)
    ok = 0
    for row in rows:
        success = collect_one(conn, scraper, row)
        conn.commit()
        ok += int(success)
        print(
            f"[intel] issue={row['issue']} idx={row['match_idx']} fid={row['fid']} status={'ok' if success else 'missing'}",
            flush=True,
        )
        if args.sleep:
            time.sleep(args.sleep)
    print(f"[summary] rows={len(rows)} ok={ok}", flush=True)


if __name__ == "__main__":
    main()
