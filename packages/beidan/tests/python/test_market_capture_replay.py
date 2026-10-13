"""Deterministic offline capture replay and provenance contracts."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from beidan_backend.market_capture.history import euro_history_url, over_under_history_url
from beidan_backend.market_capture.service import validate_fixture
from beidan_backend.market_capture.replay import replay_fixture_capture


@pytest.fixture
def saved(tmp_path):
    fixture=dict(fixture_id='26102:6', provider_id_nowscore='3014103',
                 home_nowscore='Home',away_nowscore='Away',kickoff_at='2026-10-05T18:30:00+00:00')
    fields=['281','123','Book']+['0']*21
    fields[23]='0'
    euro=('var ScheduleID=3014103;\nvar hometeam_cn="Home";\nvar guestteam_cn="Away";\n'
          'var hometeamID=146;\nvar guestteamID=138;\nvar MatchTime="2026,10-1,5,18,30,0";\nvar game=Array("'+'|'.join(fields)+'");\n'
          'var gameDetail=Array("123^1.9|3.4|4.0|10-04 18:00|0|0|0|2026");').encode()
    row=dict(ModifyTime='20261005013000',HappenTime='',Score='早',HomeOdds='.9',AwayOdds='.95',PanKou='2.5')
    total=json.dumps([row]).encode();row['PanKou']='0.5';asian=json.dumps([row]).encode()
    urls={'euro':euro_history_url('3014103'),'total':over_under_history_url('3014103',8,validate_fixture(fixture))}
    urls['asian']=urls['total'].replace('oddskind=1','oddskind=0')
    captures=[]
    for kind,body in [('euro',euro),('total',total),('asian',asian)]:
        path=tmp_path/(kind+'.raw');path.write_bytes(body)
        captures.append(dict(kind=kind,url=urls[kind],raw_path=path.name,
            observed_at='2026-10-13T00:00:00+00:00',sha256=hashlib.sha256(body).hexdigest()))
    return dict(fixture=fixture,captures=captures),tmp_path


def test_normal_replay_units_and_identity(saved):
    record,root=saved;x=replay_fixture_capture(record,str(root),dict(home_id='146',away_id='138'))
    assert x['identity_status']=='EXACT'
    assert len(x['euro'])==len(x['asian'])==len(x['totals'])==1
    assert x['asian'][0]['handicap']==-.5
    assert x['asian'][0]['home_decimal']==1.9
    assert x['totals'][0]['line']==2.5
    assert x['euro'][0]['quote_at'].endswith('+08:00')
    assert len(x['parser_bindings'])==3
    assert replay_fixture_capture(record,str(root),dict(home_id='146',away_id='138'))==x


@pytest.mark.parametrize('kind',['euro','total','asian'])
def test_channel_failures_do_not_erase_other_quotes(saved,kind):
    rec,root=saved;rec=copy.deepcopy(rec)
    c=next(c for c in rec['captures'] if c['kind']==kind)
    (root/c['raw_path']).write_bytes(b'<html>404</html>');c['sha256']=hashlib.sha256(b'<html>404</html>').hexdigest()
    x=replay_fixture_capture(rec,str(root),dict(home_id='146',away_id='138'))
    key={'euro':'euro','total':'totals','asian':'asian'}[kind]
    assert not x[key]
    for k in {'euro','totals','asian'}-{key}:assert len(x[k])==1
    assert any(c.get('status')=='PARSER_FAILURE' for c in x['diagnostics'])


def test_request_failure_is_not_normal_empty(saved):
    rec,root=saved;rec=copy.deepcopy(rec);c=rec['captures'][0]
    del c['sha256'];c['error']='bounded HTTP 503'
    x=replay_fixture_capture(rec,str(root),dict(home_id='146',away_id='138'))
    assert x['diagnostics'][0]['status']=='REQUEST_FAILURE'
    assert len(x['asian'])==len(x['totals'])==1
    assert x['identity_status']=='UNVERIFIED'


@pytest.mark.parametrize('mutation',['hash','url','naive','duplicate','no_evidence'])
def test_critical_provenance_fails_closed(saved,mutation):
    rec,root=saved;rec=copy.deepcopy(rec);c=rec['captures'][0]
    if mutation=='hash':c['sha256']='0'*64
    if mutation=='url':c['url']=c['url'].replace('3014103','3014104')
    if mutation=='naive':c['observed_at']='2026-10-13T00:00:00'
    if mutation=='duplicate':rec['captures'].append(c.copy())
    if mutation=='no_evidence':del c['sha256']
    with pytest.raises(ValueError):replay_fixture_capture(rec,str(root),dict(home_id='146',away_id='138'))


def test_identity_conflicts_remain_quarantined(saved):
    rec,root=saved;rec=copy.deepcopy(rec)
    rec['fixture']['home_nowscore']='Other'
    assert replay_fixture_capture(rec,str(root),dict(home_id='146',away_id='138'))['identity_status']=='EXACT_IDS'
    rec['fixture']['home_nowscore']='Home';c=rec['captures'][0]
    body=(root/c['raw_path']).read_bytes().replace(b'ScheduleID=3014103',b'ScheduleID=3014104')
    (root/c['raw_path']).write_bytes(body);c['sha256']=hashlib.sha256(body).hexdigest()
    x=replay_fixture_capture(rec,str(root),dict(home_id='146',away_id='138'))
    assert x['identity_status']=='NATIVE_ID_CONFLICT' and not x['euro']
    assert len(x['asian'])==1
