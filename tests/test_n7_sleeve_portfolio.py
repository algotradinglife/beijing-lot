import numpy as np
import pandas as pd
import pytest
import copy
from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_candidates import build_sleeve_candidates
from src.n7_sleeve_portfolio import sleeve_portfolios
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def test_expanded_universe_shared_world_union_and_budget():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for i in range(8)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    money=dict(budget_cny=1024,unit_cny=2,payout_factor=.65)
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=600,tradeoffs=['PROBABILITY',0.])
    bundle=build_sleeve_candidates(pool,cutoffs=cuts,candidate_count=9,seed=424,maximum_attempts=5000,
        frontier_points=[('F80',.8,-.35)],solver_seconds=10.,solver_relative_gap=.001,solver_feasibility_tolerance=1e-9,**money)
    assert len(bundle['sleeves'])==8
    assert len(bundle['expanded_pool']['encoded_tickets'])==8*2187
    args=dict(cutoffs=cuts,seed=42,training_worlds=300,evaluation_worlds=400,primary_frontier='F80',
        overlap_penalty=.02,return_union_fraction=.8,return_passes=2,**money)
    z=sleeve_portfolios(bundle,**args)
    assert len(z['plans'])==11
    rng=np.random.default_rng(np.random.SeedSequence(42).spawn(2)[1])
    worlds=np.array([np.searchsorted(np.array([.6,.9,1.]),rng.random(400),side='right') for _ in range(8)])
    for plan in z['plans']:
        assert plan['groups']==512 and plan['stake']==1024 and plan['cash_cny']==0
        assert len({tuple(zip(ii,dd)) for ii,dd in zip(plan['fixture_indices'],plan['outcomes'])})==512
        union=np.zeros(400,dtype=bool)
        for ii,dd in zip(plan['fixture_indices'],plan['outcomes']):union|=np.all(worlds[ii]==np.array(dd)[:,None],axis=0)
        assert union.mean()==plan['simulation']['evaluation_hit_rate']
        if plan['sleeve_keys']:
            assert len({k[0] for k in plan['sleeve_keys']})==8
            expected=np.mean([bundle['sleeves'][gid]['options'][kind]['coverage'] for gid,kind in plan['sleeve_keys']])
            assert plan['mean_coverage']==pytest.approx(expected)
            assert plan['mean_coverage']!=pytest.approx(expected/64)
    prob=next(p for p in z['plans'] if p['arm']=='8x64_PROB')
    random_states=next(p for p in z['plans'] if p['arm']=='8x64_RANDOM_STATES')
    # Same seven-fixture sets, different selected states: Top64 coverage cannot
    # substitute for the actual random-subset portfolio average.
    assert [k[0] for k in random_states['sleeve_keys']]==[k[0] for k in prob['sleeve_keys']]
    assert random_states['mean_coverage']<prob['mean_coverage']
    ret=next(p for p in z['plans'] if p['arm']=='8x64_RETURN_AWARE')
    assert ret['simulation']['training_hit_rate']>=.8*prob['simulation']['training_hit_rate']-1e-8
    changed=sleeve_portfolios(bundle,**{**args,'evaluation_worlds':450})
    assert [(p['fixture_indices'],p['outcomes']) for p in z['plans']]==[(p['fixture_indices'],p['outcomes']) for p in changed['plans']]
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='COMPLETE')
    for plan in z['plans']:
        settled=settle_single_tickets(plan,audit)
        assert settled['status']=='COMPLETE'
        assert settled['gross']==pytest.approx(settled['hits']*2*.65*2**7)
        if plan['sleeve_keys']:assert settled['hits']<=8
    with pytest.raises(ValueError):sleeve_portfolios(bundle,**{**args,'cutoffs':{}})
    with pytest.raises(ValueError):build_sleeve_candidates(pool,cutoffs=cuts,candidate_count=8,seed=424,
        maximum_attempts=100,frontier_points=[('F80',.8,-.35)],solver_seconds=10.,solver_relative_gap=.001,solver_feasibility_tolerance=1e-9,**money)
    with pytest.raises(ValueError):build_sleeve_candidates(pool,cutoffs=cuts,candidate_count=9,seed=424,
        maximum_attempts=100,frontier_points=[('PROB',.8,-.35)],solver_seconds=10.,solver_relative_gap=.001,solver_feasibility_tolerance=1e-9,**money)
    short=copy.deepcopy(bundle);short['sleeves']=short['sleeves'][:7]
    short['seal']=stable_json_hash({k:v for k,v in short.items() if k!='seal'})
    empty=sleeve_portfolios(short,**args)
    for plan in empty['plans']:
        if plan['arm'].startswith('8x64'):
            assert plan['stake']==0 and plan['cash_cny']==1024
            assert plan['mean_coverage'] is None
