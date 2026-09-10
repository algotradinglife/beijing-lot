"""Outcome-support diversity on already frozen fixture groups."""
import itertools
from collections import defaultdict
import math
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.temporal_learning.core import stable_json_hash


def diversify_n7_outcomes(base, *, cutoffs, rule):
    """Change repeated-fixture supports, preserving groups and single/double roles.

    rule must be PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE. Process groups in their
    frozen order. For each fixture/direction score p/(1+previous groups covering
    this direction); select the top1 or top2 according to the original role.
    Ties W,D,L. First use is unchanged; later uses may pick a different single
    or double. This score is a ranking priority, NOT a recalibrated probability.
    Original p/q unchanged. No labels, fitting, random seeds, caching or I/O.
    Native shared Cutoffs/source seal checked by the existing limiter. Return
    sealed plan, full ticket support, and pre-choice count/priority ledger.
    """
    if rule!='PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE':raise ValueError('Explicit fixed diversity rule required')
    if base.get('single_count')!=3 or base.get('group_cost_cny')!=32:raise ValueError('Three-single plan required')
    plan=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    plan.pop('seal');plan['tickets']=[];history=defaultdict(lambda:dict(W=0,D=0,L=0));ledger=[]
    for group in range(1,base['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot'])
        if len(legs)!=7 or sorted(len(r['support']) for r in legs)!=[1,1,1,2,2,2,2]:raise ValueError('Exact three-single/four-double role contract required')
        for r in legs:
            before=dict(history[r['slot']]);priority={d:r['p_'+d]/(1+before[d]) for d in 'WDL'}
            selected=sorted('WDL',key=lambda d:(-priority[d],'WDL'.index(d)))[:len(r['support'])]
            old=r['support'];r['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in selected)
            ledger.append(dict(group=group,slot=r['slot'],provider_id=r['provider_id'],prior_counts=before,
                priority=priority,source_support=old,selected_support=r['support'],changed=r['support']!=old))
            for d in selected:history[r['slot']][d]+=1
        plan['tickets'].extend(dict(group=group,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in legs)))
    if len(plan['tickets'])*plan['unit_cny']!=base['stake']:raise ValueError('Diversity changed stake')
    plan.update(diversity_rule=rule,diversity_ledger=ledger,source_support_plan_seal=base['seal'])
    return dict(**plan,seal=stable_json_hash(plan))


def replace_repeated_double_tail(base, *, cutoffs, max_gap=1.0):
    """On later fixture appearances replace Top2 with Top1+Top3, singles fixed.

    Process frozen group order; any earlier appearance (single or double)
    counts as overlap. Third/later appearances use Top1+Top3 again, never toggle.
    First appearances and all single supports remain unchanged. Require a
    sealed positive C1/C2 plan whose original doubles are Top1+Top2 and singles
    Top1, ties W,D,L. Each group has seven distinct fixtures and uniform positive
    integer ticket units. Same group sets, roles, unit allocation, stake/cash,
    p/q and cutoffs. No fitting, labels, I/O or reallocation of remaining money.
    max_gap is the inclusive absolute probability-point gap p(second)-p(third),
    in probability units (0.05 means five percentage points); default 1 permits
    all repeated doubles. Zero permits exact ties only. A 1e-12 arithmetic
    tolerance applies at the boundary. Fixed policy input, never fitted here.
    Return full new tickets and per-leg before/after ledger. Recompute support
    probabilities/proxy gross; remove stale candidate-surface metric bindings.
    Existing design_receipt records the original group-selection provenance.
    """
    if isinstance(max_gap,bool) or not isinstance(max_gap,(int,float)) or not math.isfinite(max_gap) or not 0<=max_gap<=1:
        raise ValueError('max_gap must be a finite probability difference in [0,1]')
    plan=limit_decision_chain_plan(base,groups=base['groups'],cutoffs=cutoffs)
    if base.get('single_count') not in (1,2) or base['groups']<1 or base['unit_cny']!=2 or base['payout_factor']!=.65:
        raise ValueError('Positive C1/C2 plan with CNY2 and once-only0.65 required')
    if 'diversity_rule' in base:raise ValueError('Use an unadjusted source plan')
    if base['group_cost_cny']!=2*2**(7-base['single_count']) or base['cash_cny']<0 or base['stake']+base['cash_cny']!=base['budget_cny']:
        raise ValueError('Consistent group cost and source budget required')
    plan.pop('seal');plan['tickets']=[];seen=defaultdict(int);ledger=[];masses=[];proxy=0.;identities=set();source_rows={};group_units=[]
    for group in range(1,base['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot'])
        if len(legs)!=7 or len({r['slot'] for r in legs})!=7 or sum(len(r['support'])==1 for r in legs)!=base['single_count'] or any(len(r['support']) not in (1,2) for r in legs):
            raise ValueError('Exact seven-fixture single/double role contract required')
        old_tickets=[t for t in base['tickets'] if t['group']==group];units={t['units'] for t in old_tickets}
        if len(units)!=1 or any(type(u) is not int or u<1 for u in units):raise ValueError('Uniform positive integer group units required')
        multiplier=next(iter(units));group_units.append(multiplier);old_codes={''.join(z) for z in itertools.product(*(r['support'] for r in legs))}
        if len(old_tickets)!=len(old_codes) or {t['code'] for t in old_tickets}!=old_codes:raise ValueError('Complete original physical tickets required')
        for r in legs:
            values=[r[p+d] for p in ('p_','q_') for d in 'WDL']
            if not all(math.isfinite(v) and 0<=v<=1 for v in values) or any(v<=0 for v in values[3:]) or abs(sum(values[:3])-1)>1e-8 or abs(sum(values[3:])-1)>1e-8:
                raise ValueError('Normalized probabilities and positive market q required')
            identity=tuple(r[k] for k in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L'])
            if r['slot'] in source_rows and source_rows[r['slot']]!=identity:raise ValueError('Repeated fixture identity/probabilities changed')
            source_rows[r['slot']]=identity
            order=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)));expected={dict(W='3',D='1',L='0')[d] for d in order[:len(r['support'])]}
            if set(r['support'])!=expected:raise ValueError('Original Top1/Top2 supports required; do not reapply transformation')
            before=r['support'];prior=seen[r['slot']]
            gap=r['p_'+order[1]]-r['p_'+order[2]]
            if prior and len(before)==2 and gap<=max_gap+1e-12:
                support={order[0],order[2]};r['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in support)
            ledger.append(dict(group=group,slot=r['slot'],provider_id=r['provider_id'],prior_appearances=prior,
                source_support=before,selected_support=r['support'],changed=r['support']!=before,second_third_gap=gap,
                original_mass=sum(r['p_'+d] for d,c in zip('WDL','310') if c in before),
                selected_mass=sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support'])))
            seen[r['slot']]+=1
        mass=math.prod(sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs);masses.append(mass)
        proxy+=2*.65*multiplier*math.prod(sum(r['p_'+d]/r['q_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs)
        for code in itertools.product(*(r['support'] for r in legs)):
            identity=tuple((r['slot'],c) for r,c in zip(legs,code))
            if identity in identities:raise ValueError('Duplicate physical ticket identity across groups')
            identities.add(identity);plan['tickets'].append(dict(group=group,code=''.join(code),units=multiplier))
    if sum(t['units']*2 for t in plan['tickets'])!=base['stake']:raise ValueError('Source stake/ticket units mismatch')
    for key in ['surface_seal','selected_candidates','candidate_count','source_pool_hash']:
        plan.pop(key,None)
    plan.update(diversity_rule='REPEATED_DOUBLE_TOP1_TOP3_SINGLE_UNCHANGED',max_gap=max_gap,diversity_ledger=ledger,
        source_support_plan_seal=base['seal'],group_probability=masses,group_units=group_units,model_proxy_gross=proxy,
        unique_tickets=len(plan['tickets']),paid_ticket_units=sum(t['units'] for t in plan['tickets']),
        repeat_units=sum(t['units']-1 for t in plan['tickets']))
    return dict(**plan,seal=stable_json_hash(plan))


def evaluate_fixed_supports(frame, plan, *, cutoffs, seed, draws):
    """Evaluate actual sealed supports with existing shared-fixture simulation.

    Complete original one-issue prediction frame and exact cutoff required.
    Explicit evaluation seed must differ from original design_receipt seed.
    Return existing breadth metrics plus sealed evaluation receipt bound to
    the actual plan and support surface. No selection, fitting or label inputs.
    Candidate indices are rebuilt from the actual legs, never inherited from
    an earlier support plan. Same seed/frame gives paired common scenarios.
    """
    from src.fundamentals_n7_baseline import rank_double_candidates
    from src.fundamentals_compression_breadth import breadth_scenarios,breadth_metrics
    limit_decision_chain_plan(plan,groups=plan['groups'],cutoffs=cutoffs)
    ranked,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    if plan['groups']<1 or plan['cutoffs']!=bound or plan['input_sha256']!=stable_json_hash(frame.sort_values('slot').to_json(orient='records')):
        raise ValueError('Original complete frame and cutoff identity required')
    design=plan['design_receipt']
    if stable_json_hash({k:v for k,v in design.items() if k!='seal'})!=design['seal'] or design['cutoffs']!=bound:
        raise ValueError('Original sealed design receipt required')
    slots=list(ranked.sort_values('slot').slot);by_slot=ranked.set_index('slot').to_dict('index');groups=[];masks=[]
    for g in range(1,plan['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
        if len(legs)!=7 or len({r['slot'] for r in legs})!=7:raise ValueError('Seven distinct fixtures required')
        for r in legs:
            if r['slot'] not in by_slot or any(r[k]!=by_slot[r['slot']][k] for k in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L']):raise ValueError('Plan/frame values differ')
            if not r['support'] or len(set(r['support']))!=len(r['support']) or not set(r['support'])<=set('310'):raise ValueError('Invalid outcome support')
        groups.append([slots.index(r['slot']) for r in legs]);masks.append([sum(1<<bit for bit,c in enumerate('310') if c in r['support']) for r in legs])
    pool=dict(groups=groups,cutoffs=bound,input_sha256=plan['input_sha256']);pool['seal']=stable_json_hash(pool)
    surface=dict(pool=pool,masks=masks);surface['seal']=stable_json_hash(surface)
    evaluation=breadth_scenarios(frame,surface,cutoffs=cutoffs,seed=seed,draws=draws)
    view={k:v for k,v in plan.items() if k!='seal'};view.update(surface_seal=surface['seal'],candidate_count=len(groups),selected_candidates=list(range(len(groups))));view['seal']=stable_json_hash(view)
    metrics=breadth_metrics(view,evaluation,cutoffs=cutoffs)
    receipt=dict(plan_seal=plan['seal'],support_surface=surface,evaluation={k:v for k,v in evaluation.items() if k!='hits'},original_design_receipt=design)
    receipt['seal']=stable_json_hash(receipt)
    return dict(metrics=metrics,receipt=receipt)
