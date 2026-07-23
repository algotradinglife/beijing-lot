#!/usr/bin/env python3
"""Reviewer-owned independent probe for t_f0eee7a9.
Does not import scripts/analyze_high_n_favorites.py; reads data/beidan_live.db
and recomputes favorite-leg summary + high-N exact combinatorics.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "beidan_live.db"
RR = 0.65
MC_SAMPLES = 20_000
SEED = 42
NS = (2, 3, 4, 5, 6, 7, 8, 10)


def load(order: str):
    con = sqlite3.connect(DB)
    if order == "asc":
        settle_sql = "select match_id,result_code,winning_sp from settlements where result_code is not null and winning_sp>0 order by match_id asc"
        snap_sql = "select match_id,snapshot_ts,sp_3,sp_1,sp_0 from snapshots where sp_3 is not null and sp_1 is not null and sp_0 is not null order by match_id asc, snapshot_ts asc"
    elif order == "desc":
        settle_sql = "select match_id,result_code,winning_sp from settlements where result_code is not null and winning_sp>0 order by match_id desc"
        snap_sql = "select match_id,snapshot_ts,sp_3,sp_1,sp_0 from snapshots where sp_3 is not null and sp_1 is not null and sp_0 is not null order by match_id desc, snapshot_ts desc"
    else:
        raise ValueError(order)
    settle = {str(m): (str(rc), float(wsp)) for m, rc, wsp in con.execute(settle_sql)}
    sp3 = {}
    for m, ts, sp3_v, sp1_v, sp0_v in con.execute(snap_sql):
        # Choose the max timestamp explicitly so probe semantics are independent of SQL iteration order.
        m = str(m)
        row = (str(ts), float(sp3_v), float(sp1_v), float(sp0_v))
        if m not in sp3 or row[0] > sp3[m][0]:
            sp3[m] = row
    by_issue = defaultdict(list)
    vlist = []
    for m in sorted(settle):
        if m not in sp3:
            continue
        rc, wsp = settle[m]
        _, s3, s1, s0 = sp3[m]
        odds = {"3": s3, "1": s1, "0": s0}
        fav = min(odds, key=lambda k: (odds[k], k))
        hit = fav == rc
        entry = (hit, wsp if hit else None)
        by_issue[m.split("_")[0]].append(entry)
        vlist.append(entry)
    for iss in by_issue:
        by_issue[iss] = list(by_issue[iss])
    return dict(by_issue), vlist


def metrics(by_issue, vlist):
    n = len(vlist)
    hits = sum(1 for h, _ in vlist if h)
    sum_win_sp = sum(w for h, w in vlist if h)
    v_leg = sum_win_sp / n
    rng = random.Random(SEED)
    issues = sorted(by_issue)
    rows = []
    for N in NS:
        num = den = 0
        for iss in issues:
            legs = by_issue[iss]
            m = len(legs)
            if m < N:
                continue
            h = sum(1 for hit, _ in legs if hit)
            num += math.comb(h, N)
            den += math.comb(m, N)
        exact_p = num / den if den else 0.0
        elig = [iss for iss in issues if len(by_issue[iss]) >= N]
        stake = pay = 0.0
        for _ in range(MC_SAMPLES):
            legs = by_issue[rng.choice(elig)]
            idx = rng.sample(range(len(legs)), N)
            stake += 1.0
            if all(legs[i][0] for i in idx):
                prod = 1.0
                for i in idx:
                    prod *= legs[i][1]
                pay += RR * prod
        rows.append({
            "N": N,
            "be_v": 1.538 ** (1.0 / N),
            "indep_roi_pct": 100 * (RR * (v_leg ** N) - 1),
            "exact_allhit": exact_p,
            "expected_wins_per_20000": exact_p * MC_SAMPLES,
            "mc_roi_pct": 100 * (pay / stake - 1),
        })
    return {
        "n": n,
        "hits": hits,
        "hit_rate": hits / n,
        "avg_win_sp": sum_win_sp / hits,
        "v_leg": v_leg,
        "issues": len(by_issue),
        "median_favorites_per_issue": sorted(len(x) for x in by_issue.values())[len(by_issue)//2],
        "rows": rows,
    }


def main():
    asc = metrics(*load("asc"))
    desc = metrics(*load("desc"))
    # Desc query should still produce same probe metrics because we explicitly pick latest snapshots
    # and sort settlement match IDs before grouping.
    comparable = json.dumps(asc, sort_keys=True) == json.dumps(desc, sort_keys=True)
    print(json.dumps({"asc_equals_desc_order_probe": comparable, "metrics": asc}, ensure_ascii=False, indent=2))
    assert comparable


if __name__ == "__main__":
    main()
