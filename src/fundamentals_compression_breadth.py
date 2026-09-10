"""Fixed-model compression/breadth diagnostics; no historical fitting or I/O."""
import hashlib
import itertools
import math
from collections import Counter
import numpy as np
from src.fundamentals_n7_baseline import rank_double_candidates,n7_baseline_plan
from src.temporal_learning.core import stable_json_hash


def breadth_candidates(frame, *, cutoffs, seed, pool_size):
    """Return sorted fixture-index candidate sets plus original baseline sets.

    Indices refer to slot-sorted validated frame. Include original disjoint
    Top2 groups and cyclic ranked windows, then uniform random distinct 7-sets.
    Integer seed and pool_size>=128 required; bounded attempts fail closed.
    No labels or writes. The finite pool is not all possible portfolios.
    """
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs);x=x.sort_values('slot').reset_index(drop=True)
    if type(seed) is not int or seed<0 or type(pool_size) is not int or pool_size<128 or len(x)<7:raise ValueError('Explicit seed/pool and seven fixtures required')
    slots=x.slot.to_numpy();cover=x.coverage.to_numpy();providers=x.provider_id.to_numpy()
    order=sorted(range(len(x)),key=lambda i:(-cover[i],int(slots[i]),str(providers[i])))
    original=[tuple(sorted(order[j*7:j*7+7])) for j in range(min(6,len(x)//7))]
    target=min(pool_size,math.comb(len(x),7));sets=set(original)
    for start in range(min(len(x),target)):
        if len(sets)>=target:break
        sets.add(tuple(sorted(order[(start+k)%len(x)] for k in range(7))))
    rng=np.random.default_rng(seed)
    for _ in range(target*1000):
        if len(sets)>=target:break
        sets.add(tuple(sorted(map(int,rng.choice(len(x),7,replace=False)))))
    if len(sets)!=target:raise ValueError('Candidate pool construction exhausted')
    result=dict(cutoffs=bound,groups=[list(g) for g in sorted(sets)],original=[list(g) for g in original],seed=seed,pool_size=target,
        input_sha256=stable_json_hash(frame.sort_values('slot').to_json(orient='records')))
    return dict(**result,seal=stable_json_hash(result))


def compression_surface(frame, pool, *, cutoffs, depth, rule, seed):
    """Return per-candidate supports, retained probabilities and compression ledgers.

    depth0..3. TOP1, RETENTION, ABS_LOSS, VALUE_RETENTION, RANDOM use only p/q.
    VALUE_RETENTION=(p1/q1)/(p1/q1+p2/q2); q is fixed prematch market proxy.
    RANDOM seed chooses fixture roles, never random outcomes. Slots break ties.
    Masks: bit0 W,bit1 D,bit2 L. Arrays and ledger are label-free in-memory data.
    """
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs);x=x.sort_values('slot').reset_index(drop=True)
    if stable_json_hash({k:v for k,v in pool.items() if k!='seal'})!=pool.get('seal'):raise ValueError('Pool changed')
    if pool['cutoffs']!=bound:raise ValueError('Original pool cutoff identity required')
    if pool['input_sha256']!=stable_json_hash(frame.sort_values('slot').to_json(orient='records')):raise ValueError('Pool input identity mismatch')
    if type(depth) is not int or depth not in range(4) or rule not in ['TOP1','RETENTION','ABS_LOSS','VALUE_RETENTION','RANDOM'] or type(seed) is not int or seed<0:raise ValueError('Explicit compression rule/depth/seed required')
    probs=x[['p_W','p_D','p_L']].to_numpy();q=x[['q_W','q_D','q_L']].to_numpy();order=np.argsort(-probs,axis=1,kind='stable');a=order[:,0];b=order[:,1];idx=np.arange(len(x));p1=probs[idx,a];p2=probs[idx,b];ratio=p1/(p1+p2)
    slots=x.slot.to_numpy();handicaps=x.handicap.to_numpy()
    value=(p1/q[idx,a])/(p1/q[idx,a]+p2/q[idx,b]);scores={'TOP1':p1,'RETENTION':ratio,'ABS_LOSS':-p2,'VALUE_RETENTION':value}
    rng=np.random.default_rng(seed);masks=[];ledgers=[];masses=[];ev=[]
    for group in pool['groups']:
        chosen=set(map(int,rng.choice(group,depth,replace=False))) if rule=='RANDOM' else set(sorted(group,key=lambda i:(-scores[rule][i],int(slots[i])))[:depth])
        mask=[int(1<<int(a[i])) if i in chosen else int((1<<int(a[i]))|(1<<int(b[i]))) for i in group];masks.append(mask)
        masses.append(math.prod(p1[i] if i in chosen else p1[i]+p2[i] for i in group))
        ev.append(math.prod(p1[i]/q[i,a[i]] if i in chosen else p1[i]/q[i,a[i]]+p2[i]/q[i,b[i]] for i in group))
        ledgers.append([dict(slot=int(slots[i]),single=i in chosen,top1=float(p1[i]),discarded_mass=float(p2[i]) if i in chosen else 0.,p2=float(p2[i]),retention=float(ratio[i]),cost_normalized_retention=float(2*ratio[i]),gap=float(p1[i]-p2[i]),entropy=float(-np.sum(probs[i]*np.log(np.maximum(probs[i],1e-300)))),divergence=float(.5*np.abs(probs[i]-q[i]).sum()),handicap=int(handicaps[i]),top1_direction='WDL'[a[i]],top2_coverage=float(p1[i]+p2[i]),value_retention=float(value[i])) for i in group])
    result=dict(masks=masks,ledger=ledgers,mass=masses,value_factor=ev,depth=depth,rule=rule,seed=seed,pool=pool)
    return dict(**result,seal=stable_json_hash(result))


def breadth_scenarios(frame, surface, *, cutoffs, seed, draws):
    """Shared-fixture independent model scenarios; repeated fixtures share outcomes.

    Return candidate-hit boolean matrix [candidate,scenario]. Fixed positive
    draws/seed explicit; seed streams for selection and evaluation must differ.
    No labels. Between-fixture independence is a model assumption, not a fact.
    """
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs);x=x.sort_values('slot').reset_index(drop=True)
    if stable_json_hash({k:v for k,v in surface.items() if k!='seal'})!=surface.get('seal'):raise ValueError('Surface changed')
    if surface['pool']['cutoffs']!=bound:raise ValueError('Original surface cutoff identity required')
    if surface['pool']['input_sha256']!=stable_json_hash(frame.sort_values('slot').to_json(orient='records')):raise ValueError('Scenario input identity mismatch')
    if type(seed) is not int or seed<0 or type(draws) is not int or draws<1:raise ValueError('Explicit simulation seed/draw count required')
    p=x[['p_W','p_D','p_L']].to_numpy();u=np.random.default_rng(seed).random((len(x),draws));outcome=(u>=p[:,0,None]).astype(int)+(u>=(p[:,0]+p[:,1])[:,None]).astype(int);bits=1<<outcome
    hits=np.asarray([np.all((bits[group]&np.asarray(mask)[:,None])>0,axis=0) for group,mask in zip(surface['pool']['groups'],surface['masks'])])
    receipt=dict(seed=seed,draws=draws,shape=list(hits.shape),cutoffs=bound,surface_seal=surface['seal'],sha256=hashlib.sha256(hits.tobytes()).hexdigest())
    return dict(hits=hits,**receipt,seal=stable_json_hash(receipt))


def compression_breadth_plan(frame, surface, design_hits, *, cutoffs, breadth, seed, budget_cny, quality_pool_size, unit_cny, payout_factor):
    """Freeze complete paid-ticket portfolio with matched original CNY exposure.

    REPEAT consolidates repeated physical ticket identities into units2**depth;
    QUALITY picks highest compressed mass; UNION greedily adds uncovered model
    scenarios; RANDOM samples candidates without replacement. Nonrepeat arms
    share top quality_pool_size candidates by exact compressed mass. This is
    a fixed rank-based quality floor, not a learned threshold. No hard overlap
    caps: breadth effectiveness is evaluated from shared-fixture scenarios.
    Budget must equal original disjoint Top2 baseline stake; insufficient pool
    raises, never silently increases stake or fills with repeated new groups.
    """
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs);x=x.sort_values('slot').reset_index(drop=True)
    if stable_json_hash({k:v for k,v in surface.items() if k!='seal'})!=surface.get('seal'):raise ValueError('Surface changed')
    if surface['pool']['cutoffs']!=bound:raise ValueError('Original surface cutoff identity required')
    if surface['pool']['input_sha256']!=stable_json_hash(frame.sort_values('slot').to_json(orient='records')):raise ValueError('Plan input identity mismatch')
    if breadth not in ['REPEAT','QUALITY','UNION','RANDOM'] or type(seed) is not int or seed<0 or type(quality_pool_size) is not int or quality_pool_size<1:raise ValueError('Explicit breadth, seed, quality pool required')
    base=n7_baseline_plan(frame,cutoffs=cutoffs,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=0)
    if type(budget_cny) is not int or budget_cny!=base['stake'] or budget_cny<=0:raise ValueError('Matched original positive baseline budget required')
    groups=surface['pool']['groups'];depth=surface['depth'];cost=unit_cny*2**(7-depth);count=budget_cny//cost
    eligible=sorted(range(len(groups)),key=lambda i:(-surface['mass'][i],groups[i]))[:quality_pool_size]
    if len(eligible)<count:raise ValueError('Insufficient distinct quality candidates for matched exposure')
    _checked_scenario_matrix(design_hits,expected_surface=surface['seal'],expected_cutoffs=bound,candidate_count=len(groups))
    design_receipt={k:v for k,v in design_hits.items() if k!='hits'};design_hits=design_hits['hits']
    if design_hits.dtype!=bool or design_hits.ndim!=2 or design_hits.shape[0]!=len(groups) or design_hits.shape[1]<1:raise ValueError('Candidate scenario dimensions required')
    if breadth=='REPEAT':chosen=[groups.index(g) for g in surface['pool']['original']];units=2**depth
    elif breadth=='QUALITY':chosen=eligible[:count];units=1
    elif breadth=='RANDOM':chosen=list(map(int,np.random.default_rng(seed).choice(eligible,count,replace=False)));units=1
    else:
        chosen=[];remaining=list(eligible);uncovered=np.ones(design_hits.shape[1],dtype=bool)
        for _ in range(count):
            gains=(design_hits[remaining]&uncovered).sum(axis=1);best=int(np.argmax(gains));c=remaining.pop(best);chosen.append(c);uncovered&=~design_hits[c]
        units=1
    records=x.to_dict('records')
    plan={k:v for k,v in base.items() if k!='seal'};legs=[];tickets=[];ledger=[]
    for group,c in enumerate(chosen,1):
        for i,mask,entry in zip(groups[c],surface['masks'][c],surface['ledger'][c]):
            r=dict(records[i]);r.update(group=group,support=''.join(code for bit,code in enumerate('310') if mask&(1<<bit)));legs.append(r);ledger.append(dict(entry,group=group))
        support=[r['support'] for r in legs if r['group']==group]
        tickets.extend(dict(group=group,code=''.join(z),units=units) for z in itertools.product(*support))
    stake=unit_cny*sum(t['units'] for t in tickets)
    if stake!=budget_cny:raise ValueError('Matched ticket accounting failed')
    plan.update(groups=len(chosen),legs=legs,tickets=tickets,stake=stake,budget_cny=budget_cny,cash_cny=0,group_cost_cny=cost*units,
        single_rule=surface['rule'],single_count=depth,breadth=breadth,seed=seed,quality_pool_size=quality_pool_size,
        selected_candidates=chosen,contraction_ledger=ledger,paid_ticket_units=sum(t['units'] for t in tickets),
        unique_tickets=len(tickets),repeat_units=sum(t['units']-1 for t in tickets),nominal_groups=count,
        group_probability=[surface['mass'][i] for i in chosen],model_proxy_gross=unit_cny*payout_factor*units*sum(surface['value_factor'][i] for i in chosen),
        quality_mass_floor=surface['mass'][eligible[-1]],candidate_count=len(groups),source_pool_hash=stable_json_hash(surface['pool']),surface_seal=surface['seal'],design_receipt=design_receipt,cutoffs=bound)
    return dict(**plan,seal=stable_json_hash(plan))


def breadth_metrics(plan, evaluation_hits, *, cutoffs):
    """Return model union, MC standard error and identity/exposure diagnostics.

    Evaluation scenarios must be independently generated from selection stream.
    HHI uses paid elementary-ticket leg exposures, consolidating repeat units.
    No fitting, labels, writes or probability sums presented as union coverage.
    """
    from src.fundamentals_decision_chain import limit_decision_chain_plan
    limit_decision_chain_plan(plan,groups=plan['groups'],cutoffs=cutoffs)
    _checked_scenario_matrix(evaluation_hits,expected_surface=plan['surface_seal'],expected_cutoffs=plan['cutoffs'],candidate_count=plan['candidate_count'])
    if evaluation_hits['seed']==plan['design_receipt']['seed']:raise ValueError('Independent evaluation provenance required')
    evaluation_hits=evaluation_hits['hits']
    if evaluation_hits.dtype!=bool or evaluation_hits.ndim!=2 or evaluation_hits.shape[1]<1 or max(plan['selected_candidates'])>=evaluation_hits.shape[0]:raise ValueError('Evaluation scenario shape required')
    union=evaluation_hits[plan['selected_candidates']].any(axis=0);prob=float(union.mean());fixture=Counter();outcomes=Counter();singles=Counter();sets=[]
    for g in range(1,plan['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==g],key=lambda r:r['slot']);sets.append({r['slot'] for r in legs})
        for t in [t for t in plan['tickets'] if t['group']==g]:
            for r,code in zip(legs,t['code']):fixture[r['slot']]+=t['units'];outcomes[r['slot'],code]+=t['units']
        for r in legs:
            if len(r['support'])==1:singles[r['slot']]+=1
    total=sum(fixture.values());pairs=[len(a&b) for a,b in itertools.combinations(sets,2)]
    return dict(model_union=prob,model_union_se=math.sqrt(prob*(1-prob)/len(union)),fixture_hhi=sum((v/total)**2 for v in fixture.values()),outcome_hhi=sum((v/total)**2 for v in outcomes.values()),max_pair_overlap=max(pairs,default=0),mean_pair_overlap=float(np.mean(pairs)) if pairs else 0.,max_fixture_groups=max(Counter(s for g in sets for s in g).values()),max_single_groups=max(singles.values(),default=0),unique_fixtures=len(fixture))


def _checked_scenario_matrix(bundle, *, expected_surface, expected_cutoffs, candidate_count):
    """Validate domain matrix and all metadata together; no chronology derivation.

    Expected cutoff mapping comes from shared rank_double_candidates or the
    shared plan limiter, not reconstructed here. Used by both public consumers.
    Reject seed/draw/shape/cutoff/hash mutation and inconsistent boolean arrays.
    """
    receipt={k:v for k,v in bundle.items() if k not in {'hits','seal'}}
    if stable_json_hash(receipt)!=bundle.get('seal'):raise ValueError('Scenario metadata changed')
    hits=bundle['hits']
    if (bundle['surface_seal']!=expected_surface or bundle['cutoffs']!=expected_cutoffs
        or not isinstance(hits,np.ndarray) or hits.dtype!=bool or hits.ndim!=2
        or bundle['shape']!=list(hits.shape) or hits.shape!= (candidate_count,bundle['draws'])
        or hits.shape[1]<1 or bundle['sha256']!=hashlib.sha256(hits.tobytes()).hexdigest()):
        raise ValueError('Scenario identity, dimensions or bytes changed')
    return hits


def settle_breadth_bundle(bundle, audit):
    """Settle a bundle against one immutable audit argument, reusing components.

    Each sealed plan is validated. Identical seven-leg components within this
    call are settled once by authoritative settle_n7_baseline. Memoization is
    local to this audit call; nothing persists or crosses audit/cutoff contexts.
    Only component aggregation is performed here; no new payout formula.
    Return policy->same aggregate contract as settle_n7_single, including pending
    winning-SP status. Inputs are never modified; no fitting or I/O.
    """
    from src.fundamentals_n7_baseline import settle_n7_baseline
    cache={};results={}
    for policy,entry in bundle.items():
        plan=entry['plan']
        if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan.get('seal'):raise ValueError('Plan changed')
        components=[]
        for group in range(1,plan['groups']+1):
            part={k:plan[k] for k in ['issue','selector','shape','funding','unit_cny','payout_factor']}
            part.update(cutoffs=plan['cutoffs'],input_sha256=plan['input_sha256'],groups=1,stake=plan['group_cost_cny'],legs=[dict(r,group=1) for r in plan['legs'] if r['group']==group],tickets=[dict(t,group=1) for t in plan['tickets'] if t['group']==group])
            part['seal']=stable_json_hash(part)
            if part['seal'] not in cache:cache[part['seal']]=settle_n7_baseline(part,audit)
            components.append(cache[part['seal']])
        row=dict(issue=plan['issue'],strategy=plan['single_rule'],funding='UNIT',stake=plan['stake'],budget=plan['budget_cny'],model_any_hit=None,groups=plan['groups'],cash=plan['cash_cny'])
        if any(r['status'] not in ['COMPLETE','NO_BET'] for r in components):
            results[policy]=dict(**row,status='PENDING_AUDIT_OR_WINNING_SP',gross=None,net=None,roi=None,hits=None,ideal_gross=None)
        else:
            gross=sum(r['gross'] for r in components)
            results[policy]=dict(**row,status='COMPLETE' if components else 'NO_BET',gross=gross,net=gross-plan['stake'],roi=gross/plan['stake']-1 if plan['stake'] else None,hits=sum(r['hits'] for r in components),ideal_gross=gross)
    return results
