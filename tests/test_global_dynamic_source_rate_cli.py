"""One-shot administrative CLI with the actual transactional policy implementation."""
import json,runpy,sqlite3,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[1]
CLIENT=ROOT/'src/global_dynamic_source_rate_20261018.py'

def test_import_has_no_operational_effect(monkeypatch):
    import beidan_backend.unified_sources as source
    def forbidden(*a,**kw):raise AssertionError('Import constructed source')
    monkeypatch.setattr(source,'SourceClient',forbidden)
    runpy.run_path(str(CLIENT),run_name='import_only')

@pytest.mark.parametrize('expected',[120,60])
def test_one_shot_actual_policy_receipt_and_stale_rejection(tmp_path,monkeypatch,expected):
    from beidan_backend.extraction_cache import ExtractionCache
    import beidan_backend.unified_sources as source
    import beidan_backend.catalog.paths as paths
    c=ExtractionCache(str(tmp_path/'raw.sqlite'))
    with sqlite3.connect(c.path) as con:con.execute('INSERT INTO rate VALUES(?,?,?)',('nowscore',100,120))
    target=tmp_path/'operation.json'
    monkeypatch.setattr(paths,'location',lambda *a,**kw:target)
    monkeypatch.setattr(source,'SourceClient',lambda:SimpleNamespace(cache=c))
    monkeypatch.setattr(sys,'argv',[str(CLIENT),'--source','nowscore','--expected-seconds',str(expected),'--seconds','5','--reason','Explicit user5seconds','--output','hot:operation'])
    if expected==120:
        runpy.run_path(str(CLIENT),run_name='__main__')
        result=json.loads(target.read_bytes());assert result['state']=='APPLIED'
        assert result['receipt']['last_attempt']==100 and result['receipt']['interval_seconds']==5
    else:
        with pytest.raises(ValueError,match='expected'):runpy.run_path(str(CLIENT),run_name='__main__')
        assert not target.exists() and json.loads((tmp_path/'operation-failed.json').read_bytes())['state']=='FAILED'
    with sqlite3.connect(c.path) as con:assert con.execute('SELECT * FROM rate').fetchall()==[('nowscore',100,5 if expected==120 else 120)]
    with pytest.raises(ValueError,match='One-shot'):runpy.run_path(str(CLIENT),run_name='__main__')
