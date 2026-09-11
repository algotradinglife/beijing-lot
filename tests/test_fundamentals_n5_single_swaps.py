import copy
import itertools
from collections import Counter
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
from src.fundamentals_reuse_random import random_reuse_plan


@pytest.fixture
def base():
    rows=[]
    for s in range(1,16):
        p,q=([.7,.2,.1],[.7,.2,.1]) if s<3 else ([.4,.35,.25],[.4,.35,.25])
        if s==15:p,q=[.6,.3,.1],[.4,.2,.4]
        rows.append(dict(issue='001',slot=s,provider_id=str(s),handicap=1,
            **dict(zip(['p_W','p_D','p_L'],p)),**dict(zip(['q_W','q_D','q_L'],q))))
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01T00:00:00Z') for s in range(1,16)}
    p=independent_consensus_portfolio(pd.DataFrame(rows),cutoffs=cuts,conversion_budget_fraction=0,
        budget_cny=1024,minimum_anchor_market=.5,max_uses=64,max_pair_overlap=4,
        unit_cny=2,payout_factor=.65,seed=0,group_size=5)
    p.pop('seal');p['double_source']='BASELINE';p['seal']=stable_json_hash(p)
    return p,cuts


def test_n5_full_budget_no_binding_reuse_cap(base):
    p,cuts=base
    assert len(p['components'])==64 and p['stake']==1024 and p['cash_cny']==0
    assert max(Counter(r['slot'] for c in p['components'] for r in c['legs']).values())==64
    sets=[{r['slot'] for r in c['legs']} for c in p['components']]
    assert all(len(a&b)<=4 for a,b in itertools.combinations(sets,2))
    assert all(Counter(r['role'] for r in c['legs'])==dict(A=2,D=2,C=1) and c['stake']==16 and len(c['tickets'])==8 for c in p['components'])


@pytest.mark.parametrize('probability',[0,.1,.25,1])
def test_only_reused_singles_change(base,probability):
    p,cuts=base;before=copy.deepcopy(p)
    kw=dict(cutoffs=cuts,seed=7,single_probability=probability,double_probability=0,group_size=5,budget_cny=1024,unit_cny=2,payout_factor=.65)
    z=random_reuse_plan(p,**kw)
    assert p==before and z==random_reuse_plan(p,**kw)
    assert z['components'][0]==p['components'][0]
    assert all(l['swapped']==(l['single'] and l['eligible'] and l['draw']<probability) for l in z['swap_ledger'])
    assert all(l['support']==('1' if l['swapped'] else l['original']) for l in z['swap_ledger'])
    assert z['stake']==1024 and z['cash_cny']==0
    assert all(len(c['tickets'])==8 and all(t['units']==1 for t in c['tickets']) for c in z['components'])
    if probability==.25:
        assert z!=random_reuse_plan(p,**dict(kw,seed=8))
        for bad in (-.1,1.1,float('nan'),True):
            with pytest.raises(ValueError):random_reuse_plan(p,**dict(kw,double_probability=bad))
        with pytest.raises(ValueError):random_reuse_plan(p,**dict(kw,cutoffs={}))
