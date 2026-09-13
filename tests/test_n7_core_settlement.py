import copy

import pandas as pd
import pytest

from src.n7_core_settlement import settle_core_layers
from src.temporal_learning.core import stable_json_hash


def test_layers_accounting_and_fail_closed_contracts():
    fixtures = [dict(issue='001', slot=s, provider_id=str(s), handicap=0) for s in range(1, 9)]
    layer = dict(issue='001', fixtures=fixtures, cutoffs={'1': '2010-01-01'},
                 fixture_indices=[list(range(7))], outcomes=[[0]*7], groups=1,
                 stake=2, cash_cny=14, budget_cny=16, unit_cny=2, payout_factor=.65,
                 role='CORE', copy_index=1)
    second = dict(layer, copy_index=2)
    opp = dict(layer, role='OPPORTUNITY', fixture_indices=[list(range(1, 8))])
    plan = dict(schema='CORE_COPY_LAYERS_V1', issue='001', fixtures=fixtures,
                cutoffs=layer['cutoffs'], layers=[layer, second, opp], groups=3,
                stake=6, cash_cny=10, budget_cny=16, unit_cny=2, payout_factor=.65, unique_tickets=2)
    plan['seal'] = stable_json_hash(plan)
    audit = pd.DataFrame(fixtures).assign(actual_direction='W', spf_sp=2., status='READY')
    out = settle_core_layers(plan, audit)
    assert out['hits'] == 2 and out['paid_hits'] == 3
    assert out['gross'] == pytest.approx(3*2*.65*2**7)
    assert out['core_stake'] == 4 and out['opportunity_stake'] == 2
    assert out['net'] == pytest.approx(out['gross']-6)
    assert out['roi'] == pytest.approx(out['gross']/6-1)
    assert settle_core_layers(plan, audit.assign(actual_direction='L'))['hits'] == 0
    assert settle_core_layers(plan, audit.assign(spf_sp=float('nan')))['status'] == 'PENDING_WINNING_SP'
    assert settle_core_layers(plan, audit.assign(handicap=1))['status'] == 'PENDING_AUDIT'
    with pytest.raises(ValueError, match='frozen'):
        settle_core_layers(dict(plan, stake=0), audit)
    mutations = [
        lambda p: p.update(stake=8),
        lambda p: p.update(unique_tickets=3),
        lambda p: p.update(budget_cny=True),
        lambda p: p['layers'][1].update(copy_index=3),
        lambda p: p['layers'][1].update(cutoffs={}),
        lambda p: p['layers'][1].update(outcomes=[[1]*7]),
        lambda p: p['layers'][2].update(fixture_indices=[list(range(7))]),
        lambda p: p['layers'][2].update(copy_index=2),
    ]
    for mutate in mutations:
        bad = copy.deepcopy(plan); bad.pop('seal'); mutate(bad); bad['seal'] = stable_json_hash(bad)
        with pytest.raises(ValueError):
            settle_core_layers(bad, audit)
    empty = dict(plan, layers=[], groups=0, stake=0, cash_cny=16, unique_tickets=0)
    empty.pop('seal'); empty['seal'] = stable_json_hash(empty)
    assert settle_core_layers(empty, audit)['status'] == 'NO_BET'
