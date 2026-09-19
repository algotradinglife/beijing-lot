import copy
import pytest
from src.n7_purchase_labels import bind_purchase_roster_labels


def test_binding_preserves_missing_results_and_order():
    fixtures = [dict(issue='001', slot=2, provider_id='42', handicap=-1)]
    inventory = [dict(slot=2, provider_id=42, home='H', away='A')]
    outcomes = [dict(slot=2, actual_home=None, actual_away=None, result_state='未完场')]
    before = copy.deepcopy((fixtures, inventory, outcomes))
    rows = bind_purchase_roster_labels('001', fixtures, inventory, outcomes, 'ADDITIONAL')
    assert rows == [dict(issue='001', slot=2, provider_id='42', handicap=-1,
                         home='H', away='A', actual_home=None, actual_away=None,
                         result_state='未完场', cohort='ADDITIONAL')]
    assert (fixtures, inventory, outcomes) == before


@pytest.mark.parametrize('case', ['provider', 'issue', 'fractional_slot', 'duplicate', 'missing'])
def test_binding_rejects_ambiguous_fixture_identity(case):
    fixtures = [dict(issue='001', slot=2, provider_id='42', handicap=-1)]
    inventory = [dict(slot=2, provider_id=42, home='H', away='A')]
    outcomes = [dict(slot=2, actual_home=1, actual_away=0, result_state='完场')]
    if case == 'provider':
        inventory[0]['provider_id'] = 99
    elif case == 'issue':
        fixtures[0]['issue'] = '002'
    elif case == 'fractional_slot':
        fixtures[0]['slot'] = 2.1
    elif case == 'duplicate':
        outcomes.append(dict(outcomes[0]))
    else:
        outcomes.clear()
    with pytest.raises(ValueError):
        bind_purchase_roster_labels('001', fixtures, inventory, outcomes, 'ADDITIONAL')
