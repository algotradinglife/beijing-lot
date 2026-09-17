"""Independent audit oracle for fixed R grid rotation; never produces deployed plans.

No learned clocks or weights: explicit native cutoff validates issue identity.
JSON input contains only sealed predictions and fixed parameters. Returns copies
in input order for replay comparison. No I/O or label access.
"""
import json
import numpy as np
from src.temporal_learning import Cutoff


def replay_rotation_json(payload_json, cutoff):
    """Replay fixed rotation priorities independently from R's vector/group loop."""
    x = json.loads(payload_json)
    if not isinstance(cutoff, Cutoff) or cutoff.identity != x['cutoff_identity']:
        raise ValueError('Cutoff mismatch')
    t = x['tickets']; m = x['members']; p = x['parameters']
    if any(str(r['issue']) != str(x['issue']) for r in t):
        raise ValueError('Issue mismatch')
    # Native target identity must match the explicitly supplied target issue/time.
    if Cutoff.decision_epoch(x['issue'], x['cutoff_ts']).identity != cutoff.identity:
        raise ValueError('Target mismatch')
    ids = [r['ticket_id'] for r in t]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate ticket')
    order = sorted(range(len(t)), key=lambda i: (-t[i]['prob'], ids[i]))
    state = {r['cell']: r['state'] for r in x['signals']}
    copies = np.array([r['base_copies'] for r in t], dtype=int)
    if p['mode'] == 'ROTATE':
        for cell in {r['cell'] for r in t}:
            ix = [i for i in order if t[i]['cell'] == cell and copies[i] == 1]
            if state.get(cell) == 'BAD':
                drop = int(np.floor(len(ix)*p['cut_fraction']))
                if drop:
                    copies[ix[-drop:]] = 0
    removed = np.array([r['base_copies'] == 1 and copies[i] == 0 for i,r in enumerate(t)])
    legs = {}
    for r in m:
        legs.setdefault(str(r['sleeve_id']), set()).add(str(r['fixture']))
    opened = {str(t[i]['sleeve_id']) for i in range(len(t)) if copies[i]}
    exposure = {f:0 for v in legs.values() for f in v}; base = dict(exposure)
    for i,r in enumerate(t):
        for f in legs[str(r['sleeve_id'])]:
            exposure[f] += int(copies[i])*p['unit_cny']
            base[f] += r['base_copies']*p['unit_cny']
    cap = {f:max(base[f],p['fixture_cap_cny']) for f in base}
    eligible = [i for i in order if not removed[i] and t[i]['payout_hat'] >= p['payout_floor']
                and (p['probability_only'] or state.get(t[i]['cell']) == 'GOOD')]
    count = int(copies.sum())
    for stage in (1,2,3):
        # Within a stage each index can be accepted at most once. Earlier rejected
        # exposure/overlap cannot become feasible as only additions are made.
        for i in eligible:
            if count >= p['target_units']:
                break
            sid = str(t[i]['sleeve_id']); ix = legs[sid]
            if copies[i] != (1 if stage == 3 else 0):
                continue
            if stage == 1 and sid in opened:
                continue
            if any(exposure[f]+p['unit_cny'] > cap[f]+1e-9 for f in ix):
                continue
            if sid not in opened and any(len(ix & legs[g]) > p['max_overlap'] for g in opened):
                continue
            copies[i] += 1; count += 1; opened.add(sid)
            for f in ix:
                exposure[f] += p['unit_cny']
    return copies.tolist()
