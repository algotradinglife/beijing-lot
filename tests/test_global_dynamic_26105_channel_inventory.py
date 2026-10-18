"""Cache-only native-header and quote-route contracts, including explicit gaps."""
import json,runpy,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT/'src/global_dynamic_26105_channel_inventory_20261018.py'

def test_import_is_inert(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Import opened transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

def test_wrong_scope_stops_before_cache(tmp_path,monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Invalid scope opened transport')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    p=tmp_path/'bad.json';p.write_text('{"data":[]}')
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--roster',str(p),'--output','hot:refused'])
    with pytest.raises(ValueError,match='Exact365'):runpy.run_path(str(CLIENT),run_name='__main__')

def test_365_header_census_quarantines_identity_and_distinguishes_missing_raw(tmp_path,monkeypatch):
    import beidan_backend.unified_sources as source
    import beidan_backend.fundamentals as facts
    import beidan_backend.catalog.paths as paths
    from beidan_backend.extraction_cache import CacheMissError
    rows=[dict(issue_id='26105',slot=i,native_id='00'+str(10000+i),home='H',away='A',home_id=str(i),away_id=str(i+1000),handicap=0) for i in range(1,366)]
    path=tmp_path/'roster.json';path.write_text(json.dumps(dict(data=rows)));work=tmp_path/'inventory';calls=[]
    def request(provider,url,**kw):
        assert provider=='titan' and kw==dict(max_age=0,cache_only=True,reuse_raw=True)
        calls.append(url)
        if 'scheid=10002&' in url and 'oddskind=0&' in url:raise CacheMissError('saved gap')
        return dict(data=b'saved raw',receipt=dict(network_attempts=0,sha256='a'*64,url=url))
    def header(raw,*,source,provider_id,identity_only):
        assert source=='titan' and identity_only
        i=int(provider_id)-10000
        return dict(provider_id=provider_id,home='H',away='A',home_id='9999' if i==1 else str(i),away_id=str(i+1000),kickoff_utc='2026-10-16T09:00:00+00:00')
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(request=request))
    monkeypatch.setattr(facts,'analysis_record',header)
    monkeypatch.setattr(paths,'location',lambda *a,**kw:work)
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--roster',str(path),'--output','hot:test'])
    runpy.run_path(str(CLIENT),run_name='__main__')
    x=json.loads((work/'inventory.json').read_bytes())
    assert len(x['headers'])==365 and len(x['fixtures'])==364 and len(x['channels'])==728
    assert x['headers'][0]['state']=='HEADER_REJECTED' and all(c['fixture_id']!='26105:1' for c in x['channels'])
    assert sum(c['state']=='CACHE_MISS' for c in x['channels'])==1 and x['network_attempts']==0
    assert 'provider_id' in x['fixtures'][0] and x['fixtures'][0]['provider_id']=='10002'
    assert len(calls)==1093
    assert any('matchtime=20261016170000' in url for url in calls)
    with pytest.raises(ValueError,match='Immutable'):runpy.run_path(str(CLIENT),run_name='__main__')
