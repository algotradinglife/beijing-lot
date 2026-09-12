import itertools
import numpy as np
import pandas as pd
import pytest
from src.n7_probability_gate import probability_gate_candidates,select_probability_gate
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff


@pytest.fixture
def problem():
    rng=np.random.default_rng(42)
    f=pd.DataFrame(dict(issue='001',slot=range(1,9),provider_id=[str(i) for i in range(1,9)],handicap=0))
    f[['p_W','p_D','p_L']]=rng.dirichlet([3,2,1],8)
    f[['q_W','q_D','q_L']]=rng.dirichlet([2,2,2],8)
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in f.slot}
    return f,cuts


@pytest.mark.parametrize('tradeoff',[0.,1.,'PROBABILITY'])
def test_scalar_dynamic_programming_matches_exhaustive(problem,tradeoff):
    f,cuts=problem
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=30,tradeoffs=[tradeoff])
    p=f[['p_W','p_D','p_L']].to_numpy();q=f[['q_W','q_D','q_L']].to_numpy()
    tickets=np.array([tuple(3*i+d for i,d in zip(ids,ds)) for ids in itertools.combinations(range(8),7)
        for ds in itertools.product(range(3),repeat=7)])
    idx=tickets//3;ds=tickets%3;lp=np.log(p[idx,ds]).sum(axis=1);lr=np.log(p[idx,ds]/q[idx,ds]).sum(axis=1)
    score=lp if tradeoff=='PROBABILITY' else lr+tradeoff*lp
    order=np.argsort(-score,kind='stable')[:30]
    assert {tuple(t) for t in pool['encoded_tickets']}=={tuple(t) for t in tickets[order]}
    assert pool==probability_gate_candidates(f.iloc[::-1],cutoffs=cuts,n=7,depth=30,tradeoffs=[tradeoff])


def test_gate_allocation_objective_nested_search_and_settlement(problem):
    f,cuts=problem
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=700,tradeoffs=[0.,1.,'PROBABILITY'])
    args=dict(cutoffs=cuts,min_probability=.001,ranking='EV',search_depth=700,budget_cny=1024,unit_cny=2,payout_factor=.65)
    plan=select_probability_gate(pool,**args)
    codes=np.array(pool['encoded_tickets']);idx=codes//3;ds=codes%3
    p=f[['p_W','p_D','p_L']].to_numpy();q=f[['q_W','q_D','q_L']].to_numpy()
    mass=p[idx,ds].prod(axis=1);ev=.65*(p[idx,ds]/q[idx,ds]).prod(axis=1)-1
    expected=2*sum(sorted(ev[(mass>=.001)&(ev>0)],reverse=True)[:512])
    assert plan['expected_net']==pytest.approx(expected)
    assert plan['stake']==1024 and plan['min_selected_probability']>=.001
    small=select_probability_gate(pool,**dict(args,search_depth=30))
    assert small['expected_net']<=plan['expected_net']
    pure=select_probability_gate(pool,**dict(args,ranking='PROB'))
    pos=select_probability_gate(pool,**dict(args,ranking='PROB_POS'))
    assert pure['mean_coverage']>=plan['mean_coverage'] and pos['expected_net']<=plan['expected_net']
    assert plan['positive_count']==pos['positive_count']
    boundary=select_probability_gate(pool,**dict(args,min_probability=float(mass.max()),ranking='PROB'))
    assert boundary['groups']==1
    audit=f[['issue','slot','provider_id','handicap']].assign(status='READY',actual_direction='W',spf_sp=2.)
    for i,d in zip(plan['fixture_indices'][0],plan['outcomes'][0]):audit.loc[i,'actual_direction']='WDL'[d]
    settled=settle_single_tickets(plan,audit)
    assert settled['status']=='COMPLETE' and settled['hits']>=1
    assert settled['gross']==pytest.approx(settled['hits']*2*.65*2**7)
    with pytest.raises(ValueError):select_probability_gate(dict(pool,issue='002'),**args)
    with pytest.raises(ValueError):select_probability_gate(pool,**dict(args,cutoffs={}))
    with pytest.raises(ValueError):select_probability_gate(pool,**dict(args,min_probability=-1))
    with pytest.raises(ValueError):select_probability_gate(pool,**dict(args,search_depth=701))
    with pytest.raises(ValueError):select_probability_gate(pool,**dict(args,ranking='UNKNOWN'))


def test_negative_ev_zero_outcomes_empty_universe_and_invalid_inputs(problem):
    f,cuts=problem
    f[['q_W','q_D','q_L']]=f[['p_W','p_D','p_L']].to_numpy()
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[0.,'PROBABILITY'])
    args=dict(cutoffs=cuts,min_probability=0.,ranking='EV',search_depth=20,budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert select_probability_gate(pool,**args)['cash_cny']==1024
    assert select_probability_gate(pool,**dict(args,ranking='PROB'))['expected_roi']==pytest.approx(-.35)
    f[['p_W','p_D','p_L']]=[1.,0.,0.]
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[0.,1.,'PROBABILITY'])
    assert len(pool['encoded_tickets'])==8
    assert all(c%3==0 for ticket in pool['encoded_tickets'] for c in ticket)
    six=f.iloc[:6];sixcuts={str(s):cuts[str(s)] for s in six.slot}
    pool=probability_gate_candidates(six,cutoffs=sixcuts,n=7,depth=20,tradeoffs=[0.])
    no=select_probability_gate(pool,**dict(args,cutoffs=sixcuts))
    assert no['groups']==0 and no['cash_cny']==1024
    with pytest.raises(ValueError):probability_gate_candidates(f.assign(label=1),cutoffs=cuts,n=7,depth=20,tradeoffs=[0.])
    with pytest.raises(ValueError):probability_gate_candidates(f,cutoffs=cuts,n=7,depth=0,tradeoffs=[0.])
    with pytest.raises(ValueError):probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[-1.])
    with pytest.raises(ValueError):probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[0.,0.])
