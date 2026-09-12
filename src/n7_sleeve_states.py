"""Full-state seven-fixture sleeve contracts and cardinality-constrained selection."""
import warnings
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def enumerate_sleeve(frame, *, cutoffs, unit_cny, payout_factor):
    """Enumerate 2187 mutually exclusive WDL states for exactly seven fixtures.

    Input identity/handicap and normalized p/q triplets, native cutoff per slot.
    Rows sort by slot; state codes0/1/2 map W/D/L (official3/1/0). Returns sealed
    states, modeled probabilities, estimated complete-ticket CNY payout and
    expected contribution. q-inverse payout is a diagnostic proxy, not official SP.
    CNY2 and one .65 ticket factor explicit. No I/O/labels/fit; invalid inputs stop.
    """
    required={'issue','slot','provider_id','handicap'}|{f'{k}_{d}' for k in 'pq' for d in 'WDL'}
    if set(frame)!=required or len(frame)!=7 or (unit_cny,payout_factor)!=(2,.65):
        raise ValueError('Exactly seven fixtures and explicit CNY2/.65 required')
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=frame.sort_values('slot').reset_index(drop=True)
    states=np.indices((3,)*7).reshape(7,-1).T
    p=x[[f'p_{d}' for d in 'WDL']].to_numpy(float);q=x[[f'q_{d}' for d in 'WDL']].to_numpy(float)
    mass=np.prod(p[np.arange(7),states],axis=1)
    payout=unit_cny*payout_factor/np.prod(q[np.arange(7),states],axis=1)
    if not np.isclose(mass.sum(),1,atol=1e-8,rtol=0) or not np.isfinite(payout).all():
        raise ValueError('Invalid state mass or estimated payout')
    out=dict(issue=str(x.issue.iloc[0]),fixtures=x.to_dict('records'),cutoffs=bound,
        states=states.tolist(),probability=mass.tolist(),estimated_payout=payout.tolist(),
        expected_contribution=(mass*payout).tolist(),unit_cny=unit_cny,payout_factor=payout_factor,
        price_lane='DIAGNOSTIC_MARKET_INVERSE_Q_NOT_OFFICIAL_SP',historical_admission=False)
    return dict(out,seal=stable_json_hash(out))


def select_sleeve_states(enumeration, *, cutoffs, kind, ticket_count, minimum_coverage,
                         minimum_roi, seed, hamming_minimum, solver_seconds, solver_relative_gap, solver_feasibility_tolerance):
    """Select exactly64 distinct states or return explicit INFEASIBLE/SOLVER_LIMIT.

    Kinds TOP64_PROB/TOP64_VALUE/RANDOM64/DIVERSITY/FRONTIER. Only FRONTIER applies
    supplied coverage and ROI floors (other kinds require None floors). FRONTIER
    uses SciPy/HiGHS MILP with exact cardinality, coverage and expected-gross floors.
    Solver success within the explicit relative gap required; timeout/nonoptimal result is fail-closed, even
    if an incumbent exists. Canonical state order and deterministic solver retained.
    DIVERSITY greedily selects by p then value under an explicit minimum Hamming
    distance. Controls stable-tie by state index. Returns selector receipt including
    solver status/gap, candidate source seal, cutoff, all parameters, and diagnostics.
    No I/O, target labels, historical tuning or causal admission.
    """
    e=enumeration
    if e.get('seal')!=stable_json_hash({k:v for k,v in e.items() if k!='seal'}):raise ValueError('State artifact changed')
    _,bound=rank_double_candidates(pd.DataFrame(e['fixtures']),cutoffs=cutoffs)
    if bound!=e['cutoffs'] or ticket_count!=64 or kind not in ('TOP64_PROB','TOP64_VALUE','RANDOM64','DIVERSITY','FRONTIER'):
        raise ValueError('Invalid state selection/cutoff contract')
    if (type(seed) is not int or seed<0 or type(hamming_minimum) is not int or not 1<=hamming_minimum<=7
        or not np.isfinite(solver_seconds) or solver_seconds<=0
        or not np.isfinite(solver_relative_gap) or not 0<=solver_relative_gap<=.01
        or not np.isfinite(solver_feasibility_tolerance) or not 1e-10<=solver_feasibility_tolerance<=1e-9):raise ValueError('Explicit seed/diversity/solver settings required')
    if kind=='FRONTIER':
        if minimum_coverage is None or minimum_roi is None or not np.isfinite(minimum_coverage) or not 0<=minimum_coverage<=1 or not np.isfinite(minimum_roi) or minimum_roi < -1:
            raise ValueError('Explicit feasible-range frontier floors required')
    elif minimum_coverage is not None or minimum_roi is not None:raise ValueError('Controls cannot silently ignore floors')
    p=np.asarray(e['probability']);v=np.asarray(e['expected_contribution']);states=np.asarray(e['states']);ids=np.arange(2187)
    prob_order=np.lexsort((ids,-v,-p));value_order=np.lexsort((ids,-p,-v));chosen=[];status='COMPLETE';solver={}
    if kind=='TOP64_PROB':chosen=prob_order[:64].tolist()
    elif kind=='TOP64_VALUE':chosen=value_order[:64].tolist()
    elif kind=='RANDOM64':chosen=np.random.default_rng(seed).choice(2187,64,replace=False).tolist()
    elif kind=='DIVERSITY':
        for i in prob_order:
            if not chosen or np.all(np.sum(states[chosen]!=states[i],axis=1)>=hamming_minimum):chosen.append(int(i))
            if len(chosen)==64:break
        if len(chosen)!=64:chosen=[];status='INFEASIBLE'
    else:
        floor_gross=128*(1+minimum_roi)
        if p[prob_order[:64]].sum()+1e-10<minimum_coverage or v[value_order[:64]].sum()+1e-8<floor_gross:
            status='INFEASIBLE'
        else:
            scale=max(1.,float(v.max()))
            probability_scale=max(minimum_coverage,1e-6);gross_scale=max(floor_gross,1.)
            # SciPy forwards the supported HiGHS tolerance option verbatim; its
            # forwarding notice is expected, while other warnings remain visible.
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',message='Unrecognized options detected:.*mip_feasibility_tolerance.*',category=RuntimeWarning)
                solution=milp(c=-v/scale,integrality=np.ones(2187),bounds=Bounds(0,1),
                    constraints=LinearConstraint(np.vstack((np.ones(2187),p/probability_scale,v/gross_scale)),
                        [64,minimum_coverage/probability_scale,floor_gross/gross_scale],[64,np.inf,np.inf]),
                    options=dict(time_limit=float(solver_seconds),mip_rel_gap=solver_relative_gap,
                        mip_feasibility_tolerance=solver_feasibility_tolerance,presolve=True))
            solver=dict(status=int(solution.status),message=str(solution.message),
                gap=float(solution.mip_gap) if getattr(solution,'mip_gap',None) is not None else None)
            if solution.status!=0:status='INFEASIBLE' if solution.status==2 else 'SOLVER_LIMIT'
            else:
                chosen=np.flatnonzero(solution.x>.5).tolist()
                if len(chosen)!=64 or p[chosen].sum()+1e-8<minimum_coverage or v[chosen].sum()+1e-6<floor_gross:
                    raise ValueError(f'Solver result fails explicit state contract: count={len(chosen)}, coverage_gap={p[chosen].sum()-minimum_coverage}, gross_gap={v[chosen].sum()-floor_gross}')
    chosen=sorted(chosen);distances=[]
    if chosen:
        aa=states[chosen];distances=np.sum(aa[:,None,:]!=aa[None,:,:],axis=2)[np.triu_indices(64,1)]
    out=dict(enumeration_seal=e['seal'],cutoffs=bound,status=status,state_ids=chosen,
        coverage=float(p[chosen].sum()),expected_gross=float(v[chosen].sum()),
        expected_roi=float(v[chosen].sum()/128-1) if chosen else None,
        min_probability=float(p[chosen].min()) if chosen else None,median_probability=float(np.median(p[chosen])) if chosen else None,
        max_probability=float(p[chosen].max()) if chosen else None,
        minimum_hamming=int(np.min(distances)) if chosen else None,mean_hamming=float(np.mean(distances)) if chosen else None,
        parameters=dict(kind=kind,ticket_count=ticket_count,minimum_coverage=minimum_coverage,minimum_roi=minimum_roi,
            seed=seed,hamming_minimum=hamming_minimum,solver_seconds=solver_seconds,solver_relative_gap=solver_relative_gap,solver_feasibility_tolerance=solver_feasibility_tolerance),solver=solver,historical_admission=False)
    return dict(out,seal=stable_json_hash(out))
