"""Shared-scenario 8x64 sleeve portfolios and equal-universe monolithic controls."""
import functools
import operator
import numpy as np
from src.n7_incremental_coverage import incremental_coverage_plans
from src.temporal_learning.core import stable_json_hash


def sleeve_portfolios(bundle, *, cutoffs, seed, training_worlds,evaluation_worlds,
                       primary_frontier,overlap_penalty,return_union_fraction,return_passes,
                       budget_cny,unit_cny,payout_factor):
    """Freeze11 arms under common original p/q and shared fixture-world outcomes.

    8 unique fixture sets,64 unique states each; exact512 CNY2 tickets. Missing8
    feasible sets yields explicit NO_BET, never partial exposure labeled alpha.
    Monolithic PROB/COVERAGE use ALL states from the same candidate fixture sets
    plus the prior universe, with no per-ticket probability floor. Empirical
    coverage is union of shared-world bitsets, never independent sleeve hits.
    Diversity penalizes maximum pair overlap, union arm uses marginal hit worlds.
    Return arm starts at quality PROB, one-sleeve local swaps maximize estimated
    gross subject to fixed fraction of quality's TRAINING union rate. No global
    optimum claim. Evaluation RNG cannot alter selected tickets. All constants,
    cutoffs and scenario settings explicit. No I/O or target settlement/labels.
    Returns sealed packed plans and per-sleeve simulation diagnostics.
    """
    if bundle.get('seal')!=stable_json_hash({k:v for k,v in bundle.items() if k!='seal'}):raise ValueError('Candidate bundle changed')
    if (type(seed) is not int or seed<0 or any(type(n) is not int or n<1 for n in (training_worlds,evaluation_worlds))
        or not np.isfinite(overlap_penalty) or overlap_penalty<0 or not np.isfinite(return_union_fraction)
        or not 0<=return_union_fraction<=1 or type(return_passes) is not int or return_passes<0):
        raise ValueError('Explicit portfolio selection contract required')
    pool=bundle['expanded_pool'];sleeves=bundle['sleeves']
    if primary_frontier not in [x[0] for x in bundle['parameters']['frontier_points']]:raise ValueError('Unknown frontier')
    controls=incremental_coverage_plans(pool,cutoffs=cutoffs,seed=seed,training_worlds=training_worlds,
        evaluation_worlds=evaluation_worlds,min_probabilities=[0.],budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
    base=next(p for p in controls if p['parameters']['ranking']=='PROB')
    keys=[(g['id'],name) for g in sleeves for name,s in g['options'].items() if s['status']=='COMPLETE']
    options={(g['id'],name):s for g in sleeves for name,s in g['options'].items() if s['status']=='COMPLETE'}
    groupmap={g['id']:g for g in sleeves};fixture_sets={g['id']:set(g['fixture_indices']) for g in sleeves}
    p=np.array([[x[f'p_{d}'] for d in 'WDL'] for x in pool['fixtures']]);masks=[{},{}];world_states=[]
    for index,(child,n) in enumerate(zip(np.random.SeedSequence(seed).spawn(2),(training_worlds,evaluation_worlds))):
        rng=np.random.default_rng(child)
        outcomes=np.array([np.searchsorted(np.r_[triplet.cumsum()[:2],1.],rng.random(n),side='right') for triplet in p])
        per_group={}
        for g in sleeves:
            state=(outcomes[g['fixture_indices']]*(3**np.arange(6,-1,-1))[:,None]).sum(axis=0)
            per_group[g['id']]=state
            for name,s in g['options'].items():
                if s['status']!='COMPLETE':continue
                accept=np.zeros(2187,dtype=bool);accept[s['state_ids']]=True
                masks[index][g['id'],name]=int.from_bytes(np.packbits(accept[state],bitorder='little').tobytes(),'little')
        world_states.append(per_group)
    prob=sorted([k for k in keys if k[1]=='PROB'],key=lambda k:(-options[k]['coverage'],-options[k]['expected_gross'],k))
    quality=prob[:8] if len(prob)>=8 else []
    selected={'8x64_PROB':quality}
    for arm,kind,objective in [('8x64_DIVERSIFIED_PROB','PROB','DIVERSITY'),('8x64_UNION_PROB','PROB','UNION'),('8x64_FRONTIER',primary_frontier,'UNION')]:
        available=[k for k in keys if k[1]==kind];chosen=[];covered=0
        if len(available)>=8:
            for _ in range(8):
                scored=[]
                for key in available:
                    if key in chosen:continue
                    overlap=max([len(fixture_sets[key[0]]&fixture_sets[k[0]])/7 for k in chosen] or [0.])
                    score=(masks[0][key]&~covered).bit_count()/training_worlds if objective=='UNION' else options[key]['coverage']-overlap_penalty*overlap
                    scored.append((score,options[key]['expected_gross'],options[key]['coverage'],-key[0],key))
                key=max(scored)[-1];chosen.append(key);covered|=masks[0][key]
        selected[arm]=chosen
    selected['8x64_FRONTIER_FIXEDG']=[(k[0],primary_frontier) for k in quality] if quality and all((k[0],primary_frontier) in options for k in quality) else []
    rng=np.random.default_rng(np.random.SeedSequence([seed,424,2]))
    selected['8x64_RANDOM_MATCHSETS']=[prob[int(i)] for i in rng.choice(len(prob),8,replace=False)] if len(prob)>=8 else []
    for arm,kind in [('8x64_RANDOM_STATES','RANDOM'),('8x64_DIVERSITY_STATES','DIVERSITY')]:
        selected[arm]=[(k[0],kind) for k in quality] if quality and all((k[0],kind) in options for k in quality) else []
    chosen=list(quality);quality_mask=functools.reduce(operator.or_,(masks[0][k] for k in quality),0)
    floor=return_union_fraction*quality_mask.bit_count();candidates=[k for k in keys if k[1] in ('PROB','VALUE',primary_frontier)]
    if chosen:
        for _ in range(return_passes):
            best=None
            for pos,old in enumerate(chosen):
                other=chosen[:pos]+chosen[pos+1:];used={k[0] for k in other}
                union=functools.reduce(operator.or_,(masks[0][k] for k in other),0)
                for new in candidates:
                    gain=options[new]['expected_gross']-options[old]['expected_gross']
                    if new[0] in used or gain<=1e-8 or (union|masks[0][new]).bit_count()+1e-8<floor:continue
                    score=(gain,(union|masks[0][new]).bit_count(),-new[0],new[1],pos,new)
                    if best is None or score>best:best=score
            if best is None:break
            chosen[best[-2]]=best[-1]
    selected['8x64_RETURN_AWARE']=chosen
    plans=[]
    for control in controls:
        if control['parameters']['ranking']=='EV':continue
        z={k:v for k,v in control.items() if k!='seal'}
        z.update(arm='MONOLITHIC_'+control['parameters']['ranking']+'512',sleeve_keys=[],bundle_seal=bundle['seal'])
        z['seal']=stable_json_hash(z);plans.append(z)
    for arm,chosen in selected.items():
        if chosen and (len(chosen)!=8 or len({k[0] for k in chosen})!=8):raise ValueError('Eight distinct fixture sets required')
        ii=[];dd=[]
        for key in chosen:
            group=groupmap[key[0]];enum=group['enumeration'];states=np.array(enum['states'])[options[key]['state_ids']]
            ii.extend([group['fixture_indices']]*64);dd.extend(states.tolist())
        if len({tuple(zip(a,b)) for a,b in zip(ii,dd)})!=len(ii):raise ValueError('Duplicate physical tickets')
        rates=[functools.reduce(operator.or_,(mask[k] for k in chosen),0).bit_count()/n for mask,n in zip(masks,(training_worlds,evaluation_worlds))]
        gross=sum(options[k]['expected_gross'] for k in chosen);stake=len(ii)*unit_cny
        counts=np.bincount(np.array(ii,dtype=int).ravel(),minlength=len(p));z={k:v for k,v in base.items() if k!='seal'}
        z.update(arm=arm,fixture_indices=ii,outcomes=dd,groups=len(ii),stake=stake,cash_cny=budget_cny-stake,
            expected_net=float(gross-stake),expected_roi=float(gross/stake-1) if stake else None,
            mean_coverage=float(sum(options[k]['coverage'] for k in chosen)/len(ii)) if ii else None,
            min_selected_probability=min(options[k]['min_probability'] for k in chosen) if chosen else None,
            max_reuse=int(counts.max()),sleeve_keys=[list(k) for k in chosen],bundle_seal=bundle['seal'],
            no_bet_reason=None if chosen else 'FEWER_THAN_EIGHT_FEASIBLE_DISTINCT_SLEEVES',
            simulation=dict(seed=seed,training_worlds=training_worlds,evaluation_worlds=evaluation_worlds,
                training_hit_rate=rates[0],evaluation_hit_rate=rates[1]),
            parameters=dict(primary_frontier=primary_frontier,overlap_penalty=overlap_penalty,
                return_union_fraction=return_union_fraction,return_passes=return_passes,ranking=arm))
        z['seal']=stable_json_hash(z);plans.append(z)
    diagnostics=[]
    for key in keys:
        diagnostics.append(dict(sleeve_id=key[0],kind=key[1],coverage=options[key]['coverage'],
            training_hit_rate=masks[0][key].bit_count()/training_worlds,evaluation_hit_rate=masks[1][key].bit_count()/evaluation_worlds))
    return dict(plans=plans,sleeve_simulation=diagnostics,bundle_seal=bundle['seal'])
