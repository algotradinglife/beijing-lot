"""Paired, exposed-history support ablation on fixed consensus groups."""
import copy
import itertools
from collections import Counter
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def paired_double_source(plan, *, cutoffs, double_source, budget_cny, unit_cny, payout_factor):
    """Keep frozen slots, A singles and funding; change only D/C double support.

    Sealed consensus portfolio in; sealed settlement-compatible portfolio out.
    BASELINE/MARKET selects p/q Top2 with W,D,L deterministic ties. Explicit
    native fixture cutoffs, CNY1024 wallet, CNY2 units and .65 payout required.
    No fit, labels, I/O or input mutation; source is exposed historical evidence,
    never prospective admission. Unused source cutoff keys are rejected.
    Obsolete source model_any_hit is cleared, not carried as a new prediction.
    """
    if double_source not in ('BASELINE','MARKET') or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65):
        raise ValueError('Explicit support source and business constants required')
    if plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):
        raise ValueError('Source plan changed')
    if set(cutoffs)!=set(plan['cutoffs']):
        raise ValueError('Exact source cutoff keys required')
    for key,cut in cutoffs.items():
        if cut.target_issue!=plan['issue'] or cut.cutoff_ts.isoformat()!=plan['cutoffs'][key]:
            raise ValueError('Source cutoff changed')
    result=copy.deepcopy(plan)
    result.pop('seal')
    for part in result['components']:
        if part['seal']!=stable_json_hash({k:v for k,v in part.items() if k!='seal'}):
            raise ValueError('Component changed')
        part.pop('seal')
        legs=part['legs']
        if len(legs)!=7 or Counter(r['role'] for r in legs)!=Counter(A=2,D=4,C=1):
            raise ValueError('Expected fixed two-anchor, five-double group')
        rank_double_candidates(pd.DataFrame(legs),cutoffs={str(r['slot']):cutoffs[str(r['slot'])] for r in legs})
        for r in legs:
            p=sorted(range(3),key=lambda i:(-r['p_'+'WDL'[i]],i))
            q=sorted(range(3),key=lambda i:(-r['q_'+'WDL'[i]],i))
            original=''.join('310'[i] for i in range(3) if i in (p[:1] if r['role']=='A' else p[:2]))
            if r['support']!=original or (r['role']=='A' and (p[0]!=q[0] or r['q_'+'WDL'[q[0]]]<.5)):
                raise ValueError('Source supports or anchor eligibility changed')
            if r['role']!='A':
                chosen=(p if double_source=='BASELINE' else q)[:2]
                r['support']=''.join('310'[i] for i in range(3) if i in chosen)
        part['tickets']=[dict(group=1,code=''.join(c),units=1)
            for c in itertools.product(*(r['support'] for r in legs))]
        if part['stake']!=unit_cny*len(part['tickets']) or part['stake']!=64:
            raise ValueError('Fixed unit funding required')
        part['double_source']=double_source
        part['seal']=stable_json_hash(part)
    if sum(p['stake'] for p in result['components'])!=plan['stake'] or plan['stake']>budget_cny:
        raise ValueError('Funding mismatch')
    result.update(double_source=double_source,source_plan_seal=plan['seal'],
        model_any_hit=None,historical_admission=False,budget=budget_cny,
        cash_cny=budget_cny-plan['stake'])
    return dict(**result,seal=stable_json_hash(result))
