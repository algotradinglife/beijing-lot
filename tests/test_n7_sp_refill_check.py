from copy import deepcopy
import numpy as np
import pytest
from src.n7_sp_refill_check import check_refill_prefixes
from src.temporal_learning.core import stable_json_hash


def test_prefix_checker_detects_rank_gate_and_physical_corruption():
    fs=[dict(p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2) for _ in range(7)]
    cuts={'a':'epoch'}
    b=dict(cutoffs=cuts,expanded_pool=dict(fixtures=fs),sleeves=[dict(id=5,fixture_indices=list(range(7)))])
    states=np.indices((3,)*7).reshape(7,-1).T
    b['sleeves'][0]['enumeration']=dict(probability=np.prod(np.array([.5,.3,.2])[states],axis=1).tolist(),
        expected_contribution=[1.3]*2187)
    p=dict(cutoffs=cuts,fixtures=fs,sleeve_keys=[dict(sleeve_id=5,fixture_indices=list(range(7)),
      state_ids=[0],depth=1,coverage=.5**7,expected_gross=1.3,stake=2)],
      fixture_indices=[list(range(7))],outcomes=[[0]*7],stake=2,groups=1,cash_cny=0,budget_cny=2,
      evaluation=dict(expected_net=-.7))
    p['seal']=stable_json_hash(p)
    assert check_refill_prefixes(p,b,minimum_sp=1.3,unit_cny=2,payout_factor=.65)['tickets']==1
    with pytest.raises(ValueError):check_refill_prefixes(p,b,minimum_sp=3,unit_cny=2,payout_factor=.65)
    for field in ('coverage','state_ids'):
        bad=deepcopy(p);bad.pop('seal');bad['sleeve_keys'][0][field]=.2 if field=='coverage' else [2186]
        bad['seal']=stable_json_hash(bad)
        with pytest.raises(ValueError):check_refill_prefixes(bad,b,minimum_sp=1.3,unit_cny=2,payout_factor=.65)
    bad=deepcopy(p);bad['outcomes']=[[1]*7]
    with pytest.raises(ValueError):check_refill_prefixes(bad,b,minimum_sp=1.3,unit_cny=2,payout_factor=.65)
    tied=deepcopy(b)
    for f in tied['expanded_pool']['fixtures']:
        for k in f:f[k]=1/3
    tied['sleeves'][0]['enumeration']=dict(probability=[(1/3)**7]*2187,expected_contribution=[1.3]*2187)
    bad=deepcopy(p);bad.pop('seal');bad['fixtures']=tied['expanded_pool']['fixtures']
    bad['sleeve_keys'][0].update(state_ids=[1],coverage=(1/3)**7)
    bad['outcomes']=[[0,0,0,0,0,0,1]];bad['seal']=stable_json_hash(bad)
    with pytest.raises(ValueError,match='canonical'):
        check_refill_prefixes(bad,tied,minimum_sp=1.3,unit_cny=2,payout_factor=.65)
