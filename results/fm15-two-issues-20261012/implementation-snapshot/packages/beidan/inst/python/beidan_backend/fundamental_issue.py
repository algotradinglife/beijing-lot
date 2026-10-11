"""Diagnostic match-history adapter; all temporal machinery is shared.

Date-only results have no observed label-availability proof. Explicit UTC day
end proxies below authorize historical diagnostics only. Native IDs of the
complete target roster identify every target-issue match, including bad dates.
Non-target records are football matches, not fabricated Northsingle issues.
"""
from pathlib import Path
import pandas as pd

from .temporal_learning import (Cutoff, AvailabilityPolicy, AvailabilityFilter,
    PartitionPolicy, WeightingPolicy, prepare_learning_context)
from .temporal_learning.context_replay import verify_learning_context
from .temporal_learning.core import stable_json_hash


def admit_fixture_history(rows, fixture, target_native_ids, cutoff, source_hashes,
                          repository_root):
    """Return shared-admitted dated history and a replay-verified receipt.

    One row per fixture/scope/native match. Empty/malformed history, missing
    identities or chronology fail. Original dates and score scopes remain;
    this adapter does not choose windows, fit goal rates, or access labels of
    the target roster. Input/source/R implementation hashes bind the receipt.
    Exact target-native exclusion is in addition to the shared strict cutoff.
    rows require row_key, match_id, event_date and the factual score columns.
    A source issue namespace MATCH:<native ID> describes unregistered football
    observations; registered target matches get the actual target issue ID.
    """
    if not isinstance(cutoff, Cutoff) or cutoff.kind != 'DECISION_EPOCH':
        raise ValueError('Explicit decision cutoff required')
    if (fixture['issue_id'] != cutoff.target_issue or not target_native_ids
        or len(target_native_ids) != len(set(target_native_ids))
        or not all(isinstance(x, str) and x for x in target_native_ids)
        or fixture['provider_id'] not in target_native_ids or not source_hashes):
        raise ValueError('Complete target roster and source binding required')
    frame = pd.DataFrame(rows)
    required = ['row_key', 'match_id', 'event_date', 'scope', 'home_id',
                'away_id', 'home_score', 'away_score', 'score_scope']
    if (frame.empty or not set(required).issubset(frame)
        or frame[['row_key', 'match_id', 'event_date']].isna().any().any()):
        raise ValueError('Nonempty complete history contract required')
    if frame.row_key.duplicated().any():
        raise ValueError('Duplicate history key')
    if not frame.match_id.map(lambda v: isinstance(v, str) and bool(v)).all():
        raise ValueError('Character history identities required')
    # This is a disclosed diagnostic proxy, not a safe availability boundary.
    dates = pd.to_datetime(frame.event_date, format='%Y-%m-%d', utc=True, errors='raise')
    frame['label_available_ts'] = dates + pd.Timedelta(days=1)
    frame['data_available_ts'] = frame.label_available_ts
    frame['issue_year'] = dates.dt.year
    frame['issue_code'] = frame.match_id.map(
        lambda key: cutoff.target_issue if key in target_native_ids else 'MATCH:' + key)
    context = prepare_learning_context(frame, cutoff,
        source_hashes={**source_hashes, 'fixture':stable_json_hash(fixture),
            'history_rows':stable_json_hash(rows),
            'target_roster':stable_json_hash(sorted(target_native_ids))},
        repository_root=Path(repository_root),
        implementation_modules=('beidan_backend.fundamental_issue',),
        implementation_distributions=('pandas', 'numpy'),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
            'DATE_PLUS_ONE_UTC_MATCH_HISTORY_DIAGNOSTIC'),
            data_available_column='data_available_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=1))
    verify_learning_context(context, repository_root=Path(repository_root))
    admitted = context.partitions['fit'].copy()
    if admitted[required].isna().any().any():
        raise ValueError('Admitted history has missing factual values')
    for name in ('home_id', 'away_id'):
        if not admitted[name].map(lambda v: isinstance(v, str) and bool(v)).all():
            raise ValueError('Character admitted team identities required')
    for name in ('home_score', 'away_score'):
        if not admitted[name].map(lambda v: not isinstance(v, bool) and
                isinstance(v, (int, float)) and float(v).is_integer() and 0 <= v <= 2147483647).all():
            raise ValueError('Nonnegative integer scores required')
        admitted[name] = admitted[name].astype(int)
    admitted['proxy_available_at'] = admitted.label_available_ts.map(lambda t:t.isoformat())
    return dict(rows=admitted[required + ['proxy_available_at']].to_dict('records'),
                receipt=context.receipt.payload)
