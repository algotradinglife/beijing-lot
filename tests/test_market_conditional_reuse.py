import copy
from collections import Counter
from itertools import combinations
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.market_foundation_n7 import market_foundation_n7
from src.market_conditional_reuse import conditional_reuse_plan,conditional_reuse_trigger,settle_conditional_reuse


def test_trigger_boundaries_draw_direction_and_first_use():
    r=dict(issue='001',q_W=.4,q_L=.35,q_D=.25,strength_W=.4,strength_D=.35,strength_L=.25)
    k=dict(cutoff=Cutoff.decision_epoch('001','2010-01-01'),single=True,repeated=True,single_gap=.05,draw_gap=.1,draw_enabled=True)
    assert conditional_reuse_trigger(r,**k)[0]
    assert not conditional_reuse_trigger(r,**dict(k,repeated=False))[0]
    assert conditional_reuse_trigger(r,**dict(k,single=False))[0]
    assert not conditional_reuse_trigger(r,**dict(k,single=False,draw_gap=.05))[0]
    assert not conditional_reuse_trigger(dict(r,strength_D=.1,strength_L=.5),**dict(k,single=False))[0]
    with pytest.raises(ValueError):conditional_reuse_trigger(r,**dict(k,cutoff=None))


@pytest.mark.parametrize('mode',['SWAP','AVOID'])
def test_plan_caps_repeated_only_and_input_invariance(mode):
    f=pd.DataFrame([dict(issue='001',slot=s,provider_id=str(s),handicap=0,
        q_W=.4,q_D=.25,q_L=.35) for s in range(1,22)])
    c={str(s):Cutoff.decision_epoch('001','2010-01-01') for s in f.slot}
    base=market_foundation_n7(f,cutoffs=c,max_uses=3,max_pair_overlap=5,budget_cny=1024,
        unit_cny=2,payout_factor=.65,seed=41902,source_version='market-balance-draw-1.0.0-diagnostic',single_count=2)
    frame=f.assign(strength_W=.4,strength_D=.35,strength_L=.25)
    before=copy.deepcopy(base)
    args=dict(cutoffs=c,single_gap=.05,draw_gap=.1,draw_enabled=True,mode=mode)
    p=conditional_reuse_plan(base,frame,**args)
    assert base==before and p==conditional_reuse_plan(base,frame,**args)
    assert p['stake']+p['cash_cny']==1024 and len(p['tickets'])*2==p['stake']
    assert all(not z['triggered'] for z in p['conditional_ledger'] if not z['repeated'])
    groups=[{r['slot'] for r in p['legs'] if r['group']==g} for g in range(1,p['groups']+1)]
    assert max(Counter(s for g in groups for s in g).values())<=3
    assert all(len(a&b)<=5 for a,b in combinations(groups,2))
    assert all(sum(len(r['support'])==1 for r in p['legs'] if r['group']==g)>=2 for g in range(1,p['groups']+1))
    if mode=='SWAP':
        assert p['stake']<base['stake'] and [r['slot'] for r in p['legs']]==[r['slot'] for r in base['legs']]
        assert any(z['triggered'] for z in p['conditional_ledger'])
        for z in p['conditional_ledger']:
            if z['triggered']:assert z['support']==('0' if z['single'] else '1')
    else:
        assert p['groups']<base['groups'] or any(z['replacement_slot'] is not None for z in p['conditional_ledger'])
    same=conditional_reuse_plan(base,frame,**dict(args,single_gap=None,draw_enabled=False))
    assert same['tickets']==base['tickets']
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    settled=settle_conditional_reuse(p,audit)
    expected=sum(all('3' in r['support'] for r in p['legs'] if r['group']==g)
        for g in range(1,p['groups']+1))
    assert settled['hits']==expected
    assert settled['gross']==pytest.approx(expected*2*.65*2**7)
    assert settled['net']==pytest.approx(settled['gross']-2*len(p['tickets']))
    assert settled['cash']==1024-p['stake']
    with pytest.raises(ValueError):settle_conditional_reuse(dict(p,stake=0),audit)
    pending=audit.copy();pending['spf_sp']=float('nan')
    assert settle_conditional_reuse(p,pending)['status']=='PENDING_AUDIT_OR_WINNING_SP'
    empty={k:v for k,v in p.items() if k!='seal'}
    empty.update(groups=0,legs=[],tickets=[],stake=0,cash_cny=1024)
    empty['seal']=stable_json_hash(empty)
    no_bet=settle_conditional_reuse(empty,audit)
    assert no_bet['status']=='NO_BET' and no_bet['net']==0 and no_bet['cash']==1024
    with pytest.raises(ValueError):conditional_reuse_plan(base,frame.assign(actual_direction='D'),**args)
    with pytest.raises(ValueError):conditional_reuse_plan(base,frame,**dict(args,cutoffs={}))
