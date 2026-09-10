import copy
import gzip
import json
from pathlib import Path
import pytest
from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import pilot_tables
from src.fundamentals_league_context import standings_observations,league_context_tables


@pytest.fixture(scope='module')
def sample(tmp_path_factory):
    root=Path('tests/fixtures/fundamentals_three_cases');tmp=tmp_path_factory.mktemp('league')
    for name in ['roster','003-titan','003-nowscore']:
        (tmp/(name+'.json')).write_bytes(gzip.decompress((root/(name+'.json.gz')).read_bytes()))
    r=issue_capture_report(str(tmp/'roster.json'),[str(tmp/'003-titan.json'),str(tmp/'003-nowscore.json')],issue='100101',expected_fixture_count=78)
    cutoffs=json.loads((root/'cutoffs.json').read_text())
    return r,pilot_tables(r,cutoffs=cutoffs),cutoffs


def test_titan_old_template_native_ids_scopes_and_not_handicap_or_half(sample):
    r,p,c=sample;x=league_context_tables(r,p,cutoffs=c)
    t=[s for s in x['standings'] if s['source']=='titan']
    assert len(t)==8
    home=next(s for s in t if s['role']=='home' and s['scope']=='总')
    assert (home['team_id'],home['played'],home['goals_for'],home['rank'])==('33',20,42,4)
    assert home['league_label'] is None and home['statistics_as_of'] is None
    assert all(s['valid'] and not s['historical_admission'] for s in t)
    n=next(s for s in x['standings'] if s['source']=='nowscore' and s['role']=='away' and s['scope']=='总')
    assert n['league_label']=='英甲' and n['played']==20
    assert len(x['availability'])==156
    assert len(x['pending_comparison'])==2
    candidates=[v for v in x['participation'] if v['team_id']=='353' and v['competition_id']=='37']
    assert candidates and all(v['league_tier'] is None and v['season'] is None for v in candidates)
    assert all(v['first_observed_date']<=v['last_observed_date'] for v in x['participation'])
    assert any(v['role']=='opponent' for v in x['participation'])
    with pytest.raises(ValueError):league_context_tables(r,p,cutoffs={})


def test_bad_standings_preserve_raw_and_do_not_assume_zero(sample):
    r,_,_=sample;field=next(f for f in r['page_fields'] if f['slot']==3 and f['source']=='titan')
    raw=copy.deepcopy(field['raw_fields'])
    kwargs=dict(source='titan',issue='100101',slot=3,provider_id='356276',home_id='33',away_id='353',raw_sha256='hash',identity_valid=True)
    assert standings_observations(None,**kwargs)==[]
    with pytest.raises(ValueError):standings_observations(raw,**{**kwargs,'source':'bad'})
    for t in raw['page_tables']:
        if t['rows'] and t['rows'][0][0]['text']=='[4]托特纳姆热刺' and len(t['rows'])>2:
            for row in t['rows'][2:]:
                if row and row[0]['text']=='总':row[1]['text']='bad'
    x=standings_observations(raw,**kwargs)
    bad=next(s for s in x if s['team_id']=='33' and s['scope']=='总')
    assert not bad['valid'] and bad['played'] is None and bad['raw_values'][1]=='bad'
    assert 'Invalid played' in bad['error']
    wrong=standings_observations(field['raw_fields'],**{**kwargs,'home_id':'999'})
    assert any(s['team_id']=='33' and not s['valid'] for s in wrong)
