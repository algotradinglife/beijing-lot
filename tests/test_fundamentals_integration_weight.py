import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_integration_weight import select_integration_weights


def test_fixed_and_ev_routing_keep_market_constant_and_reject_labels():
    frame=pd.DataFrame([dict(issue='100313',slot=1,provider_id='01',weight=w,p_W=p,p_D=.2,p_L=.8-p,q_W=.3,q_D=.3,q_L=.4) for w,p in [(0,.4),(.5,.5),(1,.6)]])
    cuts={'100313':{'1':Cutoff.decision_epoch('100313','2010-03-20T00:00:00Z')}}
    kw=dict(cutoffs=cuts,mode='EXPECTED_RETURN',penalty=0)
    result=select_integration_weights(frame,**kw)
    assert result['rows'][0]['weight']==1
    assert select_integration_weights(frame,**dict(kw,penalty=1))['rows'][0]['weight']==0
    assert select_integration_weights(frame,**dict(kw,mode='FIXED',fixed_weight=.5))['rows'][0]['weight']==.5
    pd.testing.assert_frame_equal(frame,frame.copy())
    for bad in [frame.assign(actual_direction='W'),pd.concat([frame,frame]),frame.assign(q_W=.5),frame.assign(weight=2),frame.iloc[:0]]:
        with pytest.raises(ValueError):select_integration_weights(bad,**kw)
    bad=frame.copy();bad.loc[1,['q_W','q_D']]=[.2,.4]
    with pytest.raises(ValueError,match='must not vary'):select_integration_weights(bad,**kw)
    with pytest.raises(ValueError):select_integration_weights(frame,**dict(kw,penalty=-1))


def test_penalty_selection_excludes_target_and_future_mutations():
    from pathlib import Path
    from src.temporal_learning import Cutoff
    from src.fundamentals_integration_weight import select_integration_penalty
    frame=pd.DataFrame([dict(issue_code=i,issue_year=2010,label_available_ts=t,data_available_ts=t,net_0=a,net_1=b) for i,t,a,b in [('1','2010-01-01T00:00Z',1,2),('2','2010-01-02T00:00Z',1,2),('3','2010-01-03T00:00Z',999,0)]])
    kw=dict(cutoff=Cutoff.decision_epoch('3','2010-01-04T00:00Z'),penalties=[0,.1],minimum_issues=2,repository_root=Path.cwd(),source_hashes={'synthetic':'a'*64})
    r=select_integration_penalty(frame,**kw);assert r['penalty']==.1
    frame.loc[2,'net_0']=-999
    assert select_integration_penalty(frame,**kw)['penalty']==r['penalty']
