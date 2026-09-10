"""Audit whether an existing frozen reverse expert can emit POSITIVE at all."""
import math
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash,utc


def reverse_positive_ceiling(frozen, *, cutoff, expected_seal):
    """Prove no positive activation if every sealed leaf is below its threshold.

    This is a model-level bound, NOT reconstructed tree inference. No rounded
    textual rules are executed, no new fit or per-fixture probability is made.
    Future/training replay is not accepted here. If a positive leaf exists,
    returns NEEDS_ROW_INFERENCE instead of fabricating an activation decision.
    Missing features would abstain in the original predictor, never POSITIVE.
    """
    receipt=frozen['receipt']
    if stable_json_hash(receipt)!=frozen.get('seal') or frozen['seal']!=expected_seal:
        raise ValueError('Frozen reverse receipt changed')
    if not isinstance(cutoff,Cutoff) or cutoff.target_issue in receipt['training_issues'] or cutoff.cutoff_ts<=utc(receipt['cutoff_ts']):
        raise ValueError('Explicit strictly later nontraining cutoff required')
    leaves=list(receipt['leaves'].values());bounds=receipt['bounds']
    if not leaves or len(bounds)!=2 or not 0<bounds[0]<bounds[1]<1 or sum(r['n'] for r in leaves)!=receipt['expert_rows']:
        raise ValueError('Complete sealed leaf support required')
    for leaf in leaves:
        if type(leaf['n']) is not int or type(leaf['positive']) is not int or not 0<=leaf['positive']<=leaf['n'] or leaf['n']<1 or not math.isclose(leaf['probability'],(leaf['positive']+1)/(leaf['n']+2),rel_tol=0,abs_tol=1e-15):
            raise ValueError('Invalid frozen Laplace leaf')
    maximum=max(r['probability'] for r in leaves)
    payload=dict(status='NO_POSITIVE_LEAF' if maximum<bounds[1] else 'NEEDS_ROW_INFERENCE',maximum_probability=maximum,
        positive_threshold=bounds[1],model_sha256=receipt['model_sha256'],expert_seal=expected_seal,
        cutoff=cutoff.cutoff_ts.isoformat(),target_issue=cutoff.target_issue,per_fixture_prediction=False,historical_admission=False)
    return dict(**payload,seal=stable_json_hash(payload))
