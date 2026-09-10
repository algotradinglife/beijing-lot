import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_n7_random_single import random_second_single_plan
from src.fundamentals_n7_precompress import precompress_n7_plan


@pytest.fixture
def sample():
    rows=[dict(issue='100101',slot=s,provider_id=str(s),handicap=0,p_W=.4+.008*s,p_D=(.6-.008*s)*.6,p_L=(.6-.008*s)*.4,q_W=.5,q_D=.3,q_L=.2) for s in range(1,43)]
    f=pd.DataFrame(rows);c={str(s):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for s in f.slot}
    return f,c


@pytest.mark.parametrize('mode',['TOP1','MODEL','TOP2_UNIFORM'])
def test_random_second_replay_and_preserved_groups(sample,mode):
    f,c=sample;base=n7_single_plan(f,max_uses=2,cutoffs=c,single_count=2,single_rule='MAX_SINGLE',budget_cny=1024,unit_cny=2,payout_factor=.65,allocation_seed=0)
    first=random_second_single_plan(base,cutoffs=c,seed=7,outcome_mode=mode)
    assert first==random_second_single_plan(base,cutoffs=c,seed=7,outcome_mode=mode)
    assert first['stake']==base['stake'] and first['cash_cny']==base['cash_cny']
    assert [(r['group'],r['slot']) for r in first['legs']]==[(r['group'],r['slot']) for r in base['legs']]
    for g in range(1,first['groups']+1):
        legs=[r for r in first['legs'] if r['group']==g]
        assert sum(len(r['support'])==1 for r in legs)==2
        assert len([t for t in first['tickets'] if t['group']==g])==32
    assert first['contraction_ledger']!=random_second_single_plan(base,cutoffs=c,seed=9,outcome_mode=mode)['contraction_ledger']
    with pytest.raises(ValueError):random_second_single_plan(base,cutoffs={},seed=7,outcome_mode=mode)
    with pytest.raises(ValueError):random_second_single_plan(base,cutoffs=c,seed=-1,outcome_mode=mode)


@pytest.mark.parametrize('mode,value',[('FIXED',8),('THRESHOLD',.6),('FIXED',0),('FIXED',100),('THRESHOLD',1)])
def test_precompression_roles_caps_cash_and_settlement(sample,mode,value):
    f,c=sample;p=precompress_n7_plan(f,cutoffs=c,budget_cny=1024,mode=mode,value=value,unit_cny=2,payout_factor=.65,allocation_seed=0)
    singles=set(p['single_slots']);sets=[]
    for group in range(1,p['groups']+1):
        legs=[r for r in p['legs'] if r['group']==group];slots={r['slot'] for r in legs};sets.append(slots)
        assert len(slots)==7 and len(slots&singles)==2
        assert all(len(r['support'])==(1 if r['slot'] in singles else 2) for r in legs)
        assert len([t for t in p['tickets'] if t['group']==group])==32
    assert all(len(a&b)<=2 for a,b in itertools.combinations(sets,2))
    assert max(Counter(s for g in sets for s in g).values(),default=0)<=2
    assert p['stake']+p['cash_cny']==1024
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    assert settle_n7_single(p,audit)['gross']==pytest.approx(p['groups']*2*.65*2**7)
    audit['actual_direction']='L';audit['spf_sp']=99.
    assert p==precompress_n7_plan(f,cutoffs=c,budget_cny=1024,mode=mode,value=value,unit_cny=2,payout_factor=.65,allocation_seed=0)


def test_precompression_boundary_and_failures(sample,monkeypatch):
    f,c=sample
    threshold=float(f.p_W.iloc[0]);p=precompress_n7_plan(f,cutoffs=c,budget_cny=0,mode='THRESHOLD',value=threshold,unit_cny=2,payout_factor=.65,allocation_seed=0)
    assert 1 in p['single_slots'] and p['stake']==0
    for mode,value in [('FIXED',1.5),('FIXED',True),('THRESHOLD',float('nan'))]:
        with pytest.raises(ValueError):precompress_n7_plan(f,cutoffs=c,budget_cny=1024,mode=mode,value=value,unit_cny=2,payout_factor=.65,allocation_seed=0)
    from types import SimpleNamespace
    monkeypatch.setattr('src.fundamentals_n7_precompress.milp',lambda *a,**k:SimpleNamespace(status=1))
    with pytest.raises(RuntimeError):precompress_n7_plan(f,cutoffs=c,budget_cny=1024,mode='FIXED',value=8,unit_cny=2,payout_factor=.65,allocation_seed=0)
