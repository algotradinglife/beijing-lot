from collections import Counter
from itertools import combinations
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.market_foundation_n7 import market_foundation_n7
from src.fundamentals_n7_single import settle_n7_single


@pytest.mark.parametrize('u',[3,6])
def test_market_only_budget_caps_support_and_settlement(u):
    frame=pd.DataFrame([dict(issue='001',slot=s,provider_id=str(s),handicap=0,
        q_W=.5+.01*s,q_D=.3-.01*s,q_L=.2) for s in range(1,15)])
    cuts={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in frame.slot}
    kw=dict(cutoffs=cuts,max_uses=u,max_pair_overlap=5,budget_cny=1024,unit_cny=2,
        payout_factor=.65,seed=41902,source_version='RAW_MARKET')
    p=market_foundation_n7(frame,**kw)
    assert p==market_foundation_n7(frame,**kw)
    assert p['stake']==64*p['groups']<=1024 and p['cash_cny']==1024-p['stake']
    groups=[]
    for g in range(1,p['groups']+1):
        legs=[r for r in p['legs'] if r['group']==g];groups.append({r['slot'] for r in legs})
        assert len(legs)==7 and sum(len(r['support'])==1 for r in legs)==2
        singles={r['slot'] for r in sorted(legs,key=lambda r:-r['q_W'])[:2]}
        assert {r['slot'] for r in legs if len(r['support'])==1}==singles
        for r in legs:
            order=sorted(range(3),key=lambda i:(-r['q_'+'WDL'[i]],i))[:len(r['support'])]
            assert r['support']==''.join('310'[i] for i in sorted(order))
    assert max(Counter(s for g in groups for s in g).values())<=u
    assert all(len(a&b)<=5 for a,b in combinations(groups,2))
    audit=frame[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    result=settle_n7_single(p,audit)
    assert result['hits']==p['groups']
    assert result['gross']==pytest.approx(p['groups']*2*.65*2**7)
    with pytest.raises(ValueError):market_foundation_n7(frame.assign(p_D=.2),**kw)
    with pytest.raises(ValueError):market_foundation_n7(frame.assign(actual_direction='D'),**kw)
    with pytest.raises(ValueError):market_foundation_n7(frame,**dict(kw,cutoffs={}))
    short=frame.head(6);empty=market_foundation_n7(short,**dict(kw,cutoffs={str(s):cuts[str(s)] for s in short.slot}))
    assert empty['groups']==0 and empty['cash_cny']==1024
