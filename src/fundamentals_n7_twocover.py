"""Outcome-blind two-cover N7 diagnostic using adjacent rank-boundary swaps."""
import copy
from src.fundamentals_n7_baseline import n7_baseline_plan, settle_n7_baseline
from src.fundamentals_n67_overlay import overlay_any_hit
from src.temporal_learning.core import stable_json_hash


def n7_twocover_plan(frame, *, cutoffs, strategy, max_groups, unit_cny, payout_factor, allocation_seed):
    """Seal BASE, DOUBLE_STAKE or TWO_COVER; no fit or writes.

    Rank by fixed Top2 coverage, consecutive seven fixtures, up to max_groups=6.
    TWO_COVER exchanges last/first fixtures across each adjacent group boundary.
    Same selected pool, each fixture occurs once per layer, no identical groups.
    With fewer than two groups no second layer exists and no extra money is spent.
    Explicit native per-fixture cutoffs are validated by the common baseline API.
    """
    if strategy not in ['BASE','DOUBLE_STAKE','TWO_COVER']:raise ValueError('Explicit strategy required')
    if (max_groups,unit_cny,payout_factor)!=(6,2,.65):raise ValueError('Explicit business constants required')
    kw=dict(selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=max_groups,
            unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=allocation_seed)
    first=n7_baseline_plan(frame,cutoffs=cutoffs,**kw)
    count=first['groups'];parts=[first]
    if strategy=='TWO_COVER' and count>=2:
        groups=[]
        for g in range(1,count+1):
            groups.append(sorted([r for r in first['legs'] if r['group']==g],key=lambda r:(-r['coverage'],r['slot'],r['provider_id'])))
        for i in range(count-1):groups[i][-1],groups[i+1][0]=groups[i+1][0],groups[i][-1]
        second=copy.deepcopy(first);second.pop('seal');second['legs']=[];second['tickets']=[]
        for g,rows in enumerate(groups,1):
            slots={r['slot'] for r in rows};subset=frame[frame.slot.isin(slots)]
            sub=n7_baseline_plan(subset,cutoffs={str(s):cutoffs[str(s)] for s in slots},**kw)
            for r in sub['legs']:r['group']=g;second['legs'].append(r)
            for t in sub['tickets']:t['group']=g;second['tickets'].append(t)
        second['seal']=stable_json_hash(second);parts.append(second)
    elif strategy=='DOUBLE_STAKE' and count>=2:
        first.pop('seal')
        for t in first['tickets']:t['units']=2
        first['stake']*=2;first['seal']=stable_json_hash(first)
    result=dict(issue=first['issue'],strategy=strategy,funding='UNIT',components=parts,
        stake=sum(p['stake'] for p in parts),budget=sum(p['stake'] for p in parts),
        model_any_hit=overlay_any_hit(parts),historical_admission=False,
        mode='EXPOSED_FIXTURE_RELATIVE_RETROSPECTIVE_NOT_SIMULTANEOUS',cutoffs=first['cutoffs'])
    result['seal']=stable_json_hash(result)
    return result


def settle_n7_twocover(plan,audit):
    """Read-only settlement via common API. Missing labels/SP leave PnL unknown.

    Hits count distinct groups, never stake multipliers. All payouts include one
    ticket-level .65 factor. No-group plan retains zero stake and undefined ROI.
    """
    if stable_json_hash({k:v for k,v in plan.items() if k!='seal'})!=plan['seal']:raise ValueError('Plan changed')
    settled=[settle_n7_baseline(p,audit) for p in plan['components']]
    row={k:plan[k] for k in ['issue','strategy','funding','stake','budget','model_any_hit']}
    row.update(groups=sum(p['groups'] for p in plan['components']),cash=0)
    if any(r['status'] not in ['COMPLETE','NO_BET'] for r in settled):
        return dict(**row,status='PENDING_AUDIT_OR_WINNING_SP',gross=None,net=None,roi=None,hits=None,ideal_gross=None)
    gross=sum(r['gross'] for r in settled)
    return dict(**row,status='COMPLETE' if row['groups'] else 'NO_BET',gross=gross,net=gross-row['stake'],
        roi=gross/row['stake']-1 if row['stake'] else None,hits=sum(r['hits'] for r in settled),ideal_gross=gross)
