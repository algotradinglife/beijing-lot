"""Second-stage walk-forward selection of historical signal-rate calibration."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.fundamentals_signal_rates import fit_signal_rates, predict_signal_rates
from src.temporal_learning import (AvailabilityFilter, AvailabilityPolicy, Cutoff,
    PartitionPolicy, WeightingPolicy, WalkForwardRunner, prepare_learning_context,
    temporal_client)
from src.temporal_learning.core import stable_json_hash


@temporal_client
def cross_validate_signal_rates(history, cutoff, *, issue_order, initial_issues,
                                validation_cutoffs, source_hashes, repository_root,
                                shrinkage_n, minimum_ess):
    """Select among fixed .5/1 blends and 0/.02/.05 abstention boosts by Brier.

    history consists only of verified independent-expert OOF predictions joined
    one-to-one to baseline probabilities and timed labels. An initial OOF window
    initializes reference rates; each later OOF issue is then predicted using
    earlier admitted OOF labels, purging repeated provider IDs. No I/O.
    """
    if (not 1 <= initial_issues < len(issue_order) or len(set(issue_order))!=len(issue_order) or
        cutoff.target_issue in issue_order or set(validation_cutoffs)!=set(issue_order[initial_issues:])):
        raise ValueError('Explicit prior OOF validation scope required')
    context=prepare_learning_context(history,cutoff,source_hashes=source_hashes,
        repository_root=Path(repository_root),
        implementation_modules=('src.fundamentals_signal_rate_cv',),
        implementation_distributions=('numpy','pandas'),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
            'FIXTURE_CUTOFF_PLUS_SIX_HOURS_DIAGNOSTIC'),data_available_column='data_available_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',partition_policy=PartitionPolicy('FIXED_PRIOR_FIT',0,0,1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_ess))
    admitted=context.partitions['fit']
    admitted=admitted.loc[admitted.issue_code.isin(issue_order)].copy()
    if set(admitted.issue_code)!=set(issue_order):
        raise ValueError('Every OOF issue requires admitted evidence')
    targets=admitted.loc[admitted.issue_code.isin(issue_order[initial_issues:])].copy()
    targets['fixture_decision_ts']=targets.issue_code.map(validation_cutoffs)
    policies=[dict(blend_weight=w,abstain_boost=b) for w in [.5,1.] for b in [0.,.02,.05]]
    receipts=[]
    def evaluate_fold(epoch,target):
        prior=issue_order[:issue_order.index(epoch.target_issue)]
        train=admitted.loc[admitted.issue_code.isin(prior)]
        purged=train.provider_id.isin(target.provider_id)
        artifact=fit_signal_rates(train.loc[~purged],epoch,shrinkage_n=shrinkage_n,
            minimum_ess=minimum_ess,source_hashes=source_hashes,repository_root=repository_root)
        receipts.append(dict(issue=epoch.target_issue,repeated_identity_purged=int(purged.sum()),
            receipt=artifact['receipt'],seal=artifact['seal']))
        rows=[]
        columns=['issue_code','slot','provider_id','handicap','draw_signal','baseline_draw','predictor_clock_ts']
        for _,fixture in target.iterrows():
            decision=Cutoff.decision_epoch(epoch.target_issue,fixture.data_available_ts)
            for candidate,policy in enumerate(policies):
                predicted=predict_signal_rates(artifact,target.loc[[fixture.name],columns],decision,**policy)
                predicted['candidate']=candidate
                predicted['draw_target']=bool(fixture.draw_target)
                predicted['baseline_draw']=float(fixture.baseline_draw)
                predicted['prediction_cutoff_ts']=decision.cutoff_ts.isoformat()
                rows.append(predicted)
        return pd.concat(rows,ignore_index=True)
    predicted=pd.concat(WalkForwardRunner().run(targets,evaluate_fold),ignore_index=True)
    keys=['issue_code','slot','provider_id']
    if predicted.duplicated(keys+['candidate']).any():
        raise ValueError('Duplicate calibration predictions')
    metrics=[]
    for candidate,policy in enumerate(policies):
        rows=predicted.loc[predicted.candidate.eq(candidate)]
        if len(rows)!=len(targets) or not np.isfinite(rows.draw_probability).all():
            raise ValueError('Incomplete calibration candidate coverage')
        metrics.append(dict(candidate=candidate,**policy,n=len(rows),
            brier=float(np.mean((rows.draw_probability-rows.draw_target.astype(int))**2)),
            baseline_brier=float(np.mean((rows.baseline_draw-rows.draw_target.astype(int))**2)),
            predicted_draw_rate=float(rows.draw_probability.mean()),
            actual_draw_rate=float(rows.draw_target.mean()),
            uncalibrated=int(rows.calibration_status.ne('CALIBRATED').sum())))
    selected=min(metrics,key=lambda x:(x['brier'],x['abstain_boost'],x['blend_weight']))['candidate']
    oof=json.loads(predicted.to_json(orient='records'))
    receipt=dict(context.receipt.payload,policies=policies,selected_candidate=selected,
        selected=policies[selected],metrics=metrics,issue_order=issue_order,initial_issues=initial_issues,
        validation_cutoffs=validation_cutoffs,shrinkage_n=shrinkage_n,minimum_ess=minimum_ess,
        fold_receipts=receipts,oof_sha256=stable_json_hash(oof),
        weight_ledger=context.weight_ledger.to_json(orient='records',date_format='iso'),
        objective='POOLED_SECOND_STAGE_OOF_BRIER',deployable=False,target_labels_opened=False)
    return dict(selected=policies[selected],selected_candidate=selected,metrics=metrics,
        oof=oof,receipt=receipt,seal=stable_json_hash(receipt))
