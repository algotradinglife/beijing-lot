import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.market_roster_supply import supply_rosters


def test_publish_and_resume_without_analysis_requests(tmp_path):
    url = 'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    plan = tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00', roster_root=str(tmp_path/'rosters'), batches=[[dict(issue='130511', roster_url=url)]])))
    calls = []
    raw = gzip.decompress(Path('tests/fixtures/fundamentals_census/roster-130511-type8.html.gz').read_bytes())
    def fetch(url, **kw):
        calls.append(url)
        return SimpleNamespace(status_code=200, url=url, headers={}, content=raw)
    args = dict(ledger_path=tmp_path/'ledger.sqlite',budget_id='test',request_budget=10,min_free_bytes=0,fetch=fetch)
    assert supply_rosters(plan,tmp_path/'out',**args)['published'] == 1
    assert supply_rosters(plan,tmp_path/'out',**args)['existing'] == 1
    assert calls == [url]
    receipt = json.loads((tmp_path/'rosters/130511/status.json').read_text())
    assert receipt['fixture_count'] > 0
    assert Path(receipt['roster_path']).is_file()
    changed=json.loads(plan.read_text());changed['historical_before']='2010-01-01T00:00:00+00:00'
    plan.write_text(json.dumps(changed))
    rejected=supply_rosters(plan,tmp_path/'out',**args)
    assert rejected['state']=='NEEDS_RETRY' and rejected['existing']==0
    assert calls==[url]


def test_rate_limit_does_not_publish_false_empty_roster(tmp_path):
    url='https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(tmp_path/'rosters'),batches=[[dict(issue='130511',roster_url=url)]])))
    result=supply_rosters(plan,tmp_path/'out',ledger_path=tmp_path/'ledger.sqlite',budget_id='test',request_budget=10,min_free_bytes=0,fetch=lambda url,**kw:SimpleNamespace(status_code=429,url=url,headers={},content=b'limited'))
    assert result['state']=='RATE_LIMITED'
    assert not (tmp_path/'rosters/130511/status.json').exists()


def test_reject_unsafe_identity_before_capture(tmp_path):
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(tmp_path/'rosters'),batches=[[dict(issue='../x',roster_url='bad')]])))
    with pytest.raises(ValueError,match='identity'):
        supply_rosters(plan,tmp_path/'out',ledger_path=tmp_path/'ledger',budget_id='t',request_budget=10)
    assert not (tmp_path/'ledger').exists()

@pytest.mark.parametrize('damage', ['hash', 'final_url'])
def test_replay_rejects_changed_capture(tmp_path, damage):
    from src.fundamentals_capture import capture_documents
    import hashlib
    url='https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(tmp_path/'rosters'),batches=[[dict(issue='130511',roster_url=url)]])))
    directory=tmp_path/'out/130511/attempt-000001'
    capture_documents([dict(source='nowscore',url=url,filename='response.json')],directory,fetch=lambda url,**kw:SimpleNamespace(status_code=200,url=url,headers={},content=b'raw'))
    path=directory/'response.json'
    receipt=json.loads(path.read_text());receipt['final_url']='https://cp.nowscore.com/wrong'
    path.write_text(json.dumps(receipt))
    if damage=='final_url':
        manifest=json.loads((directory/'capture-manifest.json').read_text())
        manifest['file_hashes']['response.json']=hashlib.sha256(path.read_bytes()).hexdigest()
        (directory/'capture-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='hash|final URL'):
        supply_rosters(plan,tmp_path/'out',ledger_path=tmp_path/'ledger',budget_id='t',request_budget=10,min_free_bytes=0)
    assert not (tmp_path/'rosters/130511/status.json').exists()


def test_destination_lock_blocks_other_output(tmp_path):
    import fcntl
    root=tmp_path/'rosters';root.mkdir()
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(root),batches=[])))
    with (root/'supply.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            supply_rosters(plan,tmp_path/'different-output',ledger_path=tmp_path/'ledger',budget_id='t',request_budget=10)


def test_retry_after_rate_limit_and_consumer_scope(tmp_path):
    from datetime import datetime, timezone
    from src.fundamentals_market_history import issue_market_scope
    url='https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    entry=dict(issue='130511',roster_url=url)
    plan=tmp_path/'plan.json'
    plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(tmp_path/'rosters'),batches=[[entry]])))
    args=dict(ledger_path=tmp_path/'ledger',budget_id='t',request_budget=10,min_free_bytes=0)
    limited=lambda url,**kw:SimpleNamespace(status_code=429,url=url,headers={},content=b'limited')
    assert supply_rosters(plan,tmp_path/'out',fetch=limited,**args)['state']=='RATE_LIMITED'
    raw=gzip.decompress(Path('tests/fixtures/fundamentals_census/roster-130511-type8.html.gz').read_bytes())
    good=lambda url,**kw:SimpleNamespace(status_code=200,url=url,headers={},content=raw)
    assert supply_rosters(plan,tmp_path/'out',fetch=good,**args)['state']=='COMPLETE'
    scope=issue_market_scope(entry,tmp_path/'rosters',datetime(2020,1,1,tzinfo=timezone.utc))
    assert scope['state']=='SCOPED' and scope['fixtures']
    assert len(list((tmp_path/'out/130511').glob('attempt-*')))==2


def test_failed_existing_status_is_not_counted(tmp_path):
    root=tmp_path/'rosters';(root/'130511').mkdir(parents=True)
    target=root/'130511/status.json';target.write_text('{"processing_complete":true,"roster_error":"failed"}')
    before=target.read_bytes()
    url='https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum=130511'
    plan=tmp_path/'plan.json';plan.write_text(json.dumps(dict(historical_before='2020-01-01T00:00:00+00:00',roster_root=str(root),batches=[[dict(issue='130511',roster_url=url)]])))
    result=supply_rosters(plan,tmp_path/'out',ledger_path=tmp_path/'ledger',budget_id='t',request_budget=10)
    assert result['state']=='NEEDS_RETRY' and result['existing']==0
    assert '130511' in result['failures'] and target.read_bytes()==before
