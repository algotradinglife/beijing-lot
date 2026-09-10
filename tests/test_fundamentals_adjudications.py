import copy
import gzip
import json
from pathlib import Path
import pytest
from src.fundamentals_adjudications import fixture_decisions
from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import pilot_tables
from src.fundamentals_home_away import home_away_windows


def test_identity_bound_decision_contract():
    fixtures=[dict(issue='x',slot=1,provider_id='001')]
    good=dict(issue='x',slot=1,provider_id='001',minimum=8,reason='owner')
    assert fixture_decisions(fixtures,[good])[1]==good
    assert fixture_decisions(fixtures,None)=={}
    for d in [{**good,'issue':'y'},{**good,'provider_id':'1'},{**good,'minimum':True},
              {**good,'exclude':True},{**good,'reason':''},{**good,'slot':2},
              {**good,'unknown':1}]:
        with pytest.raises(ValueError):fixture_decisions(fixtures,[d])
    with pytest.raises(ValueError):fixture_decisions(fixtures,[good,good])
    base={k:v for k,v in good.items() if k!='minimum'}
    for action in [dict(history_mode='bad'),dict(exclude=False),dict(titan_kickoff_utc='2010-01-02T15:00:00')]:
        with pytest.raises(ValueError):fixture_decisions(fixtures,[base|action])


def test_saved_owner_adjudications_preserve_raw_and_chronology(tmp_path):
    folder=Path('tests/fixtures/fundamentals_adjudications')
    x=json.loads((folder/'inputs.json').read_text())
    for p in folder.glob('*.gz'):(tmp_path/p.stem).write_bytes(gzip.decompress(p.read_bytes()))
    report=issue_capture_report(tmp_path/'roster.json',[tmp_path/p.removesuffix('.gz') for p in x['responses']],issue='100101',expected_fixture_count=78,cache_dir=None)
    original=copy.deepcopy(report)
    default=pilot_tables(report,cutoffs=x['cutoffs'])
    approved=pilot_tables(report,cutoffs=x['cutoffs'],adjudications=x['adjudications'])
    assert all(r['identity_source'] is None for r in default['integrated_fixtures'] if r['slot'] in (6,19))
    assert all(r['identity_source']=='titan' for r in approved['integrated_fixtures'] if r['slot'] in (6,19))
    args=dict(cutoffs=x['cutoffs'],window=10,minimum=10,repository_root=Path.cwd())
    before={w['slot']:w for w in home_away_windows(default,report['fixtures'],**args)}
    after={w['slot']:w for w in home_away_windows(approved,report['fixtures'],**args)}
    assert report==original
    assert before[63]['home_receipt']['available_prior_rows']==8
    assert before[63]['status']=='INSUFFICIENT_HISTORY'
    for slot in (1,6,19,52,63):assert after[slot]['status']=='OK_DIAGNOSTIC'
    assert len(after[63]['home_window'])==len(after[63]['away_window'])==8
    for slot in (1,52):
        w=after[slot]
        assert w['history_mode']=='ALL_VENUES'
        assert len(w['home_window'])==len(w['away_window'])==10
        for side in ('home','away'):
            assert all(w[side+'_team_id'] in (r['home_id'],r['away_id']) for r in w[side+'_window'])
            assert any(r[side+'_id']!=w[side+'_team_id'] for r in w[side+'_window'])
    excluded=[w for w in after.values() if w['status']=='OWNER_EXCLUDED']
    assert len(excluded)==12 and all(not w['home_window'] and not w['away_window'] for w in excluded)
    assert all(not w['home_receipt']['historical_admission'] for w in after.values())
    # An approved time never overrides native team IDs or the original date window.
    bad=copy.deepcopy(report)
    for r in bad['observations']:
        if r['slot']==6:r['home_id']='WRONG'
    invalid=pilot_tables(bad,cutoffs=x['cutoffs'],adjudications=x['adjudications'])
    assert next(r for r in invalid['integrated_fixtures'] if r['slot']==6)['identity_source'] is None
    bad=copy.deepcopy(report);decisions=copy.deepcopy(x['adjudications'])
    for r in bad['observations']:
        if r['slot']==6:r['kickoff_utc']='2010-02-02T15:00:00+00:00'
    next(d for d in decisions if d['slot']==6)['titan_kickoff_utc']='2010-02-02T15:00:00+00:00'
    invalid=pilot_tables(bad,cutoffs=x['cutoffs'],adjudications=decisions)
    assert next(r for r in invalid['integrated_fixtures'] if r['slot']==6)['identity_source'] is None
