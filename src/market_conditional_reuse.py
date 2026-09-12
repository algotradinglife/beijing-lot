"""Fixed post-exposure conditional reuse experiments; no fitting or labels."""
import copy
from collections import Counter
import itertools
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning import Cutoff


def conditional_reuse_plan(base, frame, *, cutoffs, single_gap, draw_gap, draw_enabled, mode):
    """Change later occurrences only, preserving first-use supports and funding caps.

    frame contains exact issue/slot/provider_id/handicap, current market q_W/D/L,
    strength_W/D/L. Strength is used ONLY to flag omitted-draw Top2 disagreement.
    single_gap: None disables singles; otherwise absolute Top1-Top2 fraction.
    draw_gap: None means unrestricted disagreement; otherwise market Top2 minus D.
    Threshold comparisons allow 1e-12 numerical tolerance; W,D,L breaks ties.
    SWAP keeps all slots, replacing Top1 by Top2 or double Top2 by D alone.
    Draw contraction reduces Cartesian tickets; savings stay in cash.
    AVOID replaces triggered later positions with highest role-probability eligible
    fixtures, preserving U/P caps against retained and remaining original groups.
    No feasible replacement drops the whole group and retains its cost as cash.
    Returns sealed plan and per-position trigger/change ledger. No input mutation,
    I/O, historical fitting, actual outcomes, or score protection.
    """
    required={'issue','slot','provider_id','handicap'}|{p+d for p in ('q_','strength_') for d in 'WDL'}
    if (set(frame)!=required or mode not in ('SWAP','AVOID') or type(draw_enabled) is not bool
            or any(v is not None and (type(v) not in (int,float) or not 0<=v<=1) for v in (single_gap,draw_gap))):
        raise ValueError('Explicit prediction-only conditional policy required')
    if base.get('seal')!=stable_json_hash({k:v for k,v in base.items() if k!='seal'}):raise ValueError('Base changed')
    if (base.get('probability_source')!='market-balance-draw-1.0.0-diagnostic'
            or base.get('single_count')!=2 or base.get('budget_cny')!=1024
            or base.get('unit_cny')!=2 or base.get('payout_factor')!=.65
            or base.get('substitution')!='NONE' or base.get('max_pair_overlap')!=5):
        raise ValueError('Frozen original calibrated C2/U3-U6/P5 plan required')
    _,bound=rank_double_candidates(frame.rename(columns={f'strength_{d}':f'p_{d}' for d in 'WDL'}),cutoffs=cutoffs)
    if bound!=base['cutoffs']:raise ValueError('Exact original cutoff scope required')
    records={int(r['slot']):r for r in frame.to_dict('records')}
    groups=[[copy.deepcopy(r) for r in base['legs'] if r['group']==g] for g in range(1,base['groups']+1)]
    for group in groups:
        if len(group)!=7 or sum(len(r['support'])==1 for r in group)!=2:raise ValueError('Invalid base shape')
        for r in group:
            x=records[r['slot']]
            if any(r[k]!=x[k] for k in ('issue','provider_id','handicap','q_W','q_D','q_L')):raise ValueError('Input identity/probability changed')
            order=sorted(range(3),key=lambda i:(-x['q_'+'WDL'[i]],i))[:len(r['support'])]
            if r['support']!=''.join('310'[i] for i in sorted(order)):raise ValueError('Base is not unmodified Top1/Top2')
    result=copy.deepcopy(base);result.pop('seal');seen=set();kept=[];ledger=[]
    for index,group in enumerate(groups):
        changed=[];skip=False
        for r in group:
            single=len(r['support'])==1
            triggered,rank,reason=conditional_reuse_trigger(records[r['slot']],cutoff=cutoffs[str(r['slot'])],single=single,
                repeated=r['slot'] in seen,single_gap=single_gap,draw_gap=draw_gap,draw_enabled=draw_enabled)
            entry=dict(original_group=index+1,slot=r['slot'],single=single,repeated=r['slot'] in seen,
                triggered=triggered,reason=reason,original=r['support'],support=r['support'],replacement_slot=None)
            if triggered and mode=='SWAP':
                selected=[rank[1]] if single else [1]
                r['support']=''.join('310'[i] for i in sorted(selected));entry['support']=r['support']
            elif triggered:
                other_groups=kept+groups[index+1:]
                counts=Counter(x['slot'] for g in other_groups for x in g)
                candidates=[]
                for slot,x in records.items():
                    if slot in {z['slot'] for z in group} or counts[slot]>=base['max_uses']:continue
                    flagged,order,_=conditional_reuse_trigger(x,cutoff=cutoffs[str(slot)],single=single,repeated=slot in seen,
                        single_gap=single_gap,draw_gap=draw_gap,draw_enabled=draw_enabled)
                    slots=({z['slot'] for z in group}-{r['slot']})|{slot}
                    if flagged or any(len(slots & {z['slot'] for z in g})>5 for g in other_groups):continue
                    selected=order[:1] if single else order[:2]
                    candidates.append((-sum(x['q_'+'WDL'[i]] for i in selected),slot,selected))
                if not candidates:
                    skip=True;entry['reason']+=':NO_REPLACEMENT_DROP_GROUP'
                else:
                    _,slot,selected=min(candidates);x=records[slot]
                    r.update({k:x[k] for k in ('issue','slot','provider_id','handicap','q_W','q_D','q_L')})
                    for d in 'WDL':r['p_'+d]=x['q_'+d]
                    order=sorted(range(3),key=lambda i:(-x['q_'+'WDL'[i]],i))
                    r.update(coverage=sum(x['q_'+'WDL'[i]] for i in order[:2]),value=2.,
                        support=''.join('310'[i] for i in sorted(selected)))
                    entry.update(replacement_slot=slot,support=r['support'])
            changed.append(entry)
        for entry in changed:entry['group_dropped']=skip
        ledger.extend(changed)
        if not skip:
            kept.append(group);seen.update(r['slot'] for r in group)
    result['legs']=[];result['tickets']=[]
    for g,group in enumerate(kept,1):
        group.sort(key=lambda r:r['slot'])
        result['legs'].extend(dict(r,group=g) for r in group)
        result['tickets'].extend(dict(group=g,code=''.join(code),units=1) for code in itertools.product(*(r['support'] for r in group)))
    stake=2*len(result['tickets'])
    result.update(groups=len(kept),stake=stake,cash_cny=1024-stake,
        single_count=None,group_cost_cny=None,shape='CONDITIONAL_DRAW_SINGLE',
        substitution=mode,conditional_ledger=ledger,conditional_source_seal=base['seal'],
        conditional_frame_hash=stable_json_hash(frame.sort_values('slot').to_json(orient='records')),
        conditional_policy=dict(single_gap=single_gap,draw_gap=draw_gap,draw_enabled=draw_enabled,mode=mode),
        strength_used=draw_enabled,contraction_ledger=[],overlap_ledger=[],disjoint_groups=None,overlap_groups=None)
    return dict(result,seal=stable_json_hash(result))


def settle_conditional_reuse(plan, audit):
    """Settle variable-cost groups via authoritative component settlement.

    Each Cartesian ticket costs CNY2. Retained cash is not a payout. Audit
    identity, missing SP and payout handling belong to settle_n7_twocover.
    No mutation or I/O; reject a changed plan seal.
    """
    from src.fundamentals_n7_twocover import settle_n7_twocover
    if plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):
        raise ValueError('Plan changed')
    components=[]
    for group in range(1,plan['groups']+1):
        part={k:v for k,v in plan.items() if k!='seal'}
        tickets=[t for t in plan['tickets'] if t['group']==group]
        part.update(groups=1,legs=[r for r in plan['legs'] if r['group']==group],
            tickets=tickets,stake=sum(t['units']*plan['unit_cny'] for t in tickets))
        part['seal']=stable_json_hash(part);components.append(part)
    envelope=dict(issue=plan['issue'],strategy=plan['single_rule'],funding='UNIT',
        stake=plan['stake'],budget=plan['budget_cny'],model_any_hit=None,components=components)
    envelope['seal']=stable_json_hash(envelope)
    result=settle_n7_twocover(envelope,audit)
    result['cash']=plan['cash_cny']
    return result


def conditional_reuse_trigger(row, *, cutoff, single, repeated, single_gap, draw_gap, draw_enabled):
    """Pure label-free trigger. Fractions, not percent. Return flag, WDL rank, reason."""
    if not isinstance(cutoff,Cutoff) or cutoff.target_issue!=row['issue']:raise ValueError('Exact native cutoff required')
    order=sorted(range(3),key=lambda i:(-row['q_'+'WDL'[i]],i))
    strength=sorted(range(3),key=lambda i:(-row['strength_'+'WDL'[i]],i))
    if not repeated:return False,order,'FIRST_USE'
    if single:
        flag=single_gap is not None and row['q_'+'WDL'[order[0]]]-row['q_'+'WDL'[order[1]]]<=single_gap+1e-12
        return flag,order,'SINGLE_GAP' if flag else 'NO_TRIGGER'
    flag=draw_enabled and 1 not in order[:2] and 1 in strength[:2]
    flag=flag and (draw_gap is None or row['q_'+'WDL'[order[1]]]-row['q_D']<=draw_gap+1e-12)
    return flag,order,'DRAW_DISAGREEMENT' if flag else 'NO_TRIGGER'
