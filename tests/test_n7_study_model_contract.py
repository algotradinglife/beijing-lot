from copy import deepcopy
import pytest
from src.n7_study_model_contract import verify_n7_frozen_model
from src.temporal_learning.core import stable_json_hash


def test_reference_contract_rejects_refitting_even_with_valid_seal():
    reference=dict(version='v',receipt=dict(target_issue='001'),parameters=dict(prior=100),cells=[dict(n=2)])
    reference['seal']=stable_json_hash(reference)
    policy=dict(refit=False,version='v',reference_issue='001',reference_model_sha256='hash')
    model=deepcopy(reference);model.pop('seal');model.update(historical_admission=False,
        receipt=dict(frozen_model_sha256='hash',frozen_model_seal=reference['seal'],
                     operation='UNCHANGED_FROZEN_CELLS_NEW_CUTOFF_RECEIPT_NO_FIT'))
    model['seal']=stable_json_hash(model)
    assert verify_n7_frozen_model(model,reference,policy,reference_sha256='hash')['status']=='PASS'
    for field,value in [('parameters',dict(prior=20)),('cells',[dict(n=9)]),('receipt',{})]:
        changed=deepcopy(model);changed[field]=value;changed.pop('seal');changed['seal']=stable_json_hash(changed)
        with pytest.raises(ValueError,match='unchanged frozen'):
            verify_n7_frozen_model(changed,reference,policy,reference_sha256='hash')
    with pytest.raises(ValueError,match='identity'):
        verify_n7_frozen_model(model,reference,{**policy,'refit':True},reference_sha256='hash')
    with pytest.raises(ValueError,match='identity'):
        verify_n7_frozen_model(model,reference,policy,reference_sha256='other')
