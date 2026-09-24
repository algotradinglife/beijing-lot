"""Time-ordered diagnostic CV for the existing two shallow experts; no I/O."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss
from src.fundamentals_retrained_experts import fit_experts, predict_experts
from beidan_backend.temporal_learning import (
    AvailabilityFilter, AvailabilityPolicy, PartitionPolicy, WeightingPolicy,
    WalkForwardRunner, prepare_learning_context, temporal_client,
)
from beidan_backend.temporal_learning.core import stable_json_hash
from beidan_backend.temporal_learning import Cutoff
from beidan_backend.temporal_learning.predictor_clock import require_prior_predictor_clock


@temporal_client
def cross_validate_experts(history, cutoff, *, features, issue_order, initial_issues,
                           candidates, source_hashes, repository_root, minimum_ess, seed,
                           validation_cutoffs):
    """Select fixed tree policy by pooled out-of-fold macro Brier loss.

    All labels must be admitted by the outer cutoff. Each validation issue is
    predicted by a model trained on nominated earlier issues only. Repeated
    provider identities are purged from that fold's training rows. Missing
    predictors abstain and are counted. Candidates must predict identical rows.
    Returns selected parameters, every OOF probability, fold receipts and a
    sealed selection receipt. No fetching, fitting outside shared contexts, or
    file writes. Raises on insufficient history or invalid identity/contracts.
    """
    if len(set(issue_order)) != len(issue_order) or not 1 <= initial_issues < len(issue_order):
        raise ValueError('Explicit ordered training and validation issues required')
    if cutoff.target_issue in issue_order or not candidates:
        raise ValueError('Test target must be excluded; candidates required')
    context = prepare_learning_context(
        history, cutoff, source_hashes=source_hashes, repository_root=Path(repository_root),
        implementation_modules=('src.fundamentals_cv_experts',),
        implementation_distributions=('numpy', 'pandas', 'scikit-learn'),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy('FIXTURE_CUTOFF_PLUS_SIX_HOURS_DIAGNOSTIC'), data_available_column='data_available_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_ess))
    admitted = context.partitions['fit'].copy()
    admitted = admitted[admitted.issue_code.isin(issue_order)].copy()
    if set(admitted.issue_code) != set(issue_order):
        raise ValueError('Every nominated issue requires admitted training rows')
    targets = admitted[admitted.issue_code.isin(issue_order[initial_issues:])].copy()
    if set(validation_cutoffs) != set(issue_order[initial_issues:]):
        raise ValueError('Full-roster validation decision epochs required')
    targets['fixture_decision_ts'] = targets.issue_code.map(validation_cutoffs)
    all_rows = []; fold_receipts = []; metrics = []
    for candidate_id, policy in enumerate(candidates):
        def evaluate_fold(epoch, target):
            prior = issue_order[:issue_order.index(epoch.target_issue)]
            training = admitted[admitted.issue_code.isin(prior)]
            purged = training.provider_id.isin(target.provider_id)
            training = training.loc[~purged].copy()
            artifact = fit_experts(training, epoch, features=features,
                training_issues=prior, source_hashes=source_hashes,
                repository_root=repository_root, depths=policy['depths'],
                minimum_leaf=policy['minimum_leaf'], minimum_ess=minimum_ess,
                bounds=policy['bounds'], seed=seed)
            columns = list(dict.fromkeys(['issue_code','slot','provider_id','handicap'] + sum(features.values(), [])))
            predictions = []
            for _, fixture in target.iterrows():
                prediction_epoch = Cutoff.decision_epoch(epoch.target_issue, fixture['data_available_ts'])
                require_prior_predictor_clock(fixture['predictor_clock_ts'], prediction_epoch)
                one = target.loc[[fixture.name], columns]
                result = predict_experts(artifact, one, prediction_epoch)
                result['prediction_cutoff_ts'] = prediction_epoch.cutoff_ts.isoformat()
                result['predictor_clock_ts'] = fixture['predictor_clock_ts']
                predictions.append(result)
            prediction = pd.concat(predictions, ignore_index=True)
            joined = prediction.merge(target[['issue_code','slot','provider_id'] + [('draw_target' if e == 'draw' else 'cover_target') for e in features]],
                on=['issue_code','slot','provider_id'], validate='one_to_one')
            joined['candidate'] = candidate_id
            fold_receipts.append(dict(candidate=candidate_id, issue=epoch.target_issue,
                repeated_identity_purged=int(purged.sum()), receipt=artifact['receipt'], seal=artifact['seal']))
            return joined
        folds = WalkForwardRunner().run(targets, evaluate_fold)
        predicted = pd.concat(folds, ignore_index=True)
        losses = []
        for expert in features:
            label = 'draw_target' if expert == 'draw' else 'cover_target'
            ready = np.isfinite(predicted[expert+'_probability'])
            sample = predicted.loc[ready]
            if sample.empty:
                raise ValueError('No out-of-fold evidence for expert')
            loss = float(brier_score_loss(sample[label].astype(int), sample[expert+'_probability']))
            losses.append(loss)
            for signal in ['POSITIVE','NEGATIVE','ABSTAIN']:
                rows = sample[sample[expert+'_signal'].eq(signal)]
                hits = None if signal == 'ABSTAIN' else int((rows[label] if signal == 'POSITIVE' else ~rows[label].astype(bool)).sum())
                metrics.append(dict(candidate=candidate_id, expert=expert, signal=signal,
                    n=len(rows), hits=hits, accuracy=None if hits is None or not len(rows) else hits/len(rows),
                    brier=loss, eligible=len(sample), missing_or_not_applicable=int((~ready).sum())))
        predicted['macro_brier'] = float(np.mean(losses))
        all_rows.append(predicted)
    reference = all_rows[0][['issue_code','slot','provider_id']]
    for rows in all_rows[1:]:
        if not rows[['issue_code','slot','provider_id']].equals(reference):
            raise ValueError('Candidate evaluation scope differs')
        for expert in features:
            if not rows[expert+'_probability'].notna().equals(all_rows[0][expert+'_probability'].notna()):
                raise ValueError('Candidate missingness differs')
    selected = min(range(len(candidates)), key=lambda i: (all_rows[i].macro_brier.iloc[0],
        sum(candidates[i]['depths'].values()), -candidates[i]['minimum_leaf'], i))
    receipt = dict(context.receipt.payload, features=features, issue_order=issue_order, initial_issues=initial_issues,
        candidates=candidates, validation_cutoffs=validation_cutoffs,
        selected_candidate=selected, selected_parameters=candidates[selected],
        objective='POOLED_OOF_MACRO_BRIER_THEN_SIMPLER_TREE', minimum_ess=minimum_ess, seed=seed,
        prediction_protocol='FIT_AT_ISSUE_START_PREDICT_AT_EACH_FIXTURE_CUTOFF_NOT_ONE_EARLY_TICKET',
        weight_ledger=context.weight_ledger.to_json(orient='records', date_format='iso'),
        metrics=metrics, fold_receipts=fold_receipts,
        oof_sha256=stable_json_hash(json.loads(pd.concat(all_rows).to_json(orient='records'))),
        target_labels_opened=False, deployable=False)
    return dict(selected=candidates[selected], selected_candidate=selected,
        metrics=metrics, oof=json.loads(pd.concat(all_rows).to_json(orient='records')),
        receipt=receipt, seal=stable_json_hash(receipt))
