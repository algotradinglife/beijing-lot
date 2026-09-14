from copy import deepcopy
import pytest
from src.n7_sp_refill import materialize_refill
from src.temporal_learning.core import stable_json_hash


def test_refill_full_states_identity_and_failures():
    fixtures=[dict(issue='001',slot=i,provider_id=str(i),handicap=0,
                   p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2) for i in range(8)]
    cuts={str(i):'2010-01-01T00:00:00+00:00' for i in range(8)}
    old=dict(id=0,fixture_indices=list(range(7)),origin='ORIGINAL',options={},enumeration={})
    b=dict(issue='001',cutoffs=cuts,sleeves=[old],historical_admission=False,
           expanded_pool=dict(fixtures=fixtures,encoded_tickets=[[3*i for i in range(7)]],minimum_scalar_rank=[1]))
    b['seal']=stable_json_hash(b)
    groups=[dict(sleeve_id=0,fixtures=list(range(1,8)),origin='RETAINED'),
            dict(sleeve_id=1,fixtures=list(range(2,9)),origin='REFILL_TOP2')]
    z=materialize_refill(b,groups,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    assert z['sleeves'][0]==old
    e=z['sleeves'][1]['enumeration']
    assert len(e['states'])==2187
    assert sum(e['probability'])==pytest.approx(1)
    assert e['estimated_payout'][0]==pytest.approx(1.3/.5**7)
    assert z['sleeves'][1]['fixture_indices']==list(range(1,8))
    assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
    assert b['sleeves']==[old]
    assert z==materialize_refill(b,groups,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    for invalid in [[],groups+[groups[1]], [dict(sleeve_id=0,fixtures=list(range(2,9)),origin='RETAINED')]]:
        with pytest.raises(ValueError):materialize_refill(b,invalid,cutoffs=cuts,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):materialize_refill(b,groups,cutoffs={},unit_cny=2,payout_factor=.65)
    bad=deepcopy(b);bad['issue']='002'
    with pytest.raises(ValueError):materialize_refill(bad,groups,cutoffs=cuts,unit_cny=2,payout_factor=.65)
