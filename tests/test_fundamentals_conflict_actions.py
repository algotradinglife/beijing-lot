from copy import deepcopy
import itertools
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_conflict_probabilities import conflict_score_projection,conflict_score_offer
from src.fundamentals_conflict_portfolios import fund_complete_plan,expand_conflict_plan,conflict_protection_plan,settle_conflict_protection
from src.fundamentals_reverse_gate import reverse_positive_ceiling
from src.fundamentals_n7_baseline import n7_baseline_plan,settle_n7_baseline


@pytest.fixture
def sample():
    rows=[];offers=[];cuts={};projections=[]
    grid=[dict(home_goals=1,away_goals=0,p=.2,q=.5),dict(home_goals=0,away_goals=0,p=.4,q=.3),dict(home_goals=0,away_goals=1,p=.4,q=.2)]
    for slot in range(1,15):
        f=dict(issue='100101',slot=slot,provider_id=f'{slot:04}',handicap=0,p_W=.2,p_D=.4,p_L=.4,q_W=.5,q_D=.3,q_L=.2)
        cutoff=Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z');cuts[str(slot)]=cutoff
        x=conflict_score_projection(grid,f,cutoff=cutoff,market_weight=0)
        rows.append(f);projections.append(x);offers.append(conflict_score_offer(x,cutoff=cutoff))
    plan=n7_baseline_plan(pd.DataFrame(rows),cutoffs=cuts,selector='COVERAGE',shape='C0E0',funding='UNIT',max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=0)
    audit=pd.DataFrame(rows)[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=3.,actual_home=1,actual_away=0,bf_option='1:0',bf_sp=8.,status='READY')
    return grid,rows,offers,cuts,plan,audit,projections


def test_projection_full_grid_and_market_invariance_and_exact_offer(sample):
    grid,rows,offers,cuts,_,_,_=sample;original=deepcopy(grid)
    for alpha in [0,.5,1]:
        x=conflict_score_projection(grid,rows[0],cutoff=cuts['1'],market_weight=alpha)
        assert x['fixture']['p_W']==pytest.approx(.2*(1-alpha)+.5*alpha)
        assert x['fixture']['q_W']==.5 and sum(r['p'] for r in x['grid'])==pytest.approx(1)
        assert x['receipt']['conflict']
    assert grid==original and offers[0]['option']=='1:0' and offers[0]['sp_proxy']==2
    f=dict(rows[0],p_W=.5,p_D=.3,p_L=.2);no_conflict=[dict(r,p=r['q']) for r in grid]
    x=conflict_score_projection(no_conflict,f,cutoff=cuts['1'],market_weight=1)
    assert not x['receipt']['conflict'] and x['receipt']['applied_weight']==0
    # Other-score bucket must not be sold as a pure omitted-direction exact bet.
    large=[dict(home_goals=9,away_goals=0,p=.2,q=.5),grid[1],grid[2]]
    z=conflict_score_projection(large,rows[0],cutoff=cuts['1'],market_weight=0)
    assert conflict_score_offer(z,cutoff=cuts['1'])['status'].startswith('NO_EXACT_SCORE')


@pytest.mark.parametrize('bad',['label','cutoff','sum','duplicate','marginal','weight','negative'])
def test_projection_contracts(sample,bad):
    grid,rows,_,cuts,_,_,_=sample;f=deepcopy(rows[0]);kw=dict(cutoff=cuts['1'],market_weight=.5)
    if bad=='label':f['actual_home']=1
    if bad=='cutoff':kw['cutoff']=Cutoff.decision_epoch('100102','2010-01-01T00:00:00Z')
    if bad=='sum':grid[0]['p']=.3
    if bad=='duplicate':grid.append(grid[0])
    if bad=='marginal':f.update(p_W=.3,p_D=.3)
    if bad=='weight':kw['market_weight']=True
    if bad=='negative':grid[0]['home_goals']=-1
    with pytest.raises(ValueError):conflict_score_projection(grid,f,**kw)


def test_expand_complete_support_and_exact_fixed_funding(sample):
    _,_,offers,cuts,base,audit,_=sample;saved=deepcopy(base)
    extra=expand_conflict_plan(base,offers,cutoffs=cuts,mode='ONE',funding='EXTRA',budget_cny=512,allocation_seed=0)
    assert extra['stake']==768 and len(extra['tickets'])==384
    assert len(extra['expanded'])==2
    fixed=expand_conflict_plan(base,offers,cutoffs=cuts,mode='ONE',funding='FIXED',budget_cny=512,allocation_seed=0)
    assert fixed['groups']==1 and fixed['stake']==512 and len(fixed['tickets'])==192
    assert sum(t['units'] for t in fixed['tickets'])==256 and min(t['units'] for t in fixed['tickets'])==1
    all_extra=expand_conflict_plan(base,offers,cutoffs=cuts,mode='ALL',funding='EXTRA',budget_cny=512,allocation_seed=0)
    assert all_extra['stake']==2*2*3**7
    all_fixed=expand_conflict_plan(base,offers,cutoffs=cuts,mode='ALL',funding='FIXED',budget_cny=512,allocation_seed=0)
    assert all_fixed['stake']==0 and all_fixed['groups']==0
    assert settle_n7_baseline(all_fixed,audit)['status']=='NO_BET'
    assert settle_n7_baseline(all_extra,audit)['gross']==pytest.approx(2*2*.65*3**7)
    assert base==saved
    assert extra==expand_conflict_plan(base,offers,cutoffs=cuts,mode='ONE',funding='EXTRA',budget_cny=512,allocation_seed=0)
    with pytest.raises(ValueError):fund_complete_plan(extra,cutoffs=cuts,budget_cny=766,allocation_seed=0)
    with pytest.raises(ValueError):fund_complete_plan(extra,cutoffs={},budget_cny=768,allocation_seed=0)
    broken=deepcopy(offers);broken[0]['provider_id']='other'
    with pytest.raises(ValueError):expand_conflict_plan(base,broken,cutoffs=cuts,mode='ONE',funding='EXTRA',budget_cny=512,allocation_seed=0)


def test_protection_budget_score_mapping_and_payout(sample):
    _,_,offers,cuts,base,audit,_=sample
    extra=conflict_protection_plan(base,offers,cutoffs=cuts,funding='EXTRA',unit_cny=2,allocation_seed=0)
    assert len(extra['scores'])==14 and extra['stake']==540
    e=settle_conflict_protection(extra,audit)
    assert e['score_gross']==pytest.approx(14*2*.65*8) and e['score_hits']==14 and e['gross']==e['score_gross']
    fixed=conflict_protection_plan(base,offers,cutoffs=cuts,funding='FIXED',unit_cny=2,allocation_seed=0)
    assert fixed['stake']==512 and len(fixed['scores'])==7 and fixed['main']['stake']==498
    assert len(fixed['main']['tickets'])==128 and min(t['units'] for t in fixed['main']['tickets'])>=1
    missing=audit.copy();missing.loc[0,'bf_sp']=None
    assert settle_conflict_protection(extra,missing)['status']=='PENDING_WINNING_BF_SP'
    wrong=audit.copy();wrong.loc[0,'bf_option']='0:0'
    with pytest.raises(ValueError):settle_conflict_protection(extra,wrong)
    mutated=deepcopy(extra);mutated['scores'][0]['stake']=4
    with pytest.raises(ValueError):settle_conflict_protection(mutated,audit)
    # A single complete base group cannot finance an extra BF unit at same budget.
    from src.fundamentals_decision_chain import limit_decision_chain_plan
    one=limit_decision_chain_plan(base,groups=1,cutoffs=cuts)
    no_room=conflict_protection_plan(one,offers,cutoffs=cuts,funding='FIXED',unit_cny=2,allocation_seed=0)
    assert no_room['scores']==[] and no_room['stake']==256
    bad=deepcopy(offers);bad[0]['score_home']=0;bad[0]['option']='0:0'
    with pytest.raises(ValueError):conflict_protection_plan(base,bad,cutoffs=cuts,funding='EXTRA',unit_cny=2,allocation_seed=0)


def test_post_cutoff_outcomes_do_not_change_expansion_or_protection(sample):
    _,_,offers,cuts,base,audit,_=sample
    kw=dict(cutoffs=cuts,mode='ALL',funding='EXTRA',budget_cny=512,allocation_seed=0)
    first=expand_conflict_plan(base,offers,**kw);first_gross=settle_n7_baseline(first,audit)['gross']
    audit['actual_direction']='D';audit['actual_home']=0;audit['bf_option']='0:0';audit['spf_sp']=99.;audit['bf_sp']=99.
    assert settle_n7_baseline(first,audit)['gross']!=first_gross
    assert expand_conflict_plan(base,offers,**kw)==first
    side=conflict_protection_plan(base,offers,cutoffs=cuts,funding='EXTRA',unit_cny=2,allocation_seed=0)
    assert settle_conflict_protection(side,audit)['score_gross']==0
    assert side==conflict_protection_plan(base,offers,cutoffs=cuts,funding='EXTRA',unit_cny=2,allocation_seed=0)


def test_reverse_ceiling_is_not_fabricated_tree_inference():
    receipt=dict(training_issues=['100101'],cutoff_ts='2010-01-02T00:00:00Z',leaves={'1':dict(n=8,positive=3,probability=.4)},bounds=[.2,.6],expert_rows=8,model_sha256='a'*64)
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt));cutoff=Cutoff.decision_epoch('100103','2010-01-03T00:00:00Z')
    z=reverse_positive_ceiling(frozen,cutoff=cutoff,expected_seal=frozen['seal'])
    assert z['status']=='NO_POSITIVE_LEAF' and not z['per_fixture_prediction']
    receipt['leaves']['1'].update(positive=7,probability=.8);frozen['seal']=stable_json_hash(receipt)
    assert reverse_positive_ceiling(frozen,cutoff=cutoff,expected_seal=frozen['seal'])['status']=='NEEDS_ROW_INFERENCE'
    with pytest.raises(ValueError):reverse_positive_ceiling(frozen,cutoff=Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z'),expected_seal=frozen['seal'])
    receipt['expert_rows']=10
    with pytest.raises(ValueError):reverse_positive_ceiling(frozen,cutoff=cutoff,expected_seal=frozen['seal'])
