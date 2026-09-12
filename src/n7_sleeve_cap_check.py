"""Independent capped-prefix and variable-cost draw replay."""
import numpy as np
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def check_capped_plan(plan, expansion, *, cutoffs):
    """Replay exact capped prefixes, affordable draws, tickets and shared worlds.

    Inputs sealed plan and bound previously verified Top64 expansion. Explicit
    cutoff checked against both. Returns selected-sleeve count; invalid identity,
    resealed selection/budget/probability edits raise ValueError. No I/O or labels.
    """
    for obj in (plan,expansion):
        if obj.get('seal')!=stable_json_hash({k:v for k,v in obj.items() if k!='seal'}):raise ValueError('Seal mismatch')
    _,bound=rank_double_candidates(pd.DataFrame(expansion['fixtures']),cutoffs=cutoffs)
    if (plan['cutoffs']!=bound or expansion['cutoffs']!=bound or plan['fixtures']!=expansion['fixtures']
        or plan['expansion_seal']!=expansion['seal'] or plan['historical_admission'] is not False
        or (plan['budget_cny'],plan['unit_cny'],plan['payout_factor'])!=(1024,2,.65)):
        raise ValueError('Source/cutoff/money mismatch')
    cfg=plan['parameters'];candidates=[]
    u=cfg['max_fixture_reuse'];overlap_cap=cfg['max_pair_overlap']
    if ((u is not None and (type(u) is not int or u<1)) or
        (overlap_cap is not None and (type(overlap_cap) is not int or not 0<=overlap_cap<=6))):
        raise ValueError('Invalid concentration caps')
    for s in expansion['sleeves'][:cfg['pool_size']]:
        triples=list(zip(s['state_ids'],s['probabilities'],s['estimated_payouts']))
        triples.sort(key=lambda t:(-t[1],-t[1]*t[2],t[0]));mass=0.;chosen=[]
        for t in triples:
            if mass+t[1]>cfg['coverage_cap']:break
            mass+=t[1];chosen.append(t)
        if mass<=cfg['coverage_floor']:continue
        candidates.append(dict(id=s['id'],fixture_indices=s['fixture_indices'],state_ids=sorted(t[0] for t in chosen),
            coverage=mass,original_coverage=s['coverage'],tickets=len(chosen),cost_cny=2*len(chosen),
            expected_gross=float(np.sum([t[1]*t[2] for t in chosen]))))
    rng=np.random.default_rng(np.random.SeedSequence([cfg['seed'],0]));cash=1024;left=list(candidates);selected=[]
    while True:
        counts={i:sum(i in g['fixture_indices'] for g in selected) for i in range(len(expansion['fixtures']))}
        allowed=[]
        for candidate in left:
            indices=set(candidate['fixture_indices'])
            if u is not None and any(counts[i]>=u for i in indices):continue
            if overlap_cap is not None and any(len(indices.intersection(g['fixture_indices']))>overlap_cap for g in selected):continue
            allowed.append(candidate)
        affordable=[s for s in allowed if s['cost_cny']<=cash]
        if not affordable:break
        weights=np.array([s['expected_gross'] for s in affordable]);j=int(rng.choice(len(affordable),p=weights/weights.sum()))
        s=affordable[j];step=len(selected)
        if step>=len(plan['draws']):raise ValueError('Affordable extension omitted')
        d=plan['draws'][step]
        if (d['step']!=step or d['sleeve_id']!=s['id'] or d['cash_before']!=cash
            or d['affordable_count']!=len(affordable) or not np.isclose(d['probability'],weights[j]/weights.sum(),rtol=1e-12)
            or not np.isclose(d['weight'],weights[j],rtol=1e-12) or not np.isclose(d['remaining_weight'],weights.sum(),rtol=1e-12)):
            raise ValueError('Affordable weighted draw mismatch')
        selected.append(s);left.remove(s);cash-=s['cost_cny']
    if len(selected)!=len(plan['sleeves']) or len(plan['draws'])!=len(selected):raise ValueError('Sleeve cardinality mismatch')
    for expected,actual in zip(selected,plan['sleeves']):
        for key in expected:
            if key in ('coverage','original_coverage','expected_gross'):
                if not np.isclose(actual[key],expected[key],rtol=1e-12,atol=1e-14):raise ValueError('Sleeve numeric mismatch')
            elif actual[key]!=expected[key]:raise ValueError('Capped prefix mismatch')
    ids=np.array(plan['fixture_indices'],dtype=int).reshape(-1,7);codes=np.array(plan['outcomes'],dtype=int).reshape(-1,7)
    if (len(ids)!=len(codes) or len(ids)!=plan['groups'] or len(ids)*2!=1024-cash
        or plan['cash_cny']!=cash or plan['stake']!=1024-cash or plan['eligible_count']!=len(candidates)
        or len({tuple(3*i+d) for i,d in zip(ids,codes)})!=len(ids)):
        raise ValueError('Packed budget/identity mismatch')
    cursor=0
    for s in selected:
        end=cursor+s['tickets']
        if not np.all(ids[cursor:end]==s['fixture_indices']) or np.ravel_multi_index(codes[cursor:end].T,(3,)*7).tolist()!=s['state_ids']:
            raise ValueError('Packed prefix identity mismatch')
        cursor=end
    gross=sum(s['expected_gross'] for s in selected)
    if not np.isclose(plan['expected_net'],gross-plan['stake'],rtol=1e-12):raise ValueError('Expected return mismatch')
    if selected:
        if not np.isclose(plan['expected_roi'],gross/plan['stake']-1,rtol=1e-12):raise ValueError('Expected ROI mismatch')
    elif plan['expected_roi'] is not None:raise ValueError('Empty ROI must be null')
    reason='NO_ELIGIBLE_SLEEVES' if not candidates else ('CANDIDATES_EXHAUSTED' if not left else ('CONCENTRATION_CAPS_EXHAUSTED' if not allowed else 'NO_AFFORDABLE_COMPLETE_SLEEVE')) if cash else None
    if plan['unspent_reason']!=reason:raise ValueError('Cash reason mismatch')
    rng=np.random.default_rng(np.random.SeedSequence([cfg['seed'],1]));n=cfg['evaluation_worlds']
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in plan['fixtures']])
    worlds=np.array([np.searchsorted(np.r_[row.cumsum()[:2],1.],rng.random(n),side='right') for row in p]);hits=np.zeros(n,dtype=int)
    for s in selected:
        sid=(worlds[s['fixture_indices']]*(3**np.arange(6,-1,-1))[:,None]).sum(axis=0)
        accept=np.zeros(2187,dtype=bool);accept[s['state_ids']]=True;hits+=accept[sid]
    if plan['eval_coverage']!=float(np.mean(hits>0)) or not np.allclose(plan['hit_sleeve_distribution'],np.bincount(hits,minlength=len(selected)+1)/n,rtol=0,atol=1e-15):
        raise ValueError('Shared-world coverage mismatch')
    return len(selected)
