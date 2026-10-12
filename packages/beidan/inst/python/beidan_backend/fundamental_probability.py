"""Adapters for frozen venue summaries; chronology is owned by temporal_learning.

Rows are source summary snapshots, not independent matches. No fitting, HTTP,
installation, or writes. Historical date proxies authorize diagnostics only.
"""
from pathlib import Path
import hashlib
import pandas as pd
from .temporal_learning import (
    Cutoff, AvailabilityPolicy, AvailabilityFilter, PartitionPolicy,
    WeightingPolicy, prepare_learning_context,
)
from .temporal_learning.core import stable_json_hash
from .temporal_learning.context_replay import verify_learning_context


def _prepare_fundamental_context(rows, fixture, cutoff, source_hashes,
                                availability_policy, intended_use, repository_root):
    """Bind explicit summary snapshots to shared admission and equal weighting.

    rows require home/away venue summaries, timestamps and source issue identity.
    cutoff is a shared Cutoff; availability_policy is an explicit shared policy.
    source_hashes identify original snapshots. No defaults infer availability.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise ValueError('Explicit decision cutoff required')
    if not isinstance(availability_policy, AvailabilityPolicy) or not source_hashes:
        raise ValueError('Explicit availability policy and source hashes required')
    frame = pd.DataFrame(rows)
    context = prepare_learning_context(frame, cutoff,
        source_hashes={**source_hashes, 'fixture': stable_json_hash(fixture),
                       'R_implementation': hashlib.sha256((Path(repository_root)/
                           'packages/beidan/R/fundamental_probability.R').read_bytes()).hexdigest()},
        repository_root=Path(repository_root),
        implementation_modules=('beidan_backend.fundamental_probability',),
        implementation_distributions=('pandas', 'numpy'),
        availability=AvailabilityFilter(availability_policy,
                                       data_available_column='data_available_ts'),
        intended_use=intended_use,
        partition_policy=PartitionPolicy('OBSERVED_PRIOR_FIT'
            if intended_use == 'PROSPECTIVE_DECISION' else 'FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1))
    return context



def build_goal_baseline_context(rows, fixture, cutoff, source_hashes,
                                availability_policy, intended_use, repository_root):
    """Prepare and verify venue snapshots using the shared context."""
    context = _prepare_fundamental_context(rows, fixture, cutoff, source_hashes,
        availability_policy, intended_use, repository_root)
    export_goal_baseline_context(context, fixture, repository_root)
    return context


def build_adjustment_evidence_context(rows, fixture, cutoff, source_hashes,
                                      availability_policy, intended_use, repository_root):
    """Prepare evidence observations with explicit release/availability clocks."""
    context = _prepare_fundamental_context(rows, fixture, cutoff, source_hashes,
        availability_policy, intended_use, repository_root)
    export_adjustment_evidence_context(context, fixture, cutoff.cutoff_ts.timestamp(),
                                      intended_use, repository_root)
    return context


def export_adjustment_evidence_context(context, fixture, cutoff_epoch,
                                       intended_use, repository_root):
    """Export only shared-admitted evidence, rejecting mismatched decision/use.

    Evidence source_hash values identify frozen sources. Shared availability
    filtering excludes target issue and future records before domain validation.
    Prospective scenarios require a prospective evidence context, never a proxy.
    """
    verify_learning_context(context, repository_root=repository_root)
    r = context.receipt.payload
    if (context.cutoff.target_issue != fixture['issue_id']
        or context.cutoff.cutoff_ts.timestamp() != cutoff_epoch
        or r['source_hashes']['fixture'] != stable_json_hash(fixture)
        or r['source_hashes']['R_implementation'] != hashlib.sha256(
          (Path(repository_root)/'packages/beidan/R/fundamental_probability.R').read_bytes()).hexdigest()
        or (intended_use == 'PROSPECTIVE_DECISION'
            and r['availability']['intended_use'] != 'PROSPECTIVE_DECISION')):
        raise ValueError('Evidence cutoff, implementation or availability binding differs')
    fit = context.partitions['fit']
    cols = ['evidence_id', 'fixture_id', 'source_hash']
    if not set(cols) <= set(fit) or fit[cols].isna().any().any():
        raise ValueError('Evidence schema required')
    if (fit.evidence_id.duplicated().any()
        or not fit.fixture_id.eq(fixture['fixture_id']).all()
        or not all(isinstance(v, str) and bool(v) for c in cols for v in fit[c])):
        raise ValueError('Unique bound evidence identities required')
    return {'evidence':fit[cols].to_dict('records'),'receipt':r}


def export_goal_baseline_context(context, fixture, repository_root):
    """Verify shared context and fixture/code bindings; return typed-source rows.

    Exactly one summary per target team/venue must remain. Counts are integers;
    zero-match summaries are rejected in R according to explicit support policy.
    Export timestamps as ISO text, retaining fractional cutoff seconds.
    """
    verify_learning_context(context, repository_root=repository_root)
    receipt = context.receipt.payload
    if (context.cutoff.kind != 'DECISION_EPOCH'
        or str(context.cutoff.target_issue) != fixture['issue_id']
        or not fixture['fixture_id'].startswith(fixture['issue_id']+':')
        or receipt['source_hashes']['fixture'] != stable_json_hash(fixture)
        or receipt['source_hashes']['R_implementation'] != hashlib.sha256(
            (Path(repository_root)/'packages/beidan/R/fundamental_probability.R').read_bytes()).hexdigest()):
        raise ValueError('Fixture or implementation cutoff binding differs')
    if receipt['weight_receipt']['policy']['kind'] != 'EXPANDING_EQUAL':
        raise ValueError('Venue snapshot baseline requires explicit equal policy')
    fit = context.partitions['fit'].copy()
    required = {'team', 'venue', 'matches', 'goals_for', 'goals_against'}
    if not required <= set(fit):
        raise ValueError('Missing venue summary columns')
    selected = fit.loc[((fit.team == fixture['home']) & (fit.venue == 'home')) |
                      ((fit.team == fixture['away']) & (fit.venue == 'away'))].copy()
    if len(selected) != 2 or selected.duplicated(['team', 'venue']).any():
        raise ValueError('Exactly two unique target venue summaries required')
    for col in ('matches', 'goals_for', 'goals_against'):
        if selected[col].isna().any() or not selected[col].map(
                lambda v: not isinstance(v, bool) and isinstance(v, (int, float))
                and float(v).is_integer() and 0 <= v <= 2147483647).all():
            raise ValueError('Invalid integer summary count: '+col)
        selected[col] = selected[col].astype(int)
    selected = selected.sort_values('venue', ascending=False)
    return {'summaries': selected[sorted(required)].to_dict('records'),
            'cutoff_epoch': context.cutoff.cutoff_ts.timestamp(),
            'issue_id': context.cutoff.target_issue,
            'receipt': receipt}
