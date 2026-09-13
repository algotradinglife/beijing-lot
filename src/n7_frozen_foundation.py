"""Bind unchanged draw-cell statistics to new target cutoffs without refitting."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pandas as pd

from src.temporal_learning import (AvailabilityFilter, AvailabilityPolicy,
    PartitionPolicy, WeightingPolicy, prepare_learning_context, temporal_client,
    verify_implementation_closure, TemporalContractError)
from src.temporal_learning.core import stable_json_hash, utc
from src.temporal_learning.diagnostic_labels import diagnostic_label_clock


def read_frozen_draw_history(*, factors_path, factors_sha256, audit_path,
                            audit_sha256, cutoff, label_delay_hours):
    """Replay original training-table construction from two explicit old snapshots.

    This is an input reader, not a fit. Hashes and unique native join keys must
    match. Shared diagnostic clocks require all supplied labels before cutoff;
    no target settlement is read. Return the original ordered pandas frame for
    bind_frozen_draw_foundation to check against its exact admitted-history hash.
    No writes. Model and source evidence stay historical diagnostic only.
    """
    payloads=[]
    for path,digest in ((factors_path,factors_sha256),(audit_path,audit_sha256)):
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise TemporalContractError('Reference history file changed')
        payloads.append(json.loads(raw))
    factors,audit=payloads
    history=pd.DataFrame(factors['rows'])
    labels=pd.DataFrame(audit['rows'])
    history=history.merge(labels[['issue','slot','provider_id','actual_direction']],
        on=['issue','slot','provider_id'],validate='one_to_one',how='left').rename(columns={'actual_direction':'actual'})
    if history.empty or not history.actual.isin(['W','D','L']).all():
        raise TemporalContractError('Missing or invalid reference history labels')
    history['fixture_decision_ts']=[factors['cutoffs'][str(r.issue)][str(r.slot)] for r in history.itertuples()]
    history['label_available_ts']=[diagnostic_label_clock(t,cutoff=cutoff,delay_hours=label_delay_hours)
                                   for t in history.fixture_decision_ts]
    history['issue_code']=history.issue.astype(str)
    history['issue_year']=pd.to_datetime(history.fixture_decision_ts,utc=True).dt.year
    return history


@temporal_client
def bind_frozen_draw_foundation(history, cutoff, *, model_path, model_sha256,
                               reference_repository_root, repository_root, source_hashes):
    """Return a new cutoff receipt with byte-identical learned cells/parameters.

    This supports only the fixed-original-history, equal-weight balance model.
    The reference model file and its original implementation snapshot are bound.
    Shared temporal_learning admits history at the target cutoff. Its admitted
    table hash and statistical weights must match the original training
    evidence exactly; changed/smaller/larger eligible histories fail. No fitting,
    tuning, new labels, or numerical cell updates occur. Later-source rows may
    be excluded by the shared boundary but cannot alter the admitted table.
    All paths/hashes are explicit. Reads model bytes; writes nothing. Availability
    remains diagnostic. Errors are TemporalContractError or filesystem errors.
    """
    path = Path(model_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=model_sha256:
        raise TemporalContractError('Frozen model file changed')
    model = json.loads(raw)
    if (stable_json_hash({k:v for k,v in model.items() if k!='seal'})!=model.get('seal')
            or model.get('historical_admission') is not False
            or model.get('version')!='market-balance-draw-1.0.0-diagnostic'):
        raise TemporalContractError('Invalid frozen balance model')
    old = model['receipt']
    if cutoff.cutoff_ts <= utc(old['cutoff_ts']) or cutoff.target_issue==old['target_issue']:
        raise TemporalContractError('New target must follow reference cutoff')
    verify_implementation_closure(Path(reference_repository_root),old['implementation'])
    sources = dict(source_hashes)
    if str(path.resolve()) in sources and sources[str(path.resolve())]!=model_sha256:
        raise TemporalContractError('Conflicting model source hash')
    sources[str(path.resolve())] = model_sha256
    context = prepare_learning_context(history,cutoff,repository_root=Path(repository_root),
        source_hashes=sources,
        implementation_modules=('src.n7_frozen_foundation','src.probability_foundation_draw',
                                'src.temporal_learning.diagnostic_labels'),
        implementation_distributions=('numpy','pandas'),
        availability=AvailabilityFilter(policy=AvailabilityPolicy.historical_proxy('FIXTURE_PLUS_6H_DIAGNOSTIC'),
                                        data_available_column='fixture_decision_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy(kind='FIXED_PRIOR_FIT',tune_years=0,calibration_years=0),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=100))
    receipt = dict(context.receipt.payload)
    for field in ('admitted_history_sha256','partition_policy'):
        if receipt[field]!=old[field]:
            raise TemporalContractError('Frozen training evidence differs: '+field)
    # Shared ledger clocks/ages necessarily change at a new cutoff. Every
    # statistical weight, component mass and policy must remain unchanged.
    current_weights = {k:v for k,v in receipt['weight_receipt'].items() if k!='weight_frame_sha256'}
    old_weights = {k:v for k,v in old['weight_receipt'].items() if k!='weight_frame_sha256'}
    ledger = json.loads(context.weight_ledger.to_json(orient='records',date_format='iso'))
    clock_columns = {'cutoff_identity','cutoff_ts','age_days'}
    if (current_weights!=old_weights or
            [{k:v for k,v in row.items() if k not in clock_columns} for row in ledger]!=
            [{k:v for k,v in row.items() if k not in clock_columns} for row in model['weight_ledger']]):
        raise TemporalContractError('Frozen training weights differ')
    if receipt['availability']['policy']!=old['availability']['policy']:
        raise TemporalContractError('Frozen availability policy differs')
    result = deepcopy(model)
    result.pop('seal')
    receipt.update(version=model['version'],parameters=deepcopy(model['parameters']),
        frozen_model_sha256=model_sha256,frozen_model_seal=model['seal'],
        reference_implementation=deepcopy(old['implementation']),
        operation='UNCHANGED_FROZEN_CELLS_NEW_CUTOFF_RECEIPT_NO_FIT',
        parameter_cache_key=stable_json_hash(dict(context_cache=receipt['cache_key'],
            parameters=model['parameters'],version=model['version'],frozen_model_sha256=model_sha256)))
    result['receipt'] = receipt
    result['weight_ledger'] = ledger
    return dict(result,seal=stable_json_hash(result))
