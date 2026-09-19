"""Condition prior-context component masses without changing their blend.

This utility only consumes the shared admitted ledger. It never admits rows or
constructs clocks. Sparse recent strata fail closed; no weights are imputed.
"""
import json
import numpy as np
import pandas as pd
from .core import Cutoff, TemporalContractError, effective_sample_size, stable_json_hash


def stratified_context_json(context_json, membership_json, *, minimum_ess,
                            minimum_recent_ess):
    """Return context plus stratum ledgers, support and a bound receipt (JSON).

    Membership rows have issue_code/cell, unique pairs. Only admitted IDs enter.
    Each component normalizes separately within a cell; alpha stays unchanged.
    ESS is measured in issues, never tickets. No I/O or cached state.
    """
    context=json.loads(context_json); receipt=context['receipt']
    cutoff=Cutoff.decision_epoch(receipt['target_issue'],receipt['cutoff_ts'])
    if cutoff.identity != receipt['cutoff_identity'] or minimum_ess <= 0 or minimum_recent_ess <= 0:
        raise TemporalContractError('Invalid stratified cutoff or support floor')
    membership=pd.DataFrame(json.loads(membership_json))
    if not {'issue_code','cell'}.issubset(membership) or membership.isna().any().any() or membership.duplicated(['issue_code','cell']).any():
        raise TemporalContractError('Invalid stratum membership')
    output=[]
    if context['status']=='READY':
        ledger=pd.DataFrame(receipt['full_weight_ledger'])
        if ledger.issue_code.duplicated().any() or ledger.issue_code.eq(cutoff.target_issue).any():
            raise TemporalContractError('Invalid admitted stratum ledger')
        alpha=float(ledger.recent_mass.sum())
        if not np.isclose(ledger.long_mass.sum()+alpha,1):
            raise TemporalContractError('Invalid component mass')
        joined=membership.merge(ledger,on='issue_code',how='inner',validate='many_to_one')
        for cell,frame in joined.groupby('cell',sort=True):
            long=frame.long_mass.to_numpy(float);recent=frame.recent_mass.to_numpy(float)
            ready=long.sum()>0 and (alpha==0 or recent.sum()>0)
            lw=long/long.sum() if long.sum()>0 else np.zeros(len(frame))
            rw=recent/recent.sum() if recent.sum()>0 else np.zeros(len(frame))
            ess=effective_sample_size((1-alpha)*lw+alpha*rw)
            recent_ess=effective_sample_size(rw) if rw.sum()>0 else 0
            ready=ready and ess>=minimum_ess and (alpha==0 or recent_ess>=minimum_recent_ess)
            output.append(dict(cell=cell,status='READY' if ready else 'UNKNOWN',alpha=alpha,
                ess=ess,recent_ess=recent_ess,rows=[dict(issue_code=i,long_weight=float(l),recent_weight=float(r))
                for i,l,r in zip(frame.issue_code,lw,rw)]))
    context['strata']=output
    context['strata_receipt']=dict(cutoff_identity=cutoff.identity,
        source_hashes=receipt['source_hashes'],minimum_ess=minimum_ess,
        minimum_recent_ess=minimum_recent_ess,ledger_sha256=stable_json_hash(output))
    return json.dumps(context,allow_nan=False)


def stratified_contexts_json(contexts_json, membership_json, *, minimum_ess,
                             minimum_recent_ess):
    """Batch the same conditioning contract without R/Python per-cutoff transfers.

    Input is the shared runner's JSON array; order and cutoff identities remain
    unchanged. No additional weighting, fitting, I/O or cache is introduced.
    """
    contexts=json.loads(contexts_json)
    if not isinstance(contexts,list):
        raise TemporalContractError('Expected an ordered context array')
    return json.dumps([json.loads(stratified_context_json(json.dumps(context),
        membership_json,minimum_ess=minimum_ess,minimum_recent_ess=minimum_recent_ess))
        for context in contexts],allow_nan=False)
