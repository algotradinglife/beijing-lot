"""Sequential probability-optimal N7 additions with bounded fixture overlap."""
from collections import Counter
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from src.fundamentals_n7_baseline import rank_double_candidates,n7_baseline_plan
from src.fundamentals_n67_overlay import overlay_any_hit
from src.temporal_learning.core import stable_json_hash


def n7_addon_plan(frame, *, cutoffs, additions, max_groups, max_overlap, max_exposure,
                  unit_cny, payout_factor, allocation_seed):
    """Seal unchanged concentrated base plus 0/1/2 sequential optimal extra groups.

    All eligible input fixtures compete; maximize sum(log Top2 coverage), hence
    individual group hit probability under independent fixtures. Each new group
    has exactly7 slots, overlaps each existing group <=3, each slot used <=2.
    ADD2 preserves ADD1, then optimizes only the second group; not a joint optimum.
    SciPy/HiGHS MILP with zero relative gap and30s limit: infeasible stops additions,
    other nonoptimal termination raises. Solver objective/status enter the receipt.
    Native cutoffs validated by shared API; no outcome inputs, fit or side effects.
    """
    if additions not in [0,1,2] or (max_groups,max_overlap,max_exposure,unit_cny,payout_factor)!=(6,3,2,2,.65):
        raise ValueError('Explicit fixed business constants required')
    x,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=x.sort_values(['coverage','slot','provider_id'],ascending=[False,True,True],kind='stable')
    kw=dict(selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=max_groups,
            unit_cny=unit_cny,group_budget_cny=432,payout_factor=payout_factor,allocation_seed=allocation_seed)
    base=n7_baseline_plan(frame,cutoffs=cutoffs,**kw);parts=[base];steps=[]
    events=[{r['slot'] for r in base['legs'] if r['group']==g} for g in range(1,base['groups']+1)]
    for step in range(additions if base['groups'] else 0):
        used=Counter(s for e in events for s in e)
        matrix=np.array([[1]*len(x)]+[[int(s in e) for s in x.slot] for e in events],dtype=float)
        result=milp(c=-np.log(x.coverage.to_numpy()),integrality=np.ones(len(x)),
            bounds=Bounds(np.zeros(len(x)),np.array([int(used[s]<max_exposure) for s in x.slot])),
            constraints=LinearConstraint(matrix,[7]+[-np.inf]*len(events),[7]+[max_overlap]*len(events)),
            options={'time_limit':30.,'mip_rel_gap':0.})
        if result.status==2:
            steps.append(dict(step=step+1,status='INFEASIBLE'));break
        if result.status!=0 or result.x is None or not np.isfinite(result.mip_gap) or result.mip_gap!=0:raise RuntimeError('Optimal addon not certified: '+result.message)
        chosen=x.loc[result.x>.5];slots=set(chosen.slot)
        if len(slots)!=7 or any(len(slots&e)>max_overlap for e in events) or any(used[s]>=max_exposure for s in slots):
            raise RuntimeError('Solver contract failure')
        sub=frame[frame.slot.isin(slots)]
        parts.append(n7_baseline_plan(sub,cutoffs={str(s):cutoffs[str(s)] for s in slots},**kw))
        steps.append(dict(step=step+1,status='OPTIMAL',objective_log_probability=float(np.log(chosen.coverage).sum()),
            hit_probability=float(chosen.coverage.prod()),mip_gap=float(result.mip_gap)))
        events.append(slots)
    plan=dict(issue=base['issue'],strategy=['BASE','ADD1','ADD2'][additions],funding='UNIT',components=parts,
        stake=sum(p['stake'] for p in parts),budget=sum(p['stake'] for p in parts),model_any_hit=overlay_any_hit(parts),
        cutoffs=bound,requested_additions=additions,actual_additions=len(parts)-1,max_overlap=max_overlap,
        max_exposure=max_exposure,solver_steps=steps,candidate_scope='ALL_ELIGIBLE',
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_RETROSPECTIVE_NOT_SIMULTANEOUS')
    plan['seal']=stable_json_hash(plan)
    return plan
