from pathlib import Path
import pytest
from beidan_backend.fundamental_issue import admit_fixture_history
from beidan_backend.temporal_learning import Cutoff


def test_shared_admission_target_future_exclusion_and_replay():
    root = Path(__file__).resolve().parents[4]
    fixture = dict(issue_id='26098', provider_id='target', fixture_id='26098:1')
    rows = [dict(row_key='prior', match_id='prior', event_date='2026-09-01',
                 scope='home_recent', home_id='h', away_id='a', home_score=2,
                 away_score=1, score_scope='SOURCE_PUBLISHED_FULL_TIME')]
    rows += [{**rows[0], 'row_key':'target', 'match_id':'target'},
             {**rows[0], 'row_key':'other-target', 'match_id':'other-target'},
             {**rows[0], 'row_key':'future', 'match_id':'future', 'event_date':'2026-09-25'}]
    cutoff = Cutoff.decision_epoch('26098','2026-09-24T00:00:00Z')
    result = admit_fixture_history(rows,fixture,['target','other-target'],cutoff,dict(raw='fixture'),root)
    assert [r['match_id'] for r in result['rows']] == ['prior']
    assert result['receipt']['target_rows_excluded'] == 2
    assert result['receipt']['availability']['intended_use'] == 'HISTORICAL_DIAGNOSTIC'
    assert result['rows'][0]['proxy_available_at'] == '2026-09-02T00:00:00+00:00'
    changed = [dict(r,home_score=999) if r['match_id'] != 'prior' else r for r in rows]
    replay = admit_fixture_history(changed,fixture,['target','other-target'],cutoff,dict(raw='changed'),root)
    assert replay['rows'] == result['rows']
    invalid_future = [dict(r, home_score=None, away_score=-99) if r['match_id'] != 'prior' else r for r in rows]
    ignored = admit_fixture_history(invalid_future,fixture,['target','other-target'],cutoff,dict(raw='invalid-future'),root)
    assert ignored['rows'] == result['rows']
    later = admit_fixture_history(rows,fixture,['target','other-target'],
        Cutoff.decision_epoch('26098','2026-09-25T00:00:00Z'),dict(raw='fixture'),root)
    assert later['receipt'] != result['receipt']
    for bad in ([], rows + [rows[0]], [{**rows[0],'event_date':None}],
                [{**rows[0],'event_date':'bad'}], [{**rows[0],'match_id':123}],
                [{**rows[0],'home_score':-1}], [{**rows[0],'home_score':True}]):
        with pytest.raises(ValueError):
            admit_fixture_history(bad,fixture,['target'],cutoff,dict(raw='fixture'),root)
    with pytest.raises(ValueError, match='roster'):
        admit_fixture_history(rows,fixture,['another'],cutoff,dict(raw='fixture'),root)
    with pytest.raises(ValueError, match='cutoff'):
        admit_fixture_history(rows,fixture,['target'],None,dict(raw='fixture'),root)
