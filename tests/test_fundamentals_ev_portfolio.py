import itertools
import math
import random
import pytest
from src.fundamentals_ev_portfolio import optimize_seven_ev
from src.temporal_learning import Cutoff


def test_assignment_hull_matches_exhaustive_subsets():
    for seed in range(15):
        rng=random.Random(seed)
        rows=[dict(issue='100104',slot=i+1,provider_id=str(i+1),main_factor=rng.uniform(.4,4),protection_factor=rng.uniform(.05,8)) for i in range(11)]
        cuts={str(r['slot']):Cutoff.decision_epoch('100104','2010-01-10T00:00:00Z') for r in rows}
        result=optimize_seven_ev(rows,cutoffs=cuts,owner_exception='OWNER_AUTHORIZED_HISTORICAL_RETURNS',n=7,unit_cny=2,budget_cny=1024,main_multiples=3,payout_factor=.65)
        brute=max(.65*(6*math.prod(r['main_factor'] for r in combo)+sum(w*r['protection_factor'] for w,r in zip([38,38,36,36,36,36,36],sorted(combo,key=lambda r:-r['protection_factor'])))) for combo in itertools.combinations(rows,7))
        assert result['expected_gross']==pytest.approx(brute,abs=1e-7)
        assert sum(r['protection_stake'] for r in result['selected'])==256
        assert len({r['provider_id'] for r in result['selected']})==7


def test_fair_proxy_constant_ties_and_no_label_input():
    rows=[dict(issue='i',slot=i+1,provider_id=str(i+1),main_factor=2.,protection_factor=1.,actual_home=999,winning_sp=99999) for i in range(9)]
    cuts={str(r['slot']):Cutoff.decision_epoch('i','2010-01-10T00:00:00Z') for r in rows}
    policy=dict(cutoffs=cuts,owner_exception='OWNER_AUTHORIZED_HISTORICAL_RETURNS',n=7,unit_cny=2,budget_cny=1024,main_multiples=3,payout_factor=.65)
    a=optimize_seven_ev(rows,**policy)
    assert a['expected_roi']==pytest.approx(-.35)
    assert [r['slot'] for r in a['selected']]==list(range(1,8))
    assert optimize_seven_ev(list(reversed(rows)),**policy)['expected_gross']==a['expected_gross']
    with pytest.raises(ValueError,match='seven'):optimize_seven_ev(rows[:6],**policy)
    with pytest.raises(ValueError,match='cutoff'):optimize_seven_ev(rows,**dict(policy,cutoffs={}))
    rows[1]['provider_id']=rows[0]['provider_id']
    with pytest.raises(ValueError,match='unique'):optimize_seven_ev(rows,**policy)
