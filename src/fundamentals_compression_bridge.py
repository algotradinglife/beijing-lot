"""Fixed-rule factorial bridge between two exposed N7 diagnostics; no learning/I/O."""
import copy
import itertools
import math
from collections import Counter

from src.fundamentals_n7_baseline import rank_double_candidates
from src.fundamentals_compression_breadth import compression_surface, _checked_scenario_matrix
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.temporal_learning.core import stable_json_hash


def bridge_surface(frame, pool, references, *, cutoffs, depth):
    """Extend a sealed label-free pool with both original depth1/2 ticket groups.

    references maps depths 1,2 to original sealed plans; exact input and cutoff
    identities required. Return the existing TOP1 compression surface, with
    legacy disjoint prefix candidate indices. No labels or fitting admitted.
    The expanded candidate pool is shared across both depths and all factors.
    """
    ranked, bound = rank_double_candidates(frame, cutoffs=cutoffs)
    if depth not in (1, 2) or set(references) != {1, 2}:
        raise ValueError('Both original depths and explicit depth1/2 required')
    if pool.get('seal') != stable_json_hash({k:v for k,v in pool.items() if k != 'seal'}):
        raise ValueError('Pool changed')
    identity = stable_json_hash(frame.sort_values('slot').to_json(orient='records'))
    if pool['cutoffs'] != bound or pool['input_sha256'] != identity:
        raise ValueError('Original pool input and cutoff identity required')
    slots = list(ranked.sort_values('slot').slot); index = {s:i for i,s in enumerate(slots)}
    groups = {tuple(g) for g in pool['groups']}; prefixes = {}; reference_seals = {}
    for d, plan in references.items():
        limit_decision_chain_plan(plan, groups=plan['groups'], cutoffs=cutoffs)
        if plan['input_sha256'] != identity or plan['single_count'] != d or plan['single_rule'] != 'MAX_SINGLE':
            raise ValueError('Original TOP1 reference identity/depth required')
        old = [tuple(sorted(index[r['slot']] for r in plan['legs'] if r['group']==g)) for g in range(1,plan['groups']+1)]
        if any(len(g)!=7 or len(set(g))!=7 for g in old):
            raise ValueError('Seven distinct fixtures required')
        groups.update(old); prefixes[str(d)] = old[:plan['disjoint_groups']]; reference_seals[str(d)] = plan['seal']
    expanded = {k:copy.deepcopy(v) for k,v in pool.items() if k!='seal'}
    expanded.update(groups=[list(g) for g in sorted(groups)], pool_size=len(groups), parent_pool_seal=pool['seal'], reference_seals=reference_seals)
    expanded['seal'] = stable_json_hash(expanded)
    surface = compression_surface(frame, expanded, cutoffs=cutoffs, depth=depth, rule='TOP1', seed=0)
    surface.pop('seal')
    surface['prefix'] = [expanded['groups'].index(list(g)) for g in prefixes[str(depth)]]
    surface['seal'] = stable_json_hash(surface)
    return surface


def bridge_plan(frame, surface, design, reference, *, cutoffs, preserve_prefix, quality,
                overlap, cash_policy, budget_cny, unit_cny, payout_factor,
                max_uses=None, max_pair_overlap=None):
    """Create complete tickets for one fixed factorial cell, without labels.

    preserve_prefix bool; quality TOP2/COMPRESSED; overlap STRICT/FREE/CAPPED;
    cash_policy HOLD/REPEAT_BEST. STRICT limits fixture reuse2 and pair overlap2.
    FREE still forbids duplicate seven-fixture sets before funding. Remaining
    CAPPED requires explicit max_uses (positive integer) and max_pair_overlap
    (integer0..6); both caps include the preserved disjoint prefix. Other modes
    reject cap arguments. Candidate pool and probability order are unchanged.
    cash under REPEAT_BEST buys complete extra units of the highest compressed
    probability selected group; original group choices never change with cash.
    Budget must match reference; CNY2 units, single ticket-level0.65 explicit.
    Return sealed plan with candidate ledger, exact stake/cash, and provenance.
    """
    ranked, bound = rank_double_candidates(frame, cutoffs=cutoffs)
    limit_decision_chain_plan(reference, groups=reference['groups'], cutoffs=cutoffs)
    identity = stable_json_hash(frame.sort_values('slot').to_json(orient='records'))
    if surface.get('seal') != stable_json_hash({k:v for k,v in surface.items() if k!='seal'}):
        raise ValueError('Surface changed')
    if surface['pool']['cutoffs'] != bound or surface['pool']['input_sha256'] != identity or reference['input_sha256'] != identity:
        raise ValueError('Original input/cutoff identity required')
    if surface['pool']['reference_seals'][str(surface['depth'])] != reference['seal']:
        raise ValueError('Original reference required')
    if type(preserve_prefix) is not bool or quality not in ('TOP2','COMPRESSED') or overlap not in ('STRICT','FREE','CAPPED') or cash_policy not in ('HOLD','REPEAT_BEST'):
        raise ValueError('Explicit fixed factors required')
    if overlap=='CAPPED':
        if type(max_uses) is not int or max_uses<1 or type(max_pair_overlap) is not int or not 0<=max_pair_overlap<=6:
            raise ValueError('Positive reuse cap and pair-overlap cap0..6 required')
        if cash_policy!='HOLD':raise ValueError('Capped comparison requires HOLD cash policy')
        use_cap,pair_cap=max_uses,max_pair_overlap
    else:
        if max_uses is not None or max_pair_overlap is not None:raise ValueError('Caps require explicit CAPPED mode')
        use_cap,pair_cap=(2,2) if overlap=='STRICT' else (None,None)
    if type(budget_cny) is not int or budget_cny != reference['budget_cny'] or unit_cny != 2 or payout_factor != .65:
        raise ValueError('Matched budget, CNY2 and once-only0.65 required')
    candidates = surface['pool']['groups']; count = len(candidates); depth = surface['depth']; cost = unit_cny*2**(7-depth)
    _checked_scenario_matrix(design, expected_surface=surface['seal'], expected_cutoffs=bound, candidate_count=count)
    ordered = ranked.sort_values(['slot','provider_id']); rows = ordered.to_dict('records')
    scores = surface['mass'] if quality=='COMPRESSED' else [math.prod(rows[i]['coverage'] for i in g) for g in candidates]
    # TOP2 matches the old per-step log objective, including its fixed tie penalty.
    order = sorted(range(count), key=lambda i:(-(math.log(scores[i])- (1e-10*sum(candidates[i]) if quality=='TOP2' else 0)), candidates[i]))
    selected = list(surface['prefix']) if preserve_prefix else []
    if len(selected)>budget_cny//cost:raise ValueError('Prefix exceeds budget')
    uses = Counter(i for g in selected for i in candidates[g]); sets = [set(candidates[g]) for g in selected]
    if use_cap is not None and (any(n>use_cap for n in uses.values()) or any(len(a&b)>pair_cap for a,b in itertools.combinations(sets,2))):
        raise ValueError('Preserved prefix violates requested caps')
    for i in order:
        if len(selected)==budget_cny//cost:break
        if i in selected:continue
        group = set(candidates[i])
        if use_cap is not None and (any(uses[j]>=use_cap for j in group) or any(len(group&s)>pair_cap for s in sets)):continue
        selected.append(i); sets.append(group); uses.update(group)
    units = [1]*len(selected); cash = budget_cny-len(selected)*cost
    if cash_policy=='REPEAT_BEST' and selected:
        best = min(range(len(selected)), key=lambda j:(-surface['mass'][selected[j]], candidates[selected[j]]))
        units[best] += cash//cost; cash %= cost
    legs=[]; tickets=[]; ledger=[]
    for group,(candidate,mult) in enumerate(zip(selected,units),1):
        current=[]
        for i,mask,item in zip(candidates[candidate],surface['masks'][candidate],surface['ledger'][candidate]):
            r=copy.deepcopy(rows[i]);r.update(group=group,support=''.join(code for bit,code in enumerate('310') if mask&(1<<bit)))
            legs.append(r);current.append(r);ledger.append(dict(group=group,**item))
        tickets.extend(dict(group=group,code=''.join(c),units=mult) for c in itertools.product(*(r['support'] for r in current)))
    plan = {k:copy.deepcopy(v) for k,v in reference.items() if k not in ('seal','group_budget_cny','overlap_ledger')}
    plan.update(shape=f'C{depth}E0',selector=quality,single_rule='TOP1',single_count=depth,group_cost_cny=cost,
        groups=len(selected),legs=legs,tickets=tickets,stake=budget_cny-cash,cash_cny=cash,
        budget_cny=budget_cny,selected_candidates=selected,candidate_count=count,group_units=units,
        group_probability=[surface['mass'][i] for i in selected],contraction_ledger=ledger,
        disjoint_groups=len(surface['prefix']) if preserve_prefix else 0,
        overlap_groups=None,unique_tickets=len(tickets),paid_ticket_units=sum(t['units'] for t in tickets),
        repeat_units=sum(t['units']-1 for t in tickets),cutoffs=bound,input_sha256=identity,
        surface_seal=surface['seal'],source_pool_hash=stable_json_hash(surface['pool']),
        design_receipt={k:v for k,v in design.items() if k!='hits'},parent_seal=reference['seal'],
        factors=dict(preserve_prefix=preserve_prefix,quality=quality,overlap=overlap,cash_policy=cash_policy),
        model_proxy_gross=unit_cny*payout_factor*sum(u*surface['value_factor'][i] for i,u in zip(selected,units)))
    if overlap=='CAPPED':
        plan['factors'].update(max_uses=max_uses,max_pair_overlap=max_pair_overlap)
        plan.update(max_uses=max_uses,max_pair_overlap=max_pair_overlap)
    return dict(**plan,seal=stable_json_hash(plan))


def bind_bridge_reference(reference, surface, design, *, cutoffs):
    """Bind original ticket supports to a shared simulation without reselecting.

    Preserve every original ticket, amount and leg. Return a newly sealed copy
    with candidate identities; incompatible depth/support/cutoff fails closed.
    Used to independently settle the old control in the same evaluation stream.
    """
    limit_decision_chain_plan(reference, groups=reference['groups'], cutoffs=cutoffs)
    if surface.get('seal') != stable_json_hash({k:v for k,v in surface.items() if k!='seal'}):raise ValueError('Surface changed')
    if surface['pool']['cutoffs']!=reference['cutoffs'] or surface['pool']['input_sha256']!=reference['input_sha256'] or surface['pool']['reference_seals'].get(str(reference['single_count']))!=reference['seal']:
        raise ValueError('Original reference identity required')
    _checked_scenario_matrix(design, expected_surface=surface['seal'], expected_cutoffs=reference['cutoffs'], candidate_count=len(surface['mass']))
    identities={tuple(l['slot'] for l in row):i for i,row in enumerate(surface['ledger'])}; selected=[]
    for g in range(1,reference['groups']+1):
        legs=sorted([l for l in reference['legs'] if l['group']==g],key=lambda l:l['slot'])
        key=tuple(l['slot'] for l in legs)
        if key not in identities:raise ValueError('Reference group absent')
        i=identities[key]
        if any(l['support']!=''.join(code for bit,code in enumerate('310') if mask&(1<<bit)) for l,mask in zip(legs,surface['masks'][i])):
            raise ValueError('Reference support mismatch')
        selected.append(i)
    p={k:copy.deepcopy(v) for k,v in reference.items() if k not in ('seal','group_budget_cny')}
    p.update(parent_seal=reference['seal'],selected_candidates=selected,candidate_count=len(surface['mass']),surface_seal=surface['seal'],
        design_receipt={k:v for k,v in design.items() if k!='hits'},group_probability=[surface['mass'][i] for i in selected],
        unique_tickets=len(p['tickets']),paid_ticket_units=sum(t['units'] for t in p['tickets']),repeat_units=sum(t['units']-1 for t in p['tickets']))
    return dict(**p,seal=stable_json_hash(p))
