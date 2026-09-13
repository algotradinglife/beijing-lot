"""Missing periods remain visible and cannot become implicit losses/no bets."""
import pytest
from src.n7_study_scope import n7_study_scope


def test_scope_preserves_order_and_explicit_missing_reason():
    result = n7_study_scope(['001','002','003'], ['003','001'], {'002':'NO_USABLE_MARKETS'})
    assert result['requested_issues'] == ['001','002','003']
    assert result['modeled_issues'] == ['001','003']
    assert result['unavailable_issues'] == [dict(issue='002',status='NOT_EVALUABLE',reason='NO_USABLE_MARKETS')]
    assert n7_study_scope(['001'], [], {'001':'NOT_PUBLISHED'})['modeled_issues'] == []
    assert n7_study_scope(['001'], ['001'], {})['unavailable_issues'] == []


@pytest.mark.parametrize('requested,modeled,missing', [
    (['001','002'],['001'],{}), (['001'],['001'],{'001':'gap'}),
    (['001'],['002'],{}), (['001','001'],['001'],{}),
    (['001'],['001','001'],{}), (['001'],[],{'001':''}),
    (['001'],[],{'001':None}), ([],[],{}), ([1],[1],{}),
])
def test_scope_rejects_dropped_extra_duplicate_or_unexplained_periods(requested,modeled,missing):
    with pytest.raises(ValueError):
        n7_study_scope(requested,modeled,missing)
