"""Frozen-group two-single randomization, independent by issue and group."""
import hashlib
import itertools
import random
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.temporal_learning.core import stable_json_hash


def random_second_single_plan(base, *, cutoffs, seed, outcome_mode):
    """Randomize second single on an archived C2E0 plan without changing groups.

    seed: nonnegative native int, fixed before outcomes. outcome_mode: TOP1,
    MODEL or TOP2_UNIFORM. The highest Top1-probability fixture is first single;
    second fixture is uniform among the other six. TOP1 retains its top direction;
    MODEL samples W/D/L by p; TOP2_UNIFORM samples uniformly from original Top2.
    Every group draws independently, so repeated fixtures may have different
    roles/supports or single directions. Identity ties slot/provider; direction
    ties W/D/L. Uses local Random seeded by SHA256(seed|issue|group), not globals.
    Returns sealed plan with exact choice ledger; groups/cost/cash unchanged.
    No fitting, outcome access, cache, source reads or writes. Explicit shared
    Cutoffs and original seal validated by authoritative plan limiter.
    """
    plan=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    if type(seed) is not int or seed<0 or outcome_mode not in {'TOP1','MODEL','TOP2_UNIFORM'}:
        raise ValueError('Explicit nonnegative seed and outcome mode required')
    if base.get('single_count')!=2 or base.get('group_cost_cny')!=64 or base['unit_cny']!=2 or base['payout_factor']!=.65:
        raise ValueError('Frozen two-single CNY2 plan required')
    plan.pop('seal');plan['tickets']=[];ledger=[]
    for group in range(1,base['groups']+1):
        rows=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:(r['slot'],r['provider_id']))
        if len(rows)!=7 or len({r['slot'] for r in rows})!=7:raise ValueError('Seven distinct fixtures required')
        ordered=sorted(rows,key=lambda r:(-max(r['p_'+d] for d in 'WDL'),r['slot'],r['provider_id']))
        anchor=ordered[0];others=sorted(ordered[1:],key=lambda r:(r['slot'],r['provider_id']))
        rng=random.Random(int.from_bytes(hashlib.sha256(f"{seed}|{base['issue']}|{group}".encode()).digest(),'big'))
        second=others[rng.randrange(6)]
        directions={r['slot']:sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d))) for r in rows}
        chosen=directions[second['slot']][0]
        if outcome_mode=='MODEL':chosen=rng.choices(list('WDL'),weights=[second['p_'+d] for d in 'WDL'],k=1)[0]
        elif outcome_mode=='TOP2_UNIFORM':chosen=directions[second['slot']][rng.randrange(2)]
        for r in rows:
            ds=directions[r['slot']][:2]
            if r['slot']==anchor['slot']:ds=ds[:1]
            elif r['slot']==second['slot']:ds=[chosen]
            r['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in ds)
        plan['tickets'].extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in rows)))
        ledger.append(dict(group=group,anchor_slot=anchor['slot'],random_slot=second['slot'],random_direction=chosen))
    if len(plan['tickets'])*2!=base['stake']:raise ValueError('Randomization changed cost')
    plan.update(single_rule='ANCHOR_PLUS_RANDOM',seed=seed,outcome_mode=outcome_mode,
        contraction_ledger=ledger,randomization_source_seal=base['seal'])
    return dict(**plan,seal=stable_json_hash(plan))
