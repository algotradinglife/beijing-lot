"""Offline CLI contracts for the exact Titan gap capture; no network or sleeping."""
import csv,json,runpy,sys,hashlib
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT/'src/global_dynamic_26105_capture_missing_20261018.py'

@pytest.fixture
def queue(tmp_path):
    p=tmp_path/'queue.csv'
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['fixture_id','source','url','kind','provider_id']);w.writeheader()
        for i in range(1,155):
            native=str(100000+i)
            for kind in ['analysis','euro']:
                w.writerow(dict(fixture_id=f'26105:{i}',source='titan',provider_id='00'+native,
                    kind=kind,url=f'https://zq.titan007.com/analysis/{native}cn.htm' if kind=='analysis' else f'https://1x2d.titan007.com/{native}.js'))
    inputs=[]
    for i in range(3):
        item=tmp_path/f'input-{i}.csv';item.write_text('saved input table')
        inputs.append(dict(path=str(item),sha256=hashlib.sha256(item.read_bytes()).hexdigest()))
    producer=ROOT/'r/global_dynamic_26105_capture_queue_20261018.R'
    Path(str(p)+'.json').write_text(json.dumps(dict(rows=308,fixtures=154,output_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),input_files=inputs,source_client=dict(path=str(producer),sha256=hashlib.sha256(producer.read_bytes()).hexdigest()))))
    return p

def test_import_is_inert(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Import instantiated transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

def test_invalid_scope_fails_before_cache_or_output(tmp_path,monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Invalid input reached transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    p=tmp_path/'bad.csv';p.write_text('fixture_id,source,url,kind,provider_id\n')
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--input',str(p),'--output','hot:must-not-exist','--min-interval-seconds','5'])
    with pytest.raises(ValueError,match='Exact308'):runpy.run_path(str(CLIENT),run_name='__main__')

@pytest.mark.parametrize('recover',[True,False])
def test_bounded_resume_preserves_failures_successes_and_binding(queue,tmp_path,monkeypatch,recover):
    import beidan_backend.unified_sources as source
    import beidan_backend.catalog.paths as paths
    from beidan_backend.transport import FetchError
    work=tmp_path/'work';calls=[];first=[]
    def extract(provider,url,parser,**kw):
        assert provider=='titan' and kw==dict(max_age=0,min_interval=5,retries=1,reuse_raw=True)
        calls.append(url)
        if not first:first.append(url)
        if url==first[0] and (calls.count(url)==1 or not recover):
            e=FetchError('timeout');e.network_attempts=2;raise e
        return dict(receipt=dict(network_attempts=0,capture_id=len(calls),sha256='a'*64,url=url))
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(cache=SimpleNamespace(extract=extract)))
    monkeypatch.setattr(paths,'location',lambda *a,**kw:work)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--input',str(queue),'--output','hot:test','--min-interval-seconds','5'])
    with pytest.raises(SystemExit) as first_run:runpy.run_path(str(CLIENT),run_name='__main__')
    assert first_run.value.code==2 and len(calls)==308
    with pytest.raises(SystemExit) as second:runpy.run_path(str(CLIENT),run_name='__main__')
    assert second.value.code==(0 if recover else 2) and len(calls)==309
    assert len(list(work.glob('*-failed-pass1.json')))==1
    before=(work/'completion.json').read_bytes()
    with pytest.raises(SystemExit):runpy.run_path(str(CLIENT),run_name='__main__')
    assert len(calls)==309 and (work/'completion.json').read_bytes()==before
    with queue.open('a') as f:f.write('\n')
    with pytest.raises(ValueError,match='receipt mismatch|binding mismatch'):runpy.run_path(str(CLIENT),run_name='__main__')
    assert len(calls)==309 and (work/'completion.json').read_bytes()==before


def test_concurrent_writer_is_refused_before_transport(queue,tmp_path,monkeypatch):
    from filelock import FileLock,Timeout
    import beidan_backend.catalog.paths as paths
    import beidan_backend.unified_sources as source
    work=tmp_path/'locked';work.mkdir()
    def forbidden(*a,**kw):raise AssertionError('Concurrent command reached transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    monkeypatch.setattr(paths,'location',lambda *a,**kw:work)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--input',str(queue),'--output','hot:test','--min-interval-seconds','5'])
    with FileLock(str(work/'capture.lock')):
        with pytest.raises(Timeout):runpy.run_path(str(CLIENT),run_name='__main__')
    assert not (work/'input-binding.json').exists()
