"""Metadata extension reuses immutable real pages and source parser contracts."""
import copy
import pytest
from beidan_backend.opponent_history import parse_opponent_history
from test_unified_sources import saved_pair


def test_real_competition_metadata_and_replay():
    pages, records, identity = saved_pair()
    for source in ('titan', 'nowscore'):
        url = next(u for u in pages if source in u and '/analysis/' in u)
        auxiliary = next((v['body'] for u, v in pages.items() if 'analysisJs/' in u), None)
        result = parse_opponent_history(pages[url]['body'], source=source,
            provider_id='1870517', expected_identity=identity, auxiliary_raw=auxiliary)
        assert len(result['rows']) == len(records[source]['history'])
        assert result['target_competition_id'] is None  # Old titles lack league.
        assert ('35','英乙') in {(r['competition_id'],r['competition_name']) for r in result['rows']}
        assert all(r['competition_id'].isdigit() for r in result['rows'])
        assert all(isinstance(r['neutral_reported'], bool) for r in result['rows'])
        assert result == parse_opponent_history(pages[url]['body'], source=source,
            provider_id='1870517', expected_identity=identity, auxiliary_raw=auxiliary)


@pytest.mark.parametrize('field,value', [('home_id','999'), ('provider_id','999'),
    ('kickoff_utc','2020-06-22T09:15:00+00:00')])
def test_wrong_bound_identity_fails(field, value):
    pages, _, identity = saved_pair()
    url = next(u for u in pages if 'titan' in u)
    bad = copy.deepcopy(identity); bad[field] = value
    with pytest.raises(ValueError):
        parse_opponent_history(pages[url]['body'], source='titan',
            provider_id='1870517', expected_identity=bad)


def test_invalid_competition_and_unmatched_title():
    pages, _, identity = saved_pair()
    raw = pages[next(u for u in pages if 'titan' in u)]['body']
    with pytest.raises(ValueError, match='competition'):
        parse_opponent_history(raw.replace(b",35,'", b",0,'"),source='titan',
            provider_id='1870517',expected_identity=identity)
    import re
    titled = re.sub(rb'<title>.*?</title>', '<title>测试(2020赛季英乙)-分析</title>'.encode(),raw,flags=re.S)
    known = parse_opponent_history(titled,source='titan',provider_id='1870517',expected_identity=identity)
    assert known['target_competition_id'] == '35'
    replaced = titled.replace('赛季英乙'.encode(), '赛季未知联赛'.encode())
    result = parse_opponent_history(replaced,source='titan',
        provider_id='1870517',expected_identity=identity)
    assert result['target_competition_id'] is None
    assert result['target_competition_state'] == 'ABSENT_OR_AMBIGUOUS_TITLE_HISTORY'


def test_original_bytes_and_explicit_identity_required():
    with pytest.raises(ValueError,match='Original bytes'):
        parse_opponent_history('html',source='titan',provider_id='1',expected_identity={})
