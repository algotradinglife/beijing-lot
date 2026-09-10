import copy,itertools,math
import pytest
from tests.test_fundamentals_repeated_double import source
from src.fundamentals_market_conflict import replace_market_conflict_doubles
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning import Cutoff


@pytest.mark.parametrize('depth',[1,2])
def test_conflict_gate_preserves_roles_money_and_direction(source,depth):
    _,cuts,plans=source;base=copy.deepcopy(plans[depth])
    for r in base['legs']:
        r.update(p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.2,q_L=.4)
    base['seal']=stable_json_hash({k:v for k,v in base.items() if k!='seal'})
    original=copy.deepcopy(base)
    p=replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=.2,minimum_market_tail_lead=.2)
    assert base==original
    assert any(r['changed'] for r in p['diversity_ledger'])
    for r in p['diversity_ledger']:
        assert r['changed']==bool(r['prior_appearances'] and len(r['source_support'])==2)
        assert r['total_variation']==pytest.approx(.2)
        assert r['market_tail_lead']==pytest.approx(.2)
        assert r['selected_mass']<=r['original_mass']+1e-12
        assert r['selected_market_mass']>=r['original_market_mass']-1e-12
    for k in ['groups','stake','cash_cny','budget_cny','group_units','cutoffs','input_sha256','single_count','paid_ticket_units']:
        assert p[k]==base[k]
    for g in range(1,p['groups']+1):
        legs=sorted([r for r in p['legs'] if r['group']==g],key=lambda r:r['slot'])
        assert {t['code'] for t in p['tickets'] if t['group']==g}=={''.join(c) for c in itertools.product(*(r['support'] for r in legs))}
        assert p['group_probability'][g-1]==pytest.approx(math.prod(sum(r['p_'+d] for d,c in zip('WDL','310') if c in r['support']) for r in legs))
    for tv,lead in [(.20001,.2),(.2,.20001)]:
        q=replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=tv,minimum_market_tail_lead=lead)
        assert q['tickets']==base['tickets'] and not any(r['changed'] for r in q['diversity_ledger'])
    # Large distribution disagreement alone must not reverse an unsupported tail.
    for r in base['legs']:r.update(q_W=.2,q_D=.6,q_L=.2)
    base['seal']=stable_json_hash({k:v for k,v in base.items() if k!='seal'})
    assert replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=.1,minimum_market_tail_lead=.05)['tickets']==base['tickets']


def test_bad_thresholds_cutoffs_and_reapplication_fail(source):
    _,cuts,plans=source;base=plans[2]
    for value in [True,-.1,1.1,float('nan'),float('inf'),'0.1']:
        with pytest.raises(ValueError):replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=value,minimum_market_tail_lead=.05)
        with pytest.raises(ValueError):replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=.1,minimum_market_tail_lead=value)
    with pytest.raises(ValueError):replace_market_conflict_doubles(base,cutoffs={k:Cutoff.decision_epoch('100101','2009-01-01T00:00:00Z') for k in cuts},minimum_tv=.1,minimum_market_tail_lead=.05)
    p=replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=.1,minimum_market_tail_lead=.05)
    with pytest.raises(ValueError):replace_market_conflict_doubles(p,cutoffs=cuts,minimum_tv=.1,minimum_market_tail_lead=.05)
