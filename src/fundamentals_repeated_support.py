"""Compose fixed single and double replacement gates on frozen C1/C2 groups."""
import math
from src.fundamentals_n7_diversity import replace_repeated_double_tail
from src.fundamentals_market_conflict import replace_market_conflict_doubles
from src.temporal_learning.core import stable_json_hash


def replace_repeated_support(base, *, cutoffs, change_singles, double_rule,
                             single_ceiling, max_gap, minimum_tv, minimum_market_tail_lead):
    """Return a sealed C1/C2 plan with the same groups, roles, units and cash.

    All thresholds are explicit, fixed probability units, inclusive within
    1e-12. double_rule is NONE/GAP/MARKET/EITHER. Any earlier fixture appearance
    counts; first uses stay unchanged. Later singles with original p1 <= ceiling
    use original Top2; qualifying later doubles use Top1+Top3. Never toggle.
    p/q and original ranking stay fixed, ties W,D,L. Market gate delegates to
    the existing comparable handicap Euro+OU gate. Original tickets are mapped
    bijectively to new supports, never reallocated. No labels, fitting or I/O.
    Native shared cutoffs and source validation delegate to existing transforms.
    """
    if type(change_singles) is not bool or double_rule not in {'NONE','GAP','MARKET','EITHER'}:
        raise ValueError('Explicit single switch and known double rule required')
    if type(base.get('single_count')) is not int or base['single_count'] not in (1,2):
        raise ValueError('One- or two-single source plan required')
    if isinstance(single_ceiling,bool) or not isinstance(single_ceiling,(int,float)) or not math.isfinite(single_ceiling) or not 0<=single_ceiling<=1:
        raise ValueError('Single ceiling must be a finite probability')
    gap = replace_repeated_double_tail(base,cutoffs=cutoffs,max_gap=max_gap)
    market = replace_market_conflict_doubles(base,cutoffs=cutoffs,minimum_tv=minimum_tv,
        minimum_market_tail_lead=minimum_market_tail_lead)
    market_rows = {(r['group'],r['slot']):r for r in market['diversity_ledger']}
    legs = {(r['group'],r['slot']):r for r in gap['legs']}
    maps = {}; gap.pop('seal')
    for row in gap['diversity_ledger']:
        key = row['group'],row['slot']; leg = legs[key]; evidence = market_rows[key]
        old = leg['support']; original = row['source_support']
        order = sorted('WDL',key=lambda d:(-leg['p_'+d],'WDL'.index(d)))
        single_gate = change_singles and len(original)==1 and leg['p_'+order[0]]<=single_ceiling+1e-12
        double_gate = ((double_rule in {'GAP','EITHER'} and row['changed']) or
                       (double_rule in {'MARKET','EITHER'} and evidence['changed']))
        selected = original
        if row['prior_appearances'] and single_gate:
            selected = dict(W='3',D='1',L='0')[order[1]]
        elif len(original)==2 and double_gate:
            selected = ''.join(c for d,c in zip('WDL','310') if d in {order[0],order[2]})
        maps[key] = dict(zip(old,selected))
        leg['support'] = selected
        row.update(gap_qualifies=row['second_third_gap']<=max_gap+1e-12,
            market_qualifies=evidence['conflict_qualifies'],
            total_variation=evidence['total_variation'],market_tail_lead=evidence['market_tail_lead'],
            single_qualifies=single_gate,selected_support=selected,changed=selected!=original,
            selected_mass=sum(leg['p_'+d] for d,c in zip('WDL','310') if c in selected))
    for ticket in gap['tickets']:
        group = ticket['group']
        ordered = sorted((r for r in gap['legs'] if r['group']==group),key=lambda r:r['slot'])
        ticket['code'] = ''.join(maps[group,r['slot']][c] for r,c in zip(ordered,ticket['code']))
    masses=[];proxy=0.
    for group in range(1,gap['groups']+1):
        group_legs=[r for r in gap['legs'] if r['group']==group]
        masses.append(math.prod(sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in group_legs))
        proxy += gap['unit_cny']*gap['payout_factor']*gap['group_units'][group-1]*math.prod(
            sum(r['p_'+d]/r['q_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in group_legs)
    gap.update(diversity_rule='FIXED_REPEATED_SINGLE_DOUBLE',change_singles=change_singles,
        double_rule=double_rule,single_ceiling=single_ceiling,minimum_tv=minimum_tv,
        minimum_market_tail_lead=minimum_market_tail_lead,group_probability=masses,model_proxy_gross=proxy)
    return dict(**gap,seal=stable_json_hash(gap))
