#!/usr/bin/env python3
"""Reviewer-owned acceptance probe for t_8138293e.
Does not import scripts/analyze_beidan_vs_euro.py. Verifies:
- figure exists and doc references it
- refund/void rows (winning_sp<=1.0) are excluded in recomputed headline stats
- line=0 clean subset remains calibrated and D≈1.0
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path('/home/drwho1985/workspace/soccer/beijing-lot')
DB = ROOT / 'data/beidan_history.db'
DOC = ROOT / 'docs/research/beidan_vs_euro_divergence.md'
FIG = ROOT / 'docs/research/figures/beidan_vs_euro_divergence.png'
CUTOFF = '2026-06-23'
BUCKETS = ['<0.2', '0.2-0.35', '0.35-0.5', '>=0.5']
MID = {'<0.2': 0.1, '0.2-0.35': 0.275, '0.35-0.5': 0.425, '>=0.5': 0.6}
RR = 0.65

def bucket(p: float) -> str:
    if p < 0.2:
        return '<0.2'
    if p < 0.35:
        return '0.2-0.35'
    if p < 0.5:
        return '0.35-0.5'
    return '>=0.5'

def devig(h: float, d: float, a: float) -> dict[str, float]:
    inv = {'3': 1/h, '1': 1/d, '0': 1/a}
    s = sum(inv.values())
    return {k: v/s for k, v in inv.items()}

def summarize(where: str = '') -> dict:
    sql = """
      select result_code, winning_sp, avg_eu_home, avg_eu_draw, avg_eu_away
      from historical_matches
      where winning_sp > 0 and avg_eu_home > 0 and avg_eu_draw > 0 and avg_eu_away > 0
        and kickoff_ts <= ?
    """ + where + " order by id"
    rows = sqlite3.connect(DB).execute(sql, (CUTOFF,)).fetchall()
    refunds = sum(1 for r in rows if float(r[1]) <= 1.0)
    rows = [r for r in rows if float(r[1]) > 1.0]
    cal = defaultdict(lambda: [0, 0])
    ds = defaultdict(list)
    for rc, wsp, h, d, a in rows:
        probs = devig(float(h), float(d), float(a))
        for outcome, p in probs.items():
            b = bucket(p)
            cal[b][0] += 1
            cal[b][1] += int(outcome == str(rc))
        p_win = probs.get(str(rc))
        if p_win and p_win > 0:
            ds[bucket(p_win)].append(float(wsp) * p_win)
    return {
        'n_after_refund_exclusion': len(rows),
        'refunds_excluded': refunds,
        'calibration': {b: {'n': cal[b][0], 'hit': round(cal[b][1] / cal[b][0], 6), 'mid': MID[b]} for b in BUCKETS},
        'winner_D': {b: {'n': len(ds[b]), 'mean_D': round(sum(ds[b]) / len(ds[b]), 6), 'projected_q': round((sum(ds[b]) / len(ds[b])) * RR, 6)} for b in BUCKETS},
    }

def main():
    doc_text = DOC.read_text(encoding='utf-8')
    out = {
        'doc_exists': DOC.exists(),
        'figure_exists': FIG.exists(),
        'figure_doc_reference': 'figures/beidan_vs_euro_divergence.png' in doc_text,
        'doc_mentions_refunds': 'winning_sp≤1.0' in doc_text and '51' in doc_text and '16' in doc_text,
        'figure_bytes': FIG.stat().st_size if FIG.exists() else None,
        'figure_sha256': hashlib.sha256(FIG.read_bytes()).hexdigest() if FIG.exists() else None,
        'all_sample': summarize(''),
        'line0': summarize(' and handicap_line = 0'),
    }
    line0_D = out['line0']['winner_D']
    out['acceptance_checks'] = {
        'line0_refunds_excluded_51': out['line0']['refunds_excluded'] == 51,
        'all_refunds_excluded_73': out['all_sample']['refunds_excluded'] == 73,
        'line0_n_23008_after_refund_exclusion': out['line0']['n_after_refund_exclusion'] == 23008,
        'line0_all_D_buckets_below_break_even': all(v['projected_q'] < 1.0 for v in line0_D.values()),
        'line0_D_approximately_flat_near_1': all(0.98 <= v['mean_D'] <= 1.06 for v in line0_D.values()),
    }
    out['errors'] = [k for k, v in out['acceptance_checks'].items() if not v]
    if not out['figure_exists'] or not out['figure_doc_reference'] or not out['doc_mentions_refunds']:
        out['errors'].append('doc_or_figure_delivery_missing')
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(1 if out['errors'] else 0)

if __name__ == '__main__':
    main()
