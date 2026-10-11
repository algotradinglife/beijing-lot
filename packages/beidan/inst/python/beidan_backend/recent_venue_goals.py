"""Domain goal-rate estimator; admission, recency weights and replay are shared.

Historical date proxies only. Per-team match distributions retain long and
recent masses separately; means are derived from their normalized mixture.
No market, target labels, fetching, writes or parameter search.
"""
from pathlib import Path
import hashlib
import pandas as pd
from .fundamental_issue import admit_fixture_history
from .temporal_learning import (AvailabilityFilter, AvailabilityPolicy,
    PartitionPolicy, WeightingPolicy, prepare_learning_context)
from .temporal_learning.context_replay import verify_learning_context
from .temporal_learning.core import stable_json_hash


def estimate_recent_venue_goals(rows, fixture, target_native_ids, cutoff,
                                source_hashes, repository_root, policy):
    """Return goal means, normalized empirical components and shared receipts.

    Policy explicitly supplies recent_n, alpha, minimum_matches and minimum_ess.
    Uses each team's own venue history, not head-to-head or all-venue records.
    Missing chronology, duplicate matches, sparse support or changed code fail.
    Opponent strength and lineups are not estimated by this bounded prototype.
    """
    if (set(policy) != {'recent_n', 'alpha', 'minimum_matches', 'minimum_ess'}
        or type(policy['recent_n']) is not int or policy['recent_n'] < 1
        or type(policy['minimum_matches']) is not int
        or policy['minimum_matches'] < policy['recent_n']
        or not 0 < policy['alpha'] < 1 or policy['minimum_ess'] <= 0):
        raise ValueError('Explicit valid recent venue policy required')
    root = Path(repository_root)
    bindings = {**source_hashes, 'recent_policy': stable_json_hash(policy),
                'R_wrapper': hashlib.sha256((root / 'packages/beidan/R/recent_venue_goals.R').read_bytes()).hexdigest()}
    admitted = admit_fixture_history(rows, fixture, target_native_ids, cutoff,
                                     bindings, root)
    frame = pd.DataFrame(admitted['rows'])
    results, components, receipts = [], [], []
    for role, scope, id_col, score_col, against_col in (
        ('home', 'home_recent', 'home_id', 'home_score', 'away_score'),
        ('away', 'away_recent', 'away_id', 'away_score', 'home_score')):
        team_id = fixture[role + '_id']
        matches = frame.loc[(frame.scope == scope) & (frame[id_col] == team_id)].copy()
        if matches.match_id.duplicated().any() or len(matches) < policy['minimum_matches']:
            raise ValueError('Sparse or duplicate venue history: ' + role)
        # These timestamps are exported by the authoritative history adapter.
        matches['label_available_ts'] = pd.to_datetime(matches.proxy_available_at, utc=True)
        matches['data_available_ts'] = matches.label_available_ts
        matches['issue_year'] = matches.label_available_ts.dt.year
        matches['issue_code'] = 'MATCH:' + matches.match_id
        context = prepare_learning_context(matches, cutoff, source_hashes={
            **bindings, 'admission_receipt': stable_json_hash(admitted['receipt']),
            'venue_rows': stable_json_hash(matches[['row_key', 'match_id', score_col, against_col]].to_dict('records')),
            'fixture': stable_json_hash(fixture), 'role': stable_json_hash(role)},
            repository_root=root,
            implementation_modules=('beidan_backend.recent_venue_goals',),
            implementation_distributions=('pandas', 'numpy'),
            availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy(
                'DATE_PLUS_ONE_UTC_MATCH_HISTORY_DIAGNOSTIC'), data_available_column='data_available_ts'),
            intended_use='HISTORICAL_DIAGNOSTIC',
            partition_policy=PartitionPolicy('FIXED_PRIOR_FIT', 0, 0, 1),
            weighting_policy=WeightingPolicy.recent_state_blend(
                policy['recent_n'], policy['alpha'], minimum_ess=policy['minimum_ess']))
        verify_learning_context(context, repository_root=root)
        fit = context.partitions['fit']
        weights = context.weight_ledger
        if len(fit) != len(weights) or len(fit) < policy['minimum_matches']:
            raise ValueError('Insufficient shared fit support')
        gf = fit[score_col].to_numpy(); ga = fit[against_col].to_numpy()
        long = weights.long_mass.to_numpy() / (1 - policy['alpha'])
        recent = weights.recent_mass.to_numpy() / policy['alpha']
        mixture = weights.total_mass.to_numpy()
        distribution = pd.DataFrame({'goals_for': gf, 'goals_against': ga,
            'long': long, 'recent': recent, 'mixture': mixture}).groupby(
                ['goals_for', 'goals_against'], as_index=False).sum()
        if not all(abs(distribution[c].sum() - 1) < 1e-10 for c in ('long', 'recent', 'mixture')):
            raise ValueError('Component probability mass mismatch')
        results.append(dict(role=role, matches=len(fit),
            recent_matches=int((recent > 0).sum()),
            long_for=float(gf @ long), long_against=float(ga @ long),
            recent_for=float(gf @ recent), recent_against=float(ga @ recent),
            goals_for=float(gf @ mixture), goals_against=float(ga @ mixture),
            ess=float(context.receipt.payload['weight_receipt']['effective_sample_size'])))
        components.append(dict(role=role, distributions=distribution.to_dict('records'),
            ledger=weights.assign(match_id=fit.match_id.to_numpy()).to_json(orient='records', date_format='iso')))
        receipts.append(context.receipt.payload)
    home, away = results
    lambdas = dict(lambda_home=(home['goals_for'] + away['goals_against']) / 2,
                   lambda_away=(away['goals_for'] + home['goals_against']) / 2)
    if min(lambdas.values()) <= 0:
        raise ValueError('Positive goal means required')
    return dict(parameters=lambdas, rates=results, components=components,
                admission_receipt=admitted['receipt'], receipts=receipts,
                policy=policy, cutoff=cutoff.cutoff_ts.isoformat(),
                output_hash=stable_json_hash({'parameters': lambdas, 'rates': results, 'components': components}))
