"""Deterministic candidate search and probability-gated single-ticket allocation."""
import numpy as np
import pandas as pd
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def probability_gate_candidates(frame, *, cutoffs, n, depth, tradeoffs):
    """Return sealed, label-free candidate pool, with exact top-depth scalar ranks.

    Frame columns: issue/slot/provider_id/handicap and normalized p_W/D/L,
    q_W/D/L; q strictly positive. p is calibrated market, q raw mapped market.
    Explicit native fixture cutoffs; n=7; integer depth>=1. tradeoffs contains
    distinct finite nonnegative numbers and/or 'PROBABILITY'. Numeric lambda
    scores sum(log(p/q) + lambda*log(p)); PROBABILITY scores sum(log(p)).
    Dynamic programming keeps the top depth partial tickets per cardinality
    after each fixture. Each scalar ranking is exact up to floating precision;
    the union is only an approximate candidate pool for constrained EV ranking.
    Ties use lexicographic fixture/outcome codes. Zero-p outcomes are excluded.
    No I/O, fitting, source admission or settlement. Packed codes are 3*row+WDL.
    Empty ticket universe (<7 fixtures) returns an empty, sealed pool.
    """
    required={'issue','slot','provider_id','handicap'}|{f'{k}_{d}' for k in 'pq' for d in 'WDL'}
    if (set(frame)!=required or n!=7 or type(depth) is not int or depth<1
            or not tradeoffs or len(set(tradeoffs))!=len(tradeoffs)
            or any(t!='PROBABILITY' and (not isinstance(t,(int,float)) or not np.isfinite(t) or t<0) for t in tradeoffs)):
        raise ValueError('Explicit candidate-search contract required')
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=frame.sort_values('slot').reset_index(drop=True)
    p=x[[f'p_{d}' for d in 'WDL']].to_numpy(float)
    q=x[[f'q_{d}' for d in 'WDL']].to_numpy(float)
    with np.errstate(divide='ignore'):
        lp=np.log(p);lr=lp-np.log(q)
    union={}
    for tradeoff in tradeoffs:
        score=lp if tradeoff=='PROBABILITY' else lr+tradeoff*lp if tradeoff else lr
        # (scores, encoded tickets), cardinality zero has one empty prefix.
        states=[(np.zeros(1),np.empty((1,0),dtype=int))]+[(np.empty(0),np.empty((0,k),dtype=int)) for k in range(1,n+1)]
        for i in range(len(x)):
            for k in range(min(n,i+1),0,-1):
                old_s,old_t=states[k];prev_s,prev_t=states[k-1]
                ss=[old_s];tt=[old_t]
                for d in range(3):
                    if not np.isfinite(score[i,d]):continue
                    ss.append(prev_s+score[i,d])
                    tt.append(np.column_stack((prev_t,np.full(len(prev_s),3*i+d,dtype=int))))
                scores=np.concatenate(ss);tickets=np.concatenate(tt)
                # Last lexsort key is primary: score, then earliest encoded leg.
                order=np.lexsort(tuple(tickets[:,j] for j in range(k-1,-1,-1))+(-scores,))[:depth]
                states[k]=(scores[order],tickets[order])
        for rank,ticket in enumerate(states[n][1],1):
            key=tuple(int(c) for c in ticket)
            union[key]=min(union.get(key,rank),rank)
    keys=sorted(union)
    pool=dict(issue=str(x.issue.iloc[0]),fixtures=x.to_dict('records'),cutoffs=bound,
        encoded_tickets=[list(t) for t in keys],minimum_scalar_rank=[union[t] for t in keys],
        parameters=dict(n=n,depth=depth,tradeoffs=list(tradeoffs)),
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET')
    return dict(pool,seal=stable_json_hash(pool))


def select_probability_gate(pool, *, cutoffs, min_probability, ranking, search_depth,
                            budget_cny, unit_cny, payout_factor):
    """Seal N7 single tickets after inclusive probability gate, CNY2 each.

    ranking EV: positive estimated EV only, descending EV then probability.
    PROB_POS: same eligible tickets, descending probability then EV.
    PROB: probability order including negative EV (controlled comparator).
    EV=.65*product(original p/raw q)-1; powers never treated as true p.
    Exact unit-cost allocation optimum within the frozen candidate universe,
    not claimed globally optimal across all fixture/outcome combinations.
    No duplicate complete tickets; no fixture reuse limit across tickets.
    Missing cutoffs, tampered pool, invalid threshold/parameters fail closed.
    Returns packed settlement-compatible plan, eligible counts, expected net,
    original probabilities and the candidate-pool seal; no I/O or labels.
    """
    if pool.get('seal')!=stable_json_hash({k:v for k,v in pool.items() if k!='seal'}):raise ValueError('Candidate pool changed')
    if (not np.isfinite(min_probability) or not 0<=min_probability<=1
            or ranking not in ('EV','PROB_POS','PROB')
            or type(search_depth) is not int or not 1<=search_depth<=pool['parameters']['depth']
            or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)):
        raise ValueError('Explicit probability-gate allocation contract required')
    f=pd.DataFrame(pool['fixtures']);_,bound=rank_double_candidates(f,cutoffs=cutoffs)
    if bound!=pool['cutoffs']:raise ValueError('Cutoff mismatch')
    encoded=np.asarray(pool['encoded_tickets'],dtype=int).reshape(-1,7)
    keep=np.asarray(pool['minimum_scalar_rank'])<=search_depth
    encoded=encoded[keep];idx=encoded//3;codes=encoded%3
    p=f[[f'p_{d}' for d in 'WDL']].to_numpy(float);q=f[[f'q_{d}' for d in 'WDL']].to_numpy(float)
    mass=np.prod(p[idx,codes],axis=1)
    ev=payout_factor*np.prod(p[idx,codes]/q[idx,codes],axis=1)-1
    if not np.isfinite(ev).all():raise ValueError('Nonfinite estimated return')
    gated=mass>=min_probability;positive=gated & (ev>0)
    eligible=positive if ranking!='PROB' else gated
    ids=np.flatnonzero(eligible)
    # Pool rows already canonical. Stable row index is final tie-break.
    primary,secondary=(ev,mass) if ranking=='EV' else (mass,ev)
    order=ids[np.lexsort((ids,-secondary[ids],-primary[ids]))][:budget_cny//unit_cny]
    chosen_i=idx[order];chosen_d=codes[order]
    count=np.bincount(chosen_i.ravel(),minlength=len(f))
    plan=dict(issue=pool['issue'],fixtures=pool['fixtures'],cutoffs=bound,
        fixture_indices=chosen_i.tolist(),outcomes=chosen_d.tolist(),groups=len(order),
        stake=unit_cny*len(order),cash_cny=budget_cny-unit_cny*len(order),
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,
        mean_coverage=float(mass[order].mean()) if len(order) else None,
        expected_roi=float(ev[order].mean()) if len(order) else None,
        expected_net=float(unit_cny*ev[order].sum()),
        min_selected_probability=float(mass[order].min()) if len(order) else None,
        candidate_count=len(encoded),gated_count=int(gated.sum()),positive_count=int(positive.sum()),
        max_reuse=int(count.max()),pool_seal=pool['seal'],
        parameters=dict(min_probability=min_probability,ranking=ranking,search_depth=search_depth),
        historical_admission=False,mode=pool['mode'])
    return dict(plan,seal=stable_json_hash(plan))
