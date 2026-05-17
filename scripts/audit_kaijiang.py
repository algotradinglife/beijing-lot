"""Audit existing kaijiang settlements against the more-authoritative
500 detail.php score. detail.php has an explicit `<span class="score">`
block (full-time) plus half-time, so it's harder to mis-parse and we've
seen it disagree with kaijiang in cases where kaijiang inverts home/away.

Usage:
  python -m scripts.audit_kaijiang [--issue 26051] [--fix]

Without --fix: dry run, prints contradictions and would-be result_code
                changes.
With --fix:    rewrites fthg/ftag/result_code/winning_sp on contradictions
                and bumps source to "kaijiang+detail" so downstream code can
                tell verified rows from raw kaijiang rows.

Re-uses ``Scraper`` so polite rate limits are honoured.
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_DEFAULT = ROOT / "data" / "beidan_live.db"

# project imports
sys.path.insert(0, str(ROOT))
from src.live_collector.scraper import Scraper
from src.live_collector.parser import parse_500_detail_score, compute_result_code


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", default=None,
                    help="Restrict to one issue (e.g. 26051). Default: all.")
    ap.add_argument("--source", default="500_kaijiang",
                    help="Settlement source to audit (default: 500_kaijiang).")
    ap.add_argument("--limit", type=int, default=10**9)
    ap.add_argument("--fix", action="store_true",
                    help="Persist corrections to settlements (default: dry run).")
    ap.add_argument("--db", default=str(DB_DEFAULT))
    args = ap.parse_args()

    c = sqlite3.connect(args.db)
    sql = ("SELECT s.match_id, s.issue, s.match_idx, s.fthg, s.ftag, "
           "s.result_code, s.winning_sp, m.fid, m.home, m.away, m.handicap_line "
           "FROM settlements s JOIN matches m ON m.match_id=s.match_id "
           "WHERE s.source=? AND m.fid IS NOT NULL ")
    params: tuple = (args.source,)
    if args.issue:
        sql += "AND s.issue=? "
        params += (args.issue,)
    sql += "ORDER BY s.issue, s.match_idx LIMIT ?"
    rows = c.execute(sql, params + (args.limit,)).fetchall()
    print(f"Auditing {len(rows)} settlements (source={args.source}"
          + (f", issue={args.issue}" if args.issue else "")
          + ").")

    sc = Scraper(min_interval=0.6, max_retries=2)
    n_ok = n_diff = n_miss = n_fix = 0
    contradictions = []
    for i, r in enumerate(rows, 1):
        mid, issue, idx, fthg, ftag, rc, wsp, fid, home, away, hcap = r
        try:
            html = sc.fetch_500_detail(fid)
        except Exception as e:
            n_miss += 1
            print(f"  [{i}/{len(rows)}] {mid} fetch fail: {e}")
            continue
        det = parse_500_detail_score(html)
        if det is None:
            n_miss += 1
            continue
        dhg, dag = det
        if (dhg, dag) == (fthg, ftag):
            n_ok += 1
            continue
        # Disagreement
        n_diff += 1
        new_rc = compute_result_code(dhg, dag, hcap) if hcap is not None else None
        contradictions.append(dict(
            match_id=mid, home=home, away=away, hcap=hcap,
            kaijiang=(fthg, ftag), kaijiang_rc=rc,
            detail=(dhg, dag), detail_rc=new_rc,
        ))
        rc_changes = "RC CHANGES" if new_rc is not None and new_rc != rc else "rc same"
        print(f"  [{i}/{len(rows)}] {mid} {home} vs {away}: kaijiang={fthg}-{ftag} "
              f"rc={rc} | detail={dhg}-{dag} rc={new_rc}  [{rc_changes}]")
        if args.fix:
            c.execute(
                "UPDATE settlements SET fthg=?, ftag=?, result_code=?, "
                "source='kaijiang+detail' WHERE match_id=?",
                (dhg, dag, new_rc, mid),
            )
            n_fix += 1
        time.sleep(0.05)

    if args.fix:
        c.commit()

    rc_flips = sum(1 for x in contradictions
                   if x["detail_rc"] is not None and x["detail_rc"] != x["kaijiang_rc"])
    print()
    print(f"Total checked     : {len(rows)}")
    print(f"  agree           : {n_ok}")
    print(f"  disagree        : {n_diff}")
    print(f"    of which rc-flips (changes payout!): {rc_flips}")
    print(f"  detail not avail: {n_miss}")
    if args.fix:
        print(f"  rows updated    : {n_fix}")
    return 0 if rc_flips == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
