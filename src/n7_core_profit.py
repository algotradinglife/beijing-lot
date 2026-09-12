"""Candidate-restricted probability core and profitable-gap allocation diagnostics."""
import functools
import operator
import numpy as np
from src.n7_probability_gate import select_probability_gate
from src.temporal_learning.core import stable_json_hash


def core_profit_plans(pool, profit_control, *, cutoffs, seed, training_worlds,
                      evaluation_worlds, core_fractions, proposal_width, joint_attempts,
                      min_probability, payout_stress, budget_cny, unit_cny, payout_factor):
    """Return sealed PROB/PROFIT and FIXED/GAP/JOINT plans for each core fraction.

    All parameters explicit; no I/O, target outcomes, actual SP or historical fit.
    Native cutoffs validated by shared probability-gate selection. Input control
    must be sealed and match the pool, gate, seed, sizes and money contract.
    FIXED locks ceil(K*fraction) PROB tickets, fills from PROFIT (probability order),
    then PROB. GAP retains the core, sequentially selects the best of an explicit
    bounded random proposal batch plus the next PROB ticket. Rank proposals by
    newly profitable training worlds, capped recovery gain, then expected payout.
    The threshold is the FINAL stake even during construction. JOINT starts at GAP,
    tries two-for-two swaps outside the core, accepts greater profitable count or
    tied count with greater capped recovery. No global optimality claim.
    Stress scales estimated whole-ticket payout during held-out evaluation only;
    it never changes ticket choice. RNG evaluation is isolated from construction.
    Complete tickets unique; fixture reuse unlimited; every ticket has 7 fixtures.
    Empty candidate universe yields NO_BET plans; invalid contracts raise ValueError.
    """
    if (type(seed) is not int or seed < 0 or any(type(n) is not int or n < 1 for n in
        (training_worlds, evaluation_worlds, proposal_width)) or type(joint_attempts) is not int
        or joint_attempts < 0 or not core_fractions or len(set(core_fractions)) != len(core_fractions)
        or any(not np.isfinite(f) or not 0 < f < 1 for f in core_fractions)
        or not payout_stress or len(set(payout_stress)) != len(payout_stress)
        or any(not np.isfinite(f) or f <= 0 for f in payout_stress)):
        raise ValueError('Explicit valid core/search/stress contract required')
    base = select_probability_gate(pool, cutoffs=cutoffs, min_probability=min_probability,
        ranking='PROB', search_depth=pool['parameters']['depth'], budget_cny=budget_cny,
        unit_cny=unit_cny, payout_factor=payout_factor)
    old = profit_control
    if old.get('seal') != stable_json_hash({k:v for k,v in old.items() if k != 'seal'}):
        raise ValueError('Changed PROFIT control')
    for key in ('pool_seal','fixtures','cutoffs','stake','groups','budget_cny','unit_cny','payout_factor'):
        if old[key] != base[key]: raise ValueError('Control contract mismatch: '+key)
    if (old['parameters']['ranking'] != 'PROFIT' or old['parameters']['min_probability'] != min_probability
        or any(old['simulation'][k] != v for k,v in dict(seed=seed,training_worlds=training_worlds,
            evaluation_worlds=evaluation_worlds).items())):
        raise ValueError('Control gate/simulation mismatch')
    fixtures=pool['fixtures'];tickets=[tuple(t) for t in pool['encoded_tickets']]
    codes=np.asarray(tickets,dtype=int).reshape(-1,7);lookup={t:i for i,t in enumerate(tickets)}
    p=np.array([[x[f'p_{d}'] for d in 'WDL'] for x in fixtures])
    q=np.array([[x[f'q_{d}'] for d in 'WDL'] for x in fixtures])
    mass=np.prod(p[codes//3,codes%3],axis=1)
    pay=unit_cny*payout_factor/np.prod(q[codes//3,codes%3],axis=1)
    if not np.isfinite(pay).all(): raise ValueError('Nonfinite estimated payout')
    indices=[]
    for control in (base,old):
        encoded=[tuple(3*i+d for i,d in zip(ii,dd)) for ii,dd in zip(control['fixture_indices'],control['outcomes'])]
        if len(encoded)!=control['groups'] or len(set(encoded))!=len(encoded) or any(t not in lookup for t in encoded):
            raise ValueError('Invalid control tickets')
        ids=[lookup[t] for t in encoded]
        if any(mass[i]<min_probability for i in ids): raise ValueError('Control probability gate')
        indices.append(ids)
    prob_ids,profit_ids=indices;stake=base['stake'];k=len(prob_ids)
    children=np.random.SeedSequence(seed).spawn(2);hits=[]
    for child,n in zip(children,(training_worlds,evaluation_worlds)):
        rng=np.random.default_rng(child);legs=[]
        for triplet in p:
            cdf=triplet.cumsum();cdf[-1]=1.
            outcome=np.searchsorted(cdf,rng.random(n),side='right')
            legs.extend(int.from_bytes(np.packbits(outcome==d,bitorder='little').tobytes(),'little') for d in range(3))
        rows=[]
        for ticket in tickets:
            bits=functools.reduce(operator.and_,(legs[c] for c in ticket))
            rows.append(np.flatnonzero(np.unpackbits(np.frombuffer(bits.to_bytes((n+7)//8,'little'),dtype=np.uint8),bitorder='little')[:n]))
        hits.append(rows)
    selections=[('PROB',None,prob_ids,[],{}),('PROFIT',None,profit_ids,[],{})]
    eligible=np.flatnonzero(mass>=min_probability)
    for ordinal,fraction in enumerate(sorted(core_fractions)):
        core=prob_ids[:int(np.ceil(k*fraction))];locked=set(core)
        ordered=core+sorted((i for i in profit_ids if i not in locked),key=lambda i:(-mass[i],i))
        ordered+= [i for i in prob_ids if i not in set(ordered)]
        fixed=ordered[:k]
        selections.append(('FIXED',fraction,fixed,core,{}))
        chosen=list(core);selected=set(core);gross=np.zeros(training_worlds)
        for i in core:gross[hits[0][i]]+=pay[i]
        rng=np.random.default_rng(np.random.SeedSequence([seed,133,ordinal,0]))
        # Fixed-size batches are an explicit approximation, not a full greedy scan.
        while len(chosen)<k:
            remaining=eligible[~np.isin(eligible,list(selected))]
            batch=rng.choice(remaining,size=min(proposal_width,len(remaining)),replace=False)
            next_prob=next(i for i in prob_ids if i not in selected)
            batch=np.unique(np.r_[batch,next_prob]);scores=[]
            for i in batch:
                before=gross[hits[0][i]];after=before+pay[i]
                scores.append((int(np.sum(after>stake)-np.sum(before>stake)),
                    float(np.minimum(after,stake).sum()-np.minimum(before,stake).sum()),float(mass[i]*pay[i]),-int(i)))
            new=int(batch[max(range(len(batch)),key=lambda j:scores[j])])
            chosen.append(new);selected.add(new);gross[hits[0][new]]+=pay[new]
        gap_rate=float(np.mean(gross>stake))
        selections.append(('GAP',fraction,list(chosen),core,dict(training_initial_profit_rate=gap_rate)))
        rng=np.random.default_rng(np.random.SeedSequence([seed,133,ordinal,1]));accepted=0
        if k-len(core)>=2 and len(eligible)-k>=2:
            for _ in range(joint_attempts):
                pos=rng.choice(np.arange(len(core),k),size=2,replace=False)
                incoming=rng.choice(eligible,size=2,replace=False)
                if any(int(i) in selected for i in incoming):continue
                outgoing=[chosen[int(j)] for j in pos]
                affected=np.unique(np.concatenate([hits[0][i] for i in [*outgoing,*incoming]]))
                before=gross[affected];after=before.copy()
                for i in outgoing:after[np.searchsorted(affected,hits[0][i])]-=pay[i]
                for i in incoming:after[np.searchsorted(affected,hits[0][i])]+=pay[i]
                gain=int(np.sum(after>stake)-np.sum(before>stake))
                recovery=float(np.minimum(after,stake).sum()-np.minimum(before,stake).sum())
                if gain>0 or (gain==0 and recovery>1e-7):
                    gross[affected]=after
                    for j,i,old_id in zip(pos,incoming,outgoing):
                        chosen[int(j)]=int(i);selected.remove(old_id);selected.add(int(i))
                    accepted+=1
        selections.append(('JOINT',fraction,list(chosen),core,dict(training_initial_profit_rate=gap_rate,accepted=accepted)))
    plans=[]
    for kind,fraction,ids,core,search in selections:
        rates=[];stress=[]
        for index,n in enumerate((training_worlds,evaluation_worlds)):
            gross=np.zeros(n)
            for i in ids:gross[hits[index][i]]+=pay[i]
            rates.append(dict(hit=float(np.mean(gross>0)),profit=float(np.mean(gross>stake))))
            if index==1:stress=[dict(scale=float(f),profit=float(np.mean(gross*f>stake))) for f in payout_stress]
        if kind=='JOINT' and rates[0]['profit']+1e-12<search['training_initial_profit_rate']:
            raise ValueError('Joint objective regressed on exact replay')
        tt=codes[ids];plan={key:value for key,value in base.items() if key!='seal'}
        plan.update(fixture_indices=(tt//3).tolist(),outcomes=(tt%3).tolist(),
            expected_net=float(np.sum(mass[ids]*pay[ids])-stake),
            expected_roi=float(np.sum(mass[ids]*pay[ids])/stake-1) if stake else None,
            mean_coverage=float(np.mean(mass[ids])) if ids else None,
            min_selected_probability=float(np.min(mass[ids])) if ids else None,
            max_reuse=int(np.bincount((tt//3).ravel(),minlength=len(fixtures)).max()),
            core_encoded_tickets=[list(tickets[i]) for i in core],
            parameters=dict(ranking=kind,core_fraction=fraction,min_probability=min_probability,
                proposal_width=proposal_width,joint_attempts=joint_attempts,search_depth=pool['parameters']['depth']),
            simulation=dict(seed=seed,training_worlds=training_worlds,evaluation_worlds=evaluation_worlds,
                training_hit_rate=rates[0]['hit'],training_profit_rate=rates[0]['profit'],
                evaluation_hit_rate=rates[1]['hit'],evaluation_profit_rate=rates[1]['profit'],payout_stress=stress),
            search=search,profit_control_seal=old['seal'])
        plan['seal']=stable_json_hash(plan);plans.append(plan)
    return plans
