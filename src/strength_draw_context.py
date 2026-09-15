"""Domain join for draw-feature calibration; shared code owns all chronology."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .temporal_learning.core import (AvailabilityFilter, AvailabilityPolicy,
    Cutoff, PartitionPolicy, WeightingPolicy, TemporalContractError)
from .temporal_learning.frozen_blocks import prepare_block_context
from .temporal_learning.prior_labels import read_prior_label_rows
from .temporal_learning.diagnostic_labels import diagnostic_label_clock


def strength_draw_context(fixtures_json, block, cutoff, *, label_path,
                          label_sha256, delay_hours, minimum_ess,
                          repository_root, source_hashes):
    """Return JSON of admitted rows, expansion weights and shared receipt.

    Input forecasts are label-free, unique issue/slot/provider_id; probability
    units are fractions. Existing CSV labels cross only the shared prior reader.
    Historical last-fixture-plus-delay clocks never authorize prospective use.
    No writes, fitting, threshold selection or networking.
    """
    frame = pd.DataFrame(json.loads(fixtures_json))
    keys = ['issue', 'slot', 'provider_id']
    required = keys + ['q_W', 'q_D', 'q_L', 'p_D',
                       'fixture_decision_ts', 'last_fixture_cutoff']
    if (not set(required).issubset(frame) or frame[required].isna().any().any()
            or frame.duplicated(keys).any()
            or any(c in frame for c in ['actual', 'actual_direction', 'actual_outcome'])):
        raise TemporalContractError('Invalid label-free forecast identities')
    probabilities = frame[['q_W', 'q_D', 'q_L']].to_numpy(float)
    if (not np.isfinite(probabilities).all() or (probabilities <= 0).any()
            or not np.allclose(probabilities.sum(1), 1, atol=1e-10, rtol=0)
            or not np.isfinite(frame.p_D).all() or not frame.p_D.between(0, 1).all()
            or (frame.groupby('issue').last_fixture_cutoff.nunique() != 1).any()):
        raise TemporalContractError('Invalid probabilities or issue clocks')
    clocks = frame.groupby('issue').last_fixture_cutoff.first().to_dict()
    labels = pd.DataFrame(read_prior_label_rows(label_path, label_sha256,
        cutoff=cutoff, issue_clocks=clocks, excluded_issues=block['excluded_issues'],
        delay_hours=delay_hours, issue_column='issue'))
    if labels.empty:
        raise TemporalContractError('No admitted history')
    labels['slot'] = pd.to_numeric(labels.slot, errors='raise').astype(int)
    rows = frame.merge(labels[keys + ['actual_direction']], on=keys,
                       how='inner', validate='one_to_one')
    if not rows.actual_direction.isin(['W', 'D', 'L']).all():
        raise TemporalContractError('Invalid prior outcomes')
    rows['label_available_ts'] = rows.issue.map({i: diagnostic_label_clock(
        clocks[i], cutoff=cutoff, delay_hours=delay_hours) for i in rows.issue.unique()})
    rows['issue_year'] = pd.to_datetime(rows.fixture_decision_ts, utc=True).dt.year
    rows = rows.rename(columns={'issue': 'issue_code', 'actual_direction': 'actual'})
    context = prepare_block_context(rows, cutoff, block=block,
        repository_root=Path(repository_root),
        source_hashes=dict(source_hashes, labels=label_sha256),
        implementation_modules=(__name__,), implementation_distributions=('numpy', 'pandas'),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
            'LAST_FIXTURE_PLUS_DELAY'), data_available_column='fixture_decision_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=minimum_ess))
    admitted = context.partitions['fit'].copy()
    admitted['weight'] = context.weights.loc[admitted.index]
    return json.dumps(dict(rows=json.loads(admitted.to_json(orient='records',
        date_format='iso', double_precision=15)), receipt=context.receipt.payload), allow_nan=False)
