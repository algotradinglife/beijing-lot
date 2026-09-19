"""Fixture-domain adapter for retrospective frozen-block draw calibration.

The R callback estimates cell rates. All clocks, cadence, history admission,
component weights, ESS and implementation receipts remain in temporal_learning.
No network or persistence. Diagnostic clocks cannot authorize future decisions.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .temporal_learning.core import (Cutoff, AvailabilityPolicy,
    AvailabilityFilter, PartitionPolicy, WeightingPolicy, TemporalContractError,
    utc)
from .temporal_learning.diagnostic_labels import diagnostic_label_clock
from .temporal_learning.frozen_blocks import prepare_block_context
from .temporal_learning.prior_labels import read_prior_label_rows


def draw_refresh_context(history, block, cutoff, *, repository_root, source_hashes,
                         delay_hours, recent_issues, minimum_ess):
    """Admit fixture history at the block's first decision epoch.

    history: unique issue_code/slot/provider_id; q_W/q_D/q_L strictly positive
    normalized fractions, actual W/D/L, fixture_decision_ts and one consistent
    last_fixture_cutoff per issue. Proxy labels are last fixture + explicit delay.
    Returns rows and full shared receipt; insufficient history fails closed.
    Long/recent ledger components each carry .5 total mass; R normalizes each
    within cells, then mixes estimated rates with an explicit domain alpha.
    """
    required = ['issue_code', 'slot', 'provider_id', 'q_W', 'q_D', 'q_L',
                'actual', 'fixture_decision_ts', 'last_fixture_cutoff']
    if not set(required).issubset(history) or history[required].isna().any().any():
        raise TemporalContractError('Missing draw history fields')
    if (history.duplicated(['issue_code', 'slot', 'provider_id']).any()
            or not history.issue_code.map(lambda x: isinstance(x, str) and bool(x)).all()
            or not history.provider_id.map(lambda x: isinstance(x, str) and bool(x)).all()
            or not history.actual.isin(['W', 'D', 'L']).all()
            or (history.groupby('issue_code').last_fixture_cutoff.nunique() != 1).any()):
        raise TemporalContractError('Invalid draw history identity/outcome')
    q = history[['q_W', 'q_D', 'q_L']].to_numpy(float)
    if not np.isfinite(q).all() or (q <= 0).any() or not np.allclose(q.sum(1), 1, atol=1e-10, rtol=0):
        raise TemporalContractError('Positive normalized market probabilities required')
    if cutoff != Cutoff.decision_epoch(block['fit_issue'], block['fit_cutoff_ts']):
        raise TemporalContractError('Exact block cutoff required')
    clocks = {}
    for issue, timestamp in history[['issue_code', 'last_fixture_cutoff']].drop_duplicates().itertuples(index=False):
        try:
            clocks[issue] = diagnostic_label_clock(timestamp, cutoff=cutoff, delay_hours=delay_hours)
        except TemporalContractError as exc:
            if str(exc) != 'Diagnostic label clock must precede cutoff':
                raise
    rows = history.loc[history.issue_code.isin(clocks)].copy()
    rows['label_available_ts'] = rows.issue_code.map(clocks)
    rows['issue_year'] = pd.to_datetime(rows.fixture_decision_ts, utc=True).dt.year
    if any(utc(a) > utc(b) for a, b in zip(rows.fixture_decision_ts, rows.last_fixture_cutoff)):
        raise TemporalContractError('Fixture after declared last fixture')
    context = prepare_block_context(rows, cutoff, block=block,
        repository_root=Path(repository_root), source_hashes=source_hashes,
        implementation_modules=(__name__, 'src.probability_foundation_draw'), implementation_distributions=('numpy', 'pandas'),
        availability=AvailabilityFilter(
            AvailabilityPolicy.historical_proxy('LAST_FIXTURE_PLUS_DELAY'),
            data_available_column='fixture_decision_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.recent_state_blend(recent_issues, .5, minimum_ess=minimum_ess))
    admitted = context.eligible.copy()
    for column in ('long_mass', 'recent_mass', 'total_mass'):
        admitted[column] = context.weight_ledger[column].to_numpy()
    return dict(rows=json.loads(admitted.to_json(orient='records', date_format='iso', double_precision=15)),
        receipt=context.receipt.payload,
        weight_ledger=json.loads(context.weight_ledger.to_json(orient='records', date_format='iso', double_precision=15)),
        block=block, historical_admission=False)


def draw_refresh_context_json(history_json, block_json, *, repository_root,
                              source_hashes_json, delay_hours, recent_issues, minimum_ess):
    """JSON bridge for R; all computation uses the authoritative adapter above."""
    block = json.loads(block_json)
    return json.dumps(draw_refresh_context(pd.DataFrame(json.loads(history_json)),
        block, Cutoff.decision_epoch(block['fit_issue'], block['fit_cutoff_ts']), repository_root=repository_root,
        source_hashes=json.loads(source_hashes_json), delay_hours=delay_hours,
        recent_issues=recent_issues, minimum_ess=minimum_ess), allow_nan=False)


def draw_refresh_prior_history_json(fixtures_json, block_json, *, label_path,
                                    label_sha256, delay_hours):
    """R bridge: acquire only prior labels through the shared availability reader.

    Fixtures contain no outcomes. Return unique READY prior fixtures for the R
    fit callback; targets and later labels are never returned to that callback.
    """
    fixtures = pd.DataFrame(json.loads(fixtures_json))
    block = json.loads(block_json)
    cutoff = Cutoff.decision_epoch(block['fit_issue'], block['fit_cutoff_ts'])
    clocks = fixtures.groupby('issue').last_fixture_cutoff.first().to_dict()
    labels = pd.DataFrame(read_prior_label_rows(label_path, label_sha256,
        cutoff=cutoff, issue_clocks=clocks, excluded_issues=block['excluded_issues'],
        delay_hours=delay_hours, issue_column='issue'))
    if labels.empty:
        raise TemporalContractError('No prior label rows')
    labels['slot'] = pd.to_numeric(labels.slot, errors='raise').astype(int)
    joined = fixtures.merge(labels[['issue', 'slot', 'provider_id', 'actual_direction', 'status']],
        on=['issue', 'slot', 'provider_id'], how='inner', validate='one_to_one')
    if not joined.status.eq('READY').all() or not joined.actual_direction.isin(['W', 'D', 'L']).all():
        raise TemporalContractError('Prior fixture label incomplete')
    joined = joined.rename(columns={'issue': 'issue_code', 'actual_direction': 'actual'})
    return joined.to_json(orient='records', double_precision=15)
