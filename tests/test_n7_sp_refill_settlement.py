from copy import deepcopy
import pytest
from src.temporal_learning.core import stable_json_hash
from src.n7_sp_refill_settlement import settle_refill_plans


def test_refill_settlement_uses_new_fixture_identity_and_single_factor():
    fixtures=[dict(issue='001',slot=i,provider_id=str(i),handicap=0) for i in range(8)]
    p=dict(issue='001',arm='REFILL',seed=1,fixtures=fixtures,fixture_indices=[list(range(1,8))],
           outcomes=[[0]*7],groups=1,stake=2,cash_cny=0,budget_cny=2,unit_cny=2,payout_factor=.65,
           sleeve_keys=[dict(sleeve_id=99,fixture_indices=list(range(1,8)),state_ids=[0])])
    p['seal']=stable_json_hash(p)
    audit=[dict(f,actual_direction='W' if f['slot'] else 'L',status='OK',spf_sp=2.) for f in fixtures]
    out=settle_refill_plans([p],audit)[0]
    assert out['gross']==pytest.approx(2*.65*2**7)
    assert out['hits']==1
    changed=deepcopy(audit);changed[1]['actual_direction']='D'
    assert settle_refill_plans([p],changed)[0]['gross']==0
    changed=deepcopy(audit);changed[1]['spf_sp']=None
    with pytest.raises(ValueError,match='Unsettled'):settle_refill_plans([p],changed)
    with pytest.raises(ValueError,match='duplicate'):settle_refill_plans([p,p],audit)
    bad=deepcopy(p);bad['stake']=4
    with pytest.raises(ValueError,match='changed'):settle_refill_plans([bad],audit)
    with pytest.raises(ValueError,match='Empty'):settle_refill_plans([],audit)
