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
