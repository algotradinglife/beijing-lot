"""Complete-support conflict expansion and explicit score-sidecar funding."""
import copy
import hashlib
import itertools
import math
import numpy as np
import pandas as pd
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning.core import stable_json_hash,utc
from src.nowscore_settlement import expected_option


def fund_complete_plan(plan, *, cutoffs, budget_cny, allocation_seed):
    """Spend an exact integer CNY2 budget across an already complete ticket set.

    Each distinct ticket receives floor(total units / ticket count); residual
    units follow fixed SHA256(issue|group|code|seed), never outcomes. All tickets
    receive at least one unit. Explicit original Cutoffs and sealed input required.
    Zero tickets only allow zero budget. Pure, no fitting or mutation.
    """
    result=limit_decision_chain_plan(plan,groups=plan['groups'],cutoffs=cutoffs)
    if type(budget_cny) is not int or budget_cny<0 or budget_cny%2 or type(allocation_seed) is not int or plan['unit_cny']!=2 or plan['payout_factor']!=.65:
        raise ValueError('Explicit integer CNY2 budget and seed required')
    tickets=result['tickets'];count=len(tickets)
    if (count==0 and budget_cny!=0) or (count and budget_cny<2*count):
        raise ValueError('Budget cannot cover complete support')
    if count:
        units,remainder=divmod(budget_cny//2,count)
        ranked=sorted(range(count),key=lambda i:hashlib.sha256(f"{result['issue']}|{tickets[i]['group']}|{tickets[i]['code']}|{allocation_seed}".encode()).hexdigest())
        extra=set(ranked[:remainder])
        for i,ticket in enumerate(tickets):ticket['units']=units+int(i in extra)
    result.pop('seal');result.update(stake=budget_cny,allocation_seed=allocation_seed,
        funding='COMPLETE_EQUAL_UNITS_HASHED_RESIDUAL',allocation='FLOOR_PLUS_FIXED_HASH_REMAINDER',group_budget_cny=None)
    result['seal']=stable_json_hash(result)
    return result


def expand_conflict_plan(base, offers, *, cutoffs, mode, funding, budget_cny, allocation_seed):
    """Expand current doubles to three directions on ONE/ALL conflicts per group.

    ONE prioritizes largest fixed market probability of omitted direction, then
    slot/provider. EXTRA retains all groups at CNY2 per ticket. FIXED examines
    groups in current probability order, keeps any affordable complete group,
    then spends the original budget with fund_complete_plan. If none fit, cash
    remains unspent. No new fixture selection, labels, fit or side effects.
    """
    result=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    if mode not in {'ONE','ALL'} or funding not in {'EXTRA','FIXED'} or budget_cny!=base['stake'] or type(allocation_seed) is not int:
        raise ValueError('Fixed expansion, funding and original budget required')
    by_slot={r['slot']:r for r in offers}
    if len(by_slot)!=len(offers):raise ValueError('Duplicate offers')
    chosen_groups=[];expanded=[];skipped=[];remaining=budget_cny
    for group in range(1,base['groups']+1):
        legs=sorted([copy.deepcopy(r) for r in base['legs'] if r['group']==group],key=lambda r:r['slot'])
        conflicts=[]
        for leg in legs:
            offer=by_slot[leg['slot']]
            if (offer['issue'],offer['provider_id'],offer['handicap'])!=(base['issue'],leg['provider_id'],leg['handicap']) or utc(offer['cutoff'])!=cutoffs[str(leg['slot'])].cutoff_ts:
                raise ValueError('Offer identity/cutoff mismatch')
            if dict(W='3',D='1',L='0')[offer['omitted']] in leg['support'] or len(leg['support'])!=2:
                raise ValueError('Offer must refer to current omitted direction')
            top=max('WDL',key=lambda d:leg['q_'+d])
            if offer['conflict']!=(dict(W='3',D='1',L='0')[top] not in leg['support']) or offer['market_omitted_probability']!=leg['q_'+offer['omitted']]:
                raise ValueError('Conflict differs from fixed market')
            if offer['conflict']:conflicts.append(offer)
        selected=sorted(conflicts,key=lambda r:(-r['market_omitted_probability'],r['slot'],r['provider_id']))[:1 if mode=='ONE' else len(conflicts)]
        slots={r['slot'] for r in selected}
        for leg in legs:
            if leg['slot'] in slots:leg['support']='310'
        cost=2*math.prod(len(r['support']) for r in legs)
        if funding=='FIXED' and cost>remaining:
            skipped.append(dict(source_group=group,cost_cny=cost,remaining_cny=remaining));continue
        remaining-=cost;chosen_groups.append(legs);expanded.extend(dict(slot=s,source_group=group) for s in sorted(slots))
    result.pop('seal');result['legs']=[];result['tickets']=[]
    for index,legs in enumerate(chosen_groups,1):
        for leg in legs:leg['source_group']=leg['group'];leg['group']=index;result['legs'].append(leg)
        for code in itertools.product(*(r['support'] for r in legs)):
            result['tickets'].append(dict(group=index,code=''.join(code),units=1))
    result.update(groups=len(chosen_groups),stake=2*len(result['tickets']),shape='CONFLICT_FULL_'+mode,
        funding='CONFLICT_'+funding,expanded=expanded,unaffordable_groups=skipped,requested_budget_cny=budget_cny,
        offers_hash=stable_json_hash(offers),group_budget_cny=None)
    result['seal']=stable_json_hash(result)
    if funding=='FIXED' and result['groups']:
        result=fund_complete_plan(result,cutoffs=cutoffs,budget_cny=budget_cny,allocation_seed=allocation_seed)
    return result


def conflict_protection_plan(base, offers, *, cutoffs, funding, unit_cny, allocation_seed):
    """Diagnostic, NOT expert-gated: CNY2 on Top1 exact score per selected conflict.

    EXTRA preserves all current parlay groups. FIXED removes the last current
    group to finance scores on retained groups; remaining cash goes uniformly
    to complete retained parlay tickets. If there is only one group or no
    retained eligible conflict, preserve CURRENT with no score bet. All budget
    decisions precede settlement. Missing-price offers are recorded, not bought.
    """
    limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    if funding not in {'EXTRA','FIXED'} or unit_cny!=2 or type(allocation_seed) is not int:
        raise ValueError('Explicit funding/CNY2/seed required')
    by_slot={r['slot']:r for r in offers}
    if len(by_slot)!=len(offers):raise ValueError('Duplicate offers')
    for leg in base['legs']:
        r=by_slot[leg['slot']]
        if (r['issue'],r['provider_id'],r['handicap'])!=(base['issue'],leg['provider_id'],leg['handicap']) or utc(r['cutoff'])!=cutoffs[str(leg['slot'])].cutoff_ts:
            raise ValueError('Offer identity/cutoff mismatch')
        if dict(W='3',D='1',L='0')[r['omitted']] in leg['support']:raise ValueError('Wrong protection direction')
        top=max('WDL',key=lambda d:leg['q_'+d])
        if r['conflict']!=(dict(W='3',D='1',L='0')[top] not in leg['support']):raise ValueError('Conflict differs from fixed market')
        if r['status']=='READY':
            numbers=[r['score_home'],r['score_away'],r['p_score'],r['q_score']]
            if not np.isfinite(numbers).all() or min(numbers)<0 or not 0<r['p_score']<=1 or not 0<r['q_score']<=1 or r['score_home']!=int(r['score_home']) or r['score_away']!=int(r['score_away']):
                raise ValueError('Invalid score offer')
            if r['option']!=f"{r['score_home']}:{r['score_away']}" or expected_option(dict(play='bf',score=r['option']))!=r['option']:
                raise ValueError('Exact bettable score required')
            net=r['score_home']-r['score_away']+r['handicap']
            if ('W' if net>0 else 'D' if net==0 else 'L')!=r['omitted']:raise ValueError('Score does not protect omitted direction')
    main=base;reason='PLANNED'
    if funding=='FIXED':
        if base['groups']<2:reason='NO_ROOM_FOR_COMPLETE_PARLAY_AND_SCORE'
        else:main=limit_decision_chain_plan(base,groups=base['groups']-1,cutoffs=cutoffs)
    scores=[dict(by_slot[r['slot']],stake=unit_cny) for r in main['legs'] if by_slot[r['slot']]['conflict'] and by_slot[r['slot']]['status']=='READY'] if reason=='PLANNED' else []
    if not scores:
        main=base;reason='NO_ELIGIBLE_CONFLICT_RETAINED' if reason=='PLANNED' else reason
    elif funding=='FIXED':
        main=fund_complete_plan(main,cutoffs=cutoffs,budget_cny=base['stake']-sum(r['stake'] for r in scores),allocation_seed=allocation_seed)
    payload=dict(main=main,scores=scores,stake=main['stake']+sum(r['stake'] for r in scores),base_stake=base['stake'],
        funding=funding,reason=reason,unit_cny=unit_cny,payout_factor=base['payout_factor'],
        offers_hash=stable_json_hash(offers),source_plan_seal=base['seal'],historical_admission=False)
    return dict(**payload,seal=stable_json_hash(payload))


def settle_conflict_protection(plan, audit):
    """Settle sealed main/score positions using archived authoritative R audits.

    Uses final BF SP only for settlement, once times .65 and CNY stake. Missing
    winning BF SP leaves the result pending; losing BF SP is unnecessary.
    Identity/handicap/score-option mismatches fail. No decision or fitting.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan.get('seal'):
        raise ValueError('Protection plan changed')
    main=settle_n7_baseline(plan['main'],audit);gross=0.;hits=0
    keys=['issue','slot','provider_id']
    if audit.duplicated(keys).any():raise ValueError('Duplicate settlement identity')
    indexed=audit.set_index(keys)
    for r in plan['scores']:
        key=tuple(r[k] for k in keys)
        if key not in indexed.index:raise ValueError('Missing score identity')
        label=indexed.loc[key]
        if label.handicap!=r['handicap'] or 'IDENTITY' in label.status:raise ValueError('Score identity mismatch')
        actual=expected_option(dict(play='bf',score=f'{int(label.actual_home)}:{int(label.actual_away)}'))
        if label.bf_option!=actual:raise ValueError('BF option differs from score')
        if r['option']==actual:
            if pd.isna(label.bf_sp) or not np.isfinite(label.bf_sp) or label.bf_sp<=0:
                return dict(main,status='PENDING_WINNING_BF_SP',stake=plan['stake'],gross=None,net=None,roi=None)
            gross+=r['stake']*plan['payout_factor']*label.bf_sp;hits+=1
    if main['status'] not in {'COMPLETE','NO_BET'}:return dict(main,stake=plan['stake'])
    total=main['gross']+gross;stake=plan['stake'];score_stake=sum(r['stake'] for r in plan['scores'])
    return dict(main,stake=stake,gross=total,net=total-stake,roi=total/stake-1 if stake else None,
        main_stake=main['stake'],main_gross=main['gross'],score_stake=score_stake,score_gross=gross,
        score_net=gross-score_stake,score_bets=len(plan['scores']),score_hits=hits)
