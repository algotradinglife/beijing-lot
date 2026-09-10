"""Compose existing fixed compression policies; no fitting or temporal helpers."""
import itertools
from src.fundamentals_n7_single import n7_single_plan
from src.fundamentals_compression_bridge import bridge_surface, bridge_plan
from src.fundamentals_compression_breadth import breadth_candidates, breadth_scenarios, settle_breadth_bundle
from src.fundamentals_n7_diversity import replace_repeated_double_tail, evaluate_fixed_supports
from src.fundamentals_market_conflict import replace_market_conflict_doubles


def build_compression_variants(frame, *, cutoffs, n, budget_cny, unit_cny,
                               payout_factor, candidate_seed, design_seed,
                               evaluation_seed, pool_size, design_draws,
                               evaluation_draws, gap_rules, conflict_rules,
                               minimum_market_tail_lead):
    """Return sealed C1/C2 plans for both rankings and reuse constraints.

    frame: one issue/slot/provider with p/q handicap WDL probabilities; optional
    home/away names. Only forecast columns are admitted. Explicit cutoffs go to
    authoritative selection/scenario functions. Monetary inputs are CNY; gaps
    and TV thresholds are unit probabilities. Fewer than seven fixtures or
    invalid inputs fail. Pure, label-free, no I/O; no thresholds are optimized.
    """
    required = {'issue', 'slot', 'provider_id', 'handicap', 'p_W', 'p_D', 'p_L', 'q_W', 'q_D', 'q_L'}
    if n != 7 or isinstance(n, bool) or len(frame) < n or not required <= set(frame) or set(frame) - required - {'home', 'away'}:
        raise ValueError('Seven fixtures and forecast-only factor columns required')
    if set(gap_rules) & (set(conflict_rules) | {'BASE'}) or 'BASE' in conflict_rules:
        raise ValueError('Unique policy names required')
    refs = {d: n7_single_plan(frame, cutoffs=cutoffs, budget_cny=budget_cny,
        single_rule='MAX_SINGLE', single_count=d, max_uses=2, unit_cny=unit_cny,
        payout_factor=payout_factor, allocation_seed=0) for d in (1, 2)}
    pool = breadth_candidates(frame, cutoffs=cutoffs, seed=candidate_seed, pool_size=pool_size)
    bundle = {}
    for depth in (1, 2):
        surface = bridge_surface(frame, pool, refs, cutoffs=cutoffs, depth=depth)
        design = breadth_scenarios(frame, surface, cutoffs=cutoffs, seed=design_seed, draws=design_draws)
        for quality, overlap in itertools.product(['TOP2', 'COMPRESSED'], ['STRICT', 'FREE']):
            case = f'D{depth}_{quality}_{overlap}'
            base = bridge_plan(frame, surface, design, refs[depth], cutoffs=cutoffs,
                preserve_prefix=True, quality=quality, overlap=overlap, cash_policy='HOLD',
                budget_cny=budget_cny, unit_cny=unit_cny, payout_factor=payout_factor)
            plans = {'BASE': base}
            plans.update({rule: replace_repeated_double_tail(base, cutoffs=cutoffs, max_gap=gap)
                          for rule, gap in gap_rules.items()})
            plans.update({rule: replace_market_conflict_doubles(base, cutoffs=cutoffs,
                minimum_tv=tv, minimum_market_tail_lead=minimum_market_tail_lead)
                for rule, tv in conflict_rules.items()})
            for rule, plan in plans.items():
                evaluation = evaluate_fixed_supports(frame, plan, cutoffs=cutoffs,
                    seed=evaluation_seed, draws=evaluation_draws)
                bundle[case+'_'+rule] = dict(case=case, rule=rule, depth=depth,
                    quality=quality, overlap=overlap, plan=plan, evaluation=evaluation)
    return bundle


def settle_compression_variants(bundle, audit):
    """Describe frozen plans using accepted READY settlement rows only.

    audit has unique issue/slot/provider IDs, handicap, actual_direction, SPF SP,
    status. The authoritative ticket settlement implementation computes payouts.
    Returns one issue/policy row, CNY net/gross and unitless ROI. Incomplete or
    ambiguous labels fail rather than become zero returns. No plan mutations.
    """
    keys = ['issue', 'slot', 'provider_id']
    if not bundle or audit.empty or audit.duplicated(keys).any() or not audit.status.eq('READY').all():
        raise ValueError('Unique READY settlement rows required')
    if not audit.actual_direction.isin(['W', 'D', 'L']).all():
        raise ValueError('Known handicap outcomes required')
    lookup = audit.set_index(keys)
    won = {}
    for policy, entry in bundle.items():
        plan = entry['plan']
        won[policy] = []
        for group in range(1, plan['groups']+1):
            legs = [z for z in plan['legs'] if z['group'] == group]
            rows = [lookup.loc[(z['issue'], z['slot'], z['provider_id'])] for z in legs]
            if any(r.handicap != z['handicap'] for r, z in zip(rows, legs)):
                raise ValueError('Settlement handicap mismatch')
            won[policy].append(all(dict(W='3', D='1', L='0')[r.actual_direction] in z['support']
                                   for r, z in zip(rows, legs)))
    settled = settle_breadth_bundle(bundle, audit)
    result = []
    for policy, entry in bundle.items():
        plan = entry['plan'];row = settled[policy]
        if row['status'] != 'COMPLETE':
            raise ValueError('Incomplete settlement cannot enter comparison')
        base = won[entry['case']+'_BASE'];actual = won[policy]
        if len(base) != len(actual):
            raise ValueError('Within-case groups differ')
        row.update(**{k: entry[k] for k in ['case', 'rule', 'depth', 'quality', 'overlap']},
            policy=policy, partition='PURE_BASELINE_RETROSPECTIVE', budget_cny=plan['budget_cny'],
            cash_cny=plan['cash_cny'], budget_return=row['net']/plan['budget_cny'], repeat_units=plan['repeat_units'],
            changed_legs=sum(z['changed'] for z in plan.get('diversity_ledger', [])),
            gained_groups=sum(x and not y for x, y in zip(actual, base)),
            lost_groups=sum(y and not x for x, y in zip(actual, base)),
            mean_group_probability=sum(plan['group_probability'])/plan['groups'], **entry['evaluation']['metrics'])
        result.append(row)
    return result
