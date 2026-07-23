#!/usr/bin/env python3
"""Reviewer-owned probe for FAV5/high-N favorite review."""
from __future__ import annotations
import json, random, sqlite3, math
from collections import defaultdict
from pathlib import Path

import pandas as pd

from src.sp_drift.forward import check_stopping_rule

RR = 0.65
LIVE = Path('data/beidan_live.db')
SAMPLES = 3000
SEED = 42

con = sqlite3.connect(LIVE)
settle = {}
for m, rc, wsp in con.execute("select match_id,result_code,winning_sp from settlements where result_code is not null and winning_sp>0"):
    settle[str(m)] = (str(rc), float(wsp))
sp3 = {}
for m, ts, a, b, c in con.execute("select match_id,snapshot_ts,sp_3,sp_1,sp_0 from snapshots where sp_3 is not null and sp_1 is not null and sp_0 is not null"):
    m = str(m)
    if m not in sp3 or ts > sp3[m][0]:
        sp3[m] = (ts, float(a), float(b), float(c))
con.close()
by_issue = defaultdict(list)
vlist = []
fav_counts = {"3":0,"1":0,"0":0}
for m, (rc, wsp) in settle.items():
    v = sp3.get(m)
    if not v:
        continue
    _, a, b, c = v
    d = {"3": a, "1": b, "0": c}
    fav = min(d, key=d.get)
    fav_counts[fav] += 1
    hit = (fav == rc)
    by_issue[m.split('_')[0]].append((hit, wsp if hit else None))
    vlist.append((hit, wsp if hit else None))

n = len(vlist)
hits = sum(1 for h,_ in vlist if h)
sw = sum(w for h,w in vlist if h)
v_leg = sw/n
rng = random.Random(SEED)
rows = []
for N in (2,3,4,5,6,7,8,10):
    be_v = 1.538 ** (1.0/N)
    indep = RR * (v_leg ** N)
    elig = [(iss, legs) for iss, legs in by_issue.items() if len(legs) >= N]
    tot_stake = tot_pay = 0.0
    wins = 0
    for _ in range(SAMPLES):
        iss, legs = rng.choice(elig)
        idx = rng.sample(range(len(legs)), N)
        tot_stake += 1.0
        if all(legs[i][0] for i in idx):
            prod = math.prod(legs[i][1] for i in idx)
            tot_pay += RR * prod
            wins += 1
    roi = tot_pay / tot_stake - 1
    rows.append({"N":N,"breakeven_v":round(be_v,3),"indep_EV_pct":round(100*(indep-1),1),"sim_ROI_pct":round(100*roi,1),"wins":wins,"eligible_issues":len(elig)})

ledger = pd.DataFrame([
    {"run_date":"2026-07-01","arm":"C0","forward_start":"2026-06-13","n_combos":999,"n_hits":0,"total_stake":0,"total_pnl":0,"roi":0.0,"max_dd":0.0,"final_bankroll":1},
    {"run_date":"2026-07-01","arm":"C1","forward_start":"2026-06-13","n_combos":999,"n_hits":0,"total_stake":0,"total_pnl":0,"roi":0.10,"max_dd":0.0,"final_bankroll":1},
    {"run_date":"2026-07-01","arm":"C2","forward_start":"2026-06-13","n_combos":220,"n_hits":0,"total_stake":0,"total_pnl":0,"roi":0.12,"max_dd":0.0,"final_bankroll":1},
    {"run_date":"2026-07-01","arm":"FAV5","forward_start":"2026-06-13","n_combos":999999,"n_hits":0,"total_stake":0,"total_pnl":0,"roi":999.0,"max_dd":0.99,"final_bankroll":1},
])
gate = check_stopping_rule(ledger, "2026-06-13", "2026-07-01")
print(json.dumps({
    "favorite_leg_summary":{"n":n,"hits":hits,"hit_rate":round(hits/n,6),"avg_win_sp":round(sw/hits,6),"realized_v":round(v_leg,6),"issues":len(by_issue),"median_favorites_per_issue":sorted(len(x) for x in by_issue.values())[len(by_issue)//2],"fav_selection_counts":fav_counts},
    "sim_rows":rows,
    "gate_ignores_fav5_probe":gate,
}, ensure_ascii=False, indent=2))
