import copy
import pytest
from src.n7_research_scope import exclude_n7_research_fixtures


def test_explicit_exclusion_preserves_other_fixtures_and_source_rows():
    rows = [dict(issue='001', slot=slot, market=market)
            for slot in (1, 2) for market in ('euro', 'total')]
    policy = [dict(issue='001', slot=1, reason='NONINTEGER_HANDICAP', roster_sha256='a')]
    before = copy.deepcopy((rows, policy))
    kept, ledger = exclude_n7_research_fixtures(rows, policy, {'001': 'a'})
    assert kept == rows[2:]
    assert ledger == [{**policy[0], 'excluded_market_rows': 2}]
    assert (rows, policy) == before
    assert exclude_n7_research_fixtures(rows, [], {}) == (rows, [])
    assert exclude_n7_research_fixtures([], [], {}) == ([], [])
    for bad in [policy * 2, [{**policy[0], 'slot': 3}],
                [{**policy[0], 'reason': ''}], [{**policy[0], 'slot': True}],
                [{**policy[0], 'roster_sha256': 'stale'}]]:
        with pytest.raises(ValueError):
            exclude_n7_research_fixtures(rows, bad, {'001': 'a'})
    with pytest.raises(ValueError):
        exclude_n7_research_fixtures(rows, policy, {})
