"""Fixed support/depth ablations on sealed groups; no fitting or label access."""
import copy
import itertools
from collections import Counter
import pandas as pd
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_missed_portfolio import drop_weak_leg
from src.temporal_learning.core import stable_json_hash

MODES=('N7_C2_TOP1','N7_C2_RETENTION','N7_C2_RETENTION_CAP2',
       'N7_C1_RETENTION','N7_C0','N6_DROP_SUPPORT','N6_C1_RETENTION')


def rescue_shape_plan(plan,*,cutoffs,market_weight,mode,budget_cny,unit_cny,payout_factor):
    """Rebuild complete holdings in original order under explicit fixed1024 wallet.

    p/q mixture0,.5,1 ranks supports; original p/q values remain in legs.
    TOP1 compresses highest first probability; RETENTION uses first/top-two
    mass. CAP2 counts only funded identical slot/direction singles. N6_DROP
    reuses drop_weak_leg on a C2 TOP1 plan with mixed probabilities for removal;
    N6_C1 first drops weakest top-two then chooses one retention single.
    Whole-group dedup/skip, no refill. Return sealed plan, ledger, source seal,
    decision probabilities and cash in CNY. Missing/invalid source/contracts
    raise ValueError. No input mutation, I/O, fitting, labels or future admission.
    """
    limit_decision_chain_plan(plan,groups=0,cutoffs=cutoffs)
    if (mode not in MODES or type(market_weight) not in (int,float) or market_weight not in (0,.5,1)
        or type(budget_cny) is not int or budget_cny!=1024 or unit_cny!=2 or payout_factor!=.65
        or any(plan[k]!=v for k,v in [('budget_cny',budget_cny),('unit_cny',unit_cny),('payout_factor',payout_factor)])
        or any(t['units']!=1 for t in plan['tickets'])):raise ValueError('Fixed diagnostic policy and business constants required')
    columns=['issue','slot','provider_id','handicap']+[a+'_'+d for a in ['p','q'] for d in 'WDL']
    frame=pd.DataFrame(plan['legs'])[columns].drop_duplicates()
    rank_double_candidates(frame,cutoffs={str(s):cutoffs[str(s)] for s in frame.slot})
    if set(frame.issue)!={plan['issue']}:raise ValueError('Source issue mismatch')
    legs=[];tickets=[];ledger=[];counts=Counter();seen=set();spent=0;number=0
    for g in range(1,plan['groups']+1):
        rows=sorted([copy.deepcopy(r) for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
        if len(rows)!=7 or len({r['slot'] for r in rows})!=7:raise ValueError('Distinct N7 source groups required')
        ranks={};mass={}
        for r in rows:
            s=r['slot'];ps=[(1-market_weight)*r['p_'+d]+market_weight*r['q_'+d] for d in 'WDL']
            mass[s]=ps;ranks[s]=sorted(range(3),key=lambda j:(-ps[j],j))
        removed=None
        if mode=='N6_C1_RETENTION':
            removed=min(rows,key=lambda r:(sum(mass[r['slot']][j] for j in ranks[r['slot']][:2]),r['slot']))['slot']
            rows=[r for r in rows if r['slot']!=removed]
        depth=0 if mode=='N7_C0' else 1 if mode in ('N7_C1_RETENTION','N6_C1_RETENTION') else 2
        candidates=[]
        for r in rows:
            s=r['slot'];order=ranks[s];top=mass[s][order[0]]
            if mode=='N7_C2_RETENTION_CAP2' and counts[s,order[0]]>=2:continue
            score=top if mode in ('N7_C2_TOP1','N6_DROP_SUPPORT') else top/sum(mass[s][j] for j in order[:2])
            candidates.append((s,score))
        singles={s for s,_ in sorted(candidates,key=lambda z:(-z[1],z[0]))[:depth]}
        current=[]
        for r in rows:
            s=r['slot'];selected=ranks[s][:1 if s in singles else 2]
            r.update(support=''.join('310'[j] for j in range(3) if j in selected),decision_probabilities=mass[s])
            current.append(r)
        key=tuple((r['slot'],r['provider_id'],r['support']) for r in current)
        cost=unit_cny*2**(len(rows)-depth)
        reason='SINGLE_CAP' if len(singles)<depth else 'DUPLICATE' if key in seen else 'BUDGET' if spent+cost>budget_cny else 'FUNDED'
        ledger.append(dict(source_group=g,reason=reason,removed_slot=removed,single_slots=sorted(singles)))
        if reason!='FUNDED':continue
        number+=1;spent+=cost;seen.add(key)
        legs.extend(dict(r,group=number) for r in current)
        tickets.extend(dict(group=number,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in current)))
        counts.update((s,ranks[s][0]) for s in singles)
    result={k:copy.deepcopy(plan[k]) for k in ['issue','cutoffs','input_sha256']}
    result.update(selector='FIXED_SOURCE_GROUPS',shape=mode,funding='UNIT',single_rule=mode,groups=number,
        legs=legs,tickets=tickets,stake=spent,cash_cny=budget_cny-spent,budget_cny=budget_cny,unit_cny=unit_cny,
        payout_factor=payout_factor,market_weight=market_weight,ledger=ledger,parent_seal=plan['seal'],historical_admission=False)
    result['seal']=stable_json_hash(result)
    if mode=='N6_DROP_SUPPORT':
        # Shared remover operates on p: use a separately sealed decision view,
        # then restore original p/q so diagnostic values never masquerade as p.
        view=copy.deepcopy(result);view.pop('seal')
        for r in view['legs']:
            for j,d in enumerate('WDL'):r['p_'+d]=r['decision_probabilities'][j]
        view['seal']=stable_json_hash(view)
        dropped=drop_weak_leg(view,cutoffs=cutoffs)
        original={r['slot']:r for r in result['legs']}
        for r in dropped['legs']:
            for d in 'WDL':r['p_'+d]=original[r['slot']]['p_'+d]
        dropped.update(shape=mode,market_weight=market_weight,ledger=ledger,decision_view_seal=view['seal'],parent_seal=plan['seal'])
        dropped.pop('seal');result=dict(**dropped,seal=stable_json_hash(dropped))
    return result
