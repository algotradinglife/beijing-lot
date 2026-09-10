"""Fixed-rule routing and matched-stake contracts, including label mutations."""
from pathlib import Path
import copy
import pandas as pd
import pytest
from src.fundamentals_decision_chain import route_decision_chain,limit_decision_chain_plan
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline
from src.temporal_learning import Cutoff


@pytest.fixture
def inputs():
    rows=[]
    for s in range(1,15):
        for w in [0,.25,.5]:
            p=[.6-.6*w,.1+.4*w,.3+.2*w] if s<=7 else [.6,.25,.15]
            rows.append(dict(issue='100101',slot=s,provider_id=f'{s:04}',handicap=0,weight=w,
                **dict(zip(['p_W','p_D','p_L'],p)),q_W=.5,q_D=.3,q_L=.2))
    cuts={str(s):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for s in range(1,15)}
    return pd.DataFrame(rows),dict(cutoffs=cuts,repository_root=Path.cwd(),source_hashes={'fixture':'a'*64})


def test_keep_reduce_skip_and_tie_contract(inputs):
    frame,kw=inputs
    # Slot 1: current .30/.30/.40 ties favour W over D, so no conflict.
    # Make D strictly greater; now market's W is excluded by D/L.
    frame.loc[(frame.slot<=7)&frame.weight.eq(.5),['p_W','p_D','p_L']]=[.29,.31,.4]
    saved=frame.copy(deep=True)
    keep=route_decision_chain(frame,policy='KEEP',fallback_weight=0,**kw)
    reduce=route_decision_chain(frame,policy='REDUCE',fallback_weight=.25,**kw)
    skip=route_decision_chain(frame,policy='SKIP',fallback_weight=0,**kw)
    assert sum(r['conflict'] for r in keep['ledger'])==7
    assert len(keep['rows'])==len(reduce['rows'])==14 and len(skip['rows'])==7
    assert reduce['ledger'][0]['draw_weight']==.25 and reduce['ledger'][7]['draw_weight']==.5
    assert reduce['rows'][0]['p_W']==pytest.approx(.45)
    assert reduce['rows'][7]==keep['rows'][7]
    assert all(r['q_W']==.5 for r in reduce['rows'])
    assert route_decision_chain(frame.sample(frac=1,random_state=1),policy='KEEP',fallback_weight=0,**kw)==keep
    pd.testing.assert_frame_equal(frame,saved)
    # Exact ties use the same W,D,L order as authoritative support ranking.
    frame.loc[frame.weight.eq(.5),['p_W','p_D','p_L']]=[.3,.3,.4]
    assert not any(r['conflict'] for r in route_decision_chain(frame,policy='SKIP',fallback_weight=0,**kw)['ledger'])


@pytest.mark.parametrize('bad',['label','duplicate','q_change','q_zero','missing_weight','handicap','cutoff','provider','empty','source'])
def test_rejects_invalid_inputs(inputs,bad):
    frame,kw=inputs
    if bad=='label':frame['actual_direction']='W'
    if bad=='duplicate':frame=pd.concat([frame,frame.iloc[:1]])
    if bad=='q_change':frame.loc[0,['q_W','q_D']]=[.4,.4]
    if bad=='q_zero':frame['q_L']=0
    if bad=='missing_weight':frame=frame[frame.weight!=0]
    if bad=='handicap':frame.loc[0,'handicap']=1
    if bad=='cutoff':kw['cutoffs']={'1':Cutoff.decision_epoch('100102','2010-01-01T00:00:00Z')}
    if bad=='provider':frame['provider_id']='0001'
    if bad=='empty':frame=frame.iloc[:0]
    if bad=='source':kw['source_hashes']={}
    with pytest.raises((ValueError,KeyError)):route_decision_chain(frame,policy='KEEP',fallback_weight=0,**kw)


def test_limit_and_post_cutoff_settlement_mutation(inputs):
    frame,kw=inputs
    route=route_decision_chain(frame,policy='KEEP',fallback_weight=0,**kw)
    business=dict(cutoffs=kw['cutoffs'],selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=0)
    plan=n7_baseline_plan(pd.DataFrame(route['rows']),**business);saved=copy.deepcopy(plan)
    limited=limit_decision_chain_plan(plan,groups=1,cutoffs=kw['cutoffs'])
    assert limited['stake']==256 and len(limited['legs'])==7 and len(limited['tickets'])==128
    assert limited['parent_seal']==plan['seal'] and plan==saved
    zero=limit_decision_chain_plan(plan,groups=0,cutoffs=kw['cutoffs'])
    audit=pd.DataFrame(route['rows'])[['issue','slot','provider_id','handicap']]
    audit['actual_direction']='L';audit['spf_sp']=3.;audit['status']='READY'
    assert settle_n7_baseline(zero,audit)['status']=='NO_BET'
    first=settle_n7_baseline(limited,audit)
    audit['actual_direction']='W';audit['spf_sp']=999.
    second=settle_n7_baseline(limited,audit)
    assert first['gross']!=second['gross']
    assert route_decision_chain(frame,policy='KEEP',fallback_weight=0,**kw)==route
    assert n7_baseline_plan(pd.DataFrame(route['rows']),**business)==plan
    assert limit_decision_chain_plan(plan,groups=1,cutoffs=kw['cutoffs'])==limited
    for count in [-1,3,True,1.5]:
        with pytest.raises(ValueError):limit_decision_chain_plan(plan,groups=count,cutoffs=kw['cutoffs'])
    with pytest.raises(ValueError):limit_decision_chain_plan(plan,groups=1,cutoffs={})
    plan['stake']+=1
    with pytest.raises(ValueError):limit_decision_chain_plan(plan,groups=1,cutoffs=kw['cutoffs'])


def test_all_conflicts_can_abstain_and_no_new_fit_is_hidden(inputs):
    frame,kw=inputs;frame.loc[frame.weight.eq(.5),['p_W','p_D','p_L']]=[.1,.5,.4]
    route=route_decision_chain(frame,policy='SKIP',fallback_weight=0,**kw)
    assert route['rows']==[] and all(r['action']=='SKIP' for r in route['ledger'])
    assert route['receipt']['learning']=='NONE_FIXED_RULE'
    assert 'src/fundamentals_integration_weight.py' in route['receipt']['implementation']['files']
    assert route['receipt']['cutoffs']['1']=='2010-01-01T00:00:00+00:00'
