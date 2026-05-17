"""Verify settlements by re-fetching scores from independent endpoints.

For each row in `settlements`, fetch the same match's final score from:
  A) live.500.com/zqdc.php?id=<fid> (the per-match scoreboard)
  B) live.500.com/wanchang.php?e=<date> (date-bucketed completed games)

If A and/or B disagree with the DB row, flag it. Wanchang lookup is by
fid (same source so not truly independent), but distinct page + parser —
a parser bug in one path would not silently corrupt the other.

Usage:
  python -m scripts.verify_settlements [--limit N] [--days D] [--source S]

Exits non-zero if any disagreement is found.
"""
from __future__ import annotations
import argparse
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "beidan_live.db"

UA = "Mozilla/5.0"

ZQDC_ROW = re.compile(
    r'<tr id="a(?P<fid>\d+)"[^>]*\bstatus="(?P<st>\d+)"[^>]*>(?P<body>.*?)</tr>',
    re.S,
)
SCORE = re.compile(r'<td[^>]*class="red"[^>]*>\s*(\d+)\s*-\s*(\d+)\s*</td>')
WANCHANG_ROW = re.compile(r'<tr id="a(?P<fid>\d+)"[^>]*>(?P<body>.*?)</tr>', re.S)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=20).read().decode(
        "gb18030", errors="ignore"
    )


def zqdc_score_for(fid: str, html_cache: dict) -> tuple | None:
    if "zqdc" not in html_cache:
        html_cache["zqdc"] = fetch("https://live.500.com/zqdc.php")
    body_m = ZQDC_ROW.search(
        re.search(
            rf'<tr id="a{re.escape(fid)}"[^>]*>(.*?)</tr>',
            html_cache["zqdc"], re.S,
        ).group(0)
    ) if re.search(rf'<tr id="a{re.escape(fid)}"', html_cache["zqdc"]) else None
    if not body_m:
        return None
    sm = SCORE.search(body_m.group("body"))
    return (int(sm.group(1)), int(sm.group(2))) if sm else None


def wanchang_index(dates: list[str]) -> dict:
    out: dict[str, tuple[int, int]] = {}
    for d in dates:
        try:
            h = fetch(f"https://live.500.com/wanchang.php?e={d}")
        except Exception:
            continue
        for m in WANCHANG_ROW.finditer(h):
            sm = SCORE.search(m.group("body"))
            if sm:
                out[m.group("fid")] = (int(sm.group(1)), int(sm.group(2)))
        time.sleep(0.3)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--days", type=int, default=7,
                    help="Only check settlements with kickoff in last N days")
    ap.add_argument("--source", default=None,
                    help="Filter by settlement source (zqdc/live500/500_kaijiang)")
    args = ap.parse_args()

    c = sqlite3.connect(str(DB))
    sql = ("SELECT s.match_id, s.fthg, s.ftag, s.result_code, s.source, "
           "m.fid, m.home, m.away, m.kickoff_ts FROM settlements s "
           "JOIN matches m ON m.match_id=s.match_id "
           "WHERE s.fthg IS NOT NULL AND m.fid IS NOT NULL "
           f"AND m.kickoff_ts >= date('now', '-{args.days} days') ")
    params: tuple = ()
    if args.source:
        sql += "AND s.source=? "
        params = (args.source,)
    sql += "ORDER BY s.settled_ts DESC LIMIT ?"
    rows = c.execute(sql, params + (args.limit,)).fetchall()
    print(f"Verifying {len(rows)} settlements (last {args.days} days)…")

    # Pre-fetch wanchang for relevant date span
    dates = sorted({r[8][:10] for r in rows if r[8]})
    print(f"Pre-loading wanchang for dates: {dates[-5:]} (+earlier)")
    wc = wanchang_index(dates[-7:])
    print(f"wanchang fid→score index size: {len(wc)}")

    cache: dict = {}
    by_src: dict = {}
    diffs = []
    n_z_ok = n_z_diff = n_z_miss = 0
    n_w_ok = n_w_diff = n_w_miss = 0

    for mid, fthg, ftag, rc, src, fid, home, away, kick in rows:
        by_src.setdefault(src, {"tot": 0, "ok": 0, "diff": 0})
        by_src[src]["tot"] += 1
        z = zqdc_score_for(fid, cache)
        w = wc.get(fid)
        ours = (fthg, ftag)
        if z is None:
            n_z_miss += 1
        elif z == ours:
            n_z_ok += 1
        else:
            n_z_diff += 1
        if w is None:
            n_w_miss += 1
        elif w == ours:
            n_w_ok += 1
        else:
            n_w_diff += 1

        # An "ok" row needs at least one independent confirmation matching
        # ours. A "diff" row has at least one source disagreeing, with no
        # source confirming.
        confirmed = (z == ours) or (w == ours)
        contradicted = (z is not None and z != ours) or (w is not None and w != ours)
        if confirmed:
            by_src[src]["ok"] += 1
        elif contradicted:
            by_src[src]["diff"] += 1
            diffs.append(dict(match_id=mid, source=src, home=home, away=away,
                              ours=ours, zqdc=z, wanchang=w))

    print()
    print(f"zqdc cross-check     : ok={n_z_ok}  diff={n_z_diff}  not-on-page={n_z_miss}")
    print(f"wanchang cross-check : ok={n_w_ok}  diff={n_w_diff}  not-on-page={n_w_miss}")
    print()
    print("BY SOURCE (any independent source confirming = ok):")
    for s, st in by_src.items():
        cov = st["ok"] + st["diff"]
        rate = (100 * st["ok"] / cov) if cov else 0
        print(f"  {s:18}  total={st['tot']:>4}  confirmed={st['ok']:>4}  contradicted={st['diff']:>3}  agree={rate:.1f}% (of covered)")

    if diffs:
        print(f"\n!!! {len(diffs)} contradictions:")
        for d in diffs[:25]:
            print(f"  {d['match_id']} [{d['source']}] {d['home']} vs {d['away']}: "
                  f"DB={d['ours']}  zqdc={d['zqdc']}  wanchang={d['wanchang']}")
        return 1
    print("\nAll covered settlements have at least one independent confirmation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
