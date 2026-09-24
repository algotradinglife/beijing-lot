"""One single plus six doubles, extra disjoint groups within an explicit budget."""
import itertools
from collections import Counter
import numpy as np
import pandas as pd
from scipy.optimize import milp,Bounds,LinearConstraint
from src.fundamentals_n7_baseline import n7_baseline_plan,rank_double_candidates
from src.fundamentals_n7_twocover import settle_n7_twocover
from beidan_backend.temporal_learning.core import stable_json_hash


def next_overlap_group(frame, existing_groups, *, cutoffs, max_uses, max_pair_overlap):
    """Select seven highest joint-double-coverage fixtures under fixed reuse caps.

    Pure sequential MILP, not fitting. Existing groups are slot lists, including
    original disjoint groups. Each fixture appears <=max_uses times total and each new
    group shares <=2 slots with every old group. Explicit shared Cutoffs required.
    Maximize sum log(double coverage); deterministic slot-rank penalty 1e-10 is
    a declared tie policy. Solver time limit 30s; nonoptimal/noninfeasible exits
    fail closed, never interpreted as lack of feasible groups. Empty slots only
    for proved infeasibility. No global claim about future-group optimality.
    """
    if type(max_uses) is not int or max_uses not in {2,3,4,6} or type(max_pair_overlap) is not int or max_pair_overlap not in {2,3,4}:raise ValueError('Explicit owner reuse caps required')
    ranked,_=rank_double_candidates(frame,cutoffs=cutoffs)
    ranked=ranked.sort_values(['slot','provider_id']);slots=list(ranked.slot)
    if any(len(g)!=7 or len(set(g))!=7 or not set(g)<=set(slots) for g in existing_groups):
        raise ValueError('Existing groups must contain seven unique known slots')
    counts=Counter(s for g in existing_groups for s in g)
    if any(n>max_uses for n in counts.values()) or any(len(set(a)&set(b))>max_pair_overlap for a,b in itertools.combinations(existing_groups,2)):
        raise ValueError('Existing groups violate reuse caps')
    matrix=[np.ones(len(slots))]+[np.array([s in g for s in slots],float) for g in existing_groups]
    objective=-np.log(ranked.coverage.to_numpy())+1e-10*np.arange(len(slots))
    fit=milp(objective,integrality=np.ones(len(slots)),
        bounds=Bounds(np.zeros(len(slots)),[int(counts[s]<max_uses) for s in slots]),
        constraints=LinearConstraint(np.array(matrix),[7]+[-np.inf]*len(existing_groups),[7]+[max_pair_overlap]*len(existing_groups)),
        options=dict(time_limit=30,mip_rel_gap=0))
    if fit.status==2:return dict(slots=[],status='PROVEN_INFEASIBLE')
    if fit.status!=0:raise RuntimeError('Overlap solver did not prove optimality: '+str(fit.message))
    selected=[int(s) for s,x in zip(slots,fit.x) if x>.5]
    if len(selected)!=7 or any(counts[s]>=max_uses for s in selected) or any(len(set(selected)&set(g))>max_pair_overlap for g in existing_groups):
        raise ValueError('Invalid MILP solution')
    return dict(slots=selected,status='OPTIMAL',objective=float(fit.fun))


def n7_single_plan(frame, *, cutoffs, budget_cny, single_rule, single_count, max_uses, unit_cny,
                   payout_factor, allocation_seed):
    """Freeze a fixed-budget probability-concentrated CkE0 portfolio (k=0..7).

    Input: exact prediction-only one-issue baseline frame and shared Cutoffs.
    budget_cny: nonnegative integer CNY; unit_cny=2; payout_factor=.65 once.
    Every seven fixtures in double-coverage descending order form one group.
    MAX_SINGLE contracts highest Top1 p; MIN_RELATIVE_LOSS maximizes Top1/Top2
    mass, minimizing the relative loss of group hit probability. Slot/provider
    break fixture ties; W,D,L break direction ties. Top1 is always retained.
    Contract the first single_count fixtures under the declared single rule.
    Group cost is 2*2**(7-single_count). First buy disjoint groups, then append feasible overlap
    groups from next_overlap_group within the remaining budget. Every fixture
    <=max_uses groups (explicit2/3/4/6), every pair shares <=2. No repeated elementary units. Cash remains
    cash; no scores, conflict exclusions, historical fitting or I/O.
    Returns baseline-compatible sealed plan plus budget/cash and selection ledger.
    """
    if type(budget_cny) is not int or budget_cny<0 or single_rule not in {'MAX_SINGLE','MIN_RELATIVE_LOSS'}:
        raise ValueError('Explicit nonnegative integer budget and fixed single rule required')
    if type(single_count) is not int or not 0<=single_count<=7:raise ValueError('Integer single_count 0..7 required')
    if type(max_uses) is not int or max_uses not in {2,3,4,6}:raise ValueError('Explicit max_uses 2/3/4/6 required')
    group_cost=unit_cny*2**(7-single_count)
    base=n7_baseline_plan(frame,cutoffs=cutoffs,selector='COVERAGE',shape='C0E0',funding='UNIT',
        max_groups=6,unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=allocation_seed)
    ranked,_=rank_double_candidates(frame,cutoffs=cutoffs)
    ranked=ranked.sort_values(['coverage','slot','provider_id'],ascending=[False,True,True],kind='stable')
    disjoint=min(budget_cny//group_cost,len(ranked)//7);legs=[];tickets=[];ledger=[]
    groups=[list(map(int,ranked.iloc[i*7:(i+1)*7].slot)) for i in range(disjoint)]
    overlap_ledger=[]
    while len(groups)<budget_cny//group_cost:
        extra=next_overlap_group(frame,groups,cutoffs=cutoffs,max_uses=max_uses,max_pair_overlap=2)
        overlap_ledger.append(extra)
        if not extra['slots']:break
        groups.append(extra['slots'])
    count=len(groups)
    for group,slots in enumerate(groups,1):
        rows=ranked[ranked.slot.isin(slots)].sort_values('slot').to_dict('records')
        candidates=[]
        for r in rows:
            order=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))
            top=r['p_'+order[0]];mass=top+r['p_'+order[1]]
            candidates.append(dict(slot=r['slot'],provider_id=r['provider_id'],direction=order[0],
                top1=top,top2=mass,retention=top/mass))
        metric='top1' if single_rule=='MAX_SINGLE' else 'retention'
        chosen=sorted(candidates,key=lambda r:(-r[metric],r['slot'],r['provider_id']))[:single_count]
        selected={r['slot']:r for r in chosen}
        ledger.extend(dict(group=group,**r) for r in chosen)
        for r in rows:
            r['group']=group
            if r['slot'] in selected:r['support']=dict(W='3',D='1',L='0')[selected[r['slot']]['direction']]
            legs.append(r)
        tickets.extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in rows)))
    result={k:v for k,v in base.items() if k!='seal'}
    result.update(shape=f'C{single_count}E0',single_rule=single_rule,single_count=single_count,group_cost_cny=group_cost,groups=count,legs=legs,tickets=tickets,
        stake=group_cost*count,budget_cny=budget_cny,cash_cny=budget_cny-group_cost*count,
        contraction_ledger=ledger,disjoint_groups=disjoint,overlap_groups=count-disjoint,
        overlap_ledger=overlap_ledger,max_uses=max_uses,max_pair_overlap=2,
        max_groups='BUDGET_AND_REUSE_CAPS',source_plan_seal=base['seal'])
    return dict(**result,seal=stable_json_hash(result))


def settle_n7_single(plan, audit):
    """Adapt repeated-fixture groups to existing component settlement API.

    audit has one row per fixture, not per group. Each component has unique
    fixtures, preserving the authoritative one-to-one identity validation.
    No new payout formula; pending winning SP remains pending. Cash is returned
    separately and never counted as gross betting proceeds. Pure, no fitting.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan['seal']:raise ValueError('Plan changed')
    components=[]
    for group in range(1,plan['groups']+1):
        part={k:v for k,v in plan.items() if k!='seal'}
        part.update(groups=1,legs=[r for r in plan['legs'] if r['group']==group],
            tickets=[t for t in plan['tickets'] if t['group']==group],stake=plan['group_cost_cny'])
        part['seal']=stable_json_hash(part);components.append(part)
    envelope=dict(issue=plan['issue'],strategy=plan['single_rule'],funding='UNIT',stake=plan['stake'],
        budget=plan['budget_cny'],model_any_hit=None,components=components)
    envelope['seal']=stable_json_hash(envelope)
    result=settle_n7_twocover(envelope,audit)
    result['cash']=plan['cash_cny']
    return result
