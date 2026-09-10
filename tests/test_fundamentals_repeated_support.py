import copy,itertools,math
import pytest
from tests.test_fundamentals_repeated_double import source
from src.fundamentals_repeated_support import replace_repeated_support
from src.fundamentals_n7_diversity import replace_repeated_double_tail
from src.fundamentals_market_conflict import replace_market_conflict_doubles
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from tests.test_fundamentals_compression_bridge import data
from src.fundamentals_compression_bridge import bridge_surface,bridge_plan
from src.fundamentals_compression_breadth import breadth_scenarios


@pytest.mark.parametrize('singles,double_rule',[(False,'NONE'),(True,'NONE'),(False,'GAP'),(False,'MARKET'),(False,'EITHER'),(True,'EITHER')])
def test_fixed_supports_gates_tickets_and_money(source,singles,double_rule):
    _,cuts,plans=source;base=copy.deepcopy(plans[2])
    for r in base['legs']:r.update(p_W=.5,p_D=.275,p_L=.225,q_W=.3,q_D=.25,q_L=.45)
    base['seal']=stable_json_hash({k:v for k,v in base.items() if k!='seal'});original=copy.deepcopy(base)
    p=replace_repeated_support(base,cutoffs=cuts,change_singles=singles,double_rule=double_rule,
        single_ceiling=.5,max_gap=.05,minimum_tv=.2,minimum_market_tail_lead=.2)
    assert base==original
    for row in p['diversity_ledger']:
        repeated=bool(row['prior_appearances']);single=len(row['source_support'])==1
        expected=('1' if single else '30') if repeated and (singles if single else double_rule!='NONE') else row['source_support']
        assert row['selected_support']==expected
        assert row['changed']==(expected!=row['source_support'])
    for k in ['groups','stake','cash_cny','budget_cny','group_units','cutoffs','input_sha256','single_count','paid_ticket_units']:
        assert p[k]==base[k]
    for g in range(1,p['groups']+1):
        legs=sorted([r for r in p['legs'] if r['group']==g],key=lambda r:r['slot'])
        assert sorted(len(r['support']) for r in legs)==[1,1,2,2,2,2,2]
        assert {t['code'] for t in p['tickets'] if t['group']==g}=={''.join(c) for c in itertools.product(*(r['support'] for r in legs))}
        assert p['group_probability'][g-1]==pytest.approx(math.prod(sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs))
    assert p['seal']==stable_json_hash({k:v for k,v in p.items() if k!='seal'})
    # A ceiling just below p1 must leave singles unchanged.
    q=replace_repeated_support(base,cutoffs=cuts,change_singles=True,double_rule='NONE',
        single_ceiling=.499,max_gap=.05,minimum_tv=.2,minimum_market_tail_lead=.2)
    assert q['tickets']==base['tickets']


def test_existing_gates_match_and_bad_inputs_fail(source):
    _,cuts,plans=source;base=plans[2]
    kw=dict(cutoffs=cuts,change_singles=False,double_rule='GAP',single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
    assert replace_repeated_support(base,**kw)['tickets']==replace_repeated_double_tail(base,cutoffs=cuts,max_gap=.05)['tickets']
    assert replace_repeated_support(base,**dict(kw,double_rule='MARKET'))['tickets']==replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=.15,minimum_market_tail_lead=.05)['tickets']
    for bad in [True,-1,2,float('nan')]:
        with pytest.raises(ValueError):replace_repeated_support(base,**dict(kw,single_ceiling=bad))
    for bad in [dict(double_rule='BAD'),dict(change_singles=1),dict(cutoffs={})]:
        with pytest.raises((ValueError,KeyError)):replace_repeated_support(base,**dict(kw,**bad))
    with pytest.raises(ValueError):replace_repeated_support(plans[1],**kw)
    with pytest.raises(ValueError):replace_repeated_support(replace_repeated_support(base,**kw),**kw)
    bad=copy.deepcopy(base);bad['stake']+=1
    with pytest.raises(ValueError):replace_repeated_support(bad,**kw)
    future={k:Cutoff.decision_epoch(base['issue'],'2099-01-01T00:00:00Z') for k in cuts}
    with pytest.raises(ValueError):replace_repeated_support(base,**dict(kw,cutoffs=future))


@pytest.mark.parametrize('p,q,gap_hit,market_hit',[
    ((.6,.21,.19),(.6,.21,.19),True,False),
    ((.5,.35,.15),(.25,.15,.6),False,True),
    ((.6,.3,.1),(.6,.3,.1),False,False)])
def test_double_or_really_accepts_either_gate(source,p,q,gap_hit,market_hit):
    _,cuts,plans=source;base=copy.deepcopy(plans[2])
    for r in base['legs']:r.update(**dict(zip(['p_W','p_D','p_L','q_W','q_D','q_L'],p+q)))
    base['seal']=stable_json_hash({k:v for k,v in base.items() if k!='seal'})
    plan=replace_repeated_support(base,cutoffs=cuts,change_singles=False,double_rule='EITHER',
        single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
    for row in plan['diversity_ledger']:
        assert row['gap_qualifies']==gap_hit
        assert row['market_qualifies']==market_hit
        assert row['changed']==bool(row['prior_appearances'] and len(row['source_support'])==2 and (gap_hit or market_hit))


@pytest.mark.parametrize('p1,changes',[(.75,True),(.750001,False)])
def test_requested_single_ceiling_inclusive(source,p1,changes):
    _,cuts,plans=source;base=copy.deepcopy(plans[2])
    for r in base['legs']:r.update(p_W=p1,p_D=.15,p_L=.85-p1)
    base['seal']=stable_json_hash({k:v for k,v in base.items() if k!='seal'})
    plan=replace_repeated_support(base,cutoffs=cuts,change_singles=True,double_rule='NONE',
        single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
    assert any(r['prior_appearances'] and len(r['source_support'])==1 for r in plan['diversity_ledger'])
    for row in plan['diversity_ledger']:
        assert row['changed']==bool(changes and row['prior_appearances'] and len(row['source_support'])==1)


@pytest.mark.parametrize('uses,pair',[(1,0),(2,2),(2,4),(6,4),(6,5),(16,6)])
def test_single75_preserves_frozen_caps_cash_and_roles(data,uses,pair):
    f,c,refs,pool=data;surface=bridge_surface(f,pool,refs,cutoffs=c,depth=2)
    design=breadth_scenarios(f,surface,cutoffs=c,seed=41901,draws=128)
    base=bridge_plan(f,surface,design,refs[2],cutoffs=c,preserve_prefix=True,quality='TOP2',
        overlap='CAPPED',max_uses=uses,max_pair_overlap=pair,cash_policy='HOLD',budget_cny=512,unit_cny=2,payout_factor=.65)
    frozen=copy.deepcopy(base)
    plan=replace_repeated_support(base,cutoffs=c,change_singles=True,double_rule='NONE',
        single_ceiling=.75,max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05)
    assert base==frozen
    for key in ['groups','stake','cash_cny','budget_cny','max_uses','max_pair_overlap','cutoffs','group_units']:
        assert plan[key]==base[key]
    before={(r['group'],r['slot']):r for r in base['legs']};seen=set()
    for r in plan['legs']:
        old=before[r['group'],r['slot']];order=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))
        support=old['support']
        if r['slot'] in seen and len(support)==1 and r['p_'+order[0]]<=.75+1e-12:
            support=dict(W='3',D='1',L='0')[order[1]]
        assert r==dict(old,support=support);seen.add(r['slot'])
    for g in range(1,plan['groups']+1):
        legs=sorted([r for r in plan['legs'] if r['group']==g],key=lambda r:r['slot'])
        assert {t['code'] for t in plan['tickets'] if t['group']==g}=={''.join(c) for c in itertools.product(*(r['support'] for r in legs))}
    assert sum(2*t['units'] for t in plan['tickets'])==base['stake']
    if uses==1:assert plan['tickets']==base['tickets'] and not any(r['changed'] for r in plan['diversity_ledger'])
