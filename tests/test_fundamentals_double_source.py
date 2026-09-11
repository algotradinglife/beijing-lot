import copy
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_consensus_portfolio import consensus_component
from src.fundamentals_double_source import paired_double_source


@pytest.fixture
def source():
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for s in range(1,8)}
    rows=[dict(issue='001',slot=s,provider_id=str(s),handicap=1,p_W=.6,p_D=.3,p_L=.1,
        q_W=.7,q_D=.2 if s<7 else .1,q_L=.1 if s<7 else .2) for s in range(1,8)]
    part=consensus_component(pd.DataFrame(rows),{s:'A' if s<3 else 'D' if s<7 else 'C' for s in range(1,8)},
        cutoffs=cuts,complement=False,unit_cny=2,payout_factor=.65,seed=0)
    body=dict(issue='001',components=[part],stake=64,cutoffs=part['cutoffs'])
    return dict(**body,seal=stable_json_hash(body)),cuts


@pytest.mark.parametrize('mode',['BASELINE','MARKET'])
def test_paired_support_preserves_fixtures_singles_funding(source,mode):
    plan,cuts=source;before=copy.deepcopy(plan)
    z=paired_double_source(plan,cutoffs=cuts,double_source=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert plan==before and z['stake']==64 and z['cash_cny']==960
    a=plan['components'][0];b=z['components'][0]
    assert [(r['slot'],r['support']) for r in a['legs'][:6]]==[(r['slot'],r['support']) for r in b['legs'][:6]]
    assert b['legs'][6]['support']==('31' if mode=='BASELINE' else '30')
    assert len(b['tickets'])==32 and len({t['code'] for t in b['tickets']})==32
    if mode=='BASELINE':assert a['tickets']==b['tickets']
    assert z['model_any_hit'] is None
    assert z['seal']==stable_json_hash({k:v for k,v in z.items() if k!='seal'})
    altered=copy.deepcopy(plan);altered['components'][0]['legs'][0]['p_W']=.1
    with pytest.raises(ValueError):paired_double_source(altered,cutoffs=cuts,double_source=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
    with pytest.raises(ValueError):paired_double_source(plan,cutoffs={},double_source=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
    bad={s:Cutoff.decision_epoch('001','2011-01-01T00:00:00Z') for s in cuts}
    with pytest.raises(ValueError):paired_double_source(plan,cutoffs=bad,double_source=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)


def test_empty_portfolio_keeps_cash_and_rejects_invalid_mode():
    body=dict(issue='001',components=[],stake=0,cutoffs={})
    plan=dict(**body,seal=stable_json_hash(body))
    z=paired_double_source(plan,cutoffs={},double_source='MARKET',budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert z['components']==[] and z['cash_cny']==1024
    with pytest.raises(ValueError):paired_double_source(plan,cutoffs={},double_source='BAD',budget_cny=1024,unit_cny=2,payout_factor=.65)
