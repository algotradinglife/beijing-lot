"""Fixed market/model conflict gates on already frozen repeated doubles."""
import itertools
import math
from src.fundamentals_n7_diversity import replace_repeated_double_tail
from src.temporal_learning.core import stable_json_hash


def replace_market_conflict_doubles(base, *, cutoffs, minimum_tv, minimum_market_tail_lead):
    """Gate existing Top2->Top3 replacement using comparable handicap W/D/L.

    p is the frozen corrected score projection; q is the prematch Euro+OU score
    projection, never realized SP. TV=0.5*sum(abs(p-q)). Require TV>=minimum_tv
    AND q(model third)-q(model second)>=minimum_market_tail_lead. Thresholds are
    explicit probability units, inclusive within1e-12, not learned here.
    Only later repeated doubles change; singles, first uses, fixture groups,
    ticket units, budgets, p/q and cutoff identities remain fixed. Return a
    sealed full plan with per-leg conflict/evidence ledger, rebuilt tickets and
    model support metrics. Pure; no labels, fitting, random choices or I/O.
    """
    for value in (minimum_tv, minimum_market_tail_lead):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
            raise ValueError('Conflict thresholds must be finite probabilities in [0,1]')
    # Authoritative source/cutoff/role/unit validation and potential changes.
    plan=replace_repeated_double_tail(base,cutoffs=cutoffs,max_gap=1.)
    plan.pop('seal');lookup={(r['group'],r['slot']):r for r in plan['legs']}
    for row in plan['diversity_ledger']:
        leg=lookup[row['group'],row['slot']]
        order=sorted('WDL',key=lambda d:(-leg['p_'+d],'WDL'.index(d)))
        tv=.5*sum(abs(leg['p_'+d]-leg['q_'+d]) for d in 'WDL')
        lead=leg['q_'+order[2]]-leg['q_'+order[1]]
        qualifies=tv+1e-12>=minimum_tv and lead+1e-12>=minimum_market_tail_lead
        if not qualifies:leg['support']=row['source_support']
        row.update(total_variation=tv,market_tail_lead=lead,conflict_qualifies=qualifies,
            model_first=order[0],model_second=order[1],model_third=order[2],
            market_first=max('WDL',key=lambda d:leg['q_'+d]),
            selected_support=leg['support'],changed=leg['support']!=row['source_support'])
        row['selected_mass']=sum(leg['p_'+d] for d,c in zip('WDL','310') if c in leg['support'])
        for label,support in [('original',row['source_support']),('selected',leg['support'])]:
            row[label+'_market_mass']=sum(leg['q_'+d] for d,c in zip('WDL','310') if c in support)
    tickets=[];identities=set();masses=[];proxy=0.
    for group in range(1,plan['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot'])
        units=plan['group_units'][group-1]
        for code in itertools.product(*(r['support'] for r in legs)):
            identity=tuple((r['slot'],c) for r,c in zip(legs,code))
            if identity in identities:raise ValueError('Conflict gate creates duplicate physical tickets')
            identities.add(identity);tickets.append(dict(group=group,code=''.join(code),units=units))
        masses.append(math.prod(sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs))
        proxy+=plan['unit_cny']*plan['payout_factor']*units*math.prod(sum(r['p_'+d]/r['q_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs)
    if sum(t['units']*plan['unit_cny'] for t in tickets)!=base['stake']:
        raise ValueError('Conflict gate changed stake')
    plan.pop('max_gap')
    plan.update(tickets=tickets,group_probability=masses,model_proxy_gross=proxy,
        diversity_rule='REPEATED_DOUBLE_MARKET_CONFLICT',minimum_tv=minimum_tv,
        minimum_market_tail_lead=minimum_market_tail_lead)
    return dict(**plan,seal=stable_json_hash(plan))
