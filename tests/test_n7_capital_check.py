"""Hand-calculated capital case and adversarial mutations; no live inputs."""
import copy
import numpy as np
import pytest
from src.n7_capital_check import check_capital_plan, check_capital_result, _capital_close
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def capital_case():
    f=[dict(issue='010101',slot=i+1,provider_id=str(i+1),handicap=0,
        p_W=.5,p_D=.3,p_L=.2,q_W=1/3,q_D=1/3,q_L=1/3) for i in range(7)]
    cuts={str(i+1):'2010-01-01T00:00:00Z' for i in range(7)}
    order=[6,0,1,2,3,4,5];code=[0,0,0,0,0,1,0]
    coverage=.5**7+.5**6*.3;payout=1.3*3**7;expected=coverage*payout
    exposure=[[4,0,0] for _ in range(7)];exposure[5]=[2,2,0]
    metrics=dict(sleeves=1,distinct_fixture_count=7,stake=4,cash=12,
        expected_gross=expected,expected_net=expected-4,expected_roi=expected/4-1,
        any_hit=.5,at_least_two=0,zero_hit=.5,profit_probability=.5,loss_probability=.5,
        zero_net_probability=0,conditional_gain=payout-4,conditional_loss=-4,payoff_ratio=(payout-4)/4,
        gain_support=2,loss_support=2,simulation_worlds=4,payoff_support_status='BOTH_EVENTS_OBSERVED',
        simulated_expected_net=payout/2-4,coverage_mean=coverage,coverage_weighted_mean=coverage,
        coverage_median=coverage,coverage_min=coverage,coverage_max=coverage)
    plan=dict(issue='010101',seed=1,cutoffs=cuts,historical_admission=False,fixtures=f,
        fixture_indices=[list(range(7))]*2,outcomes=[[0]*7,code],groups=2,stake=4,cash_cny=12,
        budget_cny=16,unit_cny=2,payout_factor=.65,funded_sleeves=1,
        sleeve_keys=[dict(sleeve_id=0,fixture_indices=order,state_ids=[0,1],depth=2,
            rule='PROB_PREFIX',coverage=coverage,expected_gross=expected,stake=4)],
        support_space='NONUNIFORM',fixture_outcome_exposure_cny=exposure,fixture_exposure_cny=[4]*7,
        max_reuse=1,max_overlap=0,max_fixture_exposure_cny=4,max_outcome_exposure_cny=4,
        solver_status='OPTIMAL_WITHIN_TOLERANCE',solver=dict(mip_gap=0),
        preference=dict(spend_all=False,minimum_roi=-1,minimum_hit=0),
        training=copy.deepcopy(metrics),evaluation=copy.deepcopy(metrics))
    plan['seal']=stable_json_hash(plan)
    worlds=dict(seed=1,training=[[0]*7,[2]*7,code,[1]*7],evaluation=[[0]*7,[2]*7,code,[1]*7])
    cfg=dict(budgets=[16],depths=[2],gap=.01,training_worlds=4,evaluation_worlds=4,coverage_tolerance=1e-12)
    bundle=dict(issue='010101',cutoffs=cuts,sleeves=[dict(id=0,fixture_indices=order)],expanded_pool=dict(fixtures=f))
    return plan,worlds,cfg,bundle


def test_independent_capital_accounting_and_cash(capital_case):
    plan,w,c,b=capital_case
    assert check_capital_plan(plan,w,c,b)==dict(tickets=2,sleeves=1,status='PASS')
    for kind in ('DEPTH_2','TAU_0.01'):
        changed=copy.deepcopy(plan);changed['support_space']=kind
        changed['seal']=stable_json_hash({k:v for k,v in changed.items() if k!='seal'})
        assert check_capital_plan(changed,w,c,b)['status']=='PASS'
    empty=copy.deepcopy(plan)
    empty.update(fixture_indices=[],outcomes=[],groups=0,stake=0,cash_cny=16,funded_sleeves=0,sleeve_keys=[],
        fixture_outcome_exposure_cny=[[0]*3 for _ in range(7)],fixture_exposure_cny=[0]*7,
        max_reuse=0,max_overlap=0,max_fixture_exposure_cny=0,max_outcome_exposure_cny=0,solver_status='Infeasible')
    for kind in ('training','evaluation'):
        empty[kind]={k:0 for k in plan[kind]}
        empty[kind].update(cash=16,zero_hit=1,zero_net_probability=1,simulation_worlds=4,
            payoff_support_status='INSUFFICIENT_CONDITIONAL_SUPPORT')
        for k in ('expected_roi','conditional_gain','conditional_loss','payoff_ratio','coverage_mean',
                  'coverage_weighted_mean','coverage_median','coverage_min','coverage_max'):empty[kind][k]=None
    empty['seal']=stable_json_hash({k:v for k,v in empty.items() if k!='seal'})
    assert check_capital_plan(empty,w,c,b)['tickets']==0


@pytest.mark.parametrize('field,value',[
    ('coverage_mean',.1),('any_hit',.6),('at_least_two',.5),('zero_hit',.6),
    ('profit_probability',1),('conditional_gain',100),('payoff_ratio',None),('expected_net',0)])
def test_independent_check_rejects_metric_mutations(capital_case,field,value):
    plan,w,c,b=capital_case;plan['evaluation'][field]=value
    plan['seal']=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
    with pytest.raises(ValueError,match='replay mismatch'):check_capital_plan(plan,w,c,b)


def test_independent_check_rejects_physical_preference_and_prefix_changes(capital_case):
    original,w,c,b=capital_case
    changes=[('budget_cny',18),('outcomes',[[0]*7,[1,0,0,0,0,0,0]]),
        ('solver_status','Infeasible'),('solver',dict(mip_gap=.2)),
        ('preference',dict(spend_all=True,minimum_roi=-1,minimum_hit=0)),
        ('preference',dict(spend_all=False,minimum_roi=-1,minimum_hit=.9)),
        ('support_space','DEPTH_8'),('support_space','TAU_0.001'),
        ('fixture_outcome_exposure_cny',[[0]*3 for _ in range(7)])]
    for key,value in changes:
        plan=copy.deepcopy(original);plan[key]=value
        plan['seal']=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
        with pytest.raises(ValueError):check_capital_plan(plan,w,c,b)
    bad=copy.deepcopy(w);bad['training'][0][0]=3
    with pytest.raises(ValueError,match='scenario'):check_capital_plan(original,bad,c,b)
    with pytest.raises(ValueError,match='replay mismatch'):_capital_close(float('nan'),1,'nonfinite')
    _capital_close(None,None,'unsupported')


def test_full_curve_trace_and_registered_preference_are_replayed(capital_case):
    plan,w,c,b=capital_case
    codes=np.indices((3,)*7).reshape(7,-1).T
    p=np.prod(np.array([.5,.3,.2])[codes],axis=1);v=p*(1.3*3**7)
    rank=np.lexsort((np.arange(2187),-v,-p));cp=np.r_[0,np.cumsum(p[rank])];cv=np.r_[0,np.cumsum(v[rank])]
    curves=[dict(sleeve_id='0',depth=k,state_id=int(rank[k-1]) if k else None,
        stake=2*k,coverage=cp[k],expected_gross=cv[k],expected_net=cv[k]-2*k,
        expected_roi=cv[k]/(2*k)-1 if k else None,
        marginal_coverage=p[rank[k]] if k<2187 else None,marginal_net=v[rank[k]]-2 if k<2187 else None)
        for k in range(2188)]
    plan['preference'].update(name='TEST',objective='any_hit');plan['arm']='NONUNIFORM_TEST_B16'
    c.update(seeds=[1],preferences=[copy.deepcopy(plan['preference'])],coverage_targets=[],equal_depths=[])
    result=dict(issue=b['issue'],cutoffs=b['cutoffs'],plans=[plan],curves=curves)
    assert check_capital_result(result,b,c)==dict(curve_rows=2188,plans=1,status='PASS')
    broken=copy.deepcopy(result);broken['curves'][100]['expected_gross']+=1
    with pytest.raises(ValueError,match='full-curve arithmetic'):check_capital_result(broken,b,c)
    broken=copy.deepcopy(result);broken['plans'][0]['preference']['minimum_roi']=0
    with pytest.raises(ValueError,match='registered preference'):check_capital_result(broken,b,c)
    broken=copy.deepcopy(result);broken['plans'][0]['sleeve_keys'][0]['state_ids']=[0,3]
    with pytest.raises(ValueError,match='full-curve trace'):check_capital_result(broken,b,c)
    broken=copy.deepcopy(result);broken['plans']=[]
    with pytest.raises(ValueError,match='grid incomplete'):check_capital_result(broken,b,c)
