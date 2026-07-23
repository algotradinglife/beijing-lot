#!/usr/bin/env python3
"""Reviewer-owned independent probe for t_2a9dd13f.
Does not import scripts/analyze_beidan_vs_euro.py; directly reads SQLite and recomputes
counts, de-vig calibration and winner-conditioned D buckets.
"""
import json
import sqlite3
from collections import defaultdict
from statistics import mean

DB = "data/beidan_history.db"
CUTOFF = "2026-06-23"
RR = 0.65
BUCKETS = ["<0.2", "0.2-0.35", "0.35-0.5", ">=0.5"]
MID = {"<0.2": 0.1, "0.2-0.35": 0.275, "0.35-0.5": 0.425, ">=0.5": 0.6}

def bucket(p):
    if p < 0.2:
        return "<0.2"
    if p < 0.35:
        return "0.2-0.35"
    if p < 0.5:
        return "0.35-0.5"
    return ">=0.5"

def devig(h, d, a):
    inv = {"3": 1.0/h, "1": 1.0/d, "0": 1.0/a}
    s = sum(inv.values())
    return {k: v/s for k, v in inv.items()}

def straight_result(fthg, ftag):
    return "3" if fthg > ftag else "1" if fthg == ftag else "0"

def summarize(rows):
    cal = defaultdict(lambda: {"n": 0, "wins": 0})
    dvals = defaultdict(list)
    line0_rc_mismatch = 0
    for rc, wsp, h, d, a, line, fthg, ftag in rows:
        if line == 0 and straight_result(fthg, ftag) != rc:
            line0_rc_mismatch += 1
        p = devig(h, d, a)
        for outcome, prob in p.items():
            b = bucket(prob)
            cal[b]["n"] += 1
            cal[b]["wins"] += int(outcome == rc)
        pw = p[rc]
        dvals[bucket(pw)].append(wsp * pw)
    return {
        "n_matches": len(rows),
        "line0_result_code_mismatches_vs_score": line0_rc_mismatch,
        "calibration": {
            b: {
                "n_outcome_probs": cal[b]["n"],
                "hit": round(cal[b]["wins"] / cal[b]["n"], 6) if cal[b]["n"] else None,
                "mid": MID[b],
            }
            for b in BUCKETS
        },
        "winner_D": {
            b: {
                "n_winners": len(dvals[b]),
                "mean_D": round(mean(dvals[b]), 6) if dvals[b] else None,
                "projected_q": round(mean(dvals[b]) * RR, 6) if dvals[b] else None,
            }
            for b in BUCKETS
        },
    }

conn = sqlite3.connect(DB)
base = """
select result_code, winning_sp, avg_eu_home, avg_eu_draw, avg_eu_away,
       handicap_line, fthg, ftag
from historical_matches
where winning_sp > 0 and avg_eu_home > 0 and avg_eu_draw > 0 and avg_eu_away > 0
  and kickoff_ts <= ?
order by id
"""
all_rows = conn.execute(base, (CUTOFF,)).fetchall()
line0_rows = [r for r in all_rows if r[5] == 0]
line_counts = conn.execute(
    """select handicap_line, count(*) from historical_matches
       where winning_sp > 0 and avg_eu_home > 0 and avg_eu_draw > 0 and avg_eu_away > 0
         and kickoff_ts <= ?
       group by handicap_line order by handicap_line""",
    (CUTOFF,),
).fetchall()
print(json.dumps({
    "total_rows_after_filters": len(all_rows),
    "line_counts": line_counts,
    "all_sample": summarize(all_rows),
    "handicap_line_0": summarize(line0_rows),
}, ensure_ascii=False, indent=2))
