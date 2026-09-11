"""Prematch weak-leg removal and fixed-wallet N5/N6/N7 diagnostic composition."""
import copy
import itertools
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_n7_baseline import settle_n7_baseline


def flatten_component_groups(plan, *, cutoffs, n, budget_cny, unit_cny, payout_factor):
    """Translate sealed one-group components to the existing flat wallet API.

    Inputs: one-issue envelope, exact native cutoffs, explicit N5/N6/N7 and
    CNY constants. Preserve group order, full ticket units/supports and source
    identity, including random swaps; no reranking, fitting, I/O or mutation.
    Reject changed seals, chronology, component shape or inconsistent funding.
    Returns a sealed flat plan bound to the original envelope and components.
    Empty envelopes produce zero groups and retain the original cutoff scope.
    """
    if (type(n) is not int or n not in (5,6,7) or
            (budget_cny,unit_cny,payout_factor)!=(1024,2,.65) or
            plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})):
        raise ValueError('Sealed source and explicit N/CNY constants required')
    result={k:copy.deepcopy(plan[k]) for k in ('issue','cutoffs','input_sha256')}
    result.update(n=n,selector='EXISTING_SOURCE_ORDER',shape='FROZEN_COMPONENTS',funding='UNIT',
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
        groups=len(plan['components']),legs=[],tickets=[],component_source_seal=plan['seal'],
        component_seals=[],historical_admission=False)
    for group,part in enumerate(plan['components'],1):
        if (part.get('seal')!=stable_json_hash({k:v for k,v in part.items() if k!='seal'}) or
                part['issue']!=plan['issue'] or part['n']!=n or part['groups']!=1 or
                part['unit_cny']!=unit_cny or part['payout_factor']!=payout_factor or
                len(part['legs'])!=n or len({r['slot'] for r in part['legs']})!=n or
                any(t['units']!=1 or t['group']!=1 for t in part['tickets']) or
                part['stake']!=unit_cny*len(part['tickets']) or
                any(plan['cutoffs'].get(s)!=t for s,t in part['cutoffs'].items()) or
                any(str(r['slot']) not in part['cutoffs'] for r in part['legs'])):
            raise ValueError('Component shape, seal, cutoff or funding changed')
        result['legs'].extend(dict(copy.deepcopy(r),group=group) for r in part['legs'])
        result['tickets'].extend(dict(copy.deepcopy(t),group=group) for t in part['tickets'])
        result['component_seals'].append(part['seal'])
    result['stake']=sum(t['units'] for t in result['tickets'])*unit_cny
    result['cash_cny']=budget_cny-result['stake']
    if result['stake']!=plan['stake'] or result['cash_cny']!=plan['cash_cny'] or result['cash_cny']<0:
        raise ValueError('Source funding changed')
    result['seal']=stable_json_hash(result)
    limit_decision_chain_plan(result,groups=0,cutoffs=cutoffs)
    return result


def drop_weak_leg(plan,*,cutoffs):
    """Remove lowest baseline support-mass leg from each frozen N7 group.

    Ties use ascending slot. Remaining supports never change; each group may
    have one or two singles. Deduplicate identical resulting holdings, no refill.
    Returns sealed N6 plan with removal ledger and cash; no labels, fit or I/O.
    """
    limit_decision_chain_plan(plan,groups=0,cutoffs=cutoffs)
    legs=[];tickets=[];removed=[];seen=set();group=0
    for old in range(1,plan['groups']+1):
        ls=sorted([dict(r) for r in plan['legs'] if r['group']==old],key=lambda r:r['slot'])
        if len(ls)!=7:raise ValueError('N7 source groups required')
        weak=min(ls,key=lambda r:(sum(r['p_'+dict(zip('310','WDL'))[c]] for c in r['support']),r['slot']))
        kept=[r for r in ls if r['slot']!=weak['slot']]
        key=tuple((r['slot'],r['provider_id'],r['support']) for r in kept)
        removed.append(dict(source_group=old,slot=weak['slot'],support=weak['support'],deduplicated=key in seen))
        if key in seen:continue
        seen.add(key);group+=1
        legs.extend(dict(r,group=group) for r in kept)
        tickets.extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in kept)))
    result={k:copy.deepcopy(plan[k]) for k in ['issue','unit_cny','payout_factor','cutoffs','input_sha256','budget_cny']}
    result.update(n=6,selector='DROP_WEAKEST_SUPPORT',shape='MIXED_C1_C2',funding='UNIT',groups=group,
        legs=legs,tickets=tickets,stake=len(tickets)*plan['unit_cny'],cash_cny=plan['budget_cny']-len(tickets)*plan['unit_cny'],
        removed=removed,parent_seal=plan['seal'],historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))


def fixed_n67_wallets(sources,*,cutoffs,wallets,budget_cny,unit_cny,payout_factor):
    """Whole-group source-order allocation with explicit wallets summing1024.

    Sources are sealed N5/N6/N7 plans with same inputs/cutoffs. No transfer/refill
    from other wallets; exact duplicate full holdings skipped. Returns sealed
    single-group components for authoritative settlement, explicit cash. No I/O.
    """
    if (type(budget_cny) is not int or budget_cny!=1024 or unit_cny!=2 or payout_factor!=.65 or
        set(sources)!=set(wallets) or any(type(v) is not int or v<0 for v in wallets.values()) or sum(wallets.values())!=budget_cny):
        raise ValueError('Explicit1024 wallets and business constants required')
    components=[];seen=set();identity=None
    for name,plan in sources.items():
        limit_decision_chain_plan(plan,groups=0,cutoffs=cutoffs)
        current=(plan['issue'],plan['input_sha256'],plan['cutoffs'])
        if identity is None:identity=current
        if current!=identity or plan['unit_cny']!=unit_cny or plan['payout_factor']!=payout_factor:raise ValueError('Same source contract required')
        spent=0
        for g in range(1,plan['groups']+1):
            ls=sorted([dict(r,group=1) for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
            ts=[dict(t,group=1) for t in plan['tickets'] if t['group']==g]
            expected={''.join(c) for c in itertools.product(*(r['support'] for r in ls))}
            if len(ls) not in (5,6,7) or len({r['slot'] for r in ls})!=len(ls) or len(ts)!=len(expected) or {t['code'] for t in ts}!=expected or any(t['units']!=1 for t in ts):
                raise ValueError('Complete one-unit N5/N6/N7 groups required')
            cost=len(ts)*unit_cny;key=tuple((r['slot'],r['provider_id'],r['support']) for r in ls)
            if key in seen or spent+cost>wallets[name]:continue
            part={k:copy.deepcopy(plan[k]) for k in ['issue','selector','shape','funding','cutoffs','input_sha256']}
            part.update(groups=1,legs=ls,tickets=ts,stake=cost,unit_cny=unit_cny,payout_factor=payout_factor)
            part['seal']=stable_json_hash(part);components.append(dict(source=name,n=len(ls),plan=part));seen.add(key);spent+=cost
    if identity is None:raise ValueError('Nonempty sources required')
    stake=sum(c['plan']['stake'] for c in components)
    result=dict(issue=identity[0],components=components,wallets=wallets,budget_cny=budget_cny,stake=stake,
        cash_cny=budget_cny-stake,source_seals={k:v['seal'] for k,v in sources.items()},cutoffs=identity[2],historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))


def settle_missed_portfolio(plan,audit):
    """Settle sealed one-group components through existing authoritative API.

    Missing or unready labels fail; return CNY totals and N6/N7 group hits.
    No probability fitting, allocation or new payout implementation.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan.get('seal'):raise ValueError('Portfolio changed')
    rows=[settle_n7_baseline(c['plan'],audit) for c in plan['components']]
    if any(r['status']!='COMPLETE' for r in rows):raise ValueError('Incomplete settlement')
    gross=sum(r['gross'] for r in rows)
    return dict(issue=plan['issue'],status='COMPLETE',stake=plan['stake'],gross=gross,net=gross-plan['stake'],
        budget_cny=plan['budget_cny'],cash_cny=plan['cash_cny'],groups=len(rows),hits=sum(r['hits'] for r in rows),
        n6_hits=sum(r['hits'] for c,r in zip(plan['components'],rows) if c['n']==6),
        n7_hits=sum(r['hits'] for c,r in zip(plan['components'],rows) if c['n']==7))
