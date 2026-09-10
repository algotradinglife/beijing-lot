"""Fixed N7 selector/grouping diagnostic; market reciprocal is an SP proxy, not a forecast fit."""
import copy
import math
import pandas as pd
from src.fundamentals_n7_baseline import n7_baseline_plan, settle_n7_baseline
from src.temporal_learning.core import stable_json_hash


def n7_selection_plan(frame, *, cutoffs, selector, grouping, max_groups, unit_cny,
                      group_budget_cny, payout_factor, allocation_seed):
    """Return sealed fixed-double plan with CONCENTRATED or SNAKE groups.

    Same selected pool under both groupings. SNAKE alternates rank direction
    across seven rounds, one fixture per group/round. No outcome/SP inputs.
    Constants are explicit; all ticket creation/validation uses baseline API.
    """
    if grouping not in ['CONCENTRATED','SNAKE']: raise ValueError('Explicit grouping required')
    kw=dict(selector=selector,shape='C0E0',funding='UNIT',max_groups=max_groups,
            unit_cny=unit_cny,group_budget_cny=group_budget_cny,payout_factor=payout_factor,allocation_seed=allocation_seed)
    plan=n7_baseline_plan(frame,cutoffs=cutoffs,**kw)
    if grouping=='SNAKE' and plan['groups']:
        pool=pd.DataFrame(plan['legs']).sort_values([selector.lower(),'slot','provider_id'],ascending=[False,True,True])
        assignments=[];count=plan['groups']
        for round_no in range(7): assignments.extend(range(1,count+1) if round_no%2==0 else range(count,0,-1))
        pool['group']=assignments;legs=[];tickets=[]
        for group,g in pool.groupby('group',sort=True):
            original=frame[frame.slot.isin(g.slot)]
            part=n7_baseline_plan(original,cutoffs={str(s):cutoffs[str(s)] for s in original.slot},**kw)
            for r in part['legs']: r['group']=int(group);legs.append(r)
            for t in part['tickets']:t['group']=int(group);tickets.append(t)
        plan['legs']=legs;plan['tickets']=tickets
    plan['grouping']=grouping
    plan['sp_proxy']='RECIPROCAL_MARKET_PROBABILITY_NOT_OBSERVED_BD_SP'
    plan.pop('seal');plan['seal']=stable_json_hash(plan)
    return plan


def n7_selection_expectation(plan):
    """Return per-group and portfolio expectation from the sealed prediction-only plan.

    Independence assumption: double hit=product(sum p), expected gross per group
    = unit * payout_factor * product(sum(p/q)). All Cartesian tickets one unit.
    Variance uses product(sum(p/q^2)); excludes estimation/correlation risk.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan['seal']:raise ValueError('Plan changed')
    if plan['shape']!='C0E0' or plan['funding']!='UNIT':raise ValueError('Fixed full doubles required')
    rows=[];codes=dict(zip('310','WDL'))
    for group in range(1,plan['groups']+1):
        legs=[r for r in plan['legs'] if r['group']==group];first=[];second=[];coverage=[]
        for r in legs:
            ds=[codes[c] for c in r['support']]
            first.append(sum(r['p_'+d]/r['q_'+d] for d in ds))
            second.append(sum(r['p_'+d]/r['q_'+d]**2 for d in ds))
            coverage.append(sum(r['p_'+d] for d in ds))
        gross=plan['unit_cny']*plan['payout_factor']*math.prod(first)
        variance=(plan['unit_cny']*plan['payout_factor'])**2*math.prod(second)-gross**2
        rows.append(dict(group=group,hit_probability=math.prod(coverage),expected_gross=gross,
                         expected_net=gross-256,expected_roi=gross/256-1,gross_variance=max(0.,variance)))
    gross=sum(r['expected_gross'] for r in rows)
    return dict(groups=rows,expected_gross=gross,expected_net=gross-plan['stake'],
                expected_roi=gross/plan['stake']-1 if plan['stake'] else None,
                any_hit_probability=1-math.prod(1-r['hit_probability'] for r in rows),
                gross_sd=math.sqrt(sum(r['gross_variance'] for r in rows)))


def settle_n7_selection(plan, audit):
    """Use authoritative baseline settlement and append grouping and ex-ante metrics."""
    row=settle_n7_baseline(plan,audit)
    expectation=n7_selection_expectation(plan)
    row.update(grouping=plan['grouping'],**{k:v for k,v in expectation.items() if k!='groups'})
    return row
