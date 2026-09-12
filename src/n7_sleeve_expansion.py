"""Nested Top64 candidate expansion; exposed-history diagnostics, never admission."""
import math
import numpy as np
import pandas as pd
from src.n7_probability_gate import select_probability_gate
from src.n7_sleeve_states import enumerate_sleeve, select_sleeve_states
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def expand_top64(pool, *, cutoffs, original_groups, candidate_count, seed,
                 maximum_attempts, budget_cny, unit_cny, payout_factor):
    """Preserve ordered original groups, append unique quality/Top2/uniform sets.

    Every appended attempt cycles through quality, Top2-weighted, uniform. Quality
    consumes distinct sets from original probability-ranked tickets, then uses
    Top2 sampling when exhausted. Prefixes are nested independently of requested
    count. Stops at combinatorial/attempt cap and reports counts. Inputs contain
    identities and normalized p/q, no labels. Output compact Top64 probabilities,
    state IDs and q-price expected gross in CNY, sealed with cutoffs/parameters.
    Enumerations and Top64 tie rules use the authoritative sleeve implementation.
    No I/O, fitting or prospective admissibility; invalid contracts raise ValueError.
    """
    if (type(candidate_count) is not int or candidate_count < len(original_groups)
        or not original_groups or type(seed) is not int or seed < 0
        or type(maximum_attempts) is not int or maximum_attempts < 1):
        raise ValueError('Invalid expansion parameters')
    select_probability_gate(pool, cutoffs=cutoffs, min_probability=0., ranking='PROB',
        search_depth=pool['parameters']['depth'], budget_cny=budget_cny,
        unit_cny=unit_cny, payout_factor=payout_factor)
    f=pd.DataFrame(pool['fixtures'])
    if f.slot.tolist()!=sorted(f.slot.tolist()):
        raise ValueError('Canonical fixture ordering required')
    groups=[];seen=set();origins=[]
    for group in original_groups:
        if (len(group)!=7 or any(type(i) is not int or not 0<=i<len(f) for i in group)
            or group!=sorted(set(group)) or tuple(group) in seen):
            raise ValueError('Original groups must be distinct canonical seven-fixture sets')
        seen.add(tuple(group));groups.append(tuple(group));origins.append('ORIGINAL24')
    p=f[[f'p_{d}' for d in 'WDL']].to_numpy(float)
    encoded=np.asarray(pool['encoded_tickets'],dtype=int).reshape(-1,7)
    mass=np.prod(p[encoded//3,encoded%3],axis=1)
    quality=list(dict.fromkeys(tuple(row//3) for row in encoded[np.lexsort((np.arange(len(mass)),-mass))]))
    cursor=0;rng=np.random.default_rng(seed);top2=np.sort(p,axis=1)[:,-2:].sum(axis=1)
    limit=min(candidate_count,math.comb(len(f),7));attempts=0
    while len(groups)<limit and attempts<maximum_attempts:
        lane=attempts%3;attempts+=1
        if lane==0:
            while cursor<len(quality) and quality[cursor] in seen:cursor+=1
        if lane==0 and cursor<len(quality):
            key=quality[cursor];cursor+=1;origin='QUALITY_EXTENSION'
        else:
            weighted=lane!=2
            key=tuple(sorted(rng.choice(len(f),7,replace=False,p=top2/top2.sum() if weighted else None).tolist()))
            origin='TOP2_WEIGHTED' if weighted else 'UNIFORM'
        if key not in seen:seen.add(key);groups.append(key);origins.append(origin)
    sleeves=[]
    for index,group in enumerate(groups):
        frame=f.iloc[list(group)];native={str(s):cutoffs[str(s)] for s in frame.slot}
        e=enumerate_sleeve(frame,cutoffs=native,unit_cny=unit_cny,payout_factor=payout_factor)
        chosen=select_sleeve_states(e,cutoffs=native,kind='TOP64_PROB',ticket_count=64,
            minimum_coverage=None,minimum_roi=None,seed=seed,hamming_minimum=2,
            solver_seconds=1.,solver_relative_gap=.001,solver_feasibility_tolerance=1e-9)
        ids=chosen['state_ids']
        sleeves.append(dict(id=index,fixture_indices=[int(i) for i in group],origin=origins[index],
            state_ids=ids,probabilities=[e['probability'][i] for i in ids],
            estimated_payouts=[e['estimated_payout'][i] for i in ids],
            coverage=chosen['coverage'],expected_gross=chosen['expected_gross']))
    out=dict(issue=pool['issue'],fixtures=pool['fixtures'],cutoffs=pool['cutoffs'],sleeves=sleeves,
        pool_seal=pool['seal'],historical_admission=False,mode=pool['mode'],attempts=attempts,
        parameters=dict(candidate_count=candidate_count,original_count=len(original_groups),seed=seed,
            maximum_attempts=maximum_attempts,budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor))
    return dict(out,seal=stable_json_hash(out))


def sample_top64(expansion, *, cutoffs, pool_size, coverage_floor, weighting, seed,
                 evaluation_worlds, budget_cny, unit_cny, payout_factor):
    """Draw eight distinct eligible sets, proportional expected gross or uniform.

    Strict coverage > floor, no replacement; normalized weights recomputed at
    each draw. Fewer than eight -> NO_BET, all cash. Each selected set uses its
    original probability Top64. Shared fixture worlds estimate any-hit, using
    an RNG independent of sampling. Receipt includes draw weights/denominators,
    source seal, cutoff and parameters; no labels/I/O/fit. Frozen p/q diagnostics.
    """
    if expansion.get('seal')!=stable_json_hash({k:v for k,v in expansion.items() if k!='seal'}):
        raise ValueError('Expansion changed')
    _,bound=rank_double_candidates(pd.DataFrame(expansion['fixtures']),cutoffs=cutoffs)
    if (bound!=expansion['cutoffs'] or type(pool_size) is not int or pool_size<1
        or pool_size>expansion['parameters']['candidate_count']
        or not np.isfinite(coverage_floor) or not 0<=coverage_floor<=1
        or weighting not in ('EXPECTED_GROSS','UNIFORM') or type(seed) is not int or seed<0
        or type(evaluation_worlds) is not int or evaluation_worlds<1
        or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)):
        raise ValueError('Invalid sampling contract/cutoff')
    available=[s for s in expansion['sleeves'][:pool_size] if s['coverage']>coverage_floor]
    selected=[];draws=[];eligible_count=len(available)
    rng=np.random.default_rng(np.random.SeedSequence([seed,0]))
    if eligible_count>=8:
        for step in range(8):
            weights=np.array([s['expected_gross'] if weighting=='EXPECTED_GROSS' else 1. for s in available])
            if not np.isfinite(weights).all() or (weights<=0).any():raise ValueError('Positive finite sampling weights required')
            i=int(rng.choice(len(available),p=weights/weights.sum()))
            draws.append(dict(step=step,sleeve_id=available[i]['id'],weight=float(weights[i]),
                remaining_weight=float(weights.sum()),probability=float(weights[i]/weights.sum())))
            selected.append(available.pop(i))
    states=np.indices((3,)*7).reshape(7,-1).T
    ii=[];dd=[]
    for s in selected:
        ii.extend([s['fixture_indices']]*64);dd.extend(states[s['state_ids']].tolist())
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in expansion['fixtures']])
    rng=np.random.default_rng(np.random.SeedSequence([seed,1]))
    outcomes=np.array([np.searchsorted(np.r_[triplet.cumsum()[:2],1.],rng.random(evaluation_worlds),side='right') for triplet in p])
    hit_count=np.zeros(evaluation_worlds,dtype=int)
    for s in selected:
        sid=(outcomes[s['fixture_indices']]*(3**np.arange(6,-1,-1))[:,None]).sum(axis=0)
        accepted=np.zeros(2187,dtype=bool);accepted[s['state_ids']]=True;hit_count+=accepted[sid]
    stake=len(ii)*unit_cny;gross=sum(s['expected_gross'] for s in selected)
    out=dict(issue=expansion['issue'],fixtures=expansion['fixtures'],cutoffs=bound,
        fixture_indices=ii,outcomes=dd,groups=len(ii),stake=stake,cash_cny=budget_cny-stake,
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
        expected_net=gross-stake,expected_roi=gross/stake-1 if stake else None,
        sleeve_ids=[s['id'] for s in selected],eligible_count=eligible_count,
        actual_pool_size=min(pool_size,len(expansion['sleeves'])),draws=draws,
        eval_coverage=float(np.mean(hit_count>0)),
        hit_sleeve_distribution=(np.bincount(hit_count,minlength=9)/evaluation_worlds).tolist(),
        independent_counterfactual=float(1-np.prod([1-s['coverage'] for s in selected])),
        selected_mean_coverage=float(np.mean([s['coverage'] for s in selected])) if selected else None,
        expansion_seal=expansion['seal'],historical_admission=False,mode=expansion['mode'],
        no_bet_reason=None if selected else 'FEWER_THAN_EIGHT_ABOVE_STRICT_FLOOR',
        parameters=dict(pool_size=pool_size,coverage_floor=coverage_floor,weighting=weighting,
            seed=seed,evaluation_worlds=evaluation_worlds))
    return dict(out,seal=stable_json_hash(out))
