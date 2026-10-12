"""Independent verification of an explicitly passed in-memory learning context."""
from pathlib import Path
from .core import (
    LearningContext, TemporalContractError, AvailabilityFilter, AvailabilityPolicy,
    PartitionPolicy, WeightingPolicy, EffectiveSamplePolicy, prepare_learning_context,
    stable_frame_hash,
)
from .provenance import verify_implementation_closure


def verify_learning_context(context, *, repository_root):
    """Verify current code, admitted rows, partitions, weights and full receipt.

    Reuses shared admission/partition/weight preparation; no chronology is copied.
    repository_root is explicit. Return the same verified LearningContext without
    mutation, I/O writes or fitting. Raw snapshots and original excluded rows are
    not available here: their replay remains the source adapter's responsibility.
    The original target-row counters are retained evidence, not recomputed from
    admitted rows. Every other receipt field and all partition/ledger values must
    independently reproduce; coordinated weight/ledger edits therefore fail.
    """
    if not isinstance(context,LearningContext):
        raise TemporalContractError('explicit shared learning context required')
    receipt = context.receipt.payload
    verify_implementation_closure(Path(repository_root),receipt['implementation'])
    if stable_frame_hash(context.weight_ledger) != receipt['weight_receipt']['weight_frame_sha256']:
        raise TemporalContractError('saved weight ledger hash differs')
    weights = dict(receipt['weight_receipt']['policy'])
    weights['effective_sample'] = EffectiveSamplePolicy(**weights['effective_sample'])
    availability = receipt['availability']
    rebuilt = prepare_learning_context(context.eligible,context.cutoff,
        source_hashes=receipt['source_hashes'],repository_root=Path(repository_root),
        implementation_modules=tuple(receipt['implementation']['root_modules']),
        implementation_distributions=tuple(receipt['implementation']['distributions']),
        availability=AvailabilityFilter(AvailabilityPolicy(**availability['policy']),
            label_available_column=availability['label_available_column'],
            data_available_column=availability['data_available_column']),
        intended_use=availability['intended_use'],
        partition_policy=PartitionPolicy(**receipt['partition_policy']),
        weighting_policy=WeightingPolicy(**weights))
    for name,value in rebuilt.receipt.payload.items():
        if name not in ('target_rows_seen','target_rows_excluded') and receipt.get(name) != value:
            raise TemporalContractError('saved learning receipt differs: '+name)
    if (not context.eligible.equals(rebuilt.eligible)
        or set(context.partitions) != set(rebuilt.partitions)
        or any(not context.partitions[k].equals(v) for k,v in rebuilt.partitions.items())
        or not context.weights.equals(rebuilt.weights)
        or not context.weight_ledger.equals(rebuilt.weight_ledger)):
        raise TemporalContractError('saved learning context differs from independent replay')
    return context
