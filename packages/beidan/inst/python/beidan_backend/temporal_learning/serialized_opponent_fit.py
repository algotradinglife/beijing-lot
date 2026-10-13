"""Shared publication validation for serialized opponent-fit receipts."""
import hashlib
from io import StringIO
from pathlib import Path
import numpy as np
import pandas as pd
from .core import (Cutoff, TemporalContractError, utc, effective_sample_size,
    AvailabilityFilter,AvailabilityPolicy,WeightingPolicy,EffectiveSamplePolicy,_weight_ledger)
from .provenance import verify_implementation_closure


def validate_serialized_opponent_fit(fit, cutoff, repository_root):
    """Validate full diagnostic admission/group chronology and weight evidence.

    fit contains receipt, group receipts and original 15-digit JSON ledgers.
    cutoff is an explicit shared decision epoch. Source/label maxima must precede
    it; fixture IDs, code and cache identities must bind. This validates a frozen
    export, not a replacement for independent raw-input fitting replay. JSON
    rounding has a fixed 1e-10 mass tolerance; ESS uses the shared implementation.
    No fits, chronology inference, fetching or writes.
    """
    if not isinstance(cutoff,Cutoff) or cutoff.kind!='DECISION_EPOCH' or not isinstance(fit,dict):
        raise TemporalContractError('Explicit serialized fit and decision cutoff required')
    root=Path(repository_root);r=fit.get('receipt',{});admission=r.get('admission',{})
    if (r.get('cutoff')!=cutoff.identity or r.get('target_label_optimization')is not False
            or r.get('intended_use')!='HISTORICAL_DIAGNOSTIC'
            or r.get('fixture',{}).get('issue_id')!=cutoff.target_issue):
        raise TemporalContractError('Fitting cutoff, fixture or intended use differs')
    required={'cutoff_identity','cutoff_ts','target_issue','maximum_source_time',
              'maximum_training_label_timestamp','implementation','availability','cache_key'}
    groups=[admission,*fit.get('receipts',[])]
    if not fit.get('receipts') or len(fit.get('ledgers',[]))!=len(fit['receipts']):
        raise TemporalContractError('Complete group ledgers and receipts required')
    for group in groups:
        if not required<=set(group):raise TemporalContractError('Complete shared receipt required')
        if (group['cutoff_identity']!=cutoff.identity or utc(group['cutoff_ts'])!=cutoff.cutoff_ts
                or group['target_issue']!=cutoff.target_issue):
            raise TemporalContractError('Group cutoff differs')
        for field in ['maximum_source_time','maximum_training_label_timestamp']:
            if not utc(group[field])<cutoff.cutoff_ts:raise TemporalContractError('Group chronology crosses cutoff')
        availability=group['availability']
        if (availability.get('intended_use')!='HISTORICAL_DIAGNOSTIC'
                or availability.get('policy',{}).get('kind')!='HISTORICAL_PROXY'
                or availability['policy'].get('prospective_capable')is not False):
            raise TemporalContractError('Diagnostic proxy evidence required')
        if not isinstance(group['cache_key'],str) or len(group['cache_key'])!=64:
            raise TemporalContractError('Shared cutoff-bound cache identity required')
        verify_implementation_closure(root,group['implementation'])
    if r.get('R_code_sha256')!=hashlib.sha256((root/'packages/beidan/R/opponent_goals.R').read_bytes()).hexdigest():
        raise TemporalContractError('Fitted R implementation differs')
    binding=r.get('admission_binding')
    if not isinstance(binding,str) or len(binding)!=64:raise TemporalContractError('Exact group admission binding required')
    for group,export in zip(fit['receipts'],fit['ledgers'],strict=True):
        if group['source_hashes'].get('admission')!=binding:
            raise TemporalContractError('Group admission binding differs')
        if not isinstance(export.get('ledger'),str):raise TemporalContractError('Original JSON weight ledger required')
        ledger=pd.read_json(StringIO(export['ledger']),orient='records')
        needed={'row_key','long_mass','recent_mass','total_mass','weight','cutoff_identity','cutoff_ts','label_available_ts'}
        if ledger.empty or not needed<=set(ledger) or ledger[list(needed)].isna().any().any() or ledger.row_key.duplicated().any():
            raise TemporalContractError('Complete keyed weight ledger required')
        if not ledger.cutoff_identity.eq(cutoff.identity).all():raise TemporalContractError('Ledger cutoff identity differs')
        if any(utc(value)!=cutoff.cutoff_ts for value in ledger.cutoff_ts):raise TemporalContractError('Ledger cutoff time differs')
        if any(not utc(value)<cutoff.cutoff_ts for value in ledger.label_available_ts):raise TemporalContractError('Ledger label chronology crosses cutoff')
        numeric=ledger[['long_mass','recent_mass','total_mass','weight']].to_numpy(float)
        if not np.isfinite(numeric).all() or (numeric<0).any() or (ledger.weight<=0).any():
            raise TemporalContractError('Finite positive weight ledger required')
        if (abs(ledger.total_mass.sum()-1)>1e-10
                or np.max(np.abs(ledger.long_mass+ledger.recent_mass-ledger.total_mass))>1e-10
                or np.max(np.abs(ledger.total_mass*len(ledger)-ledger.weight))>1e-10):
            raise TemporalContractError('Ledger component masses differ')
        weights=group['weight_receipt'];policy=weights['policy']
        wp=dict(policy);wp['effective_sample']=EffectiveSamplePolicy(**wp['effective_sample'])
        availability=group['availability']
        af=AvailabilityFilter(AvailabilityPolicy(**availability['policy']),
            label_available_column=availability['label_available_column'],
            data_available_column=availability['data_available_column'])
        history=ledger.copy()
        for column in set([af.label_available_column,wp.get('recent_order_column')])-{None}:
            history[column]=pd.to_datetime(history[column],utc=True,errors='raise')
        rebuilt=_weight_ledger(history,cutoff,af,WeightingPolicy(**wp))
        for column in ['long_mass','recent_mass','total_mass','weight']:
            if np.max(np.abs(ledger[column].to_numpy(float)-rebuilt[column].to_numpy(float)))>1e-10:
                raise TemporalContractError('Ledger differs from independently rebuilt shared weights')
        if (len(ledger)!=weights['rows'] or abs(ledger.long_mass.sum()-weights['long_history_mass'])>1e-10
                or abs(ledger.recent_mass.sum()-weights['recent_state_mass'])>1e-10
                or abs(effective_sample_size(ledger.weight.to_numpy(float))-weights['effective_sample_size'])>1e-8):
            raise TemporalContractError('Ledger mass/ESS receipt differs')
        if policy['kind']=='RECENT_STATE_BLEND' and (abs(ledger.recent_mass.sum()-policy['recent_blend'])>1e-10
                or abs(ledger.long_mass.sum()-(1-policy['recent_blend']))>1e-10):
            raise TemporalContractError('Recent/long normalized blend differs')
        if effective_sample_size(ledger.weight.to_numpy(float))+1e-8<policy['effective_sample']['minimum']:
            raise TemporalContractError('Ledger effective sample floor not met')
