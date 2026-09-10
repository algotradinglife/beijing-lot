"""Fixed diagnostic portfolio objective; no historical fitting or settlement input."""
import math
import numpy as np
from scipy.optimize import linear_sum_assignment
from src.temporal_learning import Cutoff


def optimize_seven_ev(rows, *, cutoffs, owner_exception, n, unit_cny,
                      budget_cny, main_multiples, payout_factor, tolerance=1e-8):
    """Maximize 6*product(main_factor)+weighted protection_factor over seven.

    Rows: unique issue/slot/provider_id, main_factor=sum(p_model/SP_probability)
    across the two nominated directions, protection_factor=p_model/q_market for
    the nominated BF option. No actual outcomes or realized SP are read. Factors
    must be positive/finite (protection may be zero). Explicit per-fixture shared
    Cutoff objects bind this authorized retrospective, multi-clock diagnostic.
    No prospective admission is implied. Returns selected identities, cash
    expectations and the supported-frontier witness ledger; no I/O or caches.

    log(product) plus protection is a 2D projection of seven-item assignments.
    A convex increasing objective reaches its maximum on the upper hull. Each
    support query is SciPy's rectangular assignment (2 bonus/5 regular slots).
    Recursive chord separation enumerates that hull, not all n-choose-7 subsets.
    Tolerance is an absolute support-value numerical tolerance, not a fit policy.
    """
    if owner_exception!='OWNER_AUTHORIZED_HISTORICAL_RETURNS':
        raise ValueError('Explicit historical diagnostic authorization required')
    if (n,unit_cny,budget_cny,main_multiples,payout_factor)!=(7,2,1024,3,.65):
        raise ValueError('Explicit fixed business constants required')
    if not math.isfinite(tolerance) or tolerance<=0:raise ValueError('Positive tolerance required')
    fields=('issue','slot','provider_id','main_factor','protection_factor')
    rows=sorted(({k:r[k] for k in fields} for r in rows),key=lambda r:(r['slot'],r['provider_id']))
    issues={r['issue'] for r in rows};ids=[r['provider_id'] for r in rows];slots=[r['slot'] for r in rows]
    if len(rows)<n or len(issues)!=1 or len(set(ids))!=len(rows) or len(set(slots))!=len(rows):
        raise ValueError('At least seven unique matches in one issue required')
    issue=next(iter(issues))
    for r in rows:
        c=cutoffs.get(str(r['slot']))
        if not isinstance(c,Cutoff) or c.kind!='DECISION_EPOCH' or c.target_issue!=issue:
            raise ValueError('Matching explicit fixture cutoffs required')
    a=np.array([r['main_factor'] for r in rows],dtype=float)
    b=np.array([r['protection_factor'] for r in rows],dtype=float)
    if not np.isfinite(a).all() or not np.isfinite(b).all() or (a<=0).any() or (b<0).any():
        raise ValueError('Finite positive main and nonnegative protection factors required')
    logs=np.log(a)
    main_stake=(2**n)*unit_cny*main_multiples
    units=(budget_cny-main_stake)//unit_cny
    normal=(units//n)*unit_cny;bonus=units%n
    weights=np.array([normal+unit_cny]*bonus+[normal]*(n-bonus))

    def point(indices):
        selected=sorted(map(int,indices),key=lambda i:(-b[i],rows[i]['slot'],rows[i]['provider_id']))
        log_main=float(sum(logs[i] for i in selected))
        protection=float(sum(weights[j]*b[i] for j,i in enumerate(selected)))
        main=unit_cny*main_multiples*math.exp(log_main)
        if not math.isfinite(main+protection):raise ValueError('Nonfinite expected payout')
        return dict(indices=selected,log_main=log_main,protection=protection,
                    expected_gross=payout_factor*(main+protection))

    def support(slope):
        cost=slope*logs[None,:]+weights[:,None]*b[None,:]
        _,columns=linear_sum_assignment(cost,maximize=True)
        return point(columns)

    left=point(sorted(range(len(rows)),key=lambda i:(-b[i],-logs[i],rows[i]['slot']))[:n])
    right=point(sorted(range(len(rows)),key=lambda i:(-logs[i],-b[i],rows[i]['slot']))[:n])
    vertices={tuple(sorted(left['indices'])):left,tuple(sorted(right['indices'])):right}
    pending=[(left,right)];ledger=[]
    while pending:
        lo,hi=pending.pop()
        distance=hi['log_main']-lo['log_main']
        if distance<=0:continue
        slope=(lo['protection']-hi['protection'])/distance
        q=support(slope)
        gap=(slope*q['log_main']+q['protection'])-(slope*lo['log_main']+lo['protection'])
        ledger.append(dict(slope=slope,support_gap=gap,slots=[rows[i]['slot'] for i in q['indices']]))
        key=tuple(sorted(q['indices']))
        if gap<=tolerance:continue
        if key in vertices or not lo['log_main']<q['log_main']<hi['log_main']:
            raise ValueError('Unresolved numerical frontier; do not claim optimality')
        vertices[key]=q;pending.extend([(lo,q),(q,hi)])
        if len(ledger)>10000:raise ValueError('Frontier limit exceeded')
    best=max(vertices.values(),key=lambda q:(q['expected_gross'],tuple(-rows[i]['slot'] for i in q['indices'])))
    selected=[dict(rows[i],protection_stake=int(weights[j])) for j,i in enumerate(best['indices'])]
    return dict(selected=selected,expected_gross=best['expected_gross'],
        expected_net=best['expected_gross']-budget_cny,expected_roi=best['expected_gross']/budget_cny-1,
        frontier=[dict(log_main=q['log_main'],protection=q['protection'],expected_gross=q['expected_gross'],
                       slots=[rows[i]['slot'] for i in q['indices']]) for q in vertices.values()],
        support_ledger=ledger,receipt=dict(owner_exception=owner_exception,historical_admission=False,
        cutoff_times={str(r['slot']):cutoffs[str(r['slot'])].cutoff_ts.isoformat() for r in rows},
        market_clock_policy='FIXTURE_RELATIVE_DIAGNOSTIC_NOT_COMMON_TICKET_EPOCH',
        input_rows=rows,n=n,unit_cny=unit_cny,budget_cny=budget_cny,main_multiples=main_multiples,
        payout_factor=payout_factor,tolerance=tolerance,method='CONVEX_UPPER_HULL_SCIPY_ASSIGNMENT'))
