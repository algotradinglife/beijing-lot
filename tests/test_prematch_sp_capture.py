from pathlib import Path
import json
import pytest
from tests.test_nowscore_settlement import page
from packages.beidan.inst.python.beidan_backend.prematch_sp import parse_prematch_sp, fetch_issue_prematch_sp

SCHEDULE = [dict(issue_id='25053',slot=1,fixture_key='25053:1',provider_id_nowscore='123',handicap=0,kickoff_at='2026-09-27T01:00:00+08:00')]
AT='2026-09-26T23:00:00+08:00'
BODY=page(5,status='00:55',ft='-',ht='-',values={'胜':'2.5','平':'3.4','负':'12'}).replace(b'cansale="false"',b'cansale="true"')


def test_labels_raw_values_and_receipts(tmp_path):
    x=fetch_issue_prematch_sp(SCHEDULE,str(tmp_path),pages=dict(body=BODY,observed_at=AT))
    assert {q['outcome']:q['sp_raw'] for q in x['prematch_sp']}=={'W':2.5,'D':3.4,'L':12}
    assert all(q['quote_at']==AT for q in x['prematch_sp'])
    receipt=json.loads(Path(x['receipt_path']).read_text())
    assert receipt['market']=='beidan_handicap_sp_reference'
    assert Path(receipt['raw_paths']['nowscore_beidan_sp_raw']).read_bytes()==BODY
    assert len(receipt['implementation_sha256'])==5
    assert x['receipt_path']!=fetch_issue_prematch_sp(SCHEDULE,str(tmp_path),pages=dict(body=BODY,observed_at=AT))['receipt_path']


@pytest.mark.parametrize('body,at,reason',[
 (BODY.replace(b'cansale="true"',b'cansale="false"'),AT,'not_live_prematch'),
 (BODY.replace('00:55'.encode(),'完场'.encode()),AT,'not_live_prematch'),
 (BODY,'2026-09-27T01:00:00+08:00','already_kicked_off'),
 (BODY.replace(b'>12<',b'><'),AT,'incomplete_sp_vector'),
 (BODY.replace(b'>12<',b'>NaN<'),AT,'invalid_source_contract')])
def test_exclusions(body,at,reason):
    quotes,diag=parse_prematch_sp(body,SCHEDULE,at)
    assert quotes==[] and diag[0]['reason']==reason


def test_identity_and_parser_failures(tmp_path):
    bad=[dict(SCHEDULE[0],handicap=1)]
    assert parse_prematch_sp(BODY,bad,AT)[1][0]['reason']=='identity_or_handicap_mismatch'
    with pytest.raises(ValueError,match='timezone'): parse_prematch_sp(BODY,SCHEDULE,'2026-09-26T23:00:00')
    with pytest.raises(ValueError,match='duplicate'): parse_prematch_sp(BODY,SCHEDULE*2,AT)
    with pytest.raises(ValueError): fetch_issue_prematch_sp(SCHEDULE,str(tmp_path),pages=dict(body=b'wrong',observed_at=AT))
    receipts=list(tmp_path.rglob('*source.json'))
    assert receipts and json.loads(receipts[0].read_text())['parse']['status']=='failed'


def test_live_transport_uses_shared_fetch_and_observation(tmp_path,monkeypatch):
    from packages.beidan.inst.python.beidan_backend import prematch_sp
    from types import SimpleNamespace
    calls=[]
    def fake(url,**kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(body=BODY,observed_at=AT)
    monkeypatch.setattr(prematch_sp.fetch,'fetch_issue_page',fake)
    out=fetch_issue_prematch_sp(SCHEDULE,str(tmp_path),timeout=12,retries=1)
    assert len(out['prematch_sp'])==3
    assert 'TypeID=5' in calls[0][0] and calls[0][1]==dict(timeout=12,retries=1)
