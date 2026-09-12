import numpy as np
import pandas as pd
import pytest
from src.n7_single_ticket_sampling import single_ticket_plan,settle_single_tickets
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('tau,alpha,beta',[(0.,1.,1.),(.2,2.,2.),(.25,4.,4.)])
def test_sampling_weights_and_authoritative_settlement(tau,alpha,beta):
    f=pd.DataFrame([dict(issue='001',slot=s,provider_id=str(s),handicap=0,p_W=.6,p_D=.25,p_L=.15,
        q_W=.6,q_D=.25,q_L=.15) for s in range(1,16)])
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in f.slot}
    args=dict(cutoffs=cuts,seed=5,third_threshold=tau,outcome_power=alpha,fixture_power=beta,
        max_attempts=700,budget_cny=1024,unit_cny=2,payout_factor=.65)
    plan=single_ticket_plan(f,**args)
    assert plan==single_ticket_plan(f,**args) and plan['groups']==512 and plan['stake']==1024
    assert all(len(set(row))==7 for row in plan['fixture_indices'])
    weights=np.array([.6,.25,0 if tau>.15 else .15])**alpha;weights/=weights.sum()
    assert np.allclose(plan['outcome_weights'],weights)
    assert np.allclose(plan['fixture_weights'],1/15)
    if tau>.15:assert not np.any(np.array(plan['outcomes'])==2)
    assert plan['expected_roi']==pytest.approx(-.35)
    changed=f.copy();changed[['q_W','q_D','q_L']]=[.8,.1,.1]
    other=single_ticket_plan(changed,**args)
    assert other['fixture_indices']==plan['fixture_indices'] and other['outcomes']==plan['outcomes']
    varying=f.copy();varying.loc[0,['p_W','p_D','p_L']]=[.8,.1,.1]
    weighted=single_ticket_plan(varying,**args)
    assert weighted['fixture_weights'][0]/weighted['fixture_weights'][1]==pytest.approx((.9/.85)**beta)
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    audit.loc[plan['fixture_indices'][0],'actual_direction']=['WDL'[d] for d in plan['outcomes'][0]]
    result=settle_single_tickets(plan,audit);expected=0;hits=0
    for ids,codes in zip(plan['fixture_indices'],plan['outcomes']):
        legs=f.iloc[ids][['issue','slot','provider_id','handicap']].assign(group=1).to_dict('records')
        part=dict(issue='001',selector='TEST',shape='C7',funding='UNIT',groups=1,stake=2,unit_cny=2,payout_factor=.65,
            legs=legs,tickets=[dict(group=1,code=''.join('310'[d] for d in codes),units=1)])
        part['seal']=stable_json_hash(part);z=settle_n7_baseline(part,audit);expected+=z['gross'];hits+=z['hits']
    assert result['gross']==pytest.approx(expected) and result['hits']==hits
    with pytest.raises(ValueError):single_ticket_plan(f.assign(actual_direction='D'),**args)
    with pytest.raises(ValueError):single_ticket_plan(f,**dict(args,cutoffs={}))
    with pytest.raises(ValueError):single_ticket_plan(f,**dict(args,outcome_power=0))


def test_zero_bet_duplicate_budget_pending_and_threshold_boundary():
    f=pd.DataFrame([dict(issue='001',slot=s,provider_id=str(s),handicap=0,p_W=1.,p_D=0.,p_L=0.,
        q_W=.8,q_D=.1,q_L=.1) for s in range(1,8)])
    args=dict(cutoffs={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in f.slot},seed=1,
        third_threshold=0.,outcome_power=1.,fixture_power=1.,max_attempts=20,budget_cny=1024,unit_cny=2,payout_factor=.65)
    plan=single_ticket_plan(f,**args)
    assert plan['groups']==1 and plan['duplicates']==19 and plan['cash_cny']==1022
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=np.nan,status='READY')
    assert settle_single_tickets(plan,audit)['status']=='PENDING_WINNING_SP'
    assert settle_single_tickets(plan,audit.assign(handicap=1))['status']=='PENDING_AUDIT'
    assert settle_single_tickets(plan,audit.assign(actual_direction='L'))['gross']==0
    with pytest.raises(ValueError):settle_single_tickets(dict(plan,stake=0),audit)
    small=f.iloc[:6];p=single_ticket_plan(small,**dict(args,cutoffs={k:v for k,v in args['cutoffs'].items() if k!='7'}))
    assert settle_single_tickets(p,audit)['status']=='NO_BET'
    boundary=f.copy();boundary[['p_W','p_D','p_L']]=[.5,.3,.2]
    assert single_ticket_plan(boundary,**dict(args,third_threshold=.2))['outcome_weights'][0][2]==pytest.approx(.2)
    boundary[['p_W','p_D','p_L']]=[.2,.5,.3]
    assert single_ticket_plan(boundary,**dict(args,third_threshold=.25))['outcome_weights'][0][0]==0


@pytest.mark.parametrize('budget',[512,1024,2048,4096])
def test_variable_capital_budget_preserves_one_ticket_payout(budget):
    fixtures=[dict(issue='001',slot=s,provider_id=str(s),handicap=0) for s in range(1,8)]
    plan=dict(issue='001',fixtures=fixtures,fixture_indices=[list(range(7))],outcomes=[[0]*7],groups=1,
        stake=2,cash_cny=budget-2,budget_cny=budget,unit_cny=2,payout_factor=.65)
    plan['seal']=stable_json_hash(plan)
    audit=pd.DataFrame(fixtures).assign(actual_direction='W',spf_sp=2.,status='READY')
    result=settle_single_tickets(plan,audit)
    assert result['gross']==pytest.approx(2*.65*2**7)
    assert result['cash']==budget-2 and result['net']==pytest.approx(result['gross']-2)
    for bad_budget in [-2,3,float('inf'),True]:
        bad=dict(plan,budget_cny=bad_budget);bad.pop('seal');bad['seal']=stable_json_hash(bad)
        with pytest.raises(ValueError):settle_single_tickets(bad,audit)
    for key in ('fixture_indices','outcomes'):
        bad=dict(plan);bad[key]=[list(plan[key][0])];bad[key][0][0]=.5
        bad.pop('seal');bad['seal']=stable_json_hash(bad)
        with pytest.raises(ValueError,match='integer coordinates'):settle_single_tickets(bad,audit)
