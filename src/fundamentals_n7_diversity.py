"""Outcome-support diversity on already frozen fixture groups."""
import itertools
from collections import defaultdict
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.temporal_learning.core import stable_json_hash


def diversify_n7_outcomes(base, *, cutoffs, rule):
    """Change repeated-fixture supports, preserving groups and single/double roles.

    rule must be PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE. Process groups in their
    frozen order. For each fixture/direction score p/(1+previous groups covering
    this direction); select the top1 or top2 according to the original role.
    Ties W,D,L. First use is unchanged; later uses may pick a different single
    or double. This score is a ranking priority, NOT a recalibrated probability.
    Original p/q unchanged. No labels, fitting, random seeds, caching or I/O.
    Native shared Cutoffs/source seal checked by the existing limiter. Return
    sealed plan, full ticket support, and pre-choice count/priority ledger.
    """
    if rule!='PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE':raise ValueError('Explicit fixed diversity rule required')
    if base.get('single_count')!=3 or base.get('group_cost_cny')!=32:raise ValueError('Three-single plan required')
    plan=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    plan.pop('seal');plan['tickets']=[];history=defaultdict(lambda:dict(W=0,D=0,L=0));ledger=[]
    for group in range(1,base['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot'])
        if len(legs)!=7 or sorted(len(r['support']) for r in legs)!=[1,1,1,2,2,2,2]:raise ValueError('Exact three-single/four-double role contract required')
        for r in legs:
            before=dict(history[r['slot']]);priority={d:r['p_'+d]/(1+before[d]) for d in 'WDL'}
            selected=sorted('WDL',key=lambda d:(-priority[d],'WDL'.index(d)))[:len(r['support'])]
            old=r['support'];r['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in selected)
            ledger.append(dict(group=group,slot=r['slot'],provider_id=r['provider_id'],prior_counts=before,
                priority=priority,source_support=old,selected_support=r['support'],changed=r['support']!=old))
            for d in selected:history[r['slot']][d]+=1
        plan['tickets'].extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in legs)))
    if len(plan['tickets'])*plan['unit_cny']!=base['stake']:raise ValueError('Diversity changed stake')
    plan.update(diversity_rule=rule,diversity_ledger=ledger,source_support_plan_seal=base['seal'])
    return dict(**plan,seal=stable_json_hash(plan))
