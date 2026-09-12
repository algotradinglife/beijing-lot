import copy
import numpy as np
import pandas as pd
import pytest
from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_expansion import expand_top64
from src.n7_sleeve_probability_cap import sample_capped_sleeves
from src.n7_single_ticket_sampling import settle_single_tickets
from src.n7_sleeve_cap_check import check_capped_plan
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


@pytest.fixture
def case():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.8,p_D=.15,p_L=.05,q_W=.7,q_D=.2,q_L=.1) for i in range(10)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=64,tradeoffs=['PROBABILITY'])
    money=dict(budget_cny=1024,unit_cny=2,payout_factor=.65)
    b=expand_top64(pool,cutoffs=cuts,original_groups=[list(range(7))],candidate_count=60,seed=1,maximum_attempts=1000,**money)
    opts=dict(cutoffs=cuts,pool_size=60,coverage_floor=.15,coverage_cap=.25,seed=4,evaluation_worlds=500,max_fixture_reuse=None,max_pair_overlap=None,**money)
    return f,b,opts


def test_cap_recycles_into_more_sleeves_and_shared_worlds(case):
    f,b,opts=case;z=sample_capped_sleeves(b,**opts)
    assert len(z['sleeves'])==60 and all(s['tickets']==2 for s in z['sleeves'])
    assert z['stake']==240 and z['cash_cny']==784 and z['unspent_reason']=='CANDIDATES_EXHAUSTED'
    assert len(set(s['id'] for s in z['sleeves']))==60
    for s in z['sleeves']:
        assert .15<s['coverage']<=.25
        raw=b['sleeves'][s['id']];p=np.array(raw['probabilities']);pay=np.array(raw['estimated_payouts']);ids=np.array(raw['state_ids'])
        order=np.lexsort((ids,-p*pay,-p))
        assert s['state_ids']==sorted(ids[order[:2]].tolist()) and sum(p[order[:3]])>.25
    rng=np.random.default_rng(np.random.SeedSequence([4,1]))
    worlds=np.array([np.searchsorted([.8,.95,1.],rng.random(500),side='right') for _ in range(10)])
    hits=np.zeros(500,dtype=int)
    for ii,dd in zip(z['fixture_indices'],z['outcomes']):hits+=np.all(worlds[ii]==np.array(dd)[:,None],axis=0)
    assert z['eval_coverage']==np.mean(hits>0)
    assert z['hit_sleeve_distribution']==pytest.approx(np.bincount(hits,minlength=61)/500)
    changed=sample_capped_sleeves(b,**{**opts,'evaluation_worlds':501})
    assert changed['draws']==z['draws'] and changed['outcomes']==z['outcomes']
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='COMPLETE')
    settled=settle_single_tickets(z,audit)
    assert settled['hits']==60 and settled['gross']==pytest.approx(60*1.3*2**7)
    assert sample_capped_sleeves(b,**opts)==z


def test_exact_cap_floor_and_unaffordable_cash(case):
    f,b,opts=case
    # Identical p across fixtures permits an exact first-state boundary.
    first=max(b['sleeves'][0]['probabilities'])
    z=sample_capped_sleeves(b,**{**opts,'coverage_cap':first})
    assert all(s['tickets']==1 for s in z['sleeves'])
    empty=sample_capped_sleeves(b,**{**opts,'coverage_floor':first,'coverage_cap':first+1e-8})
    assert empty['stake']==0 and empty['cash_cny']==1024
    # A cap of1 keeps64 tickets; exactly8 affordable sleeves consume the budget.
    full=sample_capped_sleeves(b,**{**opts,'coverage_cap':1.})
    assert full['stake']==1024 and len(full['sleeves'])==8
    partial=sample_capped_sleeves(b,**{**opts,'coverage_cap':.7})
    assert partial['stake']<=1024 and partial['stake']+partial['cash_cny']==1024
    assert all(s['cost_cny']>partial['cash_cny'] for s in partial['sleeves'])
    for update in ({'cutoffs':{}},{'coverage_cap':.15},{'coverage_floor':float('nan')},{'budget_cny':2048}):
        with pytest.raises(ValueError):sample_capped_sleeves(b,**{**opts,**update})
    bad=copy.deepcopy(b);bad['sleeves'][0]['probabilities'][0]=1
    with pytest.raises(ValueError):sample_capped_sleeves(bad,**opts)


def test_independent_replay_rejects_budget_depth_draw_and_simulation_mutations(case):
    f,b,opts=case;z=sample_capped_sleeves(b,**opts)
    assert check_capped_plan(z,b,cutoffs=opts['cutoffs'])==60
    for mutation in ('cash','depth','draw','simulation','omitted'):
        bad=copy.deepcopy(z)
        if mutation=='cash':bad['cash_cny']+=2
        if mutation=='depth':bad['sleeves'][0]['state_ids']=[0,1]
        if mutation=='draw':bad['draws'][0]['probability']=.99
        if mutation=='simulation':bad['eval_coverage']=1.
        if mutation=='omitted':bad['draws']=bad['draws'][:-1]
        bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
        with pytest.raises(ValueError):check_capped_plan(bad,b,cutoffs=opts['cutoffs'])
    with pytest.raises(ValueError):check_capped_plan(z,b,cutoffs={})


@pytest.mark.parametrize('u,p',[(1,None),(2,None),(3,4),(None,4),(3,2)])
def test_hard_caps_filter_before_weighting_and_hold_cash(case,u,p):
    _,b,opts=case
    z=sample_capped_sleeves(b,**{**opts,'max_fixture_reuse':u,'max_pair_overlap':p})
    assert check_capped_plan(z,b,cutoffs=opts['cutoffs'])==len(z['sleeves'])
    assert z['unspent_reason']=='CONCENTRATION_CAPS_EXHAUSTED'
    assert z['cash_cny']>0 and z['stake']+z['cash_cny']==1024
    chosen=[]
    for draw,sleeve in zip(z['draws'],z['sleeves']):
        allowed=[]
        for candidate in b['sleeves']:
            if candidate['id'] in [g['id'] for g in chosen]:continue
            if u is not None and any(sum(i in g['fixture_indices'] for g in chosen)>=u for i in candidate['fixture_indices']):continue
            if p is not None and any(len(set(candidate['fixture_indices'])&set(g['fixture_indices']))>p for g in chosen):continue
            allowed.append(candidate)
        # All toy sleeves have equal retained mass/value and are affordable.
        assert draw['affordable_count']==len(allowed)
        assert draw['probability']==pytest.approx(1/len(allowed))
        chosen.append(sleeve)
    for i in range(10):
        if u is not None:assert sum(i in s['fixture_indices'] for s in chosen)<=u
    for j,a in enumerate(chosen):
        for b2 in chosen[:j]:
            if p is not None:assert len(set(a['fixture_indices'])&set(b2['fixture_indices']))<=p
    bad=copy.deepcopy(z);bad['parameters']['max_fixture_reuse']=0
    bad['seal']=stable_json_hash({k:v for k,v in bad.items() if k!='seal'})
    with pytest.raises(ValueError):check_capped_plan(bad,b,cutoffs=opts['cutoffs'])


@pytest.mark.parametrize('key,value',[('max_fixture_reuse',0),('max_fixture_reuse',True),('max_pair_overlap',7),('max_pair_overlap',-1)])
def test_invalid_hard_caps_fail(case,key,value):
    _,b,opts=case
    with pytest.raises(ValueError):sample_capped_sleeves(b,**{**opts,key:value})
