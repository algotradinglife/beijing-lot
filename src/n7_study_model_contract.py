"""Require fixed-reference semantics before accepting research predictions."""
from src.temporal_learning.core import stable_json_hash


def verify_n7_frozen_model(model, reference, policy, *, reference_sha256):
    """Validate model seals, reference identity and exactly unchanged fit values.

    Caller verifies the reference file bytes against reference_sha256 first.
    This pure validator does not fit, tune or alter probabilities. Parameters and
    learned cells must equal the frozen reference, not merely have valid seals.
    Missing bindings, a refitted artifact or altered cells raise ValueError.
    """
    if (policy['refit'] is not False or reference_sha256!=policy['reference_model_sha256'] or
            reference['version']!=policy['version'] or
            reference['receipt']['target_issue']!=policy['reference_issue']):
        raise ValueError('Configured frozen reference identity mismatch')
    for artifact in (model,reference):
        if artifact['seal']!=stable_json_hash({k:v for k,v in artifact.items() if k!='seal'}):
            raise ValueError('Model seal mismatch')
    receipt=model['receipt']
    if (model['version']!=policy['version'] or model['historical_admission'] is not False or
            receipt.get('frozen_model_sha256')!=reference_sha256 or
            receipt.get('frozen_model_seal')!=reference['seal'] or
            receipt.get('operation')!='UNCHANGED_FROZEN_CELLS_NEW_CUTOFF_RECEIPT_NO_FIT' or
            model['parameters']!=reference['parameters'] or model['cells']!=reference['cells']):
        raise ValueError('Candidate model is not the unchanged frozen reference')
    return dict(status='PASS',reference_sha256=reference_sha256,model_seal=model['seal'])
