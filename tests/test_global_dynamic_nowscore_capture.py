"""Actual Nowscore CLI integration with saved transport and its real shared ledger."""
import csv,hashlib,json,runpy,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT/'src/global_dynamic_nowscore_capture_20261018.py'

def test_import_does_not_open_source(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Import opened source')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

def test_empty_queue_refused_before_source(tmp_path,monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Invalid queue reached source')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    p=tmp_path/'empty.csv';p.write_text('fixture_id,source,url,kind,provider_id\n')
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--input',str(p),'--output','hot:refused','--policy-receipt','not-opened.json','--min-interval-seconds','5'])
    with pytest.raises(ValueError,match='nonempty'):runpy.run_path(str(CLIENT),run_name='__main__')

def test_live_call_path_keeps_authorized_five_second_spacing(tmp_path,monkeypatch):
    from beidan_backend import extraction_cache as backend,source_rate_policy as policy_module
    from beidan_backend.source_rate_policy import set_source_interval
    import beidan_backend.unified_sources as source
    import beidan_backend.catalog.paths as paths
    cache=backend.ExtractionCache(str(tmp_path/'raw.sqlite'))
    with sqlite3.connect(cache.path) as con:con.execute('INSERT INTO rate VALUES(?,?,?)',('nowscore',999,120))
    policy=set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='Explicit authorized5seconds')
    policy_path=tmp_path/'policy.json';policy_path.write_text(json.dumps(dict(state='APPLIED',receipt=policy)))
    queue=tmp_path/'queue.csv'
    with queue.open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=['fixture_id','source','url','kind','provider_id']);w.writeheader()
        w.writerow(dict(fixture_id='26105:1',source='nowscore',url='https://live.nowscore.com/analysis/123cn.html',kind='analysis',provider_id='000123'))
    inputs=[]
    for i in range(3):
        p=tmp_path/f'saved-{i}.csv';p.write_text('saved source')
        inputs.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    producer=ROOT/'r/global_dynamic_nowscore_queue_20261018.R'
    Path(str(queue)+'.json').write_text(json.dumps(dict(rows=1,fixtures=1,output_sha256=hashlib.sha256(queue.read_bytes()).hexdigest(),input_files=inputs,source_client=dict(path=str(producer),sha256=hashlib.sha256(producer.read_bytes()).hexdigest()))))
    sleeps=[];requests=[]
    monkeypatch.setattr(backend.time,'time',lambda:1000.)
    monkeypatch.setattr(backend.time,'sleep',sleeps.append)
    def saved(url,**kw):
        requests.append(url)
        return SimpleNamespace(body=b'saved raw observation',observed_at='1970-01-01T00:16:40+00:00',content_type='application/octet-stream')
    monkeypatch.setattr(backend,'fetch_issue_page',saved)
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(cache=cache))
    work=tmp_path/'output';monkeypatch.setattr(paths,'location',lambda *a,**kw:work)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--input',str(queue),'--output','hot:test','--policy-receipt',str(policy_path),'--min-interval-seconds','5'])
    with pytest.raises(SystemExit) as result:runpy.run_path(str(CLIENT),run_name='__main__')
    assert result.value.code==0 and requests==['https://live.nowscore.com/analysis/123cn.html']
    assert sleeps==[4.] # Preserved last attempt999, now1000, required interval5.
    with sqlite3.connect(cache.path) as con:assert con.execute('SELECT * FROM rate').fetchall()==[('nowscore',1000,5)]
    assert json.loads((work/'completion.json').read_bytes())['captured']==1
    assert json.loads((work/'26105_1-analysis.json').read_bytes())['provider_id']=='000123'
