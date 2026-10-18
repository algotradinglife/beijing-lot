"""Operational cadence changes preserve request history, raw evidence and locking."""
import importlib
import sqlite3
import time
from pathlib import Path
from filelock import FileLock, Timeout
import pytest
from beidan_backend.extraction_cache import ExtractionCache, CaptureIntegrityError
from beidan_backend.source_rate_policy import set_source_interval

@pytest.fixture
def cache(tmp_path):
    c=ExtractionCache(str(tmp_path/'raw.sqlite'))
    with sqlite3.connect(c.path) as con:
        con.executemany('INSERT INTO rate VALUES(?,?,?)',[('nowscore',100,120),('titan',200,5),('novaapi',200,3)])
    from beidan_backend.unified_sources import document_bytes
    c.extract('nowscore','https://cp.nowscore.com/preserved-evidence',document_bytes,
        max_age=0,min_interval=120,offline=dict(body=b'original evidence',observed_at='2026-10-01T00:00:00+00:00',content_type='application/octet-stream'))
    return c

def test_policy_change_and_repeat_preserve_attempts_other_sources_and_raw(cache):
    with sqlite3.connect(cache.path) as con:before=con.execute('SELECT * FROM captures').fetchall()
    assert len(before)==1 and before[0][5]==b'original evidence'
    a=set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='User explicitly requested5seconds')
    assert a['changed'] and a['last_attempt']==100 and a['last_attempt_preserved']
    b=set_source_interval(cache,'nowscore',5,expected_interval_seconds=5,reason='Repeat authorized policy')
    assert not b['changed'] and b['last_attempt']==100
    with sqlite3.connect(cache.path) as con:
        assert con.execute('SELECT * FROM captures').fetchall()==before
        assert con.execute('SELECT * FROM rate ORDER BY source').fetchall()==[('novaapi',200,3),('nowscore',100,5),('titan',200,5)]
    assert len(a['implementation_sha256'])==len(a['cache_implementation_sha256'])==64

@pytest.mark.parametrize('source,value,expected,reason',[
    ('bad',5,120,'user'),('titan',True,5,'user'),('nowscore',0,120,'user'),
    ('nowscore',float('nan'),120,'user'),('nowscore',float('inf'),120,'user'),
    ('nowscore',5,False,'user'),('novaapi',2,3,'user'),('nowscore',5,120,''),
    ('nowscore',5,120,None),('nowscore',5,60,'user')])
def test_invalid_or_stale_policy_has_no_effect(cache,source,value,expected,reason):
    with sqlite3.connect(cache.path) as con:before=con.execute('SELECT * FROM rate ORDER BY source').fetchall()
    with pytest.raises(ValueError):set_source_interval(cache,source,value,expected_interval_seconds=expected,reason=reason)
    with sqlite3.connect(cache.path) as con:assert con.execute('SELECT * FROM rate ORDER BY source').fetchall()==before

def test_missing_source_invalid_context_and_chronology_fail_closed(cache):
    with pytest.raises(TypeError):set_source_interval(None,'nowscore',5,expected_interval_seconds=120,reason='user')
    with sqlite3.connect(cache.path) as con:con.execute("DELETE FROM rate WHERE source='nowscore'")
    with pytest.raises(ValueError):set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='user')
    with sqlite3.connect(cache.path) as con:con.execute('INSERT INTO rate VALUES(?,?,?)',('nowscore',time.time()+10000,120))
    with pytest.raises(CaptureIntegrityError):set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='user')

def test_transaction_rollback_releases_connection_and_lock(cache):
    with sqlite3.connect(cache.path) as con:
        con.execute("CREATE TRIGGER refuse_update BEFORE UPDATE ON rate BEGIN SELECT RAISE(ABORT,'injected rollback');END")
    with pytest.raises(sqlite3.DatabaseError,match='injected rollback'):
        set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='user')
    with sqlite3.connect(cache.path) as con:
        assert con.execute("SELECT last_attempt,interval_sec FROM rate WHERE source='nowscore'").fetchone()==(100,120)
        con.execute('DROP TRIGGER refuse_update')
    assert set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='user')['changed']

def test_external_capture_writer_blocks_policy_change(cache):
    cache.lock=FileLock(str(cache.path)+'.lock',timeout=0)
    with FileLock(str(cache.path)+'.lock'):
        with pytest.raises(Timeout):set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='user')
    with sqlite3.connect(cache.path) as con:assert con.execute("SELECT interval_sec FROM rate WHERE source='nowscore'").fetchone()==(120,)

def test_import_does_not_open_database(monkeypatch):
    import beidan_backend.source_rate_policy as module
    def forbidden(*args,**kwargs):raise AssertionError('Import opened database')
    monkeypatch.setattr(sqlite3,'connect',forbidden)
    importlib.reload(module)


@pytest.mark.parametrize('source,value,expected',[('titan',1,5),('nowscore',1,120),('novaapi',2.1,3)])
def test_inclusive_source_minimum(cache,source,value,expected):
    receipt=set_source_interval(cache,source,value,expected_interval_seconds=expected,reason='Explicit source minimum')
    assert receipt['interval_seconds']==value and receipt['last_attempt_preserved']


def test_explicit_raw_capture_honors_lowered_interval_without_resetting_history(cache,monkeypatch):
    from types import SimpleNamespace
    from beidan_backend import extraction_cache as backend
    from beidan_backend.unified_sources import document_bytes
    with sqlite3.connect(cache.path) as con:
        con.execute("UPDATE rate SET last_attempt=999 WHERE source='nowscore'")
    sleeps=[];requests=[]
    monkeypatch.setattr(backend.time,'time',lambda:1000.0)
    monkeypatch.setattr(backend.time,'sleep',sleeps.append)
    def saved_response(url,**kwargs):
        requests.append(url)
        return SimpleNamespace(body=b'new raw observation',observed_at='1970-01-01T00:16:40+00:00',content_type='application/octet-stream')
    monkeypatch.setattr(backend,'fetch_issue_page',saved_response)
    control=set_source_interval(cache,'nowscore',5,expected_interval_seconds=120,reason='User explicit5seconds')
    assert control['last_attempt']==999
    response=cache.extract('nowscore','https://live.nowscore.com/analysis/123cn.html',document_bytes,
        max_age=0,min_interval=5,retries=1,reuse_raw=True)
    assert sleeps==[4.0] and len(requests)==1 and response['receipt']['network_attempts']==1
    with sqlite3.connect(cache.path) as con:
        assert con.execute("SELECT last_attempt,interval_sec FROM rate WHERE source='nowscore'").fetchone()==(1000,5)
