"""Saved-input routing tests, including malformed and future-label boundaries."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from src.fundamentals_integration_weight import select_integration_weights,select_integration_penalty
from src.temporal_learning import Cutoff


def test_fixed_weight_preserves_inputs_tie_prefers_lower_weight_and_q_is_fixed():
    rows=[dict(issue='100313',slot=1,provider_id='0001',weight=w,p_W=.5,p_D=.3,p_L=.2,q_W=.3,q_D=.4,q_L=.3) for w in [1.,0.,.5]]
    frame=pd.DataFrame(rows);original=frame.copy(deep=True)
    kw=dict(cutoffs={'100313':{'1':Cutoff.decision_epoch('100313','2010-03-20T00:00:00Z')}},mode='EXPECTED_RETURN',penalty=0.)
    assert select_integration_weights(frame,**kw)['rows'][0]['weight']==0
    pd.testing.assert_frame_equal(frame,original)
    for weight in [.25,True,None]:
        with pytest.raises(ValueError):select_integration_weights(frame,**dict(kw,mode='FIXED',fixed_weight=weight))
    frame.loc[0,'p_W']=np.nan
    with pytest.raises(ValueError):select_integration_weights(frame,**kw)


def test_penalty_future_and_target_label_values_do_not_affect_admitted_selection():
    history=pd.DataFrame([dict(issue_code=i,issue_year=2010,data_available_ts=t,label_available_ts=t,net_0=a,net_1=b) for i,t,a,b in [('1','2010-01-01Z',3.,1.),('2','2010-01-02Z',3.,1.),('3','2010-01-03Z',0.,1.),('4','2011-01-01Z',0.,1.)]])
    history['data_available_ts']=history.data_available_ts.str.replace('Z','T00:00:00Z');history['label_available_ts']=history.data_available_ts
    kw=dict(cutoff=Cutoff.decision_epoch('3','2010-01-04T00:00:00Z'),penalties=[0.,.25],minimum_issues=2,repository_root=Path.cwd(),source_hashes={'fixture':'b'*64})
    result=select_integration_penalty(history,**kw)
    history.loc[2:,['net_0','net_1']]=np.nan
    mutated=select_integration_penalty(history,**kw)
    assert result['penalty']==mutated['penalty']==0
    with pytest.raises(Exception):select_integration_penalty(history.iloc[1:],**kw)


def test_settlement_mutation_does_not_change_routing_or_ticket_support():
    from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
    rows=[dict(issue='100313',slot=s,provider_id=str(s),weight=w,p_W=.5+.1*w,p_D=.3-.1*w,p_L=.2,q_W=.4,q_D=.3,q_L=.3) for s in range(1,15) for w in [0.,1.]]
    frame=pd.DataFrame(rows);cuts={'100313':{str(s):Cutoff.decision_epoch('100313','2010-03-20T00:00:00Z') for s in range(1,15)}}
    route=select_integration_weights(frame,cutoffs=cuts,mode='EXPECTED_RETURN',penalty=0.)
    chosen=pd.DataFrame(route['rows']);chosen['handicap']=0
    kwargs=dict(cutoffs=cuts['100313'],selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=0)
    plan=n7_baseline_plan(chosen,**kwargs)
    audit=pd.DataFrame([dict(issue='100313',slot=s,provider_id=str(s),handicap=0,actual_direction='W',spf_sp=3.,status='OK') for s in range(1,15)])
    first=settle_n7_baseline(plan,audit)
    audit['actual_direction']='L';audit['spf_sp']=999.
    second=settle_n7_baseline(plan,audit)
    assert first['gross']>second['gross']==0
    assert n7_baseline_plan(chosen,**kwargs)['seal']==plan['seal']
    assert select_integration_weights(frame,cutoffs=cuts,mode='EXPECTED_RETURN',penalty=0.)['seal']==route['seal']
