"""Fixed-budget local search for simulated profitable-issue probability."""
import functools
import operator
import numpy as np
from src.n7_probability_gate import select_probability_gate
from src.temporal_learning.core import stable_json_hash


def profit_period_plans(pool, starts, *, cutoffs, seed, training_worlds, evaluation_worlds,
                       swap_attempts, probability_proposal_weight, budget_cny, unit_cny, payout_factor):
    """Evaluate three frozen controls and add PROFIT for every supplied gate.

    Starts: sealed COVERAGE/PROB/EV portfolios for exactly one seed and pool.
    Same calibrated-p/raw-q source and native cutoffs as earlier N7 experiments.
    Simulated ticket payout is unit*.65/product(q), never target settlement SP.
    An issue profits iff total ticket payout strictly exceeds its final stake.
    Start from PROB or COVERAGE, whichever has higher TRAINING profit count;
    tie-break by expected capped payout then estimated net. Fixed-cost one-ticket
    swaps accept higher profit count, or equal count and higher capped payout.
    Proposal distribution mixes original ticket probability and uniform mass,
    with explicit weight; independent third RNG stream. Pre-generate a bounded
    proposal list, skip already selected tickets. Never use held-out evaluation
    to select a start, swap, threshold or seed. Greedy/local, not global optimum.
    Fill the same gate-dependent budget as PROB/COVERAGE, no positive-EV gate.
    Returns sealed four-policy plans with train/evaluation hit AND profit rates.
    No labels, learning from actual outcomes, I/O, or implicit source admission.
    """
    if (type(seed) is not int or seed<0 or any(type(n) is not int or n<1 for n in (training_worlds,evaluation_worlds))
            or type(swap_attempts) is not int or swap_attempts<0
            or not np.isfinite(probability_proposal_weight) or not 0<=probability_proposal_weight<=1 or not starts):
        raise ValueError('Explicit profit-search parameters required')
    thresholds=sorted({p['parameters']['min_probability'] for p in starts})
    expected={(t,r) for t in thresholds for r in ('COVERAGE','PROB','EV')}
    keys=[(p['parameters']['min_probability'],p['parameters']['ranking']) for p in starts]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:raise ValueError('Exact three-control gate grid required')
    for start in starts:
        if start.get('seal')!=stable_json_hash({k:v for k,v in start.items() if k!='seal'}):raise ValueError('Changed control')
        if (start['pool_seal']!=pool['seal'] or start['fixtures']!=pool['fixtures'] or start['cutoffs']!=pool['cutoffs']
                or start['simulation']['seed']!=seed or start['simulation']['training_worlds']!=training_worlds
                or start['simulation']['evaluation_worlds']!=evaluation_worlds
                or (start['budget_cny'],start['unit_cny'],start['payout_factor'])!=(budget_cny,unit_cny,payout_factor)):
            raise ValueError('Control/pool/simulation contract mismatch')
    for t in thresholds:
        baseline=select_probability_gate(pool,cutoffs=cutoffs,min_probability=t,ranking='PROB',
            search_depth=pool['parameters']['depth'],budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
        for start in (p for p in starts if p['parameters']['min_probability']==t and p['parameters']['ranking']!='EV'):
            if start['groups']!=baseline['groups'] or start['stake']!=baseline['stake']:raise ValueError('Unequal fixed-budget start')
    f=pool['fixtures'];p=np.array([[x[f'p_{d}'] for d in 'WDL'] for x in f]);q=np.array([[x[f'q_{d}'] for d in 'WDL'] for x in f])
    tickets=[tuple(t) for t in pool['encoded_tickets']];lookup={t:i for i,t in enumerate(tickets)}
    codes=np.array(tickets,dtype=int).reshape(-1,7)
    mass=np.prod(p[codes//3,codes%3],axis=1);pay=unit_cny*payout_factor/np.prod(q[codes//3,codes%3],axis=1)
    if not np.isfinite(pay).all():raise ValueError('Nonfinite estimated ticket payout')
    ev=mass*pay/unit_cny-1
    children=np.random.SeedSequence(seed).spawn(3);hits=[]
    for child,n in zip(children[:2],(training_worlds,evaluation_worlds)):
        rng=np.random.default_rng(child);legs=[]
        for triplet in p:
            cdf=triplet.cumsum();cdf[-1]=1.
            outcome=np.searchsorted(cdf,rng.random(n),side='right')
            legs.extend(int.from_bytes(np.packbits(outcome==d,bitorder='little').tobytes(),'little') for d in range(3))
        # Sorted winning-world indices permit sparse per-swap payout updates.
        rows=[]
        for ticket in tickets:
            bits=functools.reduce(operator.and_,(legs[c] for c in ticket))
            packed=np.frombuffer(bits.to_bytes((n+7)//8,'little'),dtype=np.uint8)
            rows.append(np.flatnonzero(np.unpackbits(packed,bitorder='little')[:n]))
        hits.append(rows)
    control_ids={}
    for start in starts:
        tt=[tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(start['fixture_indices'],start['outcomes'])]
        if len(set(tt))!=len(tt) or any(t not in lookup for t in tt):raise ValueError('Invalid control tickets')
        ids=[lookup[t] for t in tt]
        if any(mass[i]<start['parameters']['min_probability'] for i in ids):raise ValueError('Control probability gate failed')
        control_ids[start['parameters']['min_probability'],start['parameters']['ranking']]=ids
    plans=[{k:v for k,v in start.items() if k not in ('seal','marginal_training_counts')} for start in starts]
    proposal_rng=np.random.default_rng(children[2])
    for threshold in thresholds:
        scored=[]
        for ranking in ('PROB','COVERAGE'):
            start=next(z for z in starts if z['parameters']['min_probability']==threshold and z['parameters']['ranking']==ranking)
            ids=control_ids[threshold,ranking];gross=np.zeros(training_worlds)
            for i in ids:gross[hits[0][i]]+=pay[i]
            scored.append(((int(np.sum(gross>start['stake'])),float(np.minimum(gross,start['stake']).sum()),float(ev[ids].sum())),start,ids,gross))
        _,base,initial,gross=max(scored,key=lambda z:z[0]);chosen=list(initial);selected=set(chosen);stake=base['stake']
        initial_rate=float(np.mean(gross>stake));accepted=0;strict_improvements=0;attempted=0
        eligible=np.flatnonzero(mass>=threshold)
        if chosen and len(eligible)>len(chosen):
            weights=probability_proposal_weight*mass[eligible]/mass[eligible].sum()+(1-probability_proposal_weight)/len(eligible)
            incoming=proposal_rng.choice(eligible,size=swap_attempts,p=weights)
            outgoing=proposal_rng.integers(len(chosen),size=swap_attempts)
            for new,pos in zip(incoming,outgoing):
                attempted+=1;new=int(new);pos=int(pos)
                if new in selected:continue
                old=chosen[pos];affected=np.union1d(hits[0][old],hits[0][new]);before=gross[affected]
                after=before.copy();after[np.searchsorted(affected,hits[0][old])]-=pay[old]
                after[np.searchsorted(affected,hits[0][new])]+=pay[new]
                profit_gain=int(np.sum(after>stake)-np.sum(before>stake))
                recovery_gain=float(np.minimum(after,stake).sum()-np.minimum(before,stake).sum())
                if profit_gain>0 or (profit_gain==0 and recovery_gain>1e-7):
                    gross[affected]=after;selected.remove(old);selected.add(new);chosen[pos]=new
                    accepted+=1;strict_improvements+=int(profit_gain>0)
        tt=codes[chosen];counts=np.bincount((tt//3).ravel(),minlength=len(f))
        plan={k:v for k,v in base.items() if k not in ('seal','marginal_training_counts')}
        plan.update(fixture_indices=(tt//3).tolist(),outcomes=(tt%3).tolist(),
            expected_net=float(unit_cny*ev[chosen].sum()),expected_roi=float(ev[chosen].mean()) if chosen else None,
            mean_coverage=float(mass[chosen].mean()) if chosen else None,
            min_selected_probability=float(mass[chosen].min()) if chosen else None,max_reuse=int(counts.max()),
            parameters=dict(min_probability=threshold,ranking='PROFIT',search_depth=pool['parameters']['depth']),
            optimization=dict(swap_attempts=swap_attempts,attempted=attempted,accepted=accepted,strict_improvements=strict_improvements,
                probability_proposal_weight=probability_proposal_weight,initial_policy=base['parameters']['ranking'],initial_profit_rate=initial_rate))
        control_ids[threshold,'PROFIT']=chosen;plans.append(plan)
    for plan in plans:
        rates=[];ids=control_ids[plan['parameters']['min_probability'],plan['parameters']['ranking']]
        for index,n in enumerate((training_worlds,evaluation_worlds)):
            gross=np.zeros(n)
            for i in ids:gross[hits[index][i]]+=pay[i]
            rates.append((float(np.mean(gross>0)),float(np.mean(gross>plan['stake']))))
        if plan['parameters']['ranking']=='PROFIT' and rates[0][1]+1e-12<plan['optimization']['initial_profit_rate']:
            raise ValueError('Profit search regressed on exact replay')
        plan['simulation']=dict(seed=seed,training_worlds=training_worlds,evaluation_worlds=evaluation_worlds,
            training_hit_rate=rates[0][0],evaluation_hit_rate=rates[1][0],training_profit_rate=rates[0][1],evaluation_profit_rate=rates[1][1])
        plan['seal']=stable_json_hash(plan)
    return plans
