"""Frozen candidate fixture sets and complete state universes for N7 sleeves."""
import math
import numpy as np
import pandas as pd
from src.n7_probability_gate import select_probability_gate
from src.n7_sleeve_states import enumerate_sleeve,select_sleeve_states
from src.temporal_learning.core import stable_json_hash


def build_sleeve_candidates(pool, *, cutoffs, candidate_count, seed, maximum_attempts,
                             frontier_points, solver_seconds, solver_relative_gap, solver_feasibility_tolerance, budget_cny, unit_cny,payout_factor):
    """Build up to candidate_count unique7-fixture sets: quality/weighted/uniform thirds.

    Candidate_count divisible by3. Quality uses best original ticket probability
    per fixture set; weighted uses normalized match Top2; uniform is a negative
    control source. Fixed attempt cap; fewer than requested sets explicitly recorded.
    Enumerate every state's original p, estimated q-based payout; retain64-state
    PROB/VALUE/DIVERSITY/RANDOM and fixed relative-coverage/ROI frontier selections.
    frontier_points tuples(name, fraction_of_TOP64_coverage, minimum_ROI).
    Expanded monolithic pool is the union of prior pool and ALL2187 states for all
    generated sets, irrespective of selected sleeves. No labels, I/O or fitting.
    Explicit cutoffs validate through shared selection and sleeve enumeration.
    """
    if (type(candidate_count) is not int or candidate_count<3 or candidate_count%3
        or type(seed) is not int or seed<0 or type(maximum_attempts) is not int or maximum_attempts<1
        or not frontier_points or len({x[0] for x in frontier_points})!=len(frontier_points)
        or any(x[0] in ('PROB','VALUE','DIVERSITY','RANDOM') for x in frontier_points)
        or any(not isinstance(x[0],str) or not x[0] or not np.isfinite(x[1]) or not 0<x[1]<=1
               or not np.isfinite(x[2]) or x[2]<-1 for x in frontier_points)):
        raise ValueError('Explicit fixture/frontier grid required')
    select_probability_gate(pool,cutoffs=cutoffs,min_probability=0.,ranking='PROB',search_depth=pool['parameters']['depth'],
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
    x=pd.DataFrame(pool['fixtures']);p=x[[f'p_{d}' for d in 'WDL']].to_numpy(float)
    encoded=np.asarray(pool['encoded_tickets'],dtype=int).reshape(-1,7)
    mass=np.prod(p[encoded//3,encoded%3],axis=1)
    order=np.lexsort((np.arange(len(mass)),-mass));sets=[];seen=set();origin=[]
    limit=min(candidate_count,math.comb(len(x),7)) if len(x)>=7 else 0
    for i in order:
        key=tuple((encoded[i]//3).tolist())
        if key not in seen:seen.add(key);sets.append(key);origin.append('QUALITY')
        if len(sets)>=min(candidate_count//3,limit):break
    rng=np.random.default_rng(seed);top2=np.sort(p,axis=1)[:,-2:].sum(axis=1);attempts=0
    for weighted,target in ((True,min(2*candidate_count//3,limit)),(False,limit)):
        while len(sets)<target and attempts<maximum_attempts:
            attempts+=1;key=tuple(sorted(rng.choice(len(x),7,replace=False,p=top2/top2.sum() if weighted else None).tolist()))
            if key not in seen:seen.add(key);sets.append(key);origin.append('WEIGHTED' if weighted else 'UNIFORM')
    sleeves=[];union=set(map(tuple,encoded.tolist()))
    for j,group in enumerate(sets):
        frame=x.iloc[list(group)];native={str(s):cutoffs[str(s)] for s in frame.slot}
        e=enumerate_sleeve(frame,cutoffs=native,unit_cny=unit_cny,payout_factor=payout_factor)
        options={}
        common=dict(cutoffs=native,ticket_count=64,minimum_coverage=None,minimum_roi=None,seed=seed+j,
            hamming_minimum=2,solver_seconds=solver_seconds,solver_relative_gap=solver_relative_gap,solver_feasibility_tolerance=solver_feasibility_tolerance)
        for name,kind in [('PROB','TOP64_PROB'),('VALUE','TOP64_VALUE'),('DIVERSITY','DIVERSITY'),('RANDOM','RANDOM64')]:
            options[name]=select_sleeve_states(e,kind=kind,**common)
        for name,fraction,roi in frontier_points:
            options[name]=select_sleeve_states(e,kind='FRONTIER',**{**common,
                'minimum_coverage':fraction*options['PROB']['coverage'],'minimum_roi':roi})
        states=np.asarray(e['states']);global_codes=3*np.asarray(group)+states
        union.update(map(tuple,global_codes.tolist()))
        sleeves.append(dict(id=j,fixture_indices=list(group),origin=origin[j],enumeration=e,options=options))
    expanded={k:v for k,v in pool.items() if k not in ('seal','encoded_tickets','minimum_scalar_rank','parameters')}
    expanded.update(encoded_tickets=[list(t) for t in sorted(union)],minimum_scalar_rank=[1]*len(union),
        parameters=dict(n=7,depth=1,tradeoffs=['EXPLICIT_PRIOR_PLUS_ALL_SLEEVE_STATES']),prior_pool_seal=pool['seal'])
    expanded['seal']=stable_json_hash(expanded)
    out=dict(issue=pool['issue'],cutoffs=pool['cutoffs'],sleeves=sleeves,expanded_pool=expanded,
        parameters=dict(candidate_count=candidate_count,seed=seed,maximum_attempts=maximum_attempts,
            frontier_points=frontier_points,solver_seconds=solver_seconds,solver_relative_gap=solver_relative_gap,solver_feasibility_tolerance=solver_feasibility_tolerance,budget_cny=budget_cny,
            unit_cny=unit_cny,payout_factor=payout_factor),attempts=attempts,actual_candidate_count=len(sets),
        prior_pool_seal=pool['seal'],historical_admission=False)
    return dict(out,seal=stable_json_hash(out))
