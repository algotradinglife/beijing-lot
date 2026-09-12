"""Budget recycling across variable-depth N7 sleeves; historical diagnostics."""
import numpy as np
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def sample_capped_sleeves(expansion, *, cutoffs, pool_size, coverage_floor,
                           coverage_cap, seed, evaluation_worlds,
                           budget_cny, unit_cny, payout_factor):
    """Buy longest probability prefixes within cap, then expand distinct sleeves.

    Retain at most64 states per group, order p/value/canonical ID; strict floor
    applies to the retained prefix. Cap is inclusive with no tolerance overspend.
    Sample affordable groups without replacement, proportional expected CNY gross
    of retained states. Recompute weights after each purchase; no eight-group
    requirement. Stop when no remaining complete eligible group is affordable.
    No partial final sleeve or extra funding. Shared fixture-world evaluation uses
    an independent RNG stream. Explicit cutoffs and fixed1024/2/.65; no labels,
    fitting or I/O. Returns sealed settlement plan, group depths and draw ledger.
    """
    if expansion.get('seal')!=stable_json_hash({k:v for k,v in expansion.items() if k!='seal'}):
        raise ValueError('Expansion changed')
    _,bound=rank_double_candidates(pd.DataFrame(expansion['fixtures']),cutoffs=cutoffs)
    if (bound!=expansion['cutoffs'] or type(pool_size) is not int
        or not 1<=pool_size<=expansion['parameters']['candidate_count']
        or not np.isfinite(coverage_floor) or not np.isfinite(coverage_cap)
        or not 0<=coverage_floor<coverage_cap<=1 or type(seed) is not int or seed<0
        or type(evaluation_worlds) is not int or evaluation_worlds<1
        or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)):
        raise ValueError('Invalid cap allocation/cutoff contract')
    candidates=[]
    for s in expansion['sleeves'][:pool_size]:
        ids=np.asarray(s['state_ids']);p=np.asarray(s['probabilities']);pay=np.asarray(s['estimated_payouts'])
        if len(ids)!=64 or len(set(ids.tolist()))!=64 or not np.isfinite(p).all() or not np.isfinite(pay).all() or (p<0).any() or (pay<=0).any():
            raise ValueError('Invalid Top64 state contract')
        order=np.lexsort((ids,-p*pay,-p));cumulative=np.cumsum(p[order])
        k=int(np.sum(cumulative<=coverage_cap));chosen=order[:k]
        mass=float(cumulative[k-1]) if k else 0.
        if mass<=coverage_floor:continue
        candidates.append(dict(id=s['id'],fixture_indices=s['fixture_indices'],state_ids=sorted(ids[chosen].tolist()),
            coverage=mass,original_coverage=s['coverage'],tickets=k,cost_cny=k*unit_cny,
            expected_gross=float(np.sum((p*pay)[chosen]))))
    remaining=list(candidates);cash=budget_cny;selected=[];draws=[]
    rng=np.random.default_rng(np.random.SeedSequence([seed,0]))
    while True:
        affordable=[s for s in remaining if s['cost_cny']<=cash]
        if not affordable:break
        weights=np.array([s['expected_gross'] for s in affordable])
        if not np.isfinite(weights).all() or (weights<=0).any():raise ValueError('Invalid expected-gross weights')
        j=int(rng.choice(len(affordable),p=weights/weights.sum()));s=affordable[j]
        draws.append(dict(step=len(selected),sleeve_id=s['id'],cash_before=cash,
            affordable_count=len(affordable),weight=float(weights[j]),remaining_weight=float(weights.sum()),
            probability=float(weights[j]/weights.sum())))
        selected.append(s);remaining.remove(s);cash-=s['cost_cny']
    states=np.indices((3,)*7).reshape(7,-1).T;ii=[];dd=[]
    for s in selected:
        ii.extend([s['fixture_indices']]*s['tickets']);dd.extend(states[s['state_ids']].tolist())
    if len({tuple(zip(i,d)) for i,d in zip(ii,dd)})!=len(ii):raise ValueError('Duplicate complete tickets')
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in expansion['fixtures']])
    rng=np.random.default_rng(np.random.SeedSequence([seed,1]))
    worlds=np.array([np.searchsorted(np.r_[triplet.cumsum()[:2],1.],rng.random(evaluation_worlds),side='right') for triplet in p])
    hits=np.zeros(evaluation_worlds,dtype=int)
    for s in selected:
        sid=np.ravel_multi_index(worlds[s['fixture_indices']],(3,)*7)
        hits+=np.isin(sid,s['state_ids'])
    stake=budget_cny-cash;gross=sum(s['expected_gross'] for s in selected)
    out=dict(issue=expansion['issue'],fixtures=expansion['fixtures'],cutoffs=bound,
        fixture_indices=ii,outcomes=dd,groups=len(ii),stake=stake,cash_cny=cash,
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
        sleeves=selected,draws=draws,eligible_count=len(candidates),
        expected_net=gross-stake,expected_roi=gross/stake-1 if stake else None,
        eval_coverage=float(np.mean(hits>0)),
        hit_sleeve_distribution=(np.bincount(hits,minlength=len(selected)+1)/evaluation_worlds).tolist(),
        unspent_reason='NO_ELIGIBLE_SLEEVES' if not candidates else
            ('CANDIDATES_EXHAUSTED' if not remaining else 'NO_AFFORDABLE_COMPLETE_SLEEVE') if cash else None,
        expansion_seal=expansion['seal'],historical_admission=False,mode=expansion['mode'],
        parameters=dict(pool_size=pool_size,coverage_floor=coverage_floor,coverage_cap=coverage_cap,
            seed=seed,evaluation_worlds=evaluation_worlds,weighting='EXPECTED_GROSS'))
    return dict(out,seal=stable_json_hash(out))
