"""Fixed N6/N7 overlap diagnostic. Reuses Top2 validation, cutoff and cash contracts."""
import copy
import hashlib
import itertools
import math
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates,settle_n7_baseline
from beidan_backend.temporal_learning.core import stable_json_hash


def overlay_any_hit(components):
    """Exact union probability of funded group hits, assuming independent fixtures.

    Shared fixtures counted once in intersections; inclusion-exclusion over at
    most13 domain-specific ticket groups (8191 subsets), no Monte Carlo or fit.
    Components must share the same fixed Top2 support and probability per ID.
    """
    events=[];prob={}
    for part in components:
        for group in range(1,part['groups']+1):
            legs=[r for r in part['legs'] if r['group']==group];event=frozenset(r['slot'] for r in legs)
            events.append(event)
            for r in legs:
                if r['slot'] in prob and prob[r['slot']]!=r['coverage']:raise ValueError('Inconsistent coverage')
                prob[r['slot']]=r['coverage']
    if len(events)>13:raise ValueError('At most13 groups')
    cache={};terms=[]
    for size in range(1,len(events)+1):
        for subset in itertools.combinations(events,size):
            key=frozenset().union(*subset)
            if key not in cache:cache[key]=math.prod(prob[i] for i in key)
            terms.append(cache[key]*(1 if size%2 else -1))
    return min(1.,max(0.,math.fsum(terms)))


def n67_overlay_plan(frame, *, cutoffs, strategy, funding, max_n6, max_n7, unit_cny,payout_factor,allocation_seed):
    """Sealed N7/N6/DIRECT/CROSS plans, UNIT or exact-integer MATCHED allocation.

    N7 concentrated by coverage; N6 direct consecutive ranks or CROSS cyclic
    ranks across its groups. Within each N, unique fixtures. MATCHED spends the
    direct overlay's unit stake; a no-group arm preserves it as cash. Residual
    units hash-ranked before settlement. No fitting, source writes or labels.
    """
    if strategy not in ['N7','N6','DIRECT','CROSS'] or funding not in ['UNIT','MATCHED']:raise ValueError('Explicit strategy/funding required')
    if (max_n6,max_n7,unit_cny,payout_factor)!=(7,6,2,.65) or not isinstance(allocation_seed,int):raise ValueError('Explicit business constants required')
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=x.sort_values(['coverage','slot','provider_id'],ascending=[False,True,True],kind='stable')
    counts={6:min(max_n6,len(x)//6),7:min(max_n7,len(x)//7)}
    issue=str(x.issue.iloc[0]);parts=[]
    ns=[7] if strategy=='N7' else [6] if strategy=='N6' else [7,6]
    for n in ns:
        count=counts[n];pool=x.head(n*count).copy()
        pool['group']=[i%count+1 if n==6 and strategy=='CROSS' else i//n+1 for i in range(len(pool))]
        legs=[];tickets=[]
        for group,g in pool.groupby('group',sort=True):
            g=g.sort_values('slot');legs.extend(g.to_dict('records'))
            for choices in itertools.product(*(r for r in g.support)):
                tickets.append(dict(group=int(group),code=''.join(choices),units=1))
        parts.append(dict(issue=issue,selector='COVERAGE',shape='TOP2',funding=funding,n=n,groups=count,
            legs=legs,tickets=tickets,stake=len(tickets)*unit_cny,unit_cny=unit_cny,payout_factor=payout_factor,
            cutoffs=bound,historical_admission=False))
    minimum=sum(p['stake'] for p in parts)
    budget=sum(counts[n]*unit_cny*2**n for n in [6,7]) if funding=='MATCHED' else minimum
    indexed=[(p['n'],t) for p in parts for t in p['tickets']]
    if indexed:
        base,extra=divmod(budget//unit_cny,len(indexed))
        ranked=sorted(indexed,key=lambda pair:hashlib.sha256(f"{allocation_seed}|{issue}|{pair[0]}|{pair[1]['group']}|{pair[1]['code']}".encode()).hexdigest())
        for _,t in indexed:t['units']=base
        for _,t in ranked[:extra]:t['units']+=1
    for part in parts:
        part['stake']=unit_cny*sum(t['units'] for t in part['tickets']);part['seal']=stable_json_hash(part)
    max_overlap=0
    if len(parts)==2:
        a,b=parts
        for g in range(1,a['groups']+1):
            for h in range(1,b['groups']+1):
                max_overlap=max(max_overlap,len({r['slot'] for r in a['legs'] if r['group']==g}&{r['slot'] for r in b['legs'] if r['group']==h}))
    result=dict(issue=issue,strategy=strategy,funding=funding,components=parts,cutoffs=bound,
        max_n6=max_n6,max_n7=max_n7,unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=allocation_seed,
        budget=budget,stake=sum(p['stake'] for p in parts),minimum_stake=minimum,
        model_any_hit=overlay_any_hit(parts),max_pair_overlap=max_overlap,
        input_sha256=stable_json_hash(frame.sort_values('slot').to_json(orient='records')),
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_RETROSPECTIVE_NOT_SIMULTANEOUS')
    result['seal']=stable_json_hash(result)
    return result


def settle_n67_overlay(plan,audit):
    """Settle components with authoritative cash API; pending totals remain unknown.

    ideal_gross rescales uniform one-unit payouts to actual total stake, exposing
    integer residual effects. Missing winning SP blocks whole overlay; unused
    losing SP is not required. Returns zero-cash NO_BET for no tickets.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan['seal']:raise ValueError('Plan changed')
    row={k:plan[k] for k in ['issue','strategy','funding','stake','budget','model_any_hit','max_pair_overlap']}
    row.update(groups=sum(p['groups'] for p in plan['components']),cash=plan['budget']-plan['stake'])
    settled=[];base=[]
    for part in plan['components']:
        settled.append(settle_n7_baseline(part,audit))
        one=copy.deepcopy(part);one.pop('seal')
        for t in one['tickets']:t['units']=1
        one['stake']=len(one['tickets'])*one['unit_cny'];one['seal']=stable_json_hash(one)
        base.append(settle_n7_baseline(one,audit))
    if any(r['status'] not in ['COMPLETE','NO_BET'] for r in settled):
        return dict(**row,status='PENDING_AUDIT_OR_WINNING_SP',gross=None,net=None,roi=None,hits=None,ideal_gross=None,n6_hits=None,n7_hits=None)
    gross=sum(r['gross'] for r in settled);base_gross=sum(r['gross'] for r in base)
    hits={p['n']:r['hits'] for p,r in zip(plan['components'],settled)}
    return dict(**row,status='COMPLETE' if row['groups'] else 'NO_BET',gross=gross,net=gross-row['stake'],
        roi=gross/row['stake']-1 if row['stake'] else None,hits=sum(hits.values()),n6_hits=hits.get(6,0),n7_hits=hits.get(7,0),
        ideal_gross=base_gross*row['stake']/plan['minimum_stake'] if plan['minimum_stake'] else 0.)
