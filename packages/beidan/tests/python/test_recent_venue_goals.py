"""Numerical and chronology contracts for the bounded venue-rate prototype."""
import copy
import datetime as dt
from pathlib import Path
import pytest
from beidan_backend.recent_venue_goals import estimate_recent_venue_goals
from beidan_backend.temporal_learning import Cutoff

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = dict(fixture_id='26101:65', issue_id='26101', provider_id='target', home_id='h', away_id='a')
POLICY = dict(recent_n=8, alpha=.5, minimum_matches=12, minimum_ess=8)


@pytest.fixture
def history():
    rows = []
    for role in ('home', 'away'):
        for i in range(16):
            rows.append(dict(row_key=f'{role}:{i}', scope=role+'_recent',
                match_id=f'{role}{i}', event_date=(dt.date(2026, 8, 1)+dt.timedelta(days=i)).isoformat(),
                home_id='h' if role=='home' else 'x', away_id='x' if role=='home' else 'a',
                home_score=1 if role=='home' else 0,
                away_score=0 if role=='home' else (1 if i<8 else 3),
                score_scope='SOURCE_PUBLISHED_FULL_TIME'))
    return rows


def test_component_means_and_replay(history):
    cutoff = Cutoff.decision_epoch('26101', '2026-09-01T00:00:00Z')
    x = estimate_recent_venue_goals(history, FIXTURE, ['target'], cutoff, {'raw':'synthetic'}, ROOT, POLICY)
    assert x['parameters'] == pytest.approx(dict(lambda_home=.5, lambda_away=1.25))
    assert x == estimate_recent_venue_goals(history, FIXTURE, ['target'], cutoff, {'raw':'synthetic'}, ROOT, POLICY)
    for c in x['components']:
        for k in ('long','recent','mixture'):
            assert sum(d[k] for d in c['distributions']) == pytest.approx(1)
        for d in c['distributions']:
            assert d['mixture'] == pytest.approx(.5*d['long']+.5*d['recent'])
    assert all(r['weight_receipt']['effective_sample_size'] >= 8 for r in x['receipts'])


def test_future_target_and_other_venue_invariance(history):
    c = Cutoff.decision_epoch('26101', '2026-09-01T00:00:00Z')
    base = estimate_recent_venue_goals(history, FIXTURE, ['target'], c, {'raw':'synthetic'}, ROOT, POLICY)
    for key, date, home in [('future','2026-09-02','h'), ('target','2026-08-30','h'), ('other','2026-08-30','x')]:
        history.append(dict(row_key=key, scope='home_recent', match_id=key, event_date=date,
                            home_id=home, away_id='x', home_score=99, away_score=99,
                            score_scope='SOURCE_PUBLISHED_FULL_TIME'))
    poisoned = estimate_recent_venue_goals(history, FIXTURE, ['target'], c, {'raw':'synthetic'}, ROOT, POLICY)
    assert poisoned['parameters'] == base['parameters']
    assert poisoned['output_hash'] == base['output_hash']


@pytest.mark.parametrize('change', [{'alpha':0}, {'recent_n':0}, {'minimum_matches':50}, {'minimum_ess':100}])
def test_fail_closed_policy_or_support(history, change):
    with pytest.raises(ValueError):
        estimate_recent_venue_goals(history, FIXTURE, ['target'], Cutoff.decision_epoch('26101','2026-09-01T00:00:00Z'), {'raw':'synthetic'}, ROOT, {**POLICY, **change})


def test_duplicate_and_missing_chronology(history):
    c = Cutoff.decision_epoch('26101','2026-09-01T00:00:00Z')
    duplicate = copy.deepcopy(history); duplicate.append({**duplicate[0], 'row_key':'distinct'})
    with pytest.raises(ValueError, match='duplicate'):
        estimate_recent_venue_goals(duplicate,FIXTURE,['target'],c,{'raw':'synthetic'},ROOT,POLICY)
    history[0]['event_date'] = None
    with pytest.raises(ValueError):
        estimate_recent_venue_goals(history,FIXTURE,['target'],c,{'raw':'synthetic'},ROOT,POLICY)


def test_cutoff_policy_cache_isolation(history):
    a = estimate_recent_venue_goals(history,FIXTURE,['target'],Cutoff.decision_epoch('26101','2026-09-01T00:00:00Z'),{'raw':'synthetic'},ROOT,POLICY)
    b = estimate_recent_venue_goals(history,FIXTURE,['target'],Cutoff.decision_epoch('26101','2026-09-02T00:00:00Z'),{'raw':'synthetic'},ROOT,{**POLICY,'alpha':.25})
    assert a['receipts'][0]['cache_key'] != b['receipts'][0]['cache_key']
    assert a['parameters'] != b['parameters']
