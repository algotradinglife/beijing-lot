"""Fixed-rule complementary N7 portfolios; no fitting or learned routing."""
import itertools
from collections import Counter
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_decision_chain import limit_decision_chain_plan
from src.fundamentals_compression_breadth import settle_breadth_bundle
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,compression_breadth_plan
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_n7_baseline import n7_baseline_plan


def complementary_sources(frame, *, cutoffs, candidate_seeds, random_seeds, quality_pool_size,
                          base_candidate_seed, pool_size, design_seed, design_draws,
                          budget_cny, unit_cny, payout_factor):
    """Fixed seed-only C2 U6/P5 and high-quality RANDOM/UNION candidate sources.

    Seed-only preserves original TOP2 ranking/prefix. RANDOM and UNION use the
    same top quality_pool_size compressed-probability candidates and shared
    fixture scenarios. Uses existing algorithms only; no seed selection by labels.
    RANDOM/UNION source lengths follow their existing disjoint-budget contract;
    these are candidate holdings, never extra investment. Allocation caps spend.
    Explicit seeds/cutoffs/constants, no I/O or fitting; return strategy->plan.
    """
    if (budget_cny!=1024 or unit_cny!=2 or payout_factor!=.65 or
        not candidate_seeds or not random_seeds or len(set(candidate_seeds))!=len(candidate_seeds) or
        len(set(random_seeds))!=len(random_seeds)):
        raise ValueError('Fixed budget and distinct nonempty seed lists required')
    refs={d:n7_single_plan(frame,cutoffs=cutoffs,budget_cny=budget_cny,single_rule='MAX_SINGLE',single_count=d,
        max_uses=2,unit_cny=unit_cny,payout_factor=payout_factor,allocation_seed=0) for d in (1,2)}
    sources={}
    for seed in candidate_seeds:
        pool=breadth_candidates(frame,cutoffs=cutoffs,seed=seed,pool_size=pool_size)
        surface=bridge_surface(frame,pool,refs,cutoffs=cutoffs,depth=2)
        design=breadth_scenarios(frame,surface,cutoffs=cutoffs,seed=design_seed,draws=design_draws)
        sources[f'SEED_{seed}']=bridge_plan(frame,surface,design,refs[2],cutoffs=cutoffs,preserve_prefix=True,
            quality='TOP2',overlap='CAPPED',max_uses=6,max_pair_overlap=5,cash_policy='HOLD',
            budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor)
    pool=breadth_candidates(frame,cutoffs=cutoffs,seed=base_candidate_seed,pool_size=pool_size)
    surface=bridge_surface(frame,pool,refs,cutoffs=cutoffs,depth=2)
    design=breadth_scenarios(frame,surface,cutoffs=cutoffs,seed=design_seed,draws=design_draws)
    legacy=n7_baseline_plan(frame,cutoffs=cutoffs,selector='COVERAGE',shape='C0E0',funding='UNIT',
        max_groups=6,unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=0)
    for method,seeds in [('RANDOM',random_seeds),('UNION',[random_seeds[0]])]:
        for seed in seeds:
            name=f'{method}_Q{quality_pool_size}'+(f'_S{seed}' if method=='RANDOM' else '')
            sources[name]=compression_breadth_plan(frame,surface,design,cutoffs=cutoffs,breadth=method,
                seed=seed,budget_cny=legacy['stake'],quality_pool_size=quality_pool_size,unit_cny=unit_cny,payout_factor=payout_factor)
    return sources


def complement_catalog(sources, *, cutoffs, unit_cny, payout_factor):
    """Validate same-input C1/C2 sources and deduplicate physical group holdings.

    sources maps fixed strategy IDs to sealed plans. Native shared cutoffs are
    mandatory. Each source ticket has one CNY2 unit, one .65 payout factor.
    Returns sealed unique single-group settlement components, source order and
    source seals. No labels, allocation, new ticket assembly, fitting or I/O.
    A source may be a longer candidate list; its nominal stake is not investment.
    """
    if not sources or unit_cny != 2 or payout_factor != .65:
        raise ValueError('Sources, CNY2 and once-only .65 required')
    components = {}; order = {}; seals = {}; identity = None
    for name, plan in sources.items():
        limit_decision_chain_plan(plan, groups=0, cutoffs=cutoffs)
        current = (plan['issue'], plan['input_sha256'], plan['cutoffs'])
        if identity is None: identity = current
        if current != identity: raise ValueError('Same source identity/cutoffs required')
        if plan['unit_cny'] != unit_cny or plan['payout_factor'] != payout_factor or plan['single_count'] not in (1,2):
            raise ValueError('C1/C2 unit contract required')
        order[name] = []; seals[name] = plan['seal']
        for g in range(1,plan['groups']+1):
            legs = sorted([dict(z,group=1) for z in plan['legs'] if z['group']==g],key=lambda z:z['slot'])
            tickets = [dict(t,group=1) for t in plan['tickets'] if t['group']==g]
            depth = plan['single_count'];cost = 2*2**(7-depth)
            if (len(legs)!=7 or len({z['slot'] for z in legs})!=7 or
                sorted(len(z['support']) for z in legs)!=[1]*depth+[2]*(7-depth) or
                len(tickets)!=2**(7-depth) or any(t['units']!=1 for t in tickets) or
                {t['code'] for t in tickets}!={''.join(c) for c in itertools.product(*(z['support'] for z in legs))}):
                raise ValueError('Complete unique one-unit N7 tickets required')
            key = stable_json_hash([(z['slot'],z['provider_id'],z['support']) for z in legs])
            if key in order[name]: raise ValueError('Repeated identical source group')
            order[name].append(key)
            if key in components: continue
            part = dict(issue=plan['issue'],selector='FIXED_COMPLEMENT',shape=f'C{depth}E0',funding='UNIT',
                groups=1,stake=cost,group_cost_cny=cost,budget_cny=cost,cash_cny=0,unit_cny=2,payout_factor=.65,
                single_rule='FIXED',cutoffs=plan['cutoffs'],input_sha256=plan['input_sha256'],legs=legs,tickets=tickets)
            part['seal'] = stable_json_hash(part)
            ticket_ids = [stable_json_hash([(z['slot'],z['provider_id'],c) for z,c in zip(legs,t['code'])]) for t in tickets]
            components[key] = dict(plan=part,ticket_ids=ticket_ids)
    if not components: raise ValueError('At least one complete source group required')
    result = dict(issue=identity[0],input_sha256=identity[1],cutoffs=identity[2],unit_cny=unit_cny,
        payout_factor=payout_factor,components=components,source_order=order,source_seals=seals)
    return dict(**result,seal=stable_json_hash(result))


def allocate_complement(catalog, *, cutoffs, main, alternative, main_budget_cny, budget_cny):
    """Allocate complete groups in original order to fixed main/alternative wallets.

    Main wallet is 0/512/768/1024 of explicit CNY1024. Unspent wallets stay cash;
    no transfers or duplicate full holdings. Same fixtures with different support
    are allowed; partial basic-ticket duplicates are paid separately and counted.
    No added cross-arm U/P constraints: their aggregate exposure is reported.
    Returns a sealed compact recipe bound to catalogue/cutoff and source IDs.
    """
    if stable_json_hash({k:v for k,v in catalog.items() if k!='seal'})!=catalog.get('seal'):
        raise ValueError('Catalog changed')
    if type(main_budget_cny) is not int or main_budget_cny not in (0,512,768,1024) or type(budget_cny) is not int or budget_cny!=1024:
        raise ValueError('Fixed integer CNY1024 wallets required')
    if main not in catalog['source_order'] or alternative not in catalog['source_order']:
        raise ValueError('Known fixed source IDs required')
    # Delegate exact native cutoff validation to the shared existing limiter.
    for component in catalog['components'].values():
        limit_decision_chain_plan(component['plan'],groups=0,cutoffs=cutoffs)
        break
    selected=[];allocations=[];spent=0
    for role,source,wallet in [('MAIN',main,main_budget_cny),('ALTERNATIVE',alternative,budget_cny-main_budget_cny)]:
        used=0
        for key in catalog['source_order'][source]:
            cost=catalog['components'][key]['plan']['stake']
            if key in selected or used+cost>wallet: continue
            selected.append(key);used+=cost;allocations.append(dict(component=key,role=role,source=source,stake=cost))
        spent+=used
    fixture=Counter();ticket_ids=[];sets=[]
    for key in selected:
        part=catalog['components'][key];slots={z['slot'] for z in part['plan']['legs']}
        fixture.update(slots);sets.append(slots);ticket_ids.extend(part['ticket_ids'])
    result=dict(issue=catalog['issue'],catalog_seal=catalog['seal'],main=main,alternative=alternative,
        main_budget_cny=main_budget_cny,budget_cny=budget_cny,stake=spent,cash_cny=budget_cny-spent,
        allocations=allocations,groups=len(selected),max_fixture_uses=max(fixture.values(),default=0),
        max_pair_overlap=max((len(a&b) for a,b in itertools.combinations(sets,2)),default=0),
        duplicate_ticket_units=len(ticket_ids)-len(set(ticket_ids)),unique_fixtures=len(fixture),
        fixture_hhi=sum((v/sum(fixture.values()))**2 for v in fixture.values()) if fixture else 0.)
    return dict(**result,seal=stable_json_hash(result))


def settle_complements(catalog, recipes, audit):
    """Settle unique components once via authoritative settlement, then sum.

    audit has unique READY issue/slot/provider IDs, handicap, direction and final
    SPF SP. No I/O, source mutation or new payout formula. Missing results fail.
    Returns one CNY row per fixed recipe, plus actual exposure and budget ROI.
    """
    if stable_json_hash({k:v for k,v in catalog.items() if k!='seal'})!=catalog.get('seal'):
        raise ValueError('Catalog changed')
    if audit.empty or audit.duplicated(['issue','slot','provider_id']).any() or not audit.status.eq('READY').all():
        raise ValueError('Unique READY audit required')
    settled=settle_breadth_bundle(catalog['components'],audit);rows=[]
    for policy,recipe in recipes.items():
        if (stable_json_hash({k:v for k,v in recipe.items() if k!='seal'})!=recipe.get('seal') or
            recipe['catalog_seal']!=catalog['seal']): raise ValueError('Recipe changed or different catalogue')
        parts=[settled[a['component']] for a in recipe['allocations']]
        if any(p['status']!='COMPLETE' for p in parts): raise ValueError('Incomplete settlement')
        if sum(p['stake'] for p in parts)!=recipe['stake']: raise ValueError('Allocation stake mismatch')
        gross=sum(p['gross'] for p in parts);net=gross-recipe['stake']
        rows.append(dict(issue=recipe['issue'],policy=policy,main=recipe['main'],alternative=recipe['alternative'],
            main_budget_cny=recipe['main_budget_cny'],budget_cny=1024,stake=recipe['stake'],cash_cny=recipe['cash_cny'],
            groups=recipe['groups'],gross=gross,net=net,hits=sum(p['hits'] for p in parts),status='COMPLETE',
            budget_return=net/1024,roi=net/recipe['stake'] if recipe['stake'] else None,
            **{k:recipe[k] for k in ['max_fixture_uses','max_pair_overlap','duplicate_ticket_units','unique_fixtures','fixture_hhi']}))
    return rows
