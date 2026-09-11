import copy
import itertools
import pytest
from tests.test_fundamentals_double_source import source
from src.fundamentals_double_source import paired_double_source
from src.fundamentals_reuse_random import random_reuse_plan
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('mode',['BASELINE','MARKET'])
def test_first_use_fixed_repeat_changes_and_cost(source,mode):
    plan,cuts=source
    plan.pop('seal');plan['components']=[copy.deepcopy(plan['components'][0]) for _ in range(3)];plan['stake']=192;plan['seal']=stable_json_hash(plan)
    base=paired_double_source(plan,cutoffs=cuts,double_source=mode,budget_cny=1024,unit_cny=2,payout_factor=.65)
    original=copy.deepcopy(base)
    kw=dict(cutoffs=cuts,group_size=7,budget_cny=1024,unit_cny=2,payout_factor=.65,seed=7)
    zero=random_reuse_plan(base,probability=0,**kw)
    one=random_reuse_plan(base,probability=1,**kw)
    assert base==original and zero['components']==base['components']
    assert one['components'][0]==base['components'][0]
    assert [l['swapped'] for l in one['swap_ledger']]==[False]*7+[True]*14
    assert one['components'][1]['legs'][0]['support']=='1'
    assert one['components'][1]['legs'][2]['support']=='30'
    assert one['stake']==192 and one['cash_cny']==832
    assert all(len(p['tickets'])==32 for p in one['components'])
    sampled=random_reuse_plan(base,probability=.3,**kw)
    assert sampled==random_reuse_plan(base,probability=.3,**kw)
    assert all(l['swapped']==(l['eligible'] and l['draw']<.3) for l in sampled['swap_ledger'])
    assert sampled!=random_reuse_plan(base,probability=.3,**dict(kw,seed=8))
    with pytest.raises(ValueError):random_reuse_plan(base,probability=-.1,**kw)
    with pytest.raises(ValueError):random_reuse_plan(base,probability=.3,**dict(kw,seed=-1))
    with pytest.raises(ValueError):random_reuse_plan(base,probability=.3,**dict(kw,cutoffs={}))
    bad=copy.deepcopy(base);bad['stake']=0
    with pytest.raises(ValueError):random_reuse_plan(bad,probability=.3,**kw)


def test_no_bet_and_paired_draws(source):
    plan,cuts=source
    b=paired_double_source(plan,cutoffs=cuts,double_source='BASELINE',budget_cny=1024,unit_cny=2,payout_factor=.65)
    m=paired_double_source(plan,cutoffs=cuts,double_source='MARKET',budget_cny=1024,unit_cny=2,payout_factor=.65)
    kw=dict(cutoffs=cuts,group_size=7,seed=0,probability=.3,budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert [l['draw'] for l in random_reuse_plan(b,**kw)['swap_ledger']]==[l['draw'] for l in random_reuse_plan(m,**kw)['swap_ledger']]
    b.pop('seal');b.update(components=[],stake=0,cash_cny=1024);b['seal']=stable_json_hash(b)
    assert random_reuse_plan(b,**kw)['swap_ledger']==[]


def test_six_leg_two_single_price_and_repeat(source):
    plan,cuts=source
    b=paired_double_source(plan,cutoffs=cuts,double_source='BASELINE',budget_cny=1024,unit_cny=2,payout_factor=.65)
    part=b['components'][0];part.pop('seal');part['legs']=[r for r in part['legs'] if r['slot']!=6]
    part['n']=6;part['stake']=32;part['cutoffs'].pop('6');cuts={s:c for s,c in cuts.items() if s!='6'}
    part['tickets']=[dict(group=1,code=''.join(c),units=1) for c in itertools.product(*(r['support'] for r in part['legs']))]
    part['seal']=stable_json_hash(part)
    b.pop('seal');b.update(components=[copy.deepcopy(part),copy.deepcopy(part)],stake=64,cash_cny=960);b['seal']=stable_json_hash(b)
    z=random_reuse_plan(b,cutoffs=cuts,seed=0,probability=1,group_size=6,budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert z['stake']==64 and z['cash_cny']==960
    assert all(len(p['tickets'])==16 for p in z['components'])
    assert [x['swapped'] for x in z['swap_ledger']]==[False]*6+[True]*6
    with pytest.raises(ValueError):random_reuse_plan(b,cutoffs=cuts,seed=0,probability=1,group_size=7,budget_cny=1024,unit_cny=2,payout_factor=.65)
