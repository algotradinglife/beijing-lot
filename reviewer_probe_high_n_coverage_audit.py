#!/usr/bin/env python3
"""Reviewer-owned independent probe for high-N coverage Track A.

Does not import scripts/analyze_high_n_coverage.py. Recomputes the live-data pool,
drift geomeans, analytic EV identity, and a deterministic MC cross-check.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path('/home/drwho1985/workspace/soccer/beijing-lot')
LIVE = ROOT / 'data/beidan_live.db'
WEBUI = ROOT / 'data/webui.db'
RR = 0.65
CODES = ['3', '1', '0']
BEIJING = timezone(timedelta(hours=8))


def minutes_to_kickoff(snapshot_ts: str, kickoff_ts: str) -> float:
    snap = datetime.fromisoformat(snapshot_ts.replace('Z', '+00:00'))
    if snap.tzinfo is None:
        snap = snap.replace(tzinfo=timezone.utc)
    ko = datetime.fromisoformat(kickoff_ts)
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=BEIJING)
    return (ko - snap).total_seconds() / 60.0


def baseline_mtk() -> float:
    import statistics
    con = sqlite3.connect(WEBUI)
    rows = con.execute('SELECT created_ts, plan_json FROM plans').fetchall()
    con.close()
    mtks = []
    import json as _json
    for created_ts, pj in rows:
        try:
            plan = _json.loads(pj)
        except Exception:
            continue
        for ticket in plan.get('tickets', []):
            for leg in ticket.get('legs', []):
                ko = leg.get('kickoff_ts')
                if ko and created_ts:
                    mtks.append(minutes_to_kickoff(created_ts, ko))
    return float(statistics.median(mtks))


def read_decision_rows(mtk_target: float):
    con = sqlite3.connect(LIVE)
    snap_cols = [r[1] for r in con.execute('PRAGMA table_info(snapshots)').fetchall()]
    match_cols = [r[1] for r in con.execute('PRAGMA table_info(matches)').fetchall()]
    have_eu = all(c in snap_cols for c in ['eu_h', 'eu_d', 'eu_a'])
    select_eu = ', s.eu_h, s.eu_d, s.eu_a' if have_eu else ''
    q = f'''
    SELECT s.match_id, s.snapshot_ts, s.sp_3, s.sp_1, s.sp_0{select_eu}, m.kickoff_ts
    FROM snapshots s JOIN matches m ON m.match_id=s.match_id
    WHERE m.kickoff_ts IS NOT NULL
    '''
    rows = con.execute(q).fetchall()
    con.close()
    by = {}
    for row in rows:
        if have_eu:
            mid, snap_ts, sp3, sp1, sp0, euh, eud, eua, ko = row
        else:
            mid, snap_ts, sp3, sp1, sp0, ko = row
            euh = eud = eua = None
        mtk = minutes_to_kickoff(snap_ts, ko)
        if mtk < mtk_target or mtk <= 0:
            continue
        cur = by.get(mid)
        # choose latest snapshot still at/above target: minimum mtk
        if cur is None or mtk < cur['mtk']:
            by[mid] = {
                'match_id': str(mid), 'mtk': mtk,
                'sp': [sp3, sp1, sp0], 'eu': [euh, eud, eua],
            }
    return list(by.values()), have_eu, snap_cols, match_cols


def build_pool(mtk_target: float, prob_source: str = 'sp'):
    rows, have_eu, snap_cols, match_cols = read_decision_rows(mtk_target)
    con = sqlite3.connect(LIVE)
    settle = {str(m): (str(rc), float(ws)) for m, rc, ws in con.execute(
        'SELECT match_id,result_code,winning_sp FROM settlements WHERE result_code IS NOT NULL AND winning_sp>0')}
    con.close()
    drifts = []
    raw = []
    for r in rows:
        sp = r['sp']
        if any(x is None or float(x) <= 1.0 for x in sp):
            continue
        sp = [float(x) for x in sp]
        inv_sum = sum(1.0 / x for x in sp)
        if not (0.85 <= inv_sum <= 1.25):
            continue
        if r['match_id'] in settle:
            rc, ws = settle[r['match_id']]
            if rc in CODES:
                drifts.append(ws / sp[CODES.index(rc)])
        if prob_source == 'eu' and have_eu and all(x is not None and float(x) > 1.0 for x in r['eu']):
            base = [float(x) for x in r['eu']]
        else:
            base = sp
        inv = [1.0 / x for x in base]
        S = sum(inv)
        probs = [x / S for x in inv]
        raw.append((probs, sp, inv_sum))
    drift_gm = math.exp(sum(math.log(x) for x in drifts if x > 0) / len([x for x in drifts if x > 0]))
    pool = [(p, [x * drift_gm for x in sp], inv_sum) for p, sp, inv_sum in raw]
    return pool, drift_gm, len(drifts), have_eu


def analytic_ev_for_strategy(pool, n_legs: int, n_cover3: int, seed: int, n_draws: int = 50000):
    rng = random.Random(seed)
    n_single = n_legs - n_cover3
    vals = []
    hit_probs = []
    for _ in range(n_draws):
        legs = rng.sample(pool, n_legs)
        legs.sort(key=lambda L: max(L[0]), reverse=True)
        prod_ev = 1.0
        prod_hit = 1.0
        for j, (p, sp, _invsum) in enumerate(legs):
            if j < n_single:
                k = max(range(3), key=lambda idx: p[idx])
                C = [k]
            else:
                C = [0, 1, 2]
            prod_hit *= sum(p[o] for o in C)
            prod_ev *= sum(p[o] * sp[o] for o in C) / len(C)
        vals.append(RR * prod_ev)
        hit_probs.append(prod_hit)
    return sum(vals) / len(vals), sum(hit_probs) / len(hit_probs)


def mc_strategy(pool, n_legs: int, n_cover3: int, seed: int, n_sims: int = 100000, budget: float = 1000.0):
    rng = random.Random(seed)
    n_single = n_legs - n_cover3
    tickets = 3 ** n_cover3
    spt = budget / tickets
    hits = 0
    total = 0.0
    jackpots = []
    for _ in range(n_sims):
        legs = rng.sample(pool, n_legs)
        legs.sort(key=lambda L: max(L[0]), reverse=True)
        win = True
        mult = 1.0
        for j, (p, sp, _invsum) in enumerate(legs):
            r = rng.random()
            o = 0 if r < p[0] else (1 if r < p[0] + p[1] else 2)
            if j < n_single:
                fav = max(range(3), key=lambda idx: p[idx])
                if o != fav:
                    win = False
                    break
            mult *= sp[o]
        payoff = spt * mult * RR if win else 0.0
        total += payoff
        if win:
            hits += 1
            jackpots.append(payoff)
    jackpots.sort()
    return {
        'hit_rate': hits / n_sims,
        'ev_per_budget': total / n_sims / budget,
        'median_jackpot': jackpots[len(jackpots)//2] if jackpots else 0.0,
        'max_jackpot': jackpots[-1] if jackpots else 0.0,
        'tickets': tickets,
    }


def main():
    base = baseline_mtk()
    pool_sp, drift, ndrift, have_eu = build_pool(base, 'sp')
    pool_near, drift_near, nnear, _ = build_pool(180.0, 'sp')
    pool_eu, drift_eu, ndrift_eu, _ = build_pool(base, 'eu')
    rows = []
    for N in [6, 7]:
        for cover in [0, 3, N]:
            analytic_ev, analytic_hit = analytic_ev_for_strategy(pool_sp, N, cover, seed=123 + 10*N + cover, n_draws=30000)
            mc = mc_strategy(pool_sp, N, cover, seed=456 + 10*N + cover, n_sims=80000)
            rows.append({
                'N': N, 'cover3': cover,
                'analytic_ev_per_budget': round(analytic_ev, 5),
                'mc_ev_per_budget': round(mc['ev_per_budget'], 5),
                'analytic_hit': round(analytic_hit, 5),
                'mc_hit': round(mc['hit_rate'], 5),
                'median_jackpot': round(mc['median_jackpot'], 2),
                'max_jackpot': round(mc['max_jackpot'], 2),
                'tickets': mc['tickets'],
            })
    # Compare SP-implied probs vs euro-implied probs for same SP payout/drift.
    ev_sp_n7, hit_sp_n7 = analytic_ev_for_strategy(pool_sp, 7, 0, seed=999, n_draws=30000)
    ev_eu_n7, hit_eu_n7 = analytic_ev_for_strategy(pool_eu, 7, 0, seed=999, n_draws=30000) if have_eu else (None, None)
    eu_pair = None
    if have_eu and ev_eu_n7 is not None and hit_eu_n7 is not None:
        eu_pair = [round(ev_eu_n7, 6), round(hit_eu_n7, 6)]
    out = {
        'baseline_mtk': round(base, 3),
        'pool_legs_sp_probs': len(pool_sp),
        'drift_gm_base': round(drift, 6),
        'n_drift_base': ndrift,
        'drift_gm_180': round(drift_near, 6),
        'n_drift_180': nnear,
        'formula_floor_n7_base': round(RR * drift**7, 6),
        'formula_floor_n7_near': round(RR * drift_near**7, 6),
        'have_euro_odds_in_snapshots': have_eu,
        'pool_legs_eu_probs': len(pool_eu),
        'n7_single_sp_prob_ev_hit': [round(ev_sp_n7, 6), round(hit_sp_n7, 6)],
        'n7_single_eu_prob_ev_hit': eu_pair,
        'coverage_rows': rows,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
