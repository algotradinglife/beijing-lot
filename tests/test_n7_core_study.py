import pytest
from src.n7_core_study import describe_core_plan


def test_projection_preserves_units_nulls_and_no_actual_dependency():
    p = dict(budget_cny=1024, cash_cny=24, funded_sleeves=8, unique_tickets=300,
             opening_stop='ALL_CORE_OPEN', solver_status='DONE',
             policy=dict(mode='MULTIPLY'), training=dict(any_hit=.5, payoff_ratio=None),
             evaluation=dict(any_hit=.4, expected_net=-20))
    z = describe_core_plan(p)
    assert z['mode'] == 'MULTIPLY' and z['training_any_hit'] == .5
    assert z['training_payoff_ratio'] is None and z['evaluation_expected_net'] == -20
    assert z == describe_core_plan(dict(p, actual_direction='L'))
    with pytest.raises(KeyError):
        describe_core_plan({})


def test_settlement_and_projection_have_disjoint_fields():
    import gzip
    import json
    from pathlib import Path
    import pandas as pd
    from src.n7_core_settlement import settle_core_layers
    x=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/n7_core433_replay.json.gz').read_bytes()))
    p=x['plans'][0]
    audit=pd.DataFrame([dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],
        handicap=f['handicap'],actual_direction='W',spf_sp=2.,status='READY') for f in p['fixtures']])
    settled=settle_core_layers(p,audit);description=describe_core_plan(p)
    assert not (set(settled)&set(description))
    row=dict(**settled,**description)
    assert row['unique_tickets']==p['unique_tickets']
    assert row['cash']==row['cash_cny']
