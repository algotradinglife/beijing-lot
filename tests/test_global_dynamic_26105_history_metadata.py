"""Offline metadata CLI preserves whole scope, raw binding and parser failures."""
import json,runpy,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
CLIENT=Path(__file__).resolve().parents[1]/'src/global_dynamic_26105_history_metadata_20261018.py'

def test_import_inert(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Unexpected client')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

@pytest.mark.parametrize('changed_raw',[False,True])
def test_full_scope_failures_and_binding(tmp_path,monkeypatch,changed_raw):
    import beidan_backend.unified_sources as source
    import beidan_backend.opponent_history as history
    import beidan_backend.catalog.paths as paths
    headers=[dict(fixture_id=f'26105:{i}',state='HEADER_VALIDATED',identity=dict(provider_id=str(i)),analysis_receipt=dict(url=f'https://saved/{i}',sha256='a'*64)) for i in range(1,366)]
    path=tmp_path/'inventory.json';path.write_text(json.dumps(dict(issue_id='26105',headers=headers)))
    calls=[]
    def request(provider,url,**kw):
        assert provider=='titan' and kw==dict(max_age=0,cache_only=True,reuse_raw=True)
        calls.append(url);return dict(data=b'saved',receipt=dict(sha256=('b' if changed_raw else 'a')*64,network_attempts=0))
    def parse(body,*,source,provider_id,expected_identity):
        assert body==b'saved' and source=='titan' and expected_identity['provider_id']==provider_id
        if provider_id=='1':raise ValueError('Rejected saved metadata')
        return dict(target_competition_id='2',rows=[])
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(request=request))
    monkeypatch.setattr(history,'parse_opponent_history',parse)
    out=tmp_path/'out';monkeypatch.setattr(paths,'location',lambda *a,**kw:out)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--inventory',str(path),'--output','hot:test'])
    if changed_raw:
        with pytest.raises(ValueError,match='Frozen raw identity'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not (out/'metadata.json').exists()
    else:
        runpy.run_path(str(CLIENT),run_name='__main__')
        x=json.loads((out/'metadata.json').read_bytes());assert len(calls)==365
        assert len(x['packets'])==365 and x['packets'][0]['state']=='REJECTED'
        assert all(p['state']=='PARSED' for p in x['packets'][1:])
        assert x['historical_admission'] is False and x['network_attempts']==0
        with pytest.raises(ValueError,match='Immutable'):runpy.run_path(str(CLIENT),run_name='__main__')
