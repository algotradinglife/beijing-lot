import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_n7_diversity import diversify_n7_outcomes
from src.fundamentals_n7_reuse_extension import extend_n7_reuse_plan


@pytest.fixture
def sample():
    f=pd.DataFrame([dict(issue='100101',slot=s,provider_id=str(s),handicap=0,p_W=.55,p_D=.3,p_L=.15,q_W=.5,q_D=.3,q_L=.2) for s in range(1,43)])
    cuts={str(s):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for s in f.slot}
    return f,cuts


@pytest.mark.parametrize('cap',[2,3,4,6])
def test_reuse_caps_complete_tickets_and_cash(sample,cap):
    f,c=sample;p=n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=3,max_uses=cap,unit_cny=2,payout_factor=.65,allocation_seed=0)
    groups=[{r['slot'] for r in p['legs'] if r['group']==g} for g in range(1,p['groups']+1)]
    assert max(Counter(s for g in groups for s in g).values(),default=0)<=cap
    assert all(len(a&b)<=2 for a,b in itertools.combinations(groups,2))
    assert p['stake']==32*p['groups'] and p['stake']+p['cash_cny']==1024
    assert len(p['tickets'])==16*p['groups']


def test_diverse_directions_first_use_and_replay(sample):
    f,c=sample;p=n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=3,max_uses=4,unit_cny=2,payout_factor=.65,allocation_seed=0)
    kw=dict(cutoffs=c,rule='PROBABILITY_OVER_ONE_PLUS_PRIOR_COVERAGE');d=diversify_n7_outcomes(p,**kw)
    assert d['stake']==p['stake'] and [(r['slot'],r['group']) for r in d['legs']]==[(r['slot'],r['group']) for r in p['legs']]
    assert any(r['changed'] for r in d['diversity_ledger'])
    assert all(not r['changed'] for r in d['diversity_ledger'] if sum(r['prior_counts'].values())==0)
    assert any(r['source_support']!=r['selected_support'] and len(r['selected_support'])==1 for r in d['diversity_ledger'])
    assert all(a['p_W']==b['p_W'] and a['q_W']==b['q_W'] and len(a['support'])==len(b['support']) for a,b in zip(p['legs'],d['legs']))
    seen=set()
    for g in range(1,d['groups']+1):
        legs=sorted([r for r in d['legs'] if r['group']==g],key=lambda r:r['slot'])
        for t in [t for t in d['tickets'] if t['group']==g]:
            identity=tuple((r['slot'],code) for r,code in zip(legs,t['code']))
            assert identity not in seen;seen.add(identity)
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    a=settle_n7_single(d,audit);assert a['gross']<=settle_n7_single(p,audit)['gross']
    audit['actual_direction']='D';audit['spf_sp']=99
    assert diversify_n7_outcomes(p,**kw)==d
    with pytest.raises(ValueError):diversify_n7_outcomes(p,cutoffs={},rule=kw['rule'])
    with pytest.raises(ValueError):diversify_n7_outcomes(p,cutoffs=c,rule='UNKNOWN')


@pytest.mark.parametrize('cap',[True,0,5,2.5])
def test_invalid_reuse_cap(sample,cap):
    f,c=sample
    with pytest.raises(ValueError):n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=3,max_uses=cap,unit_cny=2,payout_factor=.65,allocation_seed=0)


def test_nested_extension_preserves_groups_and_identity(sample):
    f,c=sample;p=n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=3,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
    for cap in [3,4,6]:
        q=extend_n7_reuse_plan(p,f,cutoffs=c,max_uses=cap)
        assert q['legs'][:len(p['legs'])]==p['legs'] and q['tickets'][:len(p['tickets'])]==p['tickets']
        assert q['stake']>=p['stake'] and q['cash_cny']<=p['cash_cny']
        groups=[{r['slot'] for r in q['legs'] if r['group']==g} for g in range(1,q['groups']+1)]
        assert max(Counter(s for g in groups for s in g).values())<=cap
        assert all(len(a&b)<=2 for a,b in itertools.combinations(groups,2))
        assert q==extend_n7_reuse_plan(p,f,cutoffs=c,max_uses=cap)
        p=q
    with pytest.raises(ValueError):extend_n7_reuse_plan(p,f,cutoffs=c,max_uses=6)
    bad=f.copy();bad.loc[0,'p_W']=.54;bad.loc[0,'p_D']=.31
    with pytest.raises(ValueError):extend_n7_reuse_plan(n7_single_plan(f,cutoffs=c,budget_cny=1024,single_rule='MAX_SINGLE',single_count=3,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0),bad,cutoffs=c,max_uses=3)
