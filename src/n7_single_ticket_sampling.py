"""Packed all-single N7 portfolios; fixed diagnostic sampling, no learning."""
import numpy as np
import pandas as pd
from scipy.special import softmax
from src.fundamentals_n7_baseline import rank_double_candidates
from src.temporal_learning.core import stable_json_hash


def single_ticket_plan(frame, *, cutoffs, seed, third_threshold, outcome_power,
                       fixture_power, max_attempts, budget_cny, unit_cny, payout_factor):
    """Seal packed single tickets: fixture row indices and WDL indices, both T x7.

    Exact frame: identities/handicap, calibrated p_W/D/L, raw market q_W/D/L.
    All fixtures eligible. Top2 original mass raised to fixture_power selects
    seven without replacement via Gumbel top-k (Plackett-Luce). Original third
    probability strictly below threshold is zeroed; remaining p**outcome_power
    normalized determines outcome sampling. Both powers positive, fractions for
    threshold; explicit seed/cutoffs. Gumbel weights do not alter true p or SP.
    Across tickets replacement allowed; complete fixture+outcome duplicates are
    rejected up to max_attempts. CNY2/ticket, budget1024; EV recorded only using
    original p and raw-market inverse q, one ticket-level .65. No labels or I/O.
    """
    required={'issue','slot','provider_id','handicap'}|{f'{k}_{d}' for k in 'pq' for d in 'WDL'}
    if (set(frame)!=required or type(seed) is not int or seed<0
            or type(max_attempts) is not int or max_attempts<1
            or not np.isfinite(third_threshold) or not 0<=third_threshold<=1
            or any(not np.isfinite(v) or v<=0 for v in (outcome_power,fixture_power))
            or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65)):
        raise ValueError('Explicit all-single sampling contract required')
    _,bound=rank_double_candidates(frame,cutoffs=cutoffs)
    x=frame.sort_values('slot').reset_index(drop=True);p=x[[f'p_{d}' for d in 'WDL']].to_numpy(float)
    q=x[[f'q_{d}' for d in 'WDL']].to_numpy(float)
    rank=np.argsort(-p,axis=1,kind='stable');top2=np.take_along_axis(p,rank[:,:2],axis=1).sum(axis=1)
    filtered=p.copy();third=rank[:,2];remove=p[np.arange(len(x)),third]<third_threshold
    filtered[np.where(remove)[0],third[remove]]=0
    with np.errstate(divide='ignore'):
        outcome_weights=softmax(outcome_power*np.log(filtered),axis=1)
    log_weight=fixture_power*np.log(top2)
    if not np.isfinite(outcome_weights).all() or not np.isfinite(log_weight).all():raise ValueError('Nonfinite sampling weights')
    rng=np.random.default_rng(seed);slots=[];directions=[];seen=set();attempts=0;duplicates=0
    while len(x)>=7 and len(slots)<budget_cny//unit_cny and attempts<max_attempts:
        size=min(128,max_attempts-attempts)
        noise=rng.gumbel(size=(size,len(x)))+log_weight
        chosen=np.argsort(-noise,axis=1,kind='stable')[:,:7]
        chosen.sort(axis=1)
        cumulative=outcome_weights[chosen].cumsum(axis=2);cumulative[:,:,-1]=1.
        outcomes=(rng.random((size,7,1))>=cumulative).sum(axis=2)
        for ids,codes in zip(chosen,outcomes):
            attempts+=1;key=tuple(zip(ids.tolist(),codes.tolist()))
            if key in seen:duplicates+=1;continue
            seen.add(key);slots.append(ids.tolist());directions.append(codes.tolist())
            if len(slots)==budget_cny//unit_cny:break
    idx=np.asarray(slots,dtype=int).reshape(-1,7);d=np.asarray(directions,dtype=int).reshape(-1,7)
    masses=np.prod(p[idx,d],axis=1);ev=payout_factor*np.prod(p[idx,d]/q[idx,d],axis=1)-1
    counts=np.bincount(idx.ravel(),minlength=len(x))
    plan=dict(issue=str(x.issue.iloc[0]),fixtures=x.to_dict('records'),fixture_indices=slots,outcomes=directions,
        cutoffs=bound,groups=len(slots),stake=unit_cny*len(slots),cash_cny=budget_cny-unit_cny*len(slots),
        budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor,attempts=attempts,duplicates=duplicates,
        mean_coverage=float(masses.mean()) if len(masses) else None,expected_roi=float(ev.mean()) if len(ev) else None,
        max_reuse=int(counts.max()),fixture_weights=softmax(log_weight).tolist(),outcome_weights=outcome_weights.tolist(),
        parameters=dict(seed=seed,third_threshold=third_threshold,outcome_power=outcome_power,fixture_power=fixture_power,max_attempts=max_attempts),
        historical_admission=False,mode='EXPOSED_FIXTURE_RELATIVE_REVIEW_NOT_SIMULTANEOUS_TICKET')
    return dict(plan,seal=stable_json_hash(plan))


def settle_single_tickets(plan, audit):
    """Vectorized unit-ticket equivalent of settle_n7_baseline; no database writes.

    Audit unique issue/slot/provider/handicap, actual WDL, status, SPF SP. Identity
    conflicts or missing outcomes on used fixtures fail closed; missing winning
    SP leaves unknown returns. Unused fixtures cannot change settlement. Pending
    or zero-bet semantics match the authoritative component interface. Seals and
    packed shapes validated; duplicate complete tickets rejected.
    """
    if plan.get('seal')!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):raise ValueError('Plan changed')
    idx=np.asarray(plan['fixture_indices'],dtype=int).reshape(-1,7)
    codes=np.asarray(plan['outcomes'],dtype=int).reshape(-1,7)
    if (idx.shape!=codes.shape or len(idx)!=plan['groups'] or np.any(idx<0) or np.any(idx>=len(plan['fixtures']))
            or np.any(codes<0) or np.any(codes>2) or plan['stake']!=2*len(idx)
            or (plan['budget_cny'],plan['unit_cny'],plan['payout_factor'])!=(1024,2,.65)
            or plan['cash_cny']+plan['stake']!=1024 or plan['cash_cny']<0
            or np.any(np.diff(idx,axis=1)<=0)
            or len({tuple(zip(i,d)) for i,d in zip(idx,codes)})!=len(idx)):
        raise ValueError('Invalid packed tickets')
    result=dict(issue=plan['issue'],stake=plan['stake'],groups=len(idx),cash=plan['cash_cny'])
    if not len(idx):return dict(result,status='NO_BET',gross=0.,net=0.,hits=0,roi=None)
    if audit.duplicated(['issue','slot','provider_id']).any():raise ValueError('Duplicate audit identities')
    used=np.unique(idx);f=pd.DataFrame(plan['fixtures']).iloc[used].copy();f['packed_index']=used
    joined=f.merge(audit,on=['issue','slot','provider_id'],how='left',validate='one_to_one',suffixes=('','_audit'))
    if (not joined.actual_direction.isin(list('WDL')).all() or joined.status.isna().any()
            or joined.status.str.contains('spf:IDENTITY',regex=False).any() or not joined.handicap.eq(joined.handicap_audit).all()):
        return dict(result,status='PENDING_AUDIT',gross=None,net=None,hits=None,roi=None)
    actual=np.full(len(plan['fixtures']),-1);sp=np.full(len(plan['fixtures']),np.nan)
    actual[joined.packed_index]=joined.actual_direction.map(dict(W=0,D=1,L=2));sp[joined.packed_index]=joined.spf_sp
    won=np.all(actual[idx]==codes,axis=1);winning_sp=sp[idx[won]]
    if not np.isfinite(winning_sp).all() or (winning_sp<=0).any():
        return dict(result,status='PENDING_WINNING_SP',gross=None,net=None,hits=None,roi=None)
    gross=float((plan['unit_cny']*plan['payout_factor']*np.prod(winning_sp,axis=1)).sum())
    return dict(result,status='COMPLETE',gross=gross,net=gross-plan['stake'],hits=int(won.sum()),roi=gross/plan['stake']-1)
