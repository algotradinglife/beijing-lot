"""Independent NumPy replay of the R capital allocation arithmetic.

No selection, learning, actual labels or I/O. The common prefix-study checker
owns receipt/source validation; this module owns #425 domain invariants.
"""
import math
import numpy as np
import pandas as pd
from src.temporal_learning.core import stable_json_hash


def _capital_close(actual, expected, field, *, absolute=1e-12):
    """Reject missing, nonfinite or unequal replay values; preserve unsupported NA."""
    if expected is None:
        valid = actual is None
    elif isinstance(expected, str):
        valid = actual == expected
    else:
        valid = actual is not None and math.isfinite(actual) and math.isclose(
            actual, expected, rel_tol=1e-10, abs_tol=absolute)
    if not valid:
        raise ValueError(f"Capital replay mismatch: {field}")


def check_capital_plan(plan, worlds, config, source_bundle):
    """Rebuild ordered prefixes, physical tickets, exposure and shared-world P&L.

    Inputs use frozen prediction-only fixtures and explicit cutoff maps. CNY2
    tickets apply 0.65 exactly once. Reported optimality is conditional on the
    registered finite grid and solver gap; timed incumbents are only best found.
    Prefix boundary ties tolerate 1e-14 probability roundoff across R/NumPy;
    original ordered state identities and physical outcome permutations are exact.
    Returns counts; any inconsistent domain metric or constraint raises ValueError.
    """
    if plan['seal'] != stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):
        raise ValueError('Plan seal mismatch')
    if plan['cutoffs'] != source_bundle['cutoffs'] or plan['historical_admission'] is not False:
        raise ValueError('Capital cutoff/admission mismatch')
    if plan['issue'] != source_bundle['issue'] or worlds['seed'] != plan['seed']:
        raise ValueError('Capital issue/seed mismatch')
    arrays=[np.asarray(plan[key]) for key in ('fixture_indices','outcomes')]
    if any(a.size and a.dtype.kind not in 'iu' for a in arrays):
        raise ValueError('Integer physical coordinates required')
    ix,codes=[a.astype(int).reshape(-1,7) for a in arrays]
    n=len(ix);budget=plan['budget_cny'];stake=2*n
    if (ix.shape!=codes.shape or plan['groups']!=n or plan['stake']!=stake
        or budget not in config['budgets'] or budget%2 or stake>budget
        or plan['cash_cny']!=budget-stake or (plan['unit_cny'],plan['payout_factor'])!=(2,.65)):
        raise ValueError('Capital budget/shape mismatch')
    fixtures=plan['fixtures'];p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in fixtures])
    q=np.array([[f[f'q_{d}'] for d in 'WDL'] for f in fixtures])
    if (not np.isfinite(p).all() or not np.isfinite(q).all() or (p<0).any() or (q<=0).any()
        or not np.allclose(p.sum(axis=1),1,rtol=0,atol=1e-8)
        or not np.allclose(q.sum(axis=1),1,rtol=0,atol=1e-8)):
        raise ValueError('Capital probability contract mismatch')
    if (np.any(ix<0) or np.any(ix>=len(p)) or np.any(np.diff(ix,axis=1)<=0)
        or np.any(codes<0) or np.any(codes>2)
        or len(set(map(tuple,(3*ix+codes).tolist())))!=n):
        raise ValueError('Capital physical identity mismatch')
    keys=plan['sleeve_keys'];groups={g['id']:g['fixture_indices'] for g in source_bundle['sleeves']}
    if len(keys)!=plan['funded_sleeves'] or len({k['sleeve_id'] for k in keys})!=len(keys):
        raise ValueError('Capital sleeve count mismatch')
    canonical=np.indices((3,)*7).reshape(7,-1).T
    sets=[];cover=[];money=[];expected=0.;offset=0;exposure=np.zeros((len(p),3))
    for key in keys:
        f=np.asarray(key['fixture_indices']);ids=np.asarray(key['state_ids']);k=key['depth']
        if (f.dtype.kind not in 'iu' or ids.dtype.kind not in 'iu'
            or f.tolist()!=groups[key['sleeve_id']] or len(f)!=7 or len(set(f))!=7
            or len(ids)!=k or k<1 or k>2187 or len(set(ids))!=k
            or np.any(ids<0) or np.any(ids>=2187) or key['rule']!='PROB_PREFIX'):
            raise ValueError('Capital ordered prefix identity mismatch')
        order=np.argsort(f);part=canonical[ids][:,order]
        if (not np.array_equal(ix[offset:offset+k],np.tile(f[order],(k,1)))
            or not np.array_equal(codes[offset:offset+k],part)):
            raise ValueError('Capital ordered-to-physical permutation mismatch')
        offset+=k;sets.append(set(f));money.append(2*k)
        prob=np.prod(p[f,canonical],axis=1);values=1.3*np.prod(p[f,canonical]/q[f,canonical],axis=1)
        excluded=np.setdiff1d(np.arange(2187),ids)
        if np.any(np.diff(prob[ids])>1e-14) or (len(excluded) and min(prob[ids])+1e-14<max(prob[excluded])):
            raise ValueError('Capital states are not a probability prefix')
        mass=float(prob[ids].sum());gross=float(values[ids].sum());cover.append(mass);expected+=gross
        _capital_close(key['coverage'],mass,'sleeve coverage')
        _capital_close(key['expected_gross'],gross,'sleeve gross',absolute=1e-6)
        _capital_close(key['stake'],2*k,'sleeve stake')
        if plan['support_space']=='NONUNIFORM' and k not in config['depths']:
            raise ValueError('Capital depth outside registered grid')
        if plan['support_space'].startswith('DEPTH_') and k!=int(plan['support_space'][6:]):
            raise ValueError('Capital equal-depth mismatch')
        if plan['support_space'].startswith('TAU_'):
            tau=float(plan['support_space'][4:]);target=1-config['coverage_tolerance'] if tau==1 else tau
            if mass+1e-14<target or mass-prob[ids[-1]]>=target+1e-14:
                raise ValueError('Capital threshold is not minimally attained')
        for j in range(7):exposure[f[j]]+=2*np.bincount(canonical[ids,j],minlength=3)
    if offset!=n or len({tuple(sorted(s)) for s in sets})!=len(sets):
        raise ValueError('Capital unclaimed tickets or repeated physical sleeve')
    reuse=max((sum(i in s for s in sets) for i in range(len(p))),default=0)
    overlap=max((len(a&b) for j,a in enumerate(sets) for b in sets[:j]),default=0)
    if (not np.array_equal(exposure,np.asarray(plan['fixture_outcome_exposure_cny']))
        or not np.array_equal(exposure.sum(axis=1),plan['fixture_exposure_cny'])):
        raise ValueError('Capital monetary exposure mismatch')
    for field,val in [('max_reuse',reuse),('max_overlap',overlap),
        ('max_fixture_exposure_cny',float(exposure.sum(axis=1).max())),
        ('max_outcome_exposure_cny',float(exposure.max()))]:_capital_close(plan[field],val,field)
    status=plan['solver_status'];funded_status=('OPTIMAL_WITHIN_TOLERANCE','FEASIBLE_NOT_PROVEN')
    if n and status not in funded_status:raise ValueError('Capital unapproved funded incumbent')
    if status=='OPTIMAL_WITHIN_TOLERANCE' and plan['solver']['mip_gap']>config['gap']+1e-9:
        raise ValueError('Capital declared solver gap exceeded')
    pref=plan['preference']
    if status in funded_status:
        if ((pref['spend_all'] and stake!=budget) or expected<stake*(1+pref['minimum_roi'])-1e-7):
            raise ValueError('Capital funding/ROI preference violated')
    for kind in ('training','evaluation'):
        w=np.asarray(worlds[kind])
        if w.dtype.kind not in 'iu' or w.shape!=(config[f'{kind}_worlds'],len(p)) or np.any(w<0) or np.any(w>2):
            raise ValueError('Capital scenario shape mismatch')
        hits=np.zeros(len(w),dtype=int);gross=np.zeros(len(w))
        for key in keys:
            f=np.array(key['fixture_indices']);state=w[:,f]@(3**np.arange(6,-1,-1))
            won=np.isin(state,key['state_ids']);hits+=won
            gross[won]+=1.3/np.prod(q[f,w[won][:,f]],axis=1)
        net=gross-stake;win=net>1e-8;loss=net< -1e-8
        gain=float(net[win].mean()) if win.any() else None
        decline=float(net[loss].mean()) if loss.any() else None
        metrics=dict(sleeves=len(keys),distinct_fixture_count=len(set().union(*sets)),stake=stake,cash=budget-stake,
            expected_gross=expected,expected_net=expected-stake,expected_roi=expected/stake-1 if stake else None,
            any_hit=float((hits>0).mean()),at_least_two=float((hits>=2).mean()),zero_hit=float((hits==0).mean()),
            profit_probability=float(win.mean()),loss_probability=float(loss.mean()),zero_net_probability=float((~win&~loss).mean()),
            conditional_gain=gain,conditional_loss=decline,payoff_ratio=gain/abs(decline) if gain is not None and decline is not None else None,
            gain_support=int(win.sum()),loss_support=int(loss.sum()),simulation_worlds=len(w),
            payoff_support_status='BOTH_EVENTS_OBSERVED' if win.any() and loss.any() else 'INSUFFICIENT_CONDITIONAL_SUPPORT',
            simulated_expected_net=float(net.mean()),coverage_mean=float(np.mean(cover)) if cover else None,
            coverage_weighted_mean=float(np.dot(cover,money)/stake) if stake else None,
            coverage_median=float(np.median(cover)) if cover else None,
            coverage_min=min(cover) if cover else None,coverage_max=max(cover) if cover else None)
        for field,value in metrics.items():
            _capital_close(plan[kind][field],value,f'{kind}.{field}',absolute=1e-6 if field in
                ('expected_gross','expected_net','conditional_gain','conditional_loss','simulated_expected_net') else 1e-12)
        if kind=='training' and status in funded_status and metrics['any_hit']<pref['minimum_hit']-1e-9:
            raise ValueError('Capital hit preference violated')
    return dict(tickets=n,sleeves=len(keys),status='PASS')


def check_capital_result(result, source_bundle, config):
    """Check full0..2187 curves, exact selected-prefix trace and registered grid.

    Vectorized NumPy reconstruction is independent of the R cumulative-surface
    implementation. Per-plan constraints must equal their registered preference,
    not merely a looser self-reported constraint. No target labels are admitted.
    """
    if result['issue']!=source_bundle['issue'] or result['cutoffs']!=source_bundle['cutoffs']:
        raise ValueError('Capital result cutoff/issue mismatch')
    curves=pd.DataFrame(result['curves'])
    source={str(g['id']):g for g in source_bundle['sleeves']}
    if len(curves)!=2188*len(source) or set(curves.sleeve_id.astype(str))!=set(source):
        raise ValueError('Capital full-curve scope mismatch')
    fixtures=source_bundle['expanded_pool']['fixtures']
    p=np.array([[f[f'p_{d}'] for d in 'WDL'] for f in fixtures])
    q=np.array([[f[f'q_{d}'] for d in 'WDL'] for f in fixtures])
    canonical=np.indices((3,)*7).reshape(7,-1).T;rank_map={}
    for sid,rows in curves.groupby('sleeve_id',sort=False):
        z=rows.sort_values('depth');sid=str(sid)
        ids=z.state_id.to_numpy();depth=z.depth.to_numpy()
        if (not np.array_equal(depth,np.arange(2188)) or not np.isnan(ids[0])
            or not np.array_equal(np.sort(ids[1:]),np.arange(2187))):
            raise ValueError('Capital full-curve rank/depth mismatch')
        rank=ids[1:].astype(int);rank_map[sid]=rank
        f=np.array(source[sid]['fixture_indices']);prob=np.prod(p[f,canonical],axis=1)
        value=1.3*np.prod(p[f,canonical]/q[f,canonical],axis=1)
        if np.any(np.diff(prob[rank])>1e-14):raise ValueError('Capital curve rank is not descending')
        coverage=np.r_[0,np.cumsum(prob[rank])];gross=np.r_[0,np.cumsum(value[rank])]
        money=2*depth;net=gross-money
        expected=dict(stake=money,coverage=coverage,expected_gross=gross,expected_net=net,
            expected_roi=np.r_[np.nan,net[1:]/money[1:]],
            marginal_coverage=np.r_[prob[rank],np.nan],marginal_net=np.r_[value[rank]-2,np.nan])
        for field,values in expected.items():
            actual=z[field].to_numpy(dtype=float)
            tolerance=1e-6 if field in ('expected_gross','expected_net','marginal_net') else 1e-12
            if not np.allclose(actual,values,rtol=1e-10,atol=tolerance,equal_nan=True):
                raise ValueError(f'Capital full-curve arithmetic mismatch: {field}')
    prefs={}
    for budget in config['budgets']:
        for pref in config['preferences']:
            prefs[f"NONUNIFORM_{pref['name']}_B{budget}"]=('NONUNIFORM',pref)
        for tau in config['coverage_targets']:
            pool=f'TAU_{tau:g}'
            prefs[f'{pool}_ANY_B{budget}']=(pool,dict(name='ANY',objective='any_hit',minimum_roi=-1,
                minimum_hit=0,spend_all=False))
        for depth in config['equal_depths']:
            pool=f'DEPTH_{depth}'
            prefs[f'{pool}_ANY_B{budget}']=(pool,dict(name='ANY',objective='any_hit',minimum_roi=-1,
                minimum_hit=0,spend_all=budget%(2*depth)==0 and budget/(2*depth)<=len(source)))
    seen=set()
    for plan in result['plans']:
        key=(plan['seed'],plan['arm'])
        if key in seen or plan['arm'] not in prefs:raise ValueError('Capital result plan grid mismatch')
        seen.add(key);space,pref=prefs[plan['arm']]
        if plan['preference']!=pref or plan['support_space']!=space:
            raise ValueError('Capital registered preference mismatch')
        for key in plan['sleeve_keys']:
            if key['state_ids']!=rank_map[str(key['sleeve_id'])][:key['depth']].tolist():
                raise ValueError('Capital selected prefix differs from full-curve trace')
    if seen!={(seed,arm) for seed in config['seeds'] for arm in prefs}:
        raise ValueError('Capital result grid incomplete')
    return dict(curve_rows=len(curves),plans=len(result['plans']),status='PASS')


def check_capital_settlement(plan, audit_rows, result_row):
    """Independently settle by mutually exclusive sleeve states, not ticket rows.

    Only call after freeze. Audit records retain exact issue/slot/provider and
    handicap identities. Winning states use actual SP with one 0.65 factor.
    Losing-state missing SP is irrelevant; missing winning SP fails. Returns
    accounting totals and checks the authoritative evaluator's recorded result.
    """
    if plan['seal']!=stable_json_hash({k:v for k,v in plan.items() if k!='seal'}):
        raise ValueError('Settlement plan seal mismatch')
    audit={}
    for row in audit_rows:
        key=(str(row['issue']),row['slot'],row['provider_id'])
        if key in audit:raise ValueError('Duplicate settlement identity')
        audit[key]=row
    gross=0.;hits=0;directions={'W':0,'D':1,'L':2}
    for sleeve in plan['sleeve_keys']:
        state=0;quotes=[]
        for index in sleeve['fixture_indices']:
            f=plan['fixtures'][index];row=audit[(str(f['issue']),f['slot'],f['provider_id'])]
            if (f['handicap']!=row['handicap'] or row['actual_direction'] not in directions
                or not isinstance(row['status'],str) or 'spf:IDENTITY' in row['status']):
                raise ValueError('Settlement fixture conflict')
            state=3*state+directions[row['actual_direction']];quotes.append(row['spf_sp'])
        if state in sleeve['state_ids']:
            if any(q is None or not math.isfinite(q) or q<=0 for q in quotes):
                raise ValueError('Missing winning settlement SP')
            gross+=2*.65*math.prod(quotes);hits+=1
    expected=dict(stake=plan['stake'],groups=plan['groups'],hits=hits,gross=gross,
        net=gross-plan['stake'],roi=gross/plan['stake']-1 if plan['stake'] else None,
        status='COMPLETE' if plan['stake'] else 'NO_BET')
    for key,value in expected.items():_capital_close(result_row[key],value,f'settlement.{key}',absolute=1e-6)
    return expected
