"""Cutoff-bound historical draw rates conditional on independent expert signals.

Callers supply verified OOF signal history, never in-sample predictions. No I/O.
The shared learning context owns admission, weights, ESS and provenance.
"""
from pathlib import Path
from numbers import Real
import math
from src.temporal_learning.replay import prediction_scope,validate_model_chronology

import numpy as np
import pandas as pd

from src.temporal_learning import (AvailabilityFilter, AvailabilityPolicy, Cutoff,
    PartitionPolicy, WeightingPolicy, prepare_learning_context, temporal_client)
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.predictor_clock import require_prior_predictor_clock,validate_training_predictor_clocks


@temporal_client
def fit_signal_rates(history, cutoff, *, shrinkage_n, minimum_ess,
                     source_hashes, repository_root):
    """Estimate 3 signal rates within absolute handicap bands 0, 1 and 2+.

    Required history: shared chronology/identity columns, integer handicap,
    draw_signal in POSITIVE/NEGATIVE/ABSTAIN, and observed binary draw_target.
    Within each band, the reference rate is Jeffreys-smoothed (hits+.5)/(n+1).
    Each signal's rate is (hits + shrinkage_n*reference)/(n + shrinkage_n).
    An entirely unseen handicap band has no estimate. Returns a sealed artifact
    with the full admitted row/weight receipt. Missing/non-OOF rows must be
    inventoried by the caller before this boundary; invalid values fail closed.
    """
    if not np.isfinite(shrinkage_n) or shrinkage_n <= 0 or minimum_ess < 10:
        raise ValueError('Explicit positive shrinkage and minimum ESS required')
    keys = ['issue_code', 'slot', 'provider_id']
    if history[keys].isna().any().any() or history.duplicated(keys).any():
        raise ValueError('Unique complete signal identities required')
    context = prepare_learning_context(history, cutoff,
        source_hashes=source_hashes, repository_root=Path(repository_root),
        implementation_modules=('src.fundamentals_signal_rates',),
        implementation_distributions=('numpy', 'pandas'),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
            'FIXTURE_CUTOFF_PLUS_SIX_HOURS_DIAGNOSTIC'), data_available_column='data_available_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_ess))
    rows = context.partitions['fit'].copy()
    predictor_max = validate_training_predictor_clocks(rows,cutoff)
    if (rows.draw_signal.isna().any() or
        not set(rows.draw_signal).issubset({'POSITIVE', 'NEGATIVE', 'ABSTAIN'}) or
        rows.draw_target.isna().any() or not set(rows.draw_target).issubset({0, 1}) or
        not np.isfinite(rows.handicap).all() or (rows.handicap % 1 != 0).any()):
        raise ValueError('Valid OOF signals, integer handicaps and binary labels required')
    rows['band'] = np.minimum(rows.handicap.abs(), 2).astype(int)
    estimates = []
    for band in [0, 1, 2]:
        band_rows = rows.loc[rows.band.eq(band)]
        n = len(band_rows); hits = int(band_rows.draw_target.sum())
        prior = (hits + .5) / (n + 1) if n else None
        for signal in ['POSITIVE', 'NEGATIVE', 'ABSTAIN']:
            sample = band_rows.loc[band_rows.draw_signal.eq(signal)]
            count = len(sample); positive = int(sample.draw_target.sum())
            p = (positive + shrinkage_n * prior) / (count + shrinkage_n) if n else None
            estimates.append(dict(band=band, signal=signal, band_n=n,
                band_draws=hits, reference_rate=prior, n=count, draws=positive,
                raw_rate=positive/count if count else None, probability=p))
    receipt = dict(context.receipt.payload, estimates=estimates, maximum_predictor_clock=predictor_max,
        training_issues=sorted(rows.issue_code.unique().tolist()),
        shrinkage_n=shrinkage_n, minimum_ess=minimum_ess,
        band_definition='ABS_HANDICAP_0_1_2PLUS', prior='BAND_JEFFREYS_HALF',
        history_kind='CALLER_VERIFIED_OUT_OF_FOLD',
        weight_ledger=context.weight_ledger.to_json(orient='records',date_format='iso'),
        deployable=False)
    return dict(receipt=receipt, seal=stable_json_hash(receipt), cutoff=cutoff)



def validate_draw_weight(value):
    """Normalize a finite real scalar in [0,1]; reject booleans and containers.

    Returns a Python float suitable for JSON receipts. Pure input validation,
    with no fitting, data access or automatic weight selection.
    """
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or
        not 0 <= value <= 1 or not math.isfinite(value)):
        raise ValueError('draw_weight must be a finite real scalar in [0,1]')
    return float(value)

def predict_signal_rates(artifact, frame, cutoff, *, blend_weight, abstain_boost):
    """Project fixed signal-rate references onto baseline draw probabilities.

    frame: unique issue/slot/provider, handicap, draw_signal, baseline_draw and
    predictor_clock_ts. Non-signal default boost applies only to ABSTAIN. Missing
    expert features remain explicitly uncalibrated, as do unseen handicap bands.
    Returns historical reference, boosted reference and final draw probability;
    preserves the original signal label. blend_weight is a finite scalar in
    [0,1]: zero retains baseline and one uses the boosted reference. Missing
    reference/features still retain baseline. No result columns read, no I/O.
    """
    receipt = artifact['receipt']
    if stable_json_hash(receipt) != artifact['seal']:
        raise ValueError('Frozen rate artifact changed')
    validate_model_chronology(artifact["cutoff"],[receipt],receipt["training_issues"])
    blend_weight=validate_draw_weight(blend_weight)
    if (not isinstance(cutoff, Cutoff) or abstain_boost not in [0., .02, .05]):
        raise ValueError('Explicit supported prediction cutoff and calibration policy required')
    scope = prediction_scope(cutoff, receipt['training_issues'], artifact['cutoff'])
    keys = ['issue_code', 'slot', 'provider_id']
    if frame[keys].isna().any().any() or frame.duplicated(keys).any() or not frame.issue_code.eq(cutoff.target_issue).all():
        raise ValueError('Unique target identities required')
    if (not np.isfinite(frame.handicap).all() or (frame.handicap % 1 != 0).any() or
        not frame.baseline_draw.between(0, 1).all() or frame.draw_signal.isna().any() or
        not set(frame.draw_signal).issubset({'POSITIVE','NEGATIVE','ABSTAIN','INSUFFICIENT_FEATURES'})):
        raise ValueError('Invalid prediction values')
    for clock in frame.predictor_clock_ts:
        require_prior_predictor_clock(clock, cutoff)
    rates = {(r['band'],r['signal']):r['probability'] for r in receipt['estimates']}
    result = frame[keys + ['draw_signal']].copy()
    references = []; boosted = []; probabilities = []; statuses = []
    for _, row in frame.iterrows():
        reference = rates.get((min(abs(int(row.handicap)),2),row.draw_signal))
        if reference is None:
            adjusted = None; probability = float(row.baseline_draw)
            status = 'INSUFFICIENT_FEATURES' if row.draw_signal=='INSUFFICIENT_FEATURES' else 'NO_PRIOR_HANDICAP_BAND'
        else:
            adjusted = min(1., reference + (abstain_boost if row.draw_signal=='ABSTAIN' else 0.))
            probability = (1-blend_weight)*row.baseline_draw + blend_weight*adjusted
            status = 'CALIBRATED'
        references.append(reference); boosted.append(adjusted)
        probabilities.append(probability); statuses.append(status)
    result['reference_probability'] = references
    result['boosted_reference'] = boosted
    result['draw_probability'] = probabilities
    result['calibration_status'] = statuses
    result['evaluation_scope'] = scope
    result.attrs['calibration_receipt'] = dict(evaluation_scope=scope, deployable=False,
        model_cutoff_ts=artifact['cutoff'].cutoff_ts.isoformat(), rate_seal=artifact['seal'],
        cutoff_identity=cutoff.identity, blend_weight=blend_weight, abstain_boost=abstain_boost)
    return result
