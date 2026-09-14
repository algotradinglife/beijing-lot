"""Shared-cutoff adapter for fixed retrospective N7 risk monitoring. No writes.

Input issue residuals use diagnostic last-fixture-plus-delay label clocks;
they never prove observed availability. There is no threshold search or model
refit. All filtering, weighting, ESS, partitions, receipts and epoch ordering
come from temporal_learning. R supplies the domain state/allocation functions.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .temporal_learning.core import (
    Cutoff, TemporalContractError, AvailabilityPolicy, AvailabilityFilter,
    PartitionPolicy, WeightingPolicy, WalkForwardRunner, prepare_learning_context,
    utc,
)
from .temporal_learning.diagnostic_labels import diagnostic_label_clock


def n7_risk_context(history, cutoff, *, repository_root, source_hashes,
                    delay_hours, window_issues, recent_blend, minimum_ess):
    """Return prior issue residuals/weights and the common immutable receipt.

    history: DataFrame, unique issue_code, last_fixture_cutoff, hit_residual,
    depth_residual. Residual units are probability points as fractions [-1,1].
    Missing clocks/values fail. Insufficient prior observations return WARMUP;
    this is not permission to wager. No target/future labels enter the score.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise TemporalContractError('Explicit decision cutoff required')
    required = {'issue_code', 'last_fixture_cutoff', 'hit_residual', 'depth_residual'}
    if not required.issubset(history) or history[list(required)].isna().any().any():
        raise ValueError('Missing risk history fields or chronology')
    if history.issue_code.duplicated().any() or not history.issue_code.map(lambda x:isinstance(x,str) and bool(x)).all():
        raise ValueError('Unique string issue identities required')
    values=history[['hit_residual','depth_residual']].to_numpy(float)
    if not np.isfinite(values).all() or (np.abs(values)>1).any():
        raise ValueError('Invalid residual probability units')
    rows=[];late=[]
    for row in history.to_dict('records'):
        event=utc(row['last_fixture_cutoff'])
        if pd.isna(event):
            raise ValueError('Missing fixture clock')
        try:
            label=diagnostic_label_clock(event,cutoff=cutoff,delay_hours=delay_hours)
        except TemporalContractError as exc:
            if str(exc)!='Diagnostic label clock must precede cutoff':
                raise
            late.append(row['issue_code']);continue
        rows.append(dict(row,label_available_ts=label,issue_year=event.year))
    base=dict(cutoff_identity=cutoff.identity,cutoff_kind=cutoff.kind,target_issue=cutoff.target_issue,
        cutoff_ts=cutoff.cutoff_ts.isoformat(),historical_admission=False,
        source_hashes=source_hashes,delay_hours=delay_hours,late_issues=late)
    if not rows:
        return dict(status='WARMUP',receipt=base,rows=[],history_identity=None)
    try:
        ctx=prepare_learning_context(pd.DataFrame(rows),cutoff,
            source_hashes=source_hashes,repository_root=Path(repository_root),
            implementation_modules=('src.n7_risk_context',),
            implementation_distributions=('numpy','pandas'),
            availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy('LAST_FIXTURE_PLUS_DELAY')),
            intended_use='HISTORICAL_DIAGNOSTIC',
            partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
            weighting_policy=WeightingPolicy.recent_state_blend(
                window_issues,recent_blend,minimum_ess=minimum_ess))
    except TemporalContractError as exc:
        if str(exc)=='cutoff admits no prior observations' or str(exc).startswith('effective sample size '):
            return dict(status='WARMUP',receipt=dict(base,reason=str(exc)),rows=[],history_identity=None)
        raise
    frame=ctx.eligible[['issue_code','hit_residual','depth_residual']].copy()
    frame['weight']=ctx.weight_ledger['total_mass'].to_numpy()
    receipt=dict(ctx.receipt.payload,**{k:v for k,v in base.items() if k not in ctx.receipt.payload})
    receipt['full_weight_ledger']=json.loads(ctx.weight_ledger.to_json(orient='records',date_format='iso',double_precision=15))
    return dict(status='READY',rows=frame.to_dict('records'),receipt=receipt,
        history_identity=ctx.receipt.payload['admitted_history_sha256'])


def n7_risk_contexts_json(history_json, targets_json, *, repository_root,
                         source_hashes_json, delay_hours, window_issues,
                         recent_blend, minimum_ess):
    """Run the shared chronological epoch runner; return JSON for reticulate.

    targets JSON: issue_code, fixture_decision_ts (one or more rows/issue).
    R code hashes belong in source_hashes_json to bind domain implementation.
    Returns all contexts in decision-time order; no files/cache or fitting.
    """
    history=pd.DataFrame(json.loads(history_json));targets=pd.DataFrame(json.loads(targets_json))
    sources=json.loads(source_hashes_json)
    return json.dumps(WalkForwardRunner().run(targets,lambda cutoff,_:
        n7_risk_context(history,cutoff,repository_root=repository_root,source_hashes=sources,
            delay_hours=delay_hours,window_issues=window_issues,recent_blend=recent_blend,
            minimum_ess=minimum_ess)),allow_nan=False)
