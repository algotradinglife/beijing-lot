"""Saved real 26098 source boundary, chronology, identity and persistence checks."""
import copy
import json
from pathlib import Path
import pytest
from beidan_backend.market_capture.service import fetch_markets, parse_markets, titan_identity, validate_fixture

ROOT = Path(__file__).resolve().parents[2]/'packages/beidan/tests/testthat/fixtures/market_capture'

@pytest.fixture
def fixture():
    return dict(fixture_id='26098:39',provider_id_nowscore='2997421',home_nowscore='蒂华纳',away_nowscore='阿特拉斯',kickoff_at='2026-09-26T11:00:00+08:00')

@pytest.fixture
def pages():
    out={}
    for name in ('euro','total_history'):
        meta=json.loads((ROOT/f'{name}.json').read_text())
        out[meta['url']]={'body':(ROOT/f'{name}.raw').read_bytes(),'observed_at':meta['observed_at']}
    return out


def test_real_identity_and_histories(fixture):
    euro=(ROOT/'euro.raw').read_bytes()
    identity=titan_identity(euro)
    assert identity['kickoff_at'].isoformat()=='2026-09-26T11:00:00+08:00'
    result=parse_markets(fixture,euro,{'8':(ROOT/'total_history.raw').read_bytes()})
    assert len(result['euro'])==1208
    assert len(result['totals'])==43
    assert len({r['company_id'] for r in result['euro']})==130
    quote=next(r for r in result['totals'] if r['quote_at']=='2026-09-25T18:08:58+08:00')
    assert quote['line']==2.5
    assert quote['over_decimal']==quote['under_decimal']==1.9
    assert all(r['quote_at'] < fixture['kickoff_at'] for r in result['totals'])

@pytest.mark.parametrize('field,value',[('provider_id_nowscore','2997422'),('home_nowscore','阿特拉斯'),('away_nowscore','蒂华纳'),('kickoff_at','2026-09-25T11:00:00+08:00')])
def test_wrong_identity_rejected(fixture,field,value):
    fixture[field]=value
    with pytest.raises(ValueError,match='mismatch'):
        parse_markets(fixture,(ROOT/'euro.raw').read_bytes(),{})

@pytest.mark.parametrize('field,value',[('provider_id_nowscore','../x'),('fixture_id',''),('home_nowscore',None),('kickoff_at','2026-09-26T11:00:00')])
def test_invalid_fixture_before_network(fixture,field,value):
    fixture[field]=value
    with pytest.raises(ValueError):
        validate_fixture(fixture)


def test_replay_preserves_original_observation_and_repeat_runs(tmp_path,fixture,pages):
    a=fetch_markets([fixture],str(tmp_path),['8'],pages=pages)
    b=fetch_markets([fixture],str(tmp_path),['8'],pages=pages)
    assert a['coverage'][0]['status']=='ok'
    assert a['euro']==b['euro']
    assert a['receipt_path']!=b['receipt_path']
    assert all(Path(c['raw_path']).read_bytes()==pages[c['source_url']]['body'] for c in a['captures'])
    assert a['identities']==[fixture]
    assert all(row['fixture_id']==fixture['fixture_id'] for row in a['diagnostics'])
    assert len(a['captures'])==2
    assert '2026-09-26' in a['captures'][0]['observed_at']


def test_failure_retains_raw_and_does_not_return_partial_fixture(tmp_path,fixture,pages):
    bad=copy.deepcopy(pages)
    euro_url=next(u for u in bad if '1x2d' in u)
    bad[euro_url]['body']=b'not valid'
    out=fetch_markets([fixture],str(tmp_path),['8'],pages=bad)
    assert out['coverage'][0]['status']=='error'
    assert out['euro']==out['totals']==[]
    assert Path(out['captures'][0]['raw_path']).read_bytes()==b'not valid'

@pytest.mark.parametrize('company_ids',[[],['8','8'],['bad'],[8]])
def test_invalid_company_contract(tmp_path,fixture,company_ids):
    with pytest.raises(ValueError):
        fetch_markets([fixture],str(tmp_path),company_ids,pages={})


def test_empty_and_duplicate_requests(tmp_path,fixture):
    empty=fetch_markets([],str(tmp_path),['8'],pages={})
    assert empty['euro']==empty['coverage']==[]
    with pytest.raises(ValueError,match='Duplicate'):
        fetch_markets([fixture,fixture],str(tmp_path),['8'],pages={})


def test_live_orchestration_uses_bounded_fetch_and_spacing(tmp_path,fixture,pages,monkeypatch):
    import beidan_backend.market_capture.service as service
    from types import SimpleNamespace
    calls=[]
    sleeps=[]
    clock=[10.0]
    def fake_fetch(url,**kwargs):
        calls.append((url,kwargs))
        clock[0] += 1.01  # one internal retry plus response time
        return SimpleNamespace(body=pages[url]['body'],observed_at=pages[url]['observed_at'])
    monkeypatch.setattr(service,'fetch_issue_page',fake_fetch)
    monkeypatch.setattr(service.time,'sleep',sleeps.append)
    monkeypatch.setattr(service.time,'monotonic',lambda:clock[0])
    result=fetch_markets([fixture],str(tmp_path),['8'],timeout=7,retries=1)
    assert result['coverage'][0]['status']=='ok'
    assert len(calls)==2
    assert all(kwargs==dict(timeout=7,retries=1,backoff_sec=1) for _,kwargs in calls)
    assert sleeps==[1]


def test_unusable_total_history_is_partial_not_success(tmp_path,fixture,pages):
    bad=copy.deepcopy(pages)
    url=next(u for u in bad if 'Handicap' in u)
    rows=json.loads(bad[url]['body'])
    for row in rows:
        row['HomeOdds']='bad'
    bad[url]['body']=json.dumps(rows).encode()
    out=fetch_markets([fixture],str(tmp_path),['8'],pages=bad)
    assert out['coverage'][0]['status']=='partial'
    assert out['coverage'][0]['euro_rows']==1208
    assert out['coverage'][0]['totals_rows']==0
    assert out['euro'] and not out['totals']
