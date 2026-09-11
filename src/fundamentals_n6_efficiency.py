"""Fixed-source N6 compression and budget ablations; no fit, labels or I/O."""
import copy
import itertools
import math
import numpy as np
import pandas as pd
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_compression_breadth import breadth_scenarios, _checked_scenario_matrix
from src.fundamentals_missed_portfolio import fixed_n67_wallets
from src.temporal_learning.core import stable_json_hash


def n6_efficiency_catalog(plan, *, cutoffs, unit_cny, payout_factor,
                          scenario_seed, scenario_draws):
    """Describe sealed N6 C1 groups and their shared-fixture model scenarios.

    Original p/q retained, decision mass is the source's fixed 50/50 mixture.
    q is Euro+OU-projected handicap probability; price proxy is 1/q, never
    final settlement SP. Expected gross = 2*.65*product(sum(m/q in support)).
    Return sealed catalogue with original plan, per-group probability/EV,
    extra-single candidates, and bit-packed shared scenarios plus native receipt.
    Assumes independence between different fixtures; repeated fixtures share
    outcomes. Exact native cutoffs required, historical diagnostic only.
    Invalid/missing/empty source or inconsistent probabilities raise ValueError.
    No mutation, fitting, I/O or hidden seed. Prices and masses are unitless;
    cost/gross/net in CNY. Source must contain complete one-unit N6 C1 groups.
    """
    limit_decision_chain_plan(plan, groups=0, cutoffs=cutoffs)
    if unit_cny != 2 or payout_factor != .65 or plan['unit_cny'] != unit_cny or plan['payout_factor'] != payout_factor:
        raise ValueError('CNY2 and once-only .65 required')
    if plan['groups'] < 1 or plan.get('market_weight') != .5:
        raise ValueError('Nonempty original 50/50 N6 source required')
    raw = pd.DataFrame(plan['legs'])
    used = {str(s):cutoffs[str(s)] for s in raw.slot.unique()}
    rank_double_candidates(raw.drop_duplicates('slot'), cutoffs=used)
    columns = ['issue','slot','provider_id','handicap']+[a+'_'+d for a in ('p','q') for d in 'WDL']
    frame = raw[columns].drop_duplicates().sort_values('slot').reset_index(drop=True)
    if frame.slot.duplicated().any():
        raise ValueError('Repeated fixtures must have identical probabilities and identity')
    for leg in plan['legs']:
        expected = [.5*(leg['p_'+d]+leg['q_'+d]) for d in 'WDL']
        if leg.get('decision_probabilities') != expected:
            raise ValueError('Original decision mass must equal fixed 50/50 mixture')
    decision = frame.copy()
    decision[['p_W','p_D','p_L']] = .5*(frame[['p_W','p_D','p_L']].to_numpy()+frame[['q_W','q_D','q_L']].to_numpy())
    _, bound = rank_double_candidates(decision, cutoffs=used)
    index = {int(s):i for i,s in enumerate(frame.slot)}
    metrics = []; groups = []; masks = []
    for g in range(1,plan['groups']+1):
        legs = sorted([l for l in plan['legs'] if l['group']==g],key=lambda l:l['slot'])
        tickets = [t for t in plan['tickets'] if t['group']==g]
        if len(legs)!=6 or len({l['slot'] for l in legs})!=6 or sorted(len(l['support']) for l in legs)!=[1,2,2,2,2,2]:
            raise ValueError('Original six distinct fixtures and one single required')
        expected = {''.join(c) for c in itertools.product(*(l['support'] for l in legs))}
        if len(tickets)!=32 or {t['code'] for t in tickets}!=expected or any(t['units']!=1 for t in tickets):
            raise ValueError('Complete one-unit source Cartesian tickets required')
        masses=[]; values=[]; candidates=[]; mask=[]
        for l in legs:
            selected = ['310'.index(c) for c in l['support']]
            m = l['decision_probabilities']; q = [l['q_'+d] for d in 'WDL']
            mass = sum(m[j] for j in selected); value = sum(m[j]/q[j] for j in selected)
            if mass<=0 or value<=0:
                raise ValueError('Positive support mass required')
            masses.append(mass); values.append(value)
            mask.append(sum(1<<j for j in selected))
            if len(selected)==2:
                best = min(selected,key=lambda j:(-m[j],j))
                candidates.append(dict(slot=l['slot'],direction='310'[best],
                    probability_retention=m[best]/mass,return_retention=(m[best]/q[best])/value))
        gross = unit_cny*payout_factor*math.prod(values)
        metrics.append(dict(source_group=g,probability=math.prod(masses),
            expected_gross=gross,expected_net=gross-64,cost=64,compression_candidates=candidates))
        groups.append([index[l['slot']] for l in legs]); masks.append(mask)
    if plan['stake'] != 64*len(groups) or plan['stake']+plan['cash_cny'] != 1024:
        raise ValueError('Original wallet identity required')
    # Adapter for existing shared-fixture simulator; no new simulation engine.
    pool = dict(groups=groups,cutoffs=bound,
        input_sha256=stable_json_hash(decision.sort_values('slot').to_json(orient='records')))
    surface = dict(pool=pool,masks=masks)
    surface['seal'] = stable_json_hash(surface)
    scenarios = breadth_scenarios(decision,surface,cutoffs=used,seed=scenario_seed,draws=scenario_draws)
    packed = np.packbits(scenarios['hits'],axis=1).tobytes().hex()
    result = dict(source_plan=copy.deepcopy(plan),cutoffs=plan['cutoffs'],metrics=metrics,
        scenario=dict(receipt={k:v for k,v in scenarios.items() if k!='hits'},packed_hex=packed),
        surface_seal=surface['seal'],scenario_cutoffs=bound,unit_cny=unit_cny,
        payout_factor=payout_factor,price_proxy='INVERSE_EURO_OU_PROJECTED_Q',historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))


def n6_efficiency_plan(catalog, *, cutoffs, method, spend_cap_cny,
                       budget_cny, unit_cny, payout_factor):
    """Select original groups or compress one extra single, retaining all cash.

    ORIGINAL/EXTRA_PROB/EXTRA_VALUE preserve every source group (cap1024).
    Extra compression preserves old single and keeps higher-mass direction of
    one old double; position maximizes probability or price-weighted return
    retention. PROBABILITY/MARGINAL/EXPECTED_NET select up to cap/64 groups.
    Cap is explicit 0..1024 multiple64; total wallet stays1024. No EV>0 gate.
    MARGINAL greedily adds previously uncovered shared scenarios, ties by exact
    group probability then source order. Other ties use source order. Same
    source/cutoffs required; returns sealed shape, portfolio, ledger and receipt.
    New supports/selection are subsets of old tickets, so no new winning issue
    is possible. No refill, wager multiplication, labels, fit or I/O.
    """
    if catalog.get('seal') != stable_json_hash({k:v for k,v in catalog.items() if k!='seal'}):
        raise ValueError('Catalogue changed')
    source = catalog['source_plan']
    limit_decision_chain_plan(source,groups=0,cutoffs=cutoffs)
    if (method not in ('ORIGINAL','EXTRA_PROB','EXTRA_VALUE','PROBABILITY','MARGINAL','EXPECTED_NET')
            or type(budget_cny) is not int or budget_cny!=1024 or unit_cny!=2 or payout_factor!=.65
            or type(spend_cap_cny) is not int or not 0<=spend_cap_cny<=budget_cny or spend_cap_cny%64):
        raise ValueError('Explicit method, spend cap and business constants required')
    if method in ('ORIGINAL','EXTRA_PROB','EXTRA_VALUE') and spend_cap_cny!=1024:
        raise ValueError('Fixed-source compression requires full original cap')
    receipt = catalog['scenario']['receipt']; count,draws=receipt['shape']
    packed = np.frombuffer(bytes.fromhex(catalog['scenario']['packed_hex']),dtype=np.uint8)
    hits = np.unpackbits(packed.reshape(count,(draws+7)//8),axis=1)[:,:draws].astype(bool)
    _checked_scenario_matrix(dict(receipt,hits=hits),expected_surface=catalog['surface_seal'],
        expected_cutoffs=catalog['scenario_cutoffs'],candidate_count=len(catalog['metrics']))
    metrics = catalog['metrics']; ledger=[]
    if method in ('ORIGINAL','EXTRA_PROB','EXTRA_VALUE'):
        chosen=list(range(len(metrics)))
    elif method in ('PROBABILITY','EXPECTED_NET'):
        key='probability' if method=='PROBABILITY' else 'expected_net'
        chosen=sorted(range(len(metrics)),key=lambda i:(-metrics[i][key],i))[:spend_cap_cny//64]
    else:
        chosen=[];uncovered=np.ones(draws,dtype=bool)
        for _ in range(min(spend_cap_cny//64,len(metrics))):
            remaining=[i for i in range(len(metrics)) if i not in chosen]
            i=min(remaining,key=lambda j:(-int(np.count_nonzero(hits[j]&uncovered)),-metrics[j]['probability'],j))
            ledger.append(dict(source_group=i+1,marginal_probability=float(np.mean(hits[i]&uncovered))))
            chosen.append(i);uncovered &= ~hits[i]
    shape=copy.deepcopy(source);shape.pop('seal');legs=[];tickets=[];selection=[]
    for g,i in enumerate(chosen,1):
        current=sorted([copy.deepcopy(l) for l in source['legs'] if l['group']==i+1],key=lambda l:l['slot'])
        compression=None
        if method.startswith('EXTRA_'):
            key='probability_retention' if method=='EXTRA_PROB' else 'return_retention'
            compression=min(metrics[i]['compression_candidates'],key=lambda c:(-c[key],c['slot']))
            for l in current:
                if l['slot']==compression['slot']:
                    l['support']=compression['direction']
        legs.extend(dict(l,group=g) for l in current)
        tickets.extend(dict(group=g,code=''.join(c),units=1) for c in itertools.product(*(l['support'] for l in current)))
        selection.append(dict(source_group=i+1,compression=compression))
    spent=unit_cny*len(tickets)
    shape['source_shape_ledger']=shape.pop('ledger',[])
    shape.update(shape='N6_C2_EFFICIENCY' if method.startswith('EXTRA_') else 'N6_C1_EFFICIENCY',
        single_count=2 if method.startswith('EXTRA_') else 1,
        single_rule=method,groups=len(chosen),legs=legs,tickets=tickets,stake=spent,cash_cny=budget_cny-spent,
        parent_seal=source['seal'],efficiency_method=method,efficiency_selection=selection)
    shape['seal']=stable_json_hash(shape)
    portfolio=fixed_n67_wallets({'only':shape},cutoffs=cutoffs,wallets={'only':1024},
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
    if portfolio['stake']!=spent:
        raise ValueError('Unexpected duplicate or incomplete source holdings')
    result=dict(plan=portfolio,shape_plan=shape,catalog_seal=catalog['seal'],method=method,
        spend_cap_cny=spend_cap_cny,selected_source_groups=[i+1 for i in chosen],
        marginal_ledger=ledger,historical_admission=False)
    return dict(**result,seal=stable_json_hash(result))
