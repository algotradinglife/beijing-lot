import pandas as pd
import pytest
from src.n7_weighted_sampling import weighted_n7_plan
from src.market_conditional_reuse import settle_conditional_reuse
from src.temporal_learning import Cutoff


@pytest.mark.parametrize('seed',[17,18])
def test_weighted_pools_budget_cutoffs_and_rejections(seed):
    f=pd.DataFrame([dict(issue='001',slot=s,provider_id=str(s),handicap=0,
        p_W=.6,p_D=.25,p_L=.15,q_W=.6,q_D=.25,q_L=.15) for s in range(1,16)])
    f.loc[f.slot>7,['p_W','p_D','p_L','q_W','q_D','q_L']]=[.45,.35,.2,.45,.35,.2]
    f=f.assign(strength_W=.4,strength_D=.2,strength_L=.4)
    args=dict(cutoffs={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in f.slot},
        seed=seed,single_threshold=.5,max_attempts=150,single_pool_count=2,
        single_alternative_probability=None,double_alternative_probability=None,
        single_gap_limit=None,double_gap_limit=None,double_condition='ALLOW',
        budget_cny=1024,unit_cny=2,payout_factor=.65)
    plan=weighted_n7_plan(f,**args)
    assert plan==weighted_n7_plan(f,**args)
    assert plan['stake']==len(plan['tickets'])*2 and plan['stake']+plan['cash_cny']==1024
    assert plan['attempts']<=150
    assert plan['groups']>0 and plan['max_fixture_reuse']>10
    signatures=[]
    for g in range(1,plan['groups']+1):
        rows=[z for z in plan['legs'] if z['group']==g]
        assert len({z['slot'] for z in rows})==7 and sum(z['pool']=='S' for z in rows)==2
        assert all(z['support'] in ('3','1') if z['pool']=='S' else z['support'] in ('31','0') for z in rows)
        assert all((z['p_W']>=.5)==(z['pool']=='S') for z in rows)
        signatures.append(tuple((z['slot'],z['support']) for z in rows))
    assert len(set(signatures))==len(signatures)
    assert all(z['expected_roi']==pytest.approx(-.35) for z in plan['group_metrics'])
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    z=settle_conditional_reuse(plan,audit)
    expected=sum(all('3' in r['support'] for r in plan['legs'] if r['group']==g) for g in range(1,plan['groups']+1))
    assert z['gross']==pytest.approx(expected*1.3*2**7)
    assert weighted_n7_plan(f,**dict(args,single_threshold=.9))['groups']==0
    with pytest.raises(ValueError):weighted_n7_plan(f.assign(actual_direction='D'),**args)
    with pytest.raises(ValueError):weighted_n7_plan(f,**dict(args,cutoffs={}))
    assert 'LOW_EV' not in plan['rejections']
    changed=f.copy();changed[['q_W','q_D','q_L']]=[.8,.1,.1]
    other=weighted_n7_plan(changed,**args)
    assert other['tickets']==plan['tickets'] and other['stake']==plan['stake']
    for rate,s_support,b_support in [(0.,'3','31'),(1.,'1','0')]:
        fixed=weighted_n7_plan(f,**dict(args,single_alternative_probability=rate,double_alternative_probability=rate))
        assert fixed['groups']>0
        assert all(z['support']==(s_support if z['pool']=='S' else b_support) for z in fixed['legs'])
    with pytest.raises(ValueError):weighted_n7_plan(f,**dict(args,single_alternative_probability=1.1))
    forced=dict(args,single_alternative_probability=1.,double_alternative_probability=1.)
    gated=weighted_n7_plan(f,**dict(forced,single_gap_limit=.1,double_gap_limit=.2,double_condition='GAP'))
    assert all(not z['alternative_used'] for z in gated['legs'])
    boundary=weighted_n7_plan(f,**dict(forced,single_gap_limit=.35,double_gap_limit=.25,double_condition='JOINT'))
    assert all(z['alternative_used'] for z in boundary['legs'])
    no_signal=f.assign(strength_W=.4,strength_D=.5,strength_L=.1)
    blocked=weighted_n7_plan(no_signal,**dict(forced,single_gap_limit=.1,double_gap_limit=.3,double_condition='JOINT'))
    assert all(not z['alternative_used'] for z in blocked['legs'])
    signal=weighted_n7_plan(f,**dict(forced,single_gap_limit=.1,double_condition='STRENGTH_TOP2'))
    assert all(z['alternative_used']==(z['pool']=='B') for z in signal['legs'])
    all_single=f.copy();all_single[['p_W','p_D','p_L']]=[.6,.25,.15]
    assert weighted_n7_plan(all_single,**args)['groups']==0
    with pytest.raises(ValueError):weighted_n7_plan(f,**dict(args,double_condition='GAP'))
