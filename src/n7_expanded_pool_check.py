"""Independent fixed SP gate and complete prefix-pool reconstruction; no IO."""
import numpy as np


def verify_expanded_pool(snapshot, bundle, surface, cutoff, config, policy):
    """Verify all legal options, including excluded groups and opening indices.

    surface must come from independent core_replay_surface. All cutoff maps
    must match. CNY2 units, .25 target, CNY256 cap and single copies are fixed.
    Reference .25/.30 admission contributes opening depths before SP filtering,
    exactly as in the original shared pool. Return True or raise ValueError.
    Does not trust the R pool's eligibility, depth list, roles or membership.
    """
    if (not cutoff or snapshot['cutoffs']!=cutoff or bundle['cutoffs']!=cutoff
            or config['targets']!=.25 or config['cap_cny']!=256 or config['max_copies']!=1
            or config['depth_reference_targets']!=[.25,.30]
            or snapshot['mode']!=policy['mode'] or policy['mode'] not in ('BREADTH','DEPTH')
            or not np.isfinite(policy['minimum_sp']) or policy['minimum_sp']<1):
        raise ValueError('Invalid fixed pool contract')
    fixtures=bundle['expanded_pool']['fixtures']
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in fixtures])
    q=np.array([[f[f'q_{d}'] for d in 'WDL'] for f in fixtures])
    eligible=1/q[np.arange(len(p)),p.argmax(axis=1)]>=policy['minimum_sp']
    depths=set(config['depths']);openings={}
    for s in bundle['sleeves']:
        sid=s['id'];z=surface[sid]
        for target in config['depth_reference_targets']:
            crossing=int(np.searchsorted(z['mass'],target,side='left'))
            if 2*crossing<=config['cap_cny']:
                depths.add(crossing)
                if target==.25 and eligible[z['f']].all():openings[sid]=crossing
    expected=[];opening_indices=[]
    for s in bundle['sleeves']:
        sid=s['id']
        if sid not in openings:continue
        for d in sorted(depths):
            if d<openings[sid] or (policy['mode']=='BREADTH' and d!=openings[sid]):continue
            expected.append((sid,d))
            if d==openings[sid]:opening_indices.append(len(expected))
    actual=[(o['sleeve_id'],o['depth']) for o in snapshot['options']]
    if (actual!=expected or np.atleast_1d(snapshot['opening_options']).tolist()!=opening_indices
            or np.atleast_1d(snapshot['opportunity_options']).tolist()!=[]
            or any(o['role']!='CORE' or o['rule']!='PROB_PREFIX' or o['unit_copies']!=1
                   for o in snapshot['options'])):
        raise ValueError('Admissible SP/depth option pool differs')
    return True
