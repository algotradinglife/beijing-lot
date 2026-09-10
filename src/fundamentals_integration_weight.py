"""Decision-layer weight routing over frozen expert probabilities and market SP."""
from numbers import Real
import numpy as np
import pandas as pd
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def select_integration_weights(candidates, *, cutoffs, mode, penalty, fixed_weight=None):
    """Choose a weight per fixture; never fit experts or read settlement.

    candidates: one row per issue/slot/provider_id/weight, with projected p_WDL
    and FIXED market q_WDL. SP proxy is 1/q. Objective is expected gross factor
    per selected double divided by two, minus penalty*weight**2. The single
    ticket payout factor is applied by the portfolio implementation, not here.
    Top2 directions remain probability-ranked. This is local routing, not a
    claim to globally maximize portfolio return. Missing/invalid values fail.
    cutoffs: issue -> original slot -> shared Cutoff object. Returns selected rows
    plus a sealed parameter/input/cutoff receipt; no I/O or mutation.
    """
    if mode not in {'FIXED','EXPECTED_RETURN'} or not isinstance(penalty,Real) or isinstance(penalty,bool) or not np.isfinite(penalty) or penalty<0:
        raise ValueError('Explicit routing mode and nonnegative penalty required')
    if mode=='FIXED' and (not isinstance(fixed_weight,Real) or isinstance(fixed_weight,bool) or not 0<=fixed_weight<=1):
        raise ValueError('Explicit fixed weight required')
    keys=['issue','slot','provider_id'];columns=keys+['weight']+[prefix+d for prefix in ['p_','q_'] for d in 'WDL']
    if set(candidates.columns)!=set(columns) or candidates.empty or candidates[columns].isna().any().any() or candidates.duplicated(keys+['weight']).any():
        raise ValueError('Exact label-free unique candidate schema required')
    if any(not isinstance(v,str) or not v for col in ['issue','provider_id'] for v in candidates[col]):raise ValueError('String issue and provider IDs required')
    if any(isinstance(v,(bool,np.bool_)) for v in candidates.weight):raise ValueError('Numeric weights required')
    frame=candidates.copy()
    values=frame[[prefix+d for prefix in ['p_','q_'] for d in 'WDL']].to_numpy(float)
    if not np.isfinite(values).all() or (values<0).any() or (values[:,3:]<=0).any() or not np.allclose(values[:,:3].sum(axis=1),1,atol=1e-9) or not np.allclose(values[:,3:].sum(axis=1),1,atol=1e-9):
        raise ValueError('Normalized finite probabilities and positive market required')
    if not frame.weight.between(0,1).all():raise ValueError('Weight outside [0,1]')
    selected=[];clocks={}
    for key,g in frame.groupby(keys,sort=True):
        issue,slot,provider=key
        if type(slot) not in (int,np.int64) or slot<1:raise ValueError('Native positive slot required')
        cutoff=cutoffs[issue][str(slot)]
        if not isinstance(cutoff,Cutoff) or cutoff.target_issue!=issue:raise ValueError('Explicit matching Cutoff object required')
        clocks[f'{issue}/{slot}/{provider}']=cutoff.cutoff_ts.isoformat()
        q=g[['q_'+d for d in 'WDL']].to_numpy(float)
        if not np.allclose(q,q[0],rtol=0,atol=1e-12):raise ValueError('Market SP must not vary with weight')
        z=g.copy();p=z[['p_'+d for d in 'WDL']].to_numpy(float)
        order=np.argsort(-p,axis=1,kind='stable')[:,:2]
        ratio=p/q
        z['expected_double_factor']=np.take_along_axis(ratio,order,axis=1).sum(axis=1)/2
        z['objective']=z.expected_double_factor-penalty*z.weight**2
        if mode=='FIXED':z=z[z.weight==fixed_weight]
        if z.empty:raise ValueError('Fixed weight absent')
        selected.append(z.sort_values(['objective','weight'],ascending=[False,True],kind='stable').iloc[0].to_dict())
    receipt=dict(mode=mode,penalty=float(penalty),fixed_weight=fixed_weight,cutoffs=clocks,
        input_hash=stable_json_hash(frame.to_json(orient='records')),objective='LOCAL_DOUBLE_EXPECTED_FACTOR_MINUS_WEIGHT_SQUARED',sp_proxy='ONE_OVER_FIXED_MARKET_Q',historical_admission=False)
    return dict(rows=selected,receipt=receipt,seal=stable_json_hash(dict(rows=selected,receipt=receipt)))


def select_integration_penalty(history, cutoff, *, penalties, minimum_issues, repository_root, source_hashes):
    """Select a penalty from prior validation-issue returns via shared chronology.

    One row per issue; required availability columns plus net_<index> for each
    explicit candidate. Scores total net on this fixed-budget validation cohort;
    ties prefer the larger penalty. Returns a shared receipt plus chosen value.
    Historical proxy only. No training, imputation, or target-period labels.
    """
    from src.temporal_learning import AvailabilityFilter, AvailabilityPolicy, PartitionPolicy, WeightingPolicy, prepare_learning_context
    if not isinstance(cutoff,Cutoff) or not isinstance(penalties,(list,tuple)) or not penalties or any(not isinstance(p,Real) or isinstance(p,bool) or not np.isfinite(p) or p<0 for p in penalties) or len(set(penalties))!=len(penalties):
        raise ValueError('Explicit cutoff and finite unique penalties required')
    if type(minimum_issues) is not int or minimum_issues<2:raise ValueError('Independent issue rows and minimum support required')
    columns=[f'net_{i}' for i in range(len(penalties))]
    if not set(columns).issubset(history):raise ValueError('Complete candidate returns required')
    context=prepare_learning_context(history,cutoff,source_hashes=source_hashes,repository_root=repository_root,
        implementation_modules=('src.fundamentals_integration_weight','src.fundamentals_n7_baseline','src.temporal_learning.diagnostic_labels','scripts.run_integration_weight_diagnostic'),implementation_distributions=('numpy','pandas','scipy','scikit-learn'),
        availability=AvailabilityFilter(policy=AvailabilityPolicy.historical_proxy('ARCHIVED_ISSUE_SETTLEMENT_DIAGNOSTIC'),data_available_column='data_available_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=PartitionPolicy(kind='FIXED_PRIOR_FIT',tune_years=0,calibration_years=0,minimum_fit_years=1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_issues))
    prior=context.partitions['fit']
    if prior.issue_code.duplicated().any():raise ValueError('Independent admitted issue rows required')
    if not np.isfinite(prior[columns].to_numpy(float)).all():raise ValueError('Complete admitted candidate returns required')
    if len(prior)<minimum_issues:raise ValueError('Insufficient prior validation issues')
    metrics=[dict(penalty=float(p),total_net=float(prior[f'net_{i}'].sum())) for i,p in enumerate(penalties)]
    best=max(metrics,key=lambda r:(r['total_net'],r['penalty']))
    receipt=dict(context.receipt.payload,client='INTEGRATION_PENALTY_SELECTION',selected_parameters=best,metrics=metrics,domain_partition='PRIOR_VALIDATION_ISSUES_ONLY')
    return dict(penalty=best['penalty'],receipt=receipt,seal=stable_json_hash(receipt))
