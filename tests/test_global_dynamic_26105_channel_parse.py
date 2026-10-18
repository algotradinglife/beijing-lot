"""Offline parser CLI scope, missing-byte, rejection and integrity contracts."""
import json,runpy,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
CLIENT=Path(__file__).resolve().parents[1]/'src/global_dynamic_26105_channel_parse_20261018.py'

def test_import_has_no_io(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Unexpected transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

@pytest.mark.parametrize('failure',['none','integrity','document','route','document_changed'])
def test_offline_channel_states_and_raw_binding(tmp_path,monkeypatch,failure):
    import beidan_backend.unified_sources as source
    import beidan_backend.catalog.paths as paths
    from beidan_backend.extraction_cache import CacheMissError
    from beidan_backend.market_capture.history import over_under_history_url
    from datetime import datetime
    fixtures=[dict(fixture_id=f'26105:{i}',provider_id=str(i),kickoff_at='2026-10-18T10:00:00+00:00') for i in range(1,366)]
    channels=[dict(fixture_id=f['fixture_id'],provider_id=f['provider_id'],kind=k,url=over_under_history_url(f['provider_id'],8,datetime.fromisoformat(f['kickoff_at'])).replace('oddskind=1','oddskind=0' if k=='asian' else 'oddskind=1'),receipt={'sha256':'a'*64}) for i,f in enumerate(fixtures) for k in ['asian','total']]
    if failure=='route':channels[0]['url']=channels[1]['url']
    path=tmp_path/'inventory.json';path.write_text(json.dumps(dict(issue_id='26105',fixtures=fixtures,channels=channels)))
    calls=[]
    def extract(provider,url,parser,**kw):
        assert provider=='titan' and kw==dict(max_age=0,min_interval=5,cache_only=True,reuse_raw=True)
        calls.append(url)
        if failure in {'document','document_changed'} and 'scheid=2&' in url:
            error=ValueError('empty or oversized source document');error.extraction_receipt=dict(network_attempts=0,sha256=('b' if failure=='document_changed' else 'a')*64);raise error
        if 'scheid=1&' in url and 'oddskind=0&' in url:raise CacheMissError('Missing')
        return dict(data=b'invalid JSON' if 'scheid=1&' in url and 'oddskind=1&' in url else b'[]',receipt=dict(network_attempts=0,sha256=('b' if failure=='integrity' else 'a')*64))
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(cache=SimpleNamespace(extract=extract)))
    out=tmp_path/'out';monkeypatch.setattr(paths,'location',lambda *a,**kw:out)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--inventory',str(path),'--output','hot:test'])
    if failure=='route':
        with pytest.raises(ValueError,match='Native channel route'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not calls and not out.exists()
    elif failure in {'integrity','document_changed'}:
        with pytest.raises(ValueError,match='raw identity changed'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not (out/'parsed.json').exists()
    else:
        runpy.run_path(str(CLIENT),run_name='__main__')
        x=json.loads((out/'parsed.json').read_bytes())
        assert len(calls)==730 and len(x['records'])==730
        assert x['records'][0]['state']=='CACHE_MISS'
        assert x['records'][1]['state']=='PARSE_REJECTED'
        if failure=='document':
            assert all(r['state']=='DOCUMENT_REJECTED' and r['raw_receipt']['network_attempts']==0 for r in x['records'][2:4])
        else:assert all(r['state']=='OBSERVED_EMPTY' for r in x['records'][2:])
        assert x['historical_admission'] is False and x['network_attempts']==0
        with pytest.raises(ValueError,match='Immutable'):runpy.run_path(str(CLIENT),run_name='__main__')
