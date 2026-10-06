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
    assert len(result['euro'])==1190
    assert len(result['totals'])==43
    assert len({r['company_id'] for r in result['euro']})==130
    quote=next(r for r in result['totals'] if r['quote_at']=='2026-09-25T18:08:58+08:00')
    assert quote['line']==2.5
    assert quote['over_decimal']==quote['under_decimal']==1.9
    assert all(r['quote_at'] < fixture['kickoff_at'] for r in result['totals'])

def test_wrong_native_id_rejected(fixture):
    fixture['provider_id_nowscore']='2997422'
    with pytest.raises(ValueError,match='native ID mismatch'):
        parse_markets(fixture,(ROOT/'euro.raw').read_bytes(),{})

@pytest.mark.parametrize('field,value',[('home_nowscore','不同译名'),('away_nowscore','另一译名'),('kickoff_at','2026-09-26T12:00:00+08:00')])
def test_names_and_time_warn_without_losing_quotes(fixture,field,value,tmp_path,pages):
    fixture[field]=value
    from beidan_backend.market_capture.history import over_under_history_url
    old_total=next(url for url in pages if '1x2d' not in url)
    pages[over_under_history_url(fixture['provider_id_nowscore'],8,validate_fixture(fixture))]=pages.pop(old_total)
    result=fetch_markets([fixture],str(tmp_path),['8'],pages=pages)
    assert result['coverage'][0]['status']=='ok'
    assert 'warning:' in result['coverage'][0]['detail']
    assert result['euro'] and result['totals']
    assert any(r['market']=='identity' and r['reason'].startswith('warning:') for r in result['diagnostics'])

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
    assert out['coverage'][0]['euro_rows']==1190
    assert out['coverage'][0]['totals_rows']==0
    assert out['euro'] and not out['totals']


def test_interrupted_parse_keeps_observation_receipt(tmp_path,fixture,pages,monkeypatch):
    import beidan_backend.market_capture.service as service
    def interrupt(*args,**kwargs):
        raise KeyboardInterrupt()
    monkeypatch.setattr(service,'parse_markets',interrupt)
    with pytest.raises(KeyboardInterrupt):
        fetch_markets([fixture],str(tmp_path),['8'],pages=pages)
    receipt=json.loads(next(tmp_path.glob('*/receipt.json')).read_text())
    assert len(receipt['captures'])==2
    assert all(c['observed_at'] and c['source_url'] for c in receipt['captures'])
    assert all(Path(c['raw_path']).exists() for c in receipt['captures'])


def test_slot63_real_translated_names_keep_quotes():
    fixture=dict(fixture_id='26098:63',provider_id_nowscore='3007685',
        home_nowscore='纽波特郡',away_nowscore='格里姆斯比',kickoff_at='2026-09-26T22:00:00+08:00')
    result=parse_markets(fixture,(ROOT/'slot63-euro.raw').read_bytes(),{})
    assert result['euro']
    warnings=[row for row in result['diagnostics'] if row['market']=='identity']
    assert len(warnings)==2
    assert any('纽波特郡' in row['reason'] and 'Titan=纽波特' in row['reason'] for row in warnings)
    assert any('格里姆斯比' in row['reason'] and 'Titan=格林斯比' in row['reason'] for row in warnings)


def test_slot57_same_minute_uses_newest_source_row():
    from beidan_backend.market_capture.history import parse_euro_history_js
    from datetime import datetime
    body = (ROOT / "slot57-euro.raw").read_bytes()
    fixture = dict(fixture_id="26098:57", provider_id_nowscore="3007123",
                   home_nowscore="source alias", away_nowscore="source alias",
                   kickoff_at="2026-09-26T22:00:00+08:00")
    stamp = "2026-09-26T17:14:00+08:00"
    _, history, _ = parse_euro_history_js(body, kickoff_hkt=datetime.fromisoformat(fixture["kickoff_at"]), company_id=281)
    # Parser retains all source evidence and stable same-minute source order.
    tied = [r for r in history if datetime.fromisoformat(r.snapshot_ts_hkt) == datetime.fromisoformat(stamp)]
    assert [r.odds["home"] for r in tied] == [1.57, 1.5, 1.53]
    result = parse_markets(fixture, body, {})
    rows = [r for r in result["euro"] if r["company_id"] == "281" and r["quote_at"] == stamp]
    assert len(rows) == 1
    assert (rows[0]["odds_home"], rows[0]["odds_draw"], rows[0]["odds_away"]) == (1.57, 4.1, 5.25)
    assert any(r["company_id"] == "281" and r["reason"] == "same_minute_superseded_rows" and r["count"] >= 2 for r in result["diagnostics"])
    # Changing source order changes the winner: no hash/value sort may override it.
    a = b"1.57|4.1|5.25|09-26 17:14|0.95|0.90|0.90|2026"
    b = b"1.5|4.2|5.75|09-26 17:14|0.91|0.93|0.99|2026"
    assert a + b";" + b in body
    reordered = body.replace(a + b";" + b, b + b";" + a)
    changed = parse_markets(fixture, reordered, {})
    winner = next(r for r in changed["euro"] if r["company_id"] == "281" and r["quote_at"] == stamp)
    assert winner["odds_home"] == 1.5


def test_receipt_preserves_replay_provenance_without_duplicating_history(tmp_path,fixture,pages):
    result = fetch_markets([fixture],str(tmp_path),['8'],pages=pages)
    receipt = json.loads(Path(result['receipt_path']).read_text())
    assert result['euro'] and result['totals']
    assert 'euro' not in receipt and 'totals' not in receipt
    assert receipt['schema'] == 'beidan_market_capture_receipt_v1'
    assert receipt['euro_rows'] == len(result['euro'])
    assert receipt['totals_rows'] == len(result['totals'])
    assert receipt['captures'] == result['captures']
    assert receipt['coverage'] == result['coverage']
    assert all(Path(c['raw_path']).read_bytes()==pages[c['source_url']]['body'] for c in receipt['captures'])
    assert not list(Path(result['receipt_path']).parent.glob('*.tmp'))
    assert Path(result['receipt_path']).stat().st_size < len(json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8')) / 2


def test_receipt_atomic_failure_keeps_last_raw_inventory(tmp_path,monkeypatch):
    import beidan_backend.market_capture.service as service
    before={'euro':[], 'totals':[], 'captures':[{'sha256':'old'}]}
    service._write_market_receipt(tmp_path,before)
    original=(tmp_path/'receipt.json').read_bytes()
    real_replace=Path.replace
    def fail_receipt(path,target):
        if path.name=='receipt.json.tmp':
            raise OSError('publication failure')
        return real_replace(path,target)
    monkeypatch.setattr(Path,'replace',fail_receipt)
    with pytest.raises(OSError,match='publication failure'):
        service._write_market_receipt(tmp_path,{'euro':[{'value':1}]*10000,'totals':[],'captures':[]})
    assert (tmp_path/'receipt.json').read_bytes()==original
