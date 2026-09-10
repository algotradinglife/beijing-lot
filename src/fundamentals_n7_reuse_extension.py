"""Nested reuse-cap extension preserving every original logical group."""
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_n7_single import n7_single_plan,next_overlap_group
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def extend_n7_reuse_plan(base, frame, *, cutoffs, max_uses, max_pair_overlap):
    """Append C2/C3 groups under a larger cap; never replace or reprice existing bets.

    Explicit native Cutoffs, exact original predictor hash, nondecreasing caps (uses2/3/4/6, pair overlap2/3/4),
    at least one strictly relaxed. Original budget and CNY64/32 group cost required. Sequential MILP selector
    is reused. New group's support uses authoritative n7_single_plan on exactly
    seven fixtures with the original group cost; no copied contraction logic. Preserve original
    legs/tickets and all cash until an affordable feasible group is appended.
    No labels, fitting or I/O. Returns sealed plan with prefix length and solver
    receipts. This is an additional diagnostic, not a selected production rule.
    """
    result=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    rank_double_candidates(frame,cutoffs=cutoffs)
    if (type(max_uses) is not int or max_uses not in {2,3,4,6}
        or type(max_pair_overlap) is not int or max_pair_overlap not in {2,3,4}
        or max_uses<base['max_uses'] or max_pair_overlap<base['max_pair_overlap']
        or (max_uses,max_pair_overlap)==(base['max_uses'],base['max_pair_overlap'])):
        raise ValueError('At least one cap must increase; neither may decrease')
    if (base.get('single_count') not in {2,3} or base.get('group_cost_cny')!=2*2**(7-base['single_count'])
        or base.get('single_rule')!='MAX_SINGLE' or base.get('diversity_rule')):
        raise ValueError('Fixed MAX_SINGLE C2/C3 source required')
    if stable_json_hash(frame.sort_values('slot').to_json(orient='records'))!=base['input_sha256']:
        raise ValueError('Original prediction input identity required')
    groups=[[r['slot'] for r in base['legs'] if r['group']==g] for g in range(1,base['groups']+1)]
    result.pop('seal');solves=[];cost=base['group_cost_cny']
    while result['budget_cny']-cost*len(groups)>=cost:
        extra=next_overlap_group(frame,groups,cutoffs=cutoffs,max_uses=max_uses,max_pair_overlap=max_pair_overlap);solves.append(extra)
        if not extra['slots']:break
        slots=set(extra['slots']);subset=frame[frame.slot.isin(slots)];cuts={str(s):cutoffs[str(s)] for s in slots}
        part=n7_single_plan(subset,cutoffs=cuts,budget_cny=cost,single_rule='MAX_SINGLE',single_count=base['single_count'],max_uses=max_uses,unit_cny=2,payout_factor=.65,allocation_seed=base['allocation_seed'])
        group=len(groups)+1
        result['legs'].extend(dict(r,group=group) for r in part['legs'])
        result['tickets'].extend(dict(t,group=group) for t in part['tickets'])
        result['contraction_ledger'].extend(dict(r,group=group) for r in part['contraction_ledger'])
        groups.append(extra['slots'])
    result.update(groups=len(groups),stake=cost*len(groups),cash_cny=result['budget_cny']-cost*len(groups),
        max_uses=max_uses,max_pair_overlap=max_pair_overlap,overlap_groups=len(groups)-base['disjoint_groups'],overlap_ledger=solves,
        extension_source_seal=base['seal'],preserved_groups=base['groups'],extension_mode='PRESERVE_ALL_PREVIOUS_GROUPS')
    return dict(**result,seal=stable_json_hash(result))
