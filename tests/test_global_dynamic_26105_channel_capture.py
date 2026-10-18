"""Bounded capture orchestration using a saved transport, never live HTTP."""
import json,runpy,sys
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace
import pytest
CLIENT=Path(__file__).resolve().parents[1]/'src/global_dynamic_26105_channel_capture_20261018.py'

def test_import_inert(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Unexpected client')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

@pytest.mark.parametrize('failure',['none','route','document','integrity'])
def test_exact_queue_saved_capture_and_idempotent_resume(tmp_path,monkeypatch,failure):
    import beidan_backend.unified_sources as source
    import beidan_backend.catalog.paths as paths
    from beidan_backend.market_capture.history import over_under_history_url
    fixtures=[dict(fixture_id=f'26105:{i}',provider_id=str(3000000+i),kickoff_at='2026-10-18T09:00:00+00:00') for i in range(1,366)]
    channels=[]
    for f in fixtures[:154]:
        total=over_under_history_url(f['provider_id'],8,datetime.fromisoformat(f['kickoff_at']))
        for kind,url in [('total',total),('asian',total.replace('oddskind=1','oddskind=0'))]:channels.append(dict(fixture_id=f['fixture_id'],provider_id=f['provider_id'],kind=kind,url=url,state='CACHE_MISS'))
    if failure=='route':channels[0]['url']='https://attacker.invalid/'
    path=tmp_path/'inventory.json';path.write_text(json.dumps(dict(issue_id='26105',fixtures=fixtures,channels=channels)))
    calls=[]
    def extract(provider,url,parser,**kw):
        assert provider=='titan' and kw==dict(max_age=0,min_interval=5,retries=1,reuse_raw=True)
        calls.append(url)
        if failure in {'document','integrity'} and url==channels[0]['url']:
            from beidan_backend.extraction_cache import CaptureIntegrityError
            error=CaptureIntegrityError('Corrupt') if failure=='integrity' else ValueError('empty or oversized source document')
            error.extraction_receipt=dict(network_attempts=1,sha256='a'*64);raise error
        return dict(receipt=dict(sha256='a'*64,network_attempts=1))
    from filelock import FileLock
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(cache=SimpleNamespace(extract=extract,lock=FileLock(str(tmp_path/'shared.lock')))))
    out=tmp_path/'out';monkeypatch.setattr(paths,'location',lambda *a,**kw:out)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--inventory',str(path),'--output','hot:test'])
    if failure=='route':
        with pytest.raises(ValueError,match='Native route'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not calls and not out.exists()
    elif failure=='integrity':
        with pytest.raises(ValueError,match='Corrupt'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not (out/'completion.json').exists()
    else:
        for _ in range(3):
            with pytest.raises(SystemExit) as exit:runpy.run_path(str(CLIENT),run_name='__main__')
            assert exit.value.code==(2 if failure=='document' else 0)
        assert len(calls)==(309 if failure=='document' else 308)
        summary=json.loads((out/'completion.json').read_bytes())
        assert summary==dict(total=308,captured=307 if failure=='document' else 308,failed=1 if failure=='document' else 0,prices_validated=False)
