import copy
import itertools
import numpy as np
import pandas as pd
import pytest
from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_expansion import expand_top64,sample_top64
from src.n7_single_ticket_sampling import settle_single_tickets
from src.n7_sleeve_expansion_check import check_expansion_bundle
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def case():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for i in range(9)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=32,tradeoffs=['PROBABILITY'])
    money=dict(budget_cny=1024,unit_cny=2,payout_factor=.65)
    args=dict(cutoffs=cuts,original_groups=[list(range(7))],seed=1,maximum_attempts=10000,**money)
    b=expand_top64(pool,candidate_count=36,**args)
    return f,cuts,pool,money,args,b


def test_expansion_nested_exhaustive_mass_and_original_identity(case):
    f,cuts,pool,money,args,b=case
    assert len(b['sleeves'])==36
    assert {tuple(s['fixture_indices']) for s in b['sleeves']}==set(itertools.combinations(range(9),7))
    small=expand_top64(pool,candidate_count=12,**args)
    assert small['sleeves']==b['sleeves'][:12]
    states=np.array(list(itertools.product(range(3),repeat=7)))
    mass=np.prod(np.array([.6,.3,.1])[states],axis=1)
    for s in b['sleeves']:
        assert s['coverage']==pytest.approx(sum(sorted(mass,reverse=True)[:64]))
        assert s['probabilities']==pytest.approx(mass[s['state_ids']])
        assert s['estimated_payouts']==pytest.approx(1.3/np.prod(np.array([.5,.3,.2])[states[s['state_ids']]],axis=1))
    assert b['sleeves'][0]['fixture_indices']==list(range(7))
    capped=expand_top64(pool,candidate_count=100,**{**args,'maximum_attempts':1})
    assert len(capped['sleeves'])<=2
    with pytest.raises(ValueError):expand_top64(pool,candidate_count=36,**{**args,'cutoffs':{}})
    with pytest.raises(ValueError):expand_top64(pool,candidate_count=36,**{**args,'original_groups':[[0]*7]})


def test_sampling_shared_worlds_strict_gate_no_replacement_and_settlement(case):
    f,cuts,pool,money,args,b=case
    opts=dict(cutoffs=cuts,pool_size=36,coverage_floor=.15,weighting='EXPECTED_GROSS',seed=4,evaluation_worlds=600,**money)
    plan=sample_top64(b,**opts)
    assert len(set(plan['sleeve_ids']))==8 and plan['stake']==1024 and plan['groups']==512
    remaining={s['id']:s['expected_gross'] for s in b['sleeves']}
    rng=np.random.default_rng(np.random.SeedSequence([4,0]))
    for d in plan['draws']:
        ids=list(remaining);weights=np.array(list(remaining.values()))
        assert d['sleeve_id']==ids[rng.choice(len(ids),p=weights/weights.sum())]
        assert d['probability']==pytest.approx(remaining[d['sleeve_id']]/sum(remaining.values()))
        del remaining[d['sleeve_id']]
    rng=np.random.default_rng(np.random.SeedSequence([4,1]))
    worlds=np.array([np.searchsorted([.6,.9,1.],rng.random(600),side='right') for _ in range(9)])
    hits=np.zeros(600,dtype=int)
    for ii,dd in zip(plan['fixture_indices'],plan['outcomes']):hits+=np.all(worlds[ii]==np.array(dd)[:,None],axis=0)
    assert plan['eval_coverage']==np.mean(hits>0)
    assert plan['hit_sleeve_distribution']==pytest.approx(np.bincount(hits,minlength=9)/600)
    changed=sample_top64(b,**{**opts,'evaluation_worlds':601})
    assert changed['fixture_indices']==plan['fixture_indices'] and changed['outcomes']==plan['outcomes']
    for updates in ({'pool_size':7},{'coverage_floor':b['sleeves'][0]['coverage']}):
        empty=sample_top64(b,**{**opts,**updates})
        assert empty['groups']==0 and empty['cash_cny']==1024 and empty['eval_coverage']==0
    uniform=sample_top64(b,**{**opts,'weighting':'UNIFORM'})
    assert uniform['draws'][1]['probability']==pytest.approx(1/35)
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='COMPLETE')
    z=settle_single_tickets(plan,audit)
    assert z['gross']==pytest.approx(z['hits']*1.3*2**7) and z['hits']<=8
    audit.actual_direction='L'
    assert sample_top64(b,**opts)==plan  # outcome labels cannot influence selection
    bad=copy.deepcopy(b);bad['sleeves'][0]['coverage']=1
    with pytest.raises(ValueError):sample_top64(bad,**opts)
    for update in ({'cutoffs':{}},{'weighting':'NET'},{'coverage_floor':float('nan')},{'pool_size':37}):
        with pytest.raises(ValueError):sample_top64(b,**{**opts,**update})


def test_independent_replay_rejects_resealed_numerical_and_identity_mutations(case):
    f,cuts,pool,money,args,b=case
    assert check_expansion_bundle(b,cutoffs=cuts,original_groups=args['original_groups'],source_pool=pool)==36
    for field,value in (('coverage',.9),('expected_gross',1.),('state_ids',list(range(64))),
                        ('fixture_indices',[0,1,2,3,4,5,8])):
        bad=copy.deepcopy(b);bad['sleeves'][0][field]=value
        bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
        with pytest.raises(ValueError):check_expansion_bundle(bad,cutoffs=cuts,original_groups=args['original_groups'],source_pool=pool)
    with pytest.raises(ValueError):check_expansion_bundle(b,cutoffs={},original_groups=args['original_groups'],source_pool=pool)
    for mutation in ('order','seed','attempts','origin','source'):
        bad=copy.deepcopy(b);source=copy.deepcopy(pool)
        if mutation=='order':
            bad['sleeves'][2],bad['sleeves'][3]=bad['sleeves'][3],bad['sleeves'][2]
            for i,s in enumerate(bad['sleeves']):s['id']=i
        if mutation=='seed':bad['parameters']['seed']=3
        if mutation=='attempts':bad['attempts']=0
        if mutation=='origin':bad['sleeves'][2]['origin']='UNDECLARED'
        if mutation=='source':source['encoded_tickets']=source['encoded_tickets'][1:]
        bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
        with pytest.raises(ValueError):check_expansion_bundle(bad,cutoffs=cuts,original_groups=args['original_groups'],source_pool=source)
