"""Contracts for budget-preserving C2 additions under relaxed exposure caps."""
import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_n7_reuse_extension import extend_n7_reuse_plan


@pytest.fixture
def source():
    frame=pd.DataFrame([dict(issue='100101',slot=s,provider_id=str(s),handicap=0,p_W=.55,p_D=.30,p_L=.15,q_W=.50,q_D=.30,q_L=.20) for s in range(1,17)])
    cuts={str(s):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for s in frame.slot}
    plan=n7_single_plan(frame,cutoffs=cuts,budget_cny=512,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
    return frame,cuts,plan


@pytest.mark.parametrize('uses,pair',[(u,p) for u in [2,3,4,6] for p in [2,3,4] if (u,p)!=(2,2)])
def test_append_contract_and_independent_cash(source,uses,pair):
    f,c,b=source;p=extend_n7_reuse_plan(b,f,cutoffs=c,max_uses=uses,max_pair_overlap=pair)
    assert p['legs'][:len(b['legs'])]==b['legs'] and p['tickets'][:len(b['tickets'])]==b['tickets']
    assert p['budget_cny']==512 and p['stake']+p['cash_cny']==512 and b['stake']<=p['stake']<=512
    assert p['stake']==64*p['groups'] and all(t['units']==1 for t in p['tickets'])
    sets=[];identities=set()
    for g in range(1,p['groups']+1):
        legs=sorted([r for r in p['legs'] if r['group']==g],key=lambda r:r['slot']);sets.append({r['slot'] for r in legs})
        assert sorted(len(r['support']) for r in legs)==[1,1,2,2,2,2,2]
        tickets=[t for t in p['tickets'] if t['group']==g];assert len(tickets)==32
        assert {t['code'] for t in tickets}=={''.join(x) for x in itertools.product(*(r['support'] for r in legs))}
        for t in tickets:
            identity=tuple((r['slot'],z) for r,z in zip(legs,t['code']));assert identity not in identities;identities.add(identity)
    assert max(Counter(s for g in sets for s in g).values())<=uses
    assert all(len(a&b)<=pair for a,b in itertools.combinations(sets,2))
    if pair==2:assert p['groups']==2  # 2+2 from existing groups plus two unused <7
    else:assert p['groups']>2
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    r=settle_n7_single(p,audit);assert r['gross']==pytest.approx(p['groups']*2*.65*2**7)
    audit['actual_direction']='L';audit['spf_sp']=999
    assert extend_n7_reuse_plan(b,f,cutoffs=c,max_uses=uses,max_pair_overlap=pair)==p


@pytest.mark.parametrize('uses,pair',[(2,2),(1,3),(3,1),(3,5),(True,3),(3,True),(3,2.5)])
def test_invalid_relaxation(source,uses,pair):
    f,c,b=source
    with pytest.raises(ValueError):extend_n7_reuse_plan(b,f,cutoffs=c,max_uses=uses,max_pair_overlap=pair)


def test_no_cash_and_wrong_input(source):
    f,c,b=source
    full=n7_single_plan(f,cutoffs=c,budget_cny=128,single_rule='MAX_SINGLE',single_count=2,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0)
    p=extend_n7_reuse_plan(full,f,cutoffs=c,max_uses=6,max_pair_overlap=4)
    assert p['legs']==full['legs'] and p['cash_cny']==0 and not p['overlap_ledger']
    with pytest.raises(ValueError):extend_n7_reuse_plan(b,f,cutoffs={},max_uses=3,max_pair_overlap=3)
    changed=f.copy();changed.loc[0,'q_W']=.49;changed.loc[0,'q_D']=.31
    with pytest.raises(ValueError,match='identity'):extend_n7_reuse_plan(b,changed,cutoffs=c,max_uses=3,max_pair_overlap=3)
