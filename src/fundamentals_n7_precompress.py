"""Fixture-level compression before constrained two-single/five-double grouping."""
import itertools
from collections import Counter
import numpy as np
from scipy.optimize import milp,Bounds,LinearConstraint
from src.fundamentals_n7_baseline import n7_baseline_plan,rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def precompress_n7_plan(frame, *, cutoffs, budget_cny, mode, value, unit_cny,
                        payout_factor, allocation_seed):
    """Fix single/double status for the whole issue, then select complete groups.

    mode FIXED: top min(value,n) fixtures by highest direction p are single.
    mode THRESHOLD: fixtures whose highest p >= value are single (inclusive).
    FIXED value nonnegative int; THRESHOLD finite number in [0,1]. Single always
    retains Top1; others Top2. Roles/directions stay fixed across repeated groups.
    First take strongest2 singles and strongest5 doubles disjointly, ranked by
    retained probability. Then sequential MILP picks seven with exactly2 singles,
    each fixture <=2 uses and any pair shares <=2. Objective log retained mass
    plus fixed1e-10 slot-rank tie penalty. Solve30s, nonoptimal fails, infeasible
    holds cash. Cost64/group, no repeated units. Explicit native Cutoffs, no fit,
    settlement, writes or cache. Return sealed baseline-compatible C2E0 plan.
    """
    if type(budget_cny) is not int or budget_cny<0 or mode not in {'FIXED','THRESHOLD'}:raise ValueError('Budget/mode required')
    if mode=='FIXED' and (type(value) is not int or value<0):raise ValueError('Nonnegative integer count required')
    if mode=='THRESHOLD' and (type(value) not in (int,float) or not np.isfinite(value) or not 0<=value<=1):raise ValueError('Probability threshold required')
    base=n7_baseline_plan(frame,cutoffs=cutoffs,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,
        unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=allocation_seed)
    ranked,_=rank_double_candidates(frame,cutoffs=cutoffs);pool=ranked.sort_values(['slot','provider_id']).to_dict('records')
    order=sorted(pool,key=lambda r:(-max(r['p_'+d] for d in 'WDL'),r['slot'],r['provider_id']))
    singles={r['slot'] for r in (order[:value] if mode=='FIXED' else [r for r in order if max(r['p_'+d] for d in 'WDL')>=value])}
    for r in pool:
        ds=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))[:1 if r['slot'] in singles else 2]
        r['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in ds)
        r['retained_probability']=sum(r['p_'+d] for d in ds)
    single_rows=sorted([r for r in pool if r['slot'] in singles],key=lambda r:(-r['retained_probability'],r['slot'],r['provider_id']))
    double_rows=sorted([r for r in pool if r['slot'] not in singles],key=lambda r:(-r['retained_probability'],r['slot'],r['provider_id']))
    disjoint=min(budget_cny//64,len(single_rows)//2,len(double_rows)//5)
    groups=[[r['slot'] for r in single_rows[2*i:2*i+2]+double_rows[5*i:5*i+5]] for i in range(disjoint)]
    solver=[];slots=[r['slot'] for r in pool];mask=np.array([s in singles for s in slots],float)
    while len(groups)<budget_cny//64:
        uses=Counter(s for g in groups for s in g)
        matrix=[np.ones(len(slots)),mask]+[np.array([s in g for s in slots],float) for g in groups]
        fit=milp(-np.log([r['retained_probability'] for r in pool])+1e-10*np.arange(len(slots)),
            integrality=np.ones(len(slots)),bounds=Bounds(np.zeros(len(slots)),[int(uses[s]<2) for s in slots]),
            constraints=LinearConstraint(np.array(matrix),[7,2]+[-np.inf]*len(groups),[7,2]+[2]*len(groups)),
            options=dict(time_limit=30,mip_rel_gap=0))
        if fit.status==2:solver.append(dict(status='PROVEN_INFEASIBLE'));break
        if fit.status!=0:raise RuntimeError('Precompression solver did not prove optimality')
        chosen=[s for s,x in zip(slots,fit.x) if x>.5]
        if len(chosen)!=7 or len(set(chosen)&singles)!=2 or any(uses[s]>=2 for s in chosen) or any(len(set(chosen)&set(g))>2 for g in groups):raise ValueError('Invalid solver solution')
        groups.append(chosen);solver.append(dict(status='OPTIMAL',slots=chosen,objective=float(fit.fun)))
    legs=[];tickets=[]
    for group,selected in enumerate(groups,1):
        rows=[dict(r,group=group) for r in pool if r['slot'] in selected];legs.extend(rows)
        tickets.extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in rows)))
    result={k:v for k,v in base.items() if k!='seal'}
    result.update(shape='C2E0',single_rule='PRECOMPRESS',single_count=2,group_cost_cny=64,
        precompress_mode=mode,precompress_value=value,single_slots=sorted(singles),
        groups=len(groups),legs=legs,tickets=tickets,stake=64*len(groups),budget_cny=budget_cny,cash_cny=budget_cny-64*len(groups),
        disjoint_groups=disjoint,overlap_groups=len(groups)-disjoint,overlap_ledger=solver,
        max_uses=2,max_pair_overlap=2,source_plan_seal=base['seal'])
    return dict(**result,seal=stable_json_hash(result))
