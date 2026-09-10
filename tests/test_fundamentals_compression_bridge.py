import copy
import itertools
from collections import Counter
import numpy as np
import pandas as pd
import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_n7_single import n7_single_plan,settle_n7_single
from src.fundamentals_compression_breadth import breadth_candidates,breadth_scenarios,breadth_metrics,settle_breadth_bundle
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan,bind_bridge_reference


@pytest.fixture(scope='module')
def data():
    f=pd.DataFrame([dict(issue='100101',slot=i,provider_id=str(i),handicap=0,p_W=.57+.006*i,p_D=.28-.003*i,p_L=.15-.003*i,q_W=.5,q_D=.3,q_L=.2) for i in range(1,22)])
    c={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in f.slot}
    refs={d:n7_single_plan(f,cutoffs=c,budget_cny=512,single_rule='MAX_SINGLE',single_count=d,max_uses=2,unit_cny=2,payout_factor=.65,allocation_seed=0) for d in (1,2)}
    return f,c,refs,breadth_candidates(f,cutoffs=c,seed=41900,pool_size=128)


@pytest.mark.parametrize('depth',[1,2])
def test_factorial_controls(data,depth):
    f,c,refs,pool=data;s=bridge_surface(f,pool,refs,cutoffs=c,depth=depth)
    design=breadth_scenarios(f,s,cutoffs=c,seed=41901,draws=128);evaluation=breadth_scenarios(f,s,cutoffs=c,seed=41902,draws=2048)
    bound=bind_bridge_reference(refs[depth],s,design,cutoffs=c)
    assert bound['tickets']==refs[depth]['tickets'] and bound['legs']==refs[depth]['legs'] and bound['stake']==refs[depth]['stake']
    assert 0<=breadth_metrics(bound,evaluation,cutoffs=c)['model_union']<=1
    audit=pd.DataFrame([dict(issue='100101',slot=i,provider_id=str(i),handicap=0,status='OK',actual_direction='W',spf_sp=2.) for i in f.slot])
    for prefix,quality,cap in itertools.product([True,False],['TOP2','COMPRESSED'],['STRICT','FREE']):
        plans={cash:bridge_plan(f,s,design,refs[depth],cutoffs=c,preserve_prefix=prefix,quality=quality,overlap=cap,cash_policy=cash,budget_cny=512,unit_cny=2,payout_factor=.65) for cash in ['HOLD','REPEAT_BEST']}
        h,r=plans.values()
        assert h['selected_candidates']==r['selected_candidates'] and h['legs']==r['legs']
        assert r['stake']==512 and r['cash_cny']==0
        assert breadth_metrics(h,evaluation,cutoffs=c)['model_union']==breadth_metrics(r,evaluation,cutoffs=c)['model_union']
        for p in plans.values():
            assert p['stake']+p['cash_cny']==512 and p['shape']==f'C{depth}E0' and 'group_budget_cny' not in p
            sets=[{l['slot'] for l in p['legs'] if l['group']==g} for g in range(1,p['groups']+1)]
            assert len(set(map(frozenset,sets)))==p['groups']
            if cap=='STRICT':
                assert max(Counter(i for g in sets for i in g).values())<=2
                assert all(len(a&b)<=2 for a,b in itertools.combinations(sets,2))
            for g in range(1,p['groups']+1):
                legs=[l for l in p['legs'] if l['group']==g];ts=[t for t in p['tickets'] if t['group']==g]
                assert sum(len(l['support'])==1 for l in legs)==depth
                assert {t['code'] for t in ts}=={''.join(z) for z in itertools.product(*(l['support'] for l in legs))}
            assert sum(t['units']*2 for t in p['tickets'])==p['stake']
            result=settle_breadth_bundle({'x':{'plan':p}},audit)['x'];old=settle_n7_single(p,audit)
            assert result['gross']==old['gross'] and result['net']==old['net']
            expected=sum(2*.65*t['units']*2**7 for t in p['tickets'] if set(t['code'])=={'3'})
            assert result['gross']==pytest.approx(expected)
        changed=audit.copy();changed.actual_direction='L'
        assert settle_breadth_bundle({'x':{'plan':r}},changed)['x']['gross']==0
        assert bridge_plan(f,s,design,refs[depth],cutoffs=c,preserve_prefix=prefix,quality=quality,overlap=cap,cash_policy='HOLD',budget_cny=512,unit_cny=2,payout_factor=.65)==h


def test_identity_failures(data):
    f,c,refs,pool=data;s=bridge_surface(f,pool,refs,cutoffs=c,depth=1);design=breadth_scenarios(f,s,cutoffs=c,seed=1,draws=32)
    kwargs=dict(cutoffs=c,preserve_prefix=True,quality='TOP2',overlap='STRICT',cash_policy='HOLD',budget_cny=512,unit_cny=2,payout_factor=.65)
    earlier={k:Cutoff.decision_epoch('100101','2009-01-01T00:00:00Z') for k in c}
    with pytest.raises(ValueError):bridge_surface(f,pool,refs,cutoffs=earlier,depth=1)
    with pytest.raises(ValueError):bridge_surface(f,pool,{1:refs[1]},cutoffs=c,depth=1)
    bad=copy.deepcopy(s);bad['mass'][0]=.8
    with pytest.raises(ValueError):bridge_plan(f,bad,design,refs[1],**kwargs)
    for k,v in [('budget_cny',1024),('quality','EV'),('cash_policy','ALL'),('overlap','OTHER'),('preserve_prefix',1),('unit_cny',4)]:
        with pytest.raises(ValueError):bridge_plan(f,s,design,refs[1],**{**kwargs,k:v})
    bad=copy.deepcopy(design);bad['seed']=2
    with pytest.raises(ValueError):bridge_plan(f,s,bad,refs[1],**kwargs)
    with pytest.raises(ValueError):bind_bridge_reference(refs[1],s,bad,cutoffs=c)
    with pytest.raises(ValueError):bind_bridge_reference(refs[2],s,design,cutoffs=c)
    changed=f.copy();changed['p_W']+=.01;changed['p_D']-=.01
    with pytest.raises(ValueError):bridge_plan(changed,s,design,refs[1],**kwargs)
