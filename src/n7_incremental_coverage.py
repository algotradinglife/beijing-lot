"""Greedy empirical union coverage on frozen single-ticket candidates."""
import functools
import heapq
import operator
import numpy as np
from src.n7_probability_gate import select_probability_gate
from src.temporal_learning.core import stable_json_hash


def incremental_coverage_plans(pool, *, cutoffs, seed, training_worlds, evaluation_worlds,
                               min_probabilities, budget_cny, unit_cny, payout_factor):
    """Return COVERAGE/PROB/EV sealed plans for each inclusive probability gate.

    Reuses frozen calibrated-p/raw-q candidate pool and native cutoffs. Worlds
    independently simulate each fixture once and share its result across tickets.
    Two SeedSequence child streams separate selection and held-out evaluation;
    changing evaluation size cannot change selection. Counts are union events,
    never a sum of ticket probabilities. Greedy lazy maximum coverage uses exact
    integer bitsets of training worlds. Ties: estimated EV, original probability,
    canonical candidate row. Fill affordable unique tickets even if empirical
    marginal coverage reaches zero. CNY1024/issue, CNY2/ticket, one .65 payout.
    This is candidate-restricted stochastic diagnosis, not global optimization,
    fitting on actual labels, profit-probability optimization or prospective use.
    Inputs require nonnegative integer seed, positive world counts, distinct gates
    in [0,1]. No labels or I/O. Returns 3 plans per gate with held-out hit rates.
    """
    if (type(seed) is not int or seed<0 or any(type(n) is not int or n<1 for n in (training_worlds,evaluation_worlds))
            or not min_probabilities or len(set(min_probabilities))!=len(min_probabilities)):
        raise ValueError('Explicit simulation parameters required')
    depth=pool['parameters']['depth']
    controls=[]
    for threshold in min_probabilities:
        for ranking in ('PROB','EV'):
            controls.append(select_probability_gate(pool,cutoffs=cutoffs,min_probability=threshold,
                ranking=ranking,search_depth=depth,budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor))
    f=pool['fixtures'];p=np.array([[x[f'p_{d}'] for d in 'WDL'] for x in f]);q=np.array([[x[f'q_{d}'] for d in 'WDL'] for x in f])
    encoded=[tuple(t) for t in pool['encoded_tickets']];lookup={t:i for i,t in enumerate(encoded)}
    ix=np.array(encoded,dtype=int).reshape(-1,7);mass=np.prod(p[ix//3,ix%3],axis=1)
    ev=payout_factor*np.prod(p[ix//3,ix%3]/q[ix//3,ix%3],axis=1)-1
    masks=[]
    for child,worlds in zip(np.random.SeedSequence(seed).spawn(2),(training_worlds,evaluation_worlds)):
        rng=np.random.default_rng(child);legs=[]
        for triplet in p:
            cdf=triplet.cumsum();cdf[-1]=1.
            outcomes=np.searchsorted(cdf,rng.random(worlds),side='right')
            legs.extend(int.from_bytes(np.packbits(outcomes==d,bitorder='little').tobytes(),'little') for d in range(3))
        masks.append([functools.reduce(operator.and_,(legs[c] for c in ticket)) for ticket in encoded])
    plans=[]
    for threshold in min_probabilities:
        base=next(z for z in controls if z['parameters']['min_probability']==threshold and z['parameters']['ranking']=='PROB')
        eligible=np.flatnonzero(mass>=threshold)
        heap=[(-masks[0][i].bit_count(),-float(ev[i]),-float(mass[i]),int(i),0) for i in eligible];heapq.heapify(heap)
        chosen=[];covered=0;gains=[]
        while heap and len(chosen)<budget_cny//unit_cny:
            neg_gain,neg_ev,neg_mass,i,stamp=heapq.heappop(heap)
            if stamp!=len(chosen):
                gain=(masks[0][i]&~covered).bit_count()
                heapq.heappush(heap,(-gain,neg_ev,neg_mass,i,len(chosen)));continue
            chosen.append(i);gains.append(-neg_gain);covered|=masks[0][i]
        tickets=ix[chosen];counts=np.bincount((tickets//3).ravel(),minlength=len(f))
        plan={k:v for k,v in base.items() if k!='seal'}
        plan.update(fixture_indices=(tickets//3).tolist(),outcomes=(tickets%3).tolist(),
            groups=len(chosen),stake=unit_cny*len(chosen),cash_cny=budget_cny-unit_cny*len(chosen),
            mean_coverage=float(mass[chosen].mean()) if chosen else None,
            expected_roi=float(ev[chosen].mean()) if chosen else None,
            expected_net=float(unit_cny*ev[chosen].sum()),
            min_selected_probability=float(mass[chosen].min()) if chosen else None,max_reuse=int(counts.max()),
            parameters=dict(min_probability=threshold,ranking='COVERAGE',search_depth=depth),
            marginal_training_counts=gains)
        plans.append(plan)
    plans.extend({k:v for k,v in z.items() if k!='seal'} for z in controls)
    for plan in plans:
        ids=[lookup[tuple(3*i+d for i,d in zip(ii,dd))] for ii,dd in zip(plan['fixture_indices'],plan['outcomes'])]
        rates=[functools.reduce(operator.or_,(bits[i] for i in ids),0).bit_count()/n for bits,n in zip(masks,(training_worlds,evaluation_worlds))]
        plan['simulation']=dict(seed=seed,training_worlds=training_worlds,evaluation_worlds=evaluation_worlds,
            training_hit_rate=rates[0],evaluation_hit_rate=rates[1])
        plan['seal']=stable_json_hash(plan)
    return plans
