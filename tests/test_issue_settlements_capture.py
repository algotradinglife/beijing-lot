from datetime import datetime
import json
import pytest
from packages.beidan.inst.python.beidan_backend.settlement import fetch_issue_settlements
from tests.test_nowscore_settlement import page


def call(tmp_path, **kwargs):
    schedule = kwargs.pop('schedule', [dict(issue_id='25053', slot=1, fixture_key='25053:1', provider_id_nowscore='123', handicap=0)])
    body = kwargs.pop('body', page(5, values={'胜':'2.5'}))
    return fetch_issue_settlements(schedule, str(tmp_path), pages={'body':body, 'observed_at':'2026-09-26T10:00:00+08:00'}, **kwargs)


def test_settled_and_raw_receipt(tmp_path):
    out = call(tmp_path)
    row = out['settlements'][0]
    assert row['outcome']=='W' and row['settled_sp']==2.5 and row['fixture_id']=='25053:1'
    assert row['label_available_at']=='2026-09-26T10:00:00+08:00'
    receipt = json.loads(__import__('pathlib').Path(out['receipt_path']).read_text())
    assert __import__('pathlib').Path(receipt['raw_path']).read_bytes()==page(5, values={'胜':'2.5'})
    assert call(tmp_path)['receipt_path'] != out['receipt_path']
    assert len(receipt['implementation_sha256']) == 4
    assert json.loads(__import__('pathlib').Path(receipt['schedule_path']).read_text())[0]['fixture_key']=='25053:1'


@pytest.mark.parametrize('body,reason', [(page(5,status='22:25'), 'not_finished'),(page(5,status='取消'), 'not_finished'),(page(5,values={}), 'settled_sp_not_unique'),(page(5,values={'胜':'2','平':'3','负':'4'}), 'settled_sp_not_unique'),(page(5,values={'负':'2.5'}), 'score_outcome_mismatch'),(page(5,values={'胜':'bad'}), 'invalid_source_contract')])
def test_nonsettlements(tmp_path,body,reason):
    out=call(tmp_path,body=body)
    assert not out['settlements']
    assert out['diagnostics'][0]['reason']==reason


@pytest.mark.parametrize('field,value', [('provider_id_nowscore','999'),('handicap',1)])
def test_identity_binding(tmp_path,field,value):
    schedule=[dict(issue_id='25053',slot=1,fixture_key='25053:1',provider_id_nowscore='123',handicap=0)]
    schedule[0][field]=value
    assert call(tmp_path,schedule=schedule)['diagnostics'][0]['reason']=='identity_or_handicap_mismatch'


def test_bad_inputs(tmp_path):
    with pytest.raises(ValueError): call(tmp_path,schedule=[])
    with pytest.raises(ValueError): call(tmp_path,timeout=0)
    with pytest.raises(ValueError): call(tmp_path,retries=True)
    with pytest.raises(ValueError): call(tmp_path,body=b'invalid')
    assert list(tmp_path.rglob('nowscore.raw.html'))


def test_repository_clients_import_without_pythonpath():
    import os, subprocess, sys
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    subprocess.run([sys.executable, '-c', 'import src.nowscore_settlement; import src.nowscore_bjdc_sp_history'], env=env, check=True)
