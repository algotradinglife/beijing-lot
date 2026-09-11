"""Fixed single-position safeguards over sealed N7 groups; no learning."""
import itertools
from collections import Counter
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_decision_chain import limit_decision_chain_plan


def guard_single_positions(plan,*,cutoffs,protect_conflict,minimum_tv,single_cap):
    """Keep source group order/fixtures; choose two eligible TOP1 single legs.

    Conflict means differing p/q top direction and TV>=explicit threshold.
    A cap counts prior funded singles for the same slot/direction, including
    prefix groups. Ineligible positions stay double. If fewer than two are
    eligible, skip the whole group, no refill, hold cash. No support reversal.
    Complete CNY2 unit tickets only, budget1024, payout.65 from sealed source.
    Returns sealed plan plus reason ledger. No fitting, labels, mutation or I/O.
    """
    limit_decision_chain_plan(plan,groups=0,cutoffs=cutoffs)
    if (type(protect_conflict) is not bool or minimum_tv!=.15 or
        (single_cap is not None and (type(single_cap) is not int or single_cap not in (2,3))) or
        plan['budget_cny']!=1024 or plan['unit_cny']!=2 or plan['payout_factor']!=.65 or
        any(t['units']!=1 for t in plan['tickets'])):
        raise ValueError('Explicit fixed policy and one-unit budget required')
    counts=Counter();legs=[];tickets=[];ledger=[];number=0
    for g in range(1,plan['groups']+1):
        rows=sorted([dict(r) for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
        if len(rows)!=7 or len({r['slot'] for r in rows})!=7:raise ValueError('N7 distinct source fixtures required')
        eligible=[];meta=[]
        for i,r in enumerate(rows):
            ps=[r['p_'+d] for d in 'WDL'];qs=[r['q_'+d] for d in 'WDL']
            order=sorted(range(3),key=lambda j:(-ps[j],j));top=order[0];mtop=max(range(3),key=lambda j:qs[j])
            conflict=top!=mtop and sum(abs(p-q) for p,q in zip(ps,qs))/2>=minimum_tv
            capped=single_cap is not None and counts[r['slot'],top]>=single_cap
            meta.append((order,conflict,capped))
            if not (protect_conflict and conflict) and not capped:eligible.append(i)
        chosen=set(sorted(eligible,key=lambda i:(-rows[i]['p_'+'WDL'[meta[i][0][0]]],rows[i]['slot']))[:2])
        funded=len(chosen)==2
        for i,r in enumerate(rows):
            order,conflict,capped=meta[i]
            ledger.append(dict(source_group=g,slot=r['slot'],conflict=conflict,capped=capped,single=funded and i in chosen,funded=funded))
        if not funded:continue
        number+=1;current=[]
        for i,r in enumerate(rows):
            order=meta[i][0];selected=order[:1] if i in chosen else order[:2]
            r.update(group=number,support=''.join('310'[j] for j in range(3) if j in selected))
            current.append(r);legs.append(r)
            if i in chosen:counts[r['slot'],order[0]]+=1
        tickets.extend(dict(group=number,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in current)))
    result={k:plan[k] for k in ['issue','cutoffs','input_sha256','unit_cny','payout_factor','budget_cny']}
    result.update(selector='TOP2_FIXED_GROUPS',shape='C2E0',funding='UNIT',single_rule='GUARDED_TOP1',single_count=2,
        groups=number,legs=legs,tickets=tickets,group_cost_cny=64,stake=len(tickets)*2,cash_cny=1024-len(tickets)*2,
        guard_ledger=ledger,protect_conflict=protect_conflict,minimum_tv=minimum_tv,single_cap=single_cap,
        parent_seal=plan['seal'],historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))
