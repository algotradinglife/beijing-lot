"""Prediction-only preservation contract for residual-cash additions."""
from src.temporal_learning.core import stable_json_hash


def check_locked_groups(plan, original_rows, *, new_group_ids, cutoffs):
    """Require every originally funded prefix to remain at exactly its old depth.

    original_rows are the frozen control funded records (issue/arm/seed/group,
    depth,copies,stake). New IDs come from the bound candidate ledger. Monetary
    units are CNY. Returns locked/additional stake; missing or altered locks fail.
    Prefix identity/rank is separately checked against the original source bundle.
    No IO, learning or settlement labels.
    """
    if (plan['cutoffs']!=cutoffs or
        plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})):
        raise ValueError('Residual cutoff/seal mismatch')
    rows=[r for r in original_rows if str(r['issue'])==plan['issue'] and
          r['arm']==plan['original_arm'] and r['seed']==plan['seed']]
    old={str(r['sleeve_id']):r for r in rows}
    selected={str(s['sleeve_id']):s for s in plan['sleeve_keys']}
    if len(old)!=len(rows) or len(selected)!=len(plan['sleeve_keys']):
        raise ValueError('Duplicate funded group')
    if set(map(str,plan['locked_sleeve_ids']))!=set(old):
        raise ValueError('Missing original lock')
    for sid,row in old.items():
        if (sid not in selected or selected[sid]['depth']!=row['depth'] or
            row['copies']!=1 or selected[sid]['stake']!=row['stake']):
            raise ValueError('Original prefix displaced or resized')
    if not (set(selected)-set(old)).issubset(set(map(str,new_group_ids))):
        raise ValueError('Addition is not a new refill group')
    original_stake=sum(r['stake'] for r in rows)
    if (plan['stake']<original_stake or plan['stake']>plan['budget_cny'] or
        plan['stake']+plan['cash_cny']!=plan['budget_cny']):
        raise ValueError('Residual budget violation')
    return dict(status='PASS',original_stake=original_stake,
                added_stake=plan['stake']-original_stake)
