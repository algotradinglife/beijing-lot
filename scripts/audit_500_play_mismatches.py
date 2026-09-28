#!/usr/bin/env python3
"""Audit 500 play mismatches against Nowscore DanChang match status.

Read-only audit: detects jq/ds rows where the extracted winning option does
not agree with the score-derived result, then fetches one Nowscore TypeID=5
page per issue.  It records Nowscore status/score/polygoal/SP in
`settlement_mismatch_audit`; it does NOT modify settlement rows.

Use the audit table in the QMD before any targeted correction:
  * Nowscore 推迟/取消/中断/腰斩 -> mark the match non-settled
  * Nowscore 完场 + score agrees -> compute play outcome from score
  * Nowscore status/score disagrees -> manual review
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

NOWSCORE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum={issue}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
NS_ROW_RE = re.compile(r'(?s)<tr id="row_\d+"[^>]*matchid="\d+"[^>]*>.*?</tr>')
NS_SCORE_RE = re.compile(r'style="font-weight:bold;color:Red;">(\d+)-(\d+)</td>')
NS_POLY_RE = re.compile(r'polygoal="(-?\d+)"')
NS_SP_RE = re.compile(r'id="sp_\d+_\d+"[^>]*>(.*?)</span>', re.S)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_nowscore(issue: str) -> str:
    req = urllib.request.Request(NOWSCORE_URL.format(issue=issue), headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rows(html: str) -> dict[int, tuple[str | None, int | None, int | None, int | None, str | None]]:
    """slot -> (status, home_score, away_score, polygoal, unique_sp)."""
    result = {}
    for match in NS_ROW_RE.finditer(html):
        tr = match.group(0)
        slot_m = re.search(r'matchid="(\d+)"', tr)
        if slot_m is None:
            continue
        slot = int(slot_m.group(1))
        seg = re.sub(r"\s+", " ", tr)
        status_m = re.search(r'<td[^>]*title="截止时间：[^"]*"[^>]*>(.*?)</td>', seg)
        status = re.sub(r"<[^>]+>", "", status_m.group(1)).strip() if status_m else None
        score_m = NS_SCORE_RE.search(seg)
        home = int(score_m.group(1)) if score_m else None
        away = int(score_m.group(2)) if score_m else None
        poly_m = NS_POLY_RE.search(tr)
        poly = int(poly_m.group(1)) if poly_m else None
        cells = [re.sub(r"<[^>]+>", "", x).strip() for x in NS_SP_RE.findall(tr)]
        filled = [x for x in cells if x]
        unique_sp = filled[0] if len(filled) == 1 else None
        result[slot] = (status, home, away, poly, unique_sp)
    return result


def expected(play_type: str, home: int, away: int) -> str:
    total = home + away
    if play_type == "jq":
        return "7+" if total >= 7 else str(total)
    return ("上" if total >= 3 else "下") + "+" + ("单" if total % 2 else "双")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--issues", help="comma-separated issue codes (audit subset)")
    parser.add_argument("--limit-issues", type=int, default=0)
    parser.add_argument("--rate-per-minute", type=int, default=30)
    args = parser.parse_args()

    db = args.data_root / "control" / "settlement_500" / "settlement.sqlite"
    con = sqlite3.connect(db)
    con.execute("""
      CREATE TABLE IF NOT EXISTS settlement_mismatch_audit (
        issue_code TEXT NOT NULL,
        issue_slot INTEGER NOT NULL,
        play_type TEXT NOT NULL,
        home_score_500 INTEGER,
        away_score_500 INTEGER,
        expected_option TEXT,
        extracted_option TEXT,
        extracted_sp REAL,
        nowscore_status TEXT,
        home_score_ns INTEGER,
        away_score_ns INTEGER,
        polygoal_ns INTEGER,
        unique_sp_ns REAL,
        source_url TEXT NOT NULL,
        audited_at_utc TEXT NOT NULL,
        PRIMARY KEY(issue_code, issue_slot, play_type)
      )
    """)

    mismatches = []
    for pt in ("jq", "ds"):
        rows = con.execute("""
          SELECT issue_code, issue_slot, home_score, away_score, winning_option, winning_sp
          FROM raw_settlement_play_row
          WHERE play_type=? AND settlement_state='settled'
            AND home_score IS NOT NULL AND winning_option IS NOT NULL
        """, (pt,)).fetchall()
        for issue, slot, home, away, option, sp in rows:
            exp = expected(pt, home, away)
            if option != exp:
                mismatches.append((issue, slot, pt, home, away, exp, option, sp))

    issues = sorted({m[0] for m in mismatches})
    if args.issues:
        wanted = {x for x in args.issues.split(",") if x}
        issues = [x for x in issues if x in wanted]
        mismatches = [m for m in mismatches if m[0] in wanted]
    if args.limit_issues:
        issues = issues[:args.limit_issues]
        mismatches = [m for m in mismatches if m[0] in set(issues)]
    print({"mismatches": len(mismatches), "issues": len(issues)}, flush=True)

    interval = 60 / args.rate_per_minute
    for i, issue in enumerate(issues, 1):
        try:
            html = fetch_nowscore(issue)
            ns = parse_rows(html)
            audit_rows = []
            for rec in mismatches:
                if rec[0] != issue:
                    continue
                _, slot, pt, h500, a500, exp, opt, sp = rec
                status, hns, ans, poly, nssp = ns.get(slot, (None, None, None, None, None))
                audit_rows.append((
                    issue, slot, pt, h500, a500, exp, opt, sp,
                    status, hns, ans, poly,
                    float(nssp) if nssp else None,
                    NOWSCORE_URL.format(issue=issue), now_utc(),
                ))
            con.executemany("INSERT OR REPLACE INTO settlement_mismatch_audit VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", audit_rows)
            con.commit()
            print({"issue": issue, "audited": len(audit_rows)}, flush=True)
        except Exception as exc:
            print({"issue": issue, "error": type(exc).__name__, "detail": str(exc)[:160]}, flush=True)
        time.sleep(max(0, interval - 0.2))

    print({"status": "DONE"})
    con.close()


if __name__ == "__main__":
    main()
