"""Fixed issue-cadence schedules and prior contexts for frozen block research.

No fitting, storage or inference of label availability. A trusted target epoch
calendar defines exclusions even when a label claims an impossible early date.
"""
from pathlib import Path


from .core import (Cutoff, TemporalContractError, WalkForwardRunner,
                   prepare_learning_context, stable_json_hash)


def frozen_block_schedule(targets, *, cadence):
    """Return chronological issue blocks, each bound to its first decision epoch.

    targets: DataFrame issue_code/fixture_decision_ts, potentially many fixtures
    per issue. cadence is a positive integer issue count, not a calendar interval.
    Returned target rows contain no labels. Equal-time issues may share an epoch
    but never a history update based on each other's results.
    """
    if type(cadence) is not int or cadence < 1:
        raise TemporalContractError('Positive integer cadence required')
    epochs = WalkForwardRunner().run(targets, lambda cutoff, _: dict(
        issue=cutoff.target_issue, cutoff_ts=cutoff.cutoff_ts.isoformat()))
    blocks = []
    for start in range(0, len(epochs), cadence):
        members = epochs[start:start + cadence]
        body = dict(cadence=cadence, block_index=len(blocks),
                    fit_issue=members[0]['issue'], fit_cutoff_ts=members[0]['cutoff_ts'],
                    targets=members,
                    excluded_issues=[r['issue'] for r in epochs[start:]])
        blocks.append(dict(body, seal=stable_json_hash(body)))
    return blocks


def prepare_block_context(history, cutoff, *, block, repository_root,
                          source_hashes, implementation_modules,
                          implementation_distributions, availability,
                          intended_use, partition_policy, weighting_policy):
    """Prepare shared learning context excluding the current/later target blocks.

    Requires an unmodified schedule block and its exact fit cutoff. The common
    context enforces all other clocks, availability, weights, ESS and receipts.
    Returns LearningContext; binds the schedule seal to its source/cache identity.
    """
    body = {k: v for k, v in block.items() if k != 'seal'}
    if stable_json_hash(body) != block.get('seal'):
        raise TemporalContractError('Frozen block seal mismatch')
    expected = Cutoff.decision_epoch(block['fit_issue'], block['fit_cutoff_ts'])
    if not isinstance(cutoff, Cutoff) or cutoff != expected:
        raise TemporalContractError('Frozen block fit cutoff mismatch')
    column = availability.source_issue_column
    if column not in history or history[column].isna().any():
        raise TemporalContractError('Missing source issue identities')
    prior = history.loc[~history[column].astype(str).isin(block['excluded_issues'])].copy()
    sources = dict(source_hashes, frozen_block=block['seal'])
    return prepare_learning_context(prior, cutoff,
        repository_root=Path(repository_root), source_hashes=sources,
        implementation_modules=tuple(implementation_modules) + (__name__,),
        implementation_distributions=implementation_distributions,
        availability=availability, intended_use=intended_use,
        partition_policy=partition_policy, weighting_policy=weighting_policy)


def verify_block_target(block, cutoff):
    """Require an exact target identity AND timestamp in a sealed frozen block."""
    body = {k: v for k, v in block.items() if k != 'seal'}
    if stable_json_hash(body) != block.get('seal') or not isinstance(cutoff, Cutoff):
        raise TemporalContractError('Invalid frozen block or target cutoff')
    matches = [r for r in block['targets'] if r['issue'] == cutoff.target_issue]
    if len(matches) != 1 or cutoff != Cutoff.decision_epoch(
            matches[0]['issue'], matches[0]['cutoff_ts']):
        raise TemporalContractError('Target outside frozen block')
    return True
