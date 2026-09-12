"""Fixed diagnostic weighted pools; replacement across groups, never within one."""
from collections import Counter
import itertools
import math
import numpy as np
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def weighted_n7_plan(frame, *, cutoffs, seed, single_threshold,
                     single_alternative_probability, double_alternative_probability,
                     single_gap_limit, double_gap_limit, double_condition,
                     max_attempts, single_pool_count, budget_cny, unit_cny, payout_factor):
    """Return sealed label-free N7 plan with arbitrary-precision outcome sampling.

    Exact columns: issue/slot/provider_id/handicap, p_W/D/L (calibrated market),
    q_W/D/L (raw market, proxy SP=1/q), strength_W/D/L. Probabilities are fractions. S pool uses
    pTop1 weights and conditional Top1/Top2 choices. B pool uses pTop2 mass weights
    and Top2/third choices. Explicit alternative probabilities override those
    outcome proportions (None selects probability-proportional sampling).
    S alternative=second outcome; B alternative=third outcome SINGLE.
    Pools are disjoint: S=Top1>=threshold; B=its complement. S alternatives need
    Top1-Top2<=single_gap_limit (None unrestricted). B condition is ALLOW, GAP,
    STRENGTH_TOP2, or JOINT (gap AND strength). Gap=Top1-Top3; strength means
    market third belongs to strength Top2. Gap comparisons allow1e-12 tolerance.
    Pool roles are shuffled before sequential PPS draws; weights renormalize.
    Across groups there is no depletion/cap; within a group slots are unique.
    Expected ROI is recorded only, never filters groups. Unaffordable/duplicate
    groups cost nothing; stop at max_attempts or cash<unit. Exact support groups
    are unique, though elementary bets may overlap (reported separately).
    Fixed diagnostic parameters, no tuning, I/O, labels or input mutation.
    """
    required={'issue','slot','provider_id','handicap'}|{f'{p}_{d}' for p in ('p','q','strength') for d in 'WDL'}
    if (set(frame)!=required or type(seed) is not int or seed<0
            or type(max_attempts) is not int or max_attempts<1
            or type(single_pool_count) is not int or not 0<=single_pool_count<=7
            or not np.isfinite(single_threshold) or not 0<=single_threshold<=1
            or any(v is not None and (not np.isfinite(v) or not 0<=v<=1)
                for v in (single_alternative_probability,double_alternative_probability))
            or any(v is not None and (not np.isfinite(v) or not 0<=v<=1) for v in (single_gap_limit,double_gap_limit))
            or double_condition not in ('ALLOW','GAP','STRENGTH_TOP2','JOINT')
            or (double_condition in ('GAP','JOINT') and double_gap_limit is None)
            or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)):
        raise ValueError('Explicit fixed sampling contract required')
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=x.sort_values('slot');records=x.to_dict('records')
    strength=x[[f'strength_{d}' for d in 'WDL']].to_numpy(float)
    if not np.isfinite(strength).all() or (strength<0).any() or not np.allclose(strength.sum(axis=1),1,atol=1e-8,rtol=0):
        raise ValueError('Normalized strength probabilities required')
    p=x[[f'p_{d}' for d in 'WDL']].to_numpy(float)
    order=np.argsort(-p,axis=1,kind='stable')
    top1=np.take_along_axis(p,order[:,:1],axis=1).ravel()
    top2=np.take_along_axis(p,order[:,:2],axis=1).sum(axis=1)
    single_mask=top1>=single_threshold
    single_allowed=np.ones(len(x),dtype=bool) if single_gap_limit is None else top1-p[np.arange(len(x)),order[:,1]]<=single_gap_limit+1e-12
    strength_order=np.argsort(-strength,axis=1,kind='stable')
    signal=(strength_order[:,:2]==order[:,2,None]).any(axis=1)
    gap=np.ones(len(x),dtype=bool) if double_gap_limit is None else top1-p[np.arange(len(x)),order[:,2]]<=double_gap_limit+1e-12
    double_allowed={'ALLOW':np.ones(len(x),dtype=bool),'GAP':gap,'STRENGTH_TOP2':signal,'JOINT':gap&signal}[double_condition]
    rng=np.random.default_rng(seed);seen=set();legs=[];tickets=[];accepted=[];reasons=Counter()
    cash=budget_cny;attempts=0
    enough=int(single_mask.sum())>=single_pool_count and int((~single_mask).sum())>=7-single_pool_count
    for attempt in range(max_attempts if enough else 0):
        if cash<unit_cny:break
        attempts=attempt+1;chosen=set();group=[];failed=False
        roles=rng.permutation([True]*single_pool_count+[False]*(7-single_pool_count))
        for single in roles:
            weight=(top1 if single else top2).copy()
            weight[~single_mask if single else single_mask]=0
            if chosen:weight[list(chosen)]=0
            if weight.sum()<=0:failed=True;break
            i=int(rng.choice(len(x),p=weight/weight.sum()));chosen.add(i)
            ranks=order[i]
            if single:
                primary=top1[i]/top2[i] if single_alternative_probability is None else 1-single_alternative_probability
                allowed=bool(single_allowed[i])
                if not allowed:primary=1.
                selected=[int(ranks[0] if rng.random()<primary else ranks[1])]
            else:
                primary=top2[i] if double_alternative_probability is None else 1-double_alternative_probability
                allowed=bool(double_allowed[i])
                if not allowed:primary=1.
                selected=list(ranks[:2]) if rng.random()<primary else [int(ranks[2])]
            row=records[i].copy();row.update(support=''.join('310'[d] for d in sorted(selected)),
                pool='S' if single else 'B',mass=float(sum(p[i,d] for d in selected)),
                alternative_eligible=allowed,alternative_used=bool(selected==[int(ranks[1])] if single else selected==[int(ranks[2])]),
                value=float(sum(p[i,d]/row['q_'+'WDL'[d]] for d in selected)/len(selected)))
            group.append(row)
        if failed:reasons['POOL_EXHAUSTED_WITHIN_GROUP']+=1;continue
        group.sort(key=lambda z:z['slot']);signature=tuple((z['slot'],z['support']) for z in group)
        if signature in seen:reasons['DUPLICATE']+=1;continue
        seen.add(signature)
        cost=unit_cny*math.prod(len(z['support']) for z in group)
        roi=payout_factor*math.prod(z['value'] for z in group)-1
        if cost>cash:reasons['UNAFFORDABLE']+=1;continue
        g=len(accepted)+1;cash-=cost
        legs.extend(dict(z,group=g) for z in group)
        tickets.extend(dict(group=g,code=''.join(c),units=1) for c in itertools.product(*(z['support'] for z in group)))
        accepted.append(dict(group=g,cost=cost,expected_roi=roi,coverage=math.prod(z['mass'] for z in group),
            actual_singles=sum(len(z['support'])==1 for z in group)))
    elementary=Counter((tuple(z['slot'] for z in legs if z['group']==t['group']),t['code']) for t in tickets)
    plan=dict(issue=str(x.issue.iloc[0]),selector='WEIGHTED_POOLS',single_rule='WEIGHTED_POOLS',
        shape='VARIABLE_SINGLES',funding='UNIT',groups=len(accepted),legs=legs,tickets=tickets,
        stake=budget_cny-cash,cash_cny=cash,budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
        cutoffs=bound,parameters=dict(seed=seed,single_threshold=single_threshold,
            single_alternative_probability=single_alternative_probability,double_alternative_probability=double_alternative_probability,
            single_gap_limit=single_gap_limit,double_gap_limit=double_gap_limit,double_condition=double_condition,
            max_attempts=max_attempts,single_pool_count=single_pool_count),attempts=attempts,
        pool_counts=dict(single=int(single_mask.sum()),double=int((~single_mask).sum()),
            eligible_single=int((single_mask&single_allowed).sum()),eligible_double=int((~single_mask&double_allowed).sum())),
        rejections=dict(reasons),group_metrics=accepted,unique_elementary=len(elementary),
        repeated_elementary=len(tickets)-len(elementary),max_fixture_reuse=max(Counter(z['slot'] for z in legs).values(),default=0),
        input_hash=stable_json_hash(frame.sort_values('slot').to_json(orient='records')),
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET')
    return dict(plan,seal=stable_json_hash(plan))
