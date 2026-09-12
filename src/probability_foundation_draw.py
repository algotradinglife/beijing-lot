"""Market score foundation with cutoff-bound strength/market draw correction."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from src.temporal_learning import (Cutoff, AvailabilityFilter, AvailabilityPolicy,
    PartitionPolicy, WeightingPolicy, prepare_learning_context, temporal_client,
    verify_implementation_closure, TemporalContractError)
from src.temporal_learning.core import stable_json_hash


def draw_cells(frame, cutoff, *, market_edges, strength_edges):
    """Return integer bin pairs; probabilities are fractions, endpoints 0/1 allowed."""
    if not isinstance(cutoff, Cutoff):
        raise TemporalContractError('Explicit cutoff required')
    result = frame.copy()
    for column, edges, output in [('q_D', market_edges, 'market_bin'), ('p_D', strength_edges, 'strength_bin')]:
        values = result[column].to_numpy(float)
        edges = np.asarray(edges, dtype=float)
        if (not np.isfinite(edges).all() or len(edges) < 2 or edges[0] != 0 or edges[-1] != 1
                or (np.diff(edges) <= 0).any() or not np.isfinite(values).all()
                or ((values < 0) | (values > 1)).any()):
            raise TemporalContractError('Invalid probability/bin contract')
        result[output] = np.searchsorted(edges[1:-1], values, side='right')
    return result


@temporal_client
def fit_draw_foundation(history, cutoff, *, repository_root, source_hashes,
                        market_edges, strength_edges, prior_strength, epsilon, version):
    """Fixed-policy historical diagnostic fit; no target labels or parameter search.

    Each bin learns its observed draw rate, shrunk toward the fixture market rate.
    Shared context owns chronology, ESS, partitions, weights, hashes and receipts.
    Requires explicit proxy clocks; never authorizes prospective decisions.
    """
    if (not np.isfinite(prior_strength) or prior_strength <= 0 or not 0 < epsilon < .01
            or version != 'market-strength-draw-1.0.0-diagnostic'):
        raise TemporalContractError('Invalid fixed foundation parameters/version')
    context = prepare_learning_context(history, cutoff, repository_root=Path(repository_root),
        source_hashes=source_hashes, implementation_modules=('src.probability_foundation_draw', 'src.temporal_learning.diagnostic_labels'),
        implementation_distributions=('numpy','pandas'),
        availability=AvailabilityFilter(policy=AvailabilityPolicy.historical_proxy('FIXTURE_PLUS_6H_DIAGNOSTIC'),
                                        data_available_column='fixture_decision_ts'),
        intended_use='HISTORICAL_DIAGNOSTIC',
        partition_policy=PartitionPolicy(kind='FIXED_PRIOR_FIT',tune_years=0,calibration_years=0),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=100))
    rows = draw_cells(context.partitions['fit'], cutoff, market_edges=market_edges,strength_edges=strength_edges)
    if (rows.duplicated(['issue_code','slot','provider_id']).any()
            or not rows.actual.isin(['W','D','L']).all()):
        raise TemporalContractError('Invalid history identities/outcomes')
    rows['weight'] = context.weights.loc[rows.index]
    rows['draw_mass'] = rows.weight * rows.actual.eq('D').astype(float)
    cells = rows.groupby(['market_bin','strength_bin'],as_index=False).agg(
        n=('weight','sum'),draws=('draw_mass','sum'))
    cells['observed_draw_rate'] = cells.draws/cells.n
    parameters = dict(market_edges=list(market_edges),strength_edges=list(strength_edges),
                      prior_strength=float(prior_strength),epsilon=float(epsilon))
    receipt = dict(context.receipt.payload)
    receipt.update(version=version,parameters=parameters,
        parameter_cache_key=stable_json_hash(dict(context_cache=receipt['cache_key'],parameters=parameters,version=version)))
    artifact = dict(version=version,historical_admission=False,parameters=parameters,
                    cells=cells.to_dict('records'),receipt=receipt,
                    weight_ledger=json.loads(context.weight_ledger.to_json(orient='records',date_format='iso')))
    return dict(artifact,seal=stable_json_hash(artifact))


def predict_draw_foundation(artifact, frame, cutoff, *, repository_root):
    """Apply one immutable cutoff artifact to label-free fixture probabilities.

    Returns p/q inputs plus calibrated W/D/L and source-bin support. Keeps market
    W:L ratio; scores must be projected by the corresponding R grid adapter.
    """
    body = {k:v for k,v in artifact.items() if k!='seal'}
    if stable_json_hash(body) != artifact.get('seal'):
        raise TemporalContractError('Artifact seal mismatch')
    receipt = artifact['receipt']
    if (receipt['cutoff_identity'] != cutoff.identity or receipt['cutoff_ts'] != cutoff.cutoff_ts.isoformat()
            or artifact['historical_admission'] is not False):
        raise TemporalContractError('Artifact cutoff/admission mismatch')
    verify_implementation_closure(Path(repository_root),receipt['implementation'])
    if (frame.empty or frame.duplicated(['issue','slot','provider_id']).any()
            or set(frame.issue.astype(str)) != {cutoff.target_issue}
            or pd.to_datetime(frame.fixture_decision_ts,utc=True).isna().any()
            or (pd.to_datetime(frame.fixture_decision_ts,utc=True)<cutoff.cutoff_ts).any()
            or 'actual' in frame):
        raise TemporalContractError('Label-free exact target issue and valid clocks required')
    q = frame[['q_W','q_D','q_L']].to_numpy(float)
    if not np.isfinite(q).all() or (q<=0).any() or not np.allclose(q.sum(axis=1),1,atol=1e-10,rtol=0):
        raise TemporalContractError('Strictly positive normalized market probabilities required')
    params = artifact['parameters']
    result = draw_cells(frame,cutoff,market_edges=params['market_edges'],strength_edges=params['strength_edges'])
    result = result.merge(pd.DataFrame(artifact['cells']),on=['market_bin','strength_bin'],how='left',validate='many_to_one')
    result[['n','draws']] = result[['n','draws']].fillna(0)
    result['new_D'] = np.clip((result.draws+params['prior_strength']*result.q_D)/
        (result.n+params['prior_strength']),params['epsilon'],1-params['epsilon'])
    result['correction'] = result.new_D-result.q_D
    ratio = (1-result.new_D)/(1-result.q_D)
    result['new_W'],result['new_L'] = result.q_W*ratio,result.q_L*ratio
    result['model_seal'] = artifact['seal']
    result['version'] = artifact['version']
    return result
