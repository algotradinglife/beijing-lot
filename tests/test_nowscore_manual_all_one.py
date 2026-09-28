import json
import sqlite3

import pytest

from tests.test_nowscore_settlement import page
from src.nowscore_settlement import build_database, canonical, digest, source_url
from src.nowscore_manual_all_one import apply_decisions, prepare_decisions, persist_decisions, special_notices
from scripts.apply_nowscore_manual_all_one import main

TIME = '2026-09-05T10:00:00+00:00'


@pytest.fixture
def source(tmp_path):
    raw = tmp_path/'raw'
    raw.mkdir()
    captures = []
    for tid,option in [(5,'胜'),(6,'4球'),(7,'上+双'),(8,'3:1'),(9,'胜-胜')]:
        b = page(tid,values={option:'1.00'})
        sha = digest(b)
        (raw/f'{sha}.html').write_bytes(b)
        captures.append(dict(issue='25053',typeid=tid,url=source_url('25053',tid),sha256=sha,received_at=TIME))
    (tmp_path/'manifest.json').write_text(canonical(dict(schema='nowscore_capture_v1',source='nowscore',requested_issues=['25053'],captures=captures)))
    db = tmp_path/'source.sqlite'
    build_database(tmp_path,db)
    with sqlite3.connect(db) as con:
        con.executescript('''CREATE TABLE bf_derivation(observation_id INTEGER,derived_option TEXT,derived_sp REAL,evidence_class TEXT,decision_id TEXT,issue TEXT,slot INTEGER);
          CREATE VIEW effective_finding AS SELECT * FROM finding;
          CREATE VIEW effective_option_sp AS SELECT * FROM option_sp;''')
    return db


def test_apply_replay_raw_preservation_and_repeat_refusal(source,tmp_path):
    before = source.read_bytes()
    r = apply_decisions(source,tmp_path/'a.sqlite',[('25053',1)],TIME)
    assert r['options']==49 and r['newly_filled_options']==44
    assert source.read_bytes()==before
    assert r==apply_decisions(source,tmp_path/'b.sqlite',[('25053',1)],TIME)
    with sqlite3.connect(tmp_path/'a.sqlite') as con:
        assert con.execute('SELECT count(*) FROM effective_option_sp WHERE effective_sp=1').fetchone()[0]==49
        assert con.execute('SELECT count(*) FROM effective_finding').fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM finding').fetchone()[0]==5
        assert con.execute('SELECT count(*) FROM option_sp WHERE sp IS NULL').fetchone()[0]==44
    with pytest.raises(FileExistsError):
        apply_decisions(source,tmp_path/'a.sqlite',[('25053',1)],TIME)


@pytest.mark.parametrize('targets,time', [([],TIME),([('25053',1),('25053',1)],TIME),([('25053',2)],TIME),([('25053',1)],'2026-09-05')])
def test_invalid_targets(source,tmp_path,targets,time):
    with pytest.raises(ValueError):
        apply_decisions(source,tmp_path/'bad.sqlite',targets,time)
    assert not (tmp_path/'bad.sqlite').exists()


def test_nonempty_or_conflicting_cells_rejected(source,tmp_path):
    with sqlite3.connect(source) as con:
        con.execute("UPDATE option_sp SET raw_sp='0' WHERE sp IS NULL")
    with pytest.raises(ValueError,match='representations'):
        apply_decisions(source,tmp_path/'bad.sqlite',[('25053',1)],TIME)


def test_persistence_rollback_and_connection_reusable(source):
    with sqlite3.connect(source) as con:
        ledger = prepare_decisions(con,[('25053',1)],TIME)
        def deny_receipt(action, arg1, arg2, db, trigger):
            return sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_INSERT and arg1=='manual_all_one_receipt' else sqlite3.SQLITE_OK
        con.set_authorizer(deny_receipt)
        with pytest.raises(sqlite3.DatabaseError):
            persist_decisions(con,ledger)
        con.set_authorizer(None)
        assert con.execute("SELECT count(*) FROM sqlite_master WHERE name='manual_all_one'").fetchone()[0]==0
        assert con.execute('SELECT count(*) FROM effective_finding').fetchone()[0]==5
        assert persist_decisions(con,ledger)['options']==49


def test_cli(source,tmp_path,capsys):
    main(['--source-db',str(source),'--output',str(tmp_path/'cli.sqlite'),'--target','25053:1','--reviewed-at',TIME])
    assert json.loads(capsys.readouterr().out)['newly_filled_options']==44
    with pytest.raises(SystemExit):
        main(['--source-db',str(source),'--output',str(tmp_path/'bad.sqlite'),'--target','broken','--reviewed-at',TIME])


@pytest.fixture
def abnormal_source(source):
    with sqlite3.connect(source) as con:
        for oid, payload in con.execute('SELECT observation_id,payload_json FROM observation').fetchall():
            raw = json.loads(payload)
            raw.update(status='推迟', score='-', halftime_score='-')
            if raw['play'] == 'bf':
                raw.update(summary_sp=1, summary_sp_raw='1.0000')
            for o in raw['options']:
                o.update(sp=2.5, raw_sp='2.5')
            con.execute('UPDATE observation SET payload_json=? WHERE observation_id=?', (canonical(raw), oid))
        con.execute("UPDATE option_sp SET sp=2.5,raw_sp='2.5'")
        con.execute("UPDATE finding SET code='abnormal_without_all_one'")
    return source


def test_abnormal_manual_overlay_preserves_reference_and_status(abnormal_source,tmp_path):
    before = abnormal_source.read_bytes()
    output = tmp_path/'abnormal.sqlite'
    receipt = apply_decisions(abnormal_source,output,[('25053',1)],TIME)
    assert receipt['replaced_reference_options'] == 49
    assert receipt['newly_filled_options'] == 0
    assert receipt['ledger']['decisions'][0]['reason'] == 'abnormal_status_bf_summary_one'
    assert not receipt['ledger']['decisions'][0]['official_notice_verified']
    assert abnormal_source.read_bytes() == before
    assert receipt == apply_decisions(abnormal_source,tmp_path/'replay.sqlite',[('25053',1)],TIME)
    with sqlite3.connect(output) as con:
        assert con.execute('SELECT count(*) FROM effective_finding').fetchone()[0] == 0
        assert con.execute('SELECT count(*) FROM effective_option_sp WHERE sp=2.5 AND effective_sp=1').fetchone()[0] == 49
        assert {json.loads(r[0])['status'] for r in con.execute('SELECT payload_json FROM observation')} == {'推迟'}


@pytest.mark.parametrize('field,value', [('summary_sp',2), ('status','完场'), ('score','0-0'), ('halftime_score','0-0'), ('native_match_id','different')])
def test_abnormal_evidence_conflict_rejected(abnormal_source,tmp_path,field,value):
    with sqlite3.connect(abnormal_source) as con:
        oid,payload = con.execute("SELECT observation_id,payload_json FROM observation WHERE play='bf'").fetchone()
        raw = json.loads(payload)
        raw[field] = value
        con.execute('UPDATE observation SET payload_json=? WHERE observation_id=?',(canonical(raw),oid))
    with pytest.raises(ValueError):
        apply_decisions(abnormal_source,tmp_path/'bad.sqlite',[('25053',1)],TIME)
    assert not (tmp_path/'bad.sqlite').exists()


@pytest.fixture
def zero_source(abnormal_source):
    with sqlite3.connect(abnormal_source) as c:
        for oid,p in c.execute("SELECT observation_id,payload_json FROM observation WHERE play IN ('bf','bq')").fetchall():
            r=json.loads(p)
            r['options'][0].update(raw_sp='0.00',sp=None)
            r['parse_errors']=['invalid_sp']
            c.execute('UPDATE observation SET payload_json=? WHERE observation_id=?',(canonical(r),oid))
            c.execute('UPDATE option_sp SET raw_sp=?,sp=NULL WHERE observation_id=? AND option=?',('0.00',oid,r['options'][0]['option']))
            c.execute("INSERT INTO finding SELECT issue,slot,play,'invalid_sp',detail,source_sha256 FROM finding WHERE play=?",(r['play'],))
    return abnormal_source


def test_zero_exception_requires_explicit_target_and_preserves_raw(zero_source,tmp_path):
    targets=[('25053',1)]
    with pytest.raises(ValueError):
        apply_decisions(zero_source,tmp_path/'denied.sqlite',targets,TIME)
    r=apply_decisions(zero_source,tmp_path/'ok.sqlite',targets,TIME,tuple(targets))
    assert r['reviewed_original_zero_options']==2 and r['newly_filled_options']==0
    assert r['replaced_reference_options']==47
    with sqlite3.connect(tmp_path/'ok.sqlite') as c:
        assert c.execute('SELECT count(*) FROM effective_finding').fetchone()[0]==0
        assert c.execute("SELECT count(*) FROM option_sp WHERE raw_sp='0.00' AND sp IS NULL").fetchone()[0]==2
        assert c.execute("SELECT count(*) FROM manual_all_one WHERE original_raw_sp='0.00' AND effective_sp=1").fetchone()[0]==2
    assert r==apply_decisions(zero_source,tmp_path/'replay.sqlite',targets,TIME,tuple(targets))


def test_zero_exception_rejects_unrelated_errors_and_bad_scope(zero_source,tmp_path):
    with pytest.raises(ValueError,match='unique explicit'):
        apply_decisions(zero_source,tmp_path/'bad.sqlite',[('25053',1)],TIME,(('999',1),))
    with sqlite3.connect(zero_source) as c:
        oid,p=c.execute("SELECT observation_id,payload_json FROM observation WHERE play='bf'").fetchone()
        r=json.loads(p)
        r['parse_errors'].append('malformed')
        c.execute('UPDATE observation SET payload_json=? WHERE observation_id=?',(canonical(r),oid))
    with pytest.raises(ValueError,match='clean'):
        apply_decisions(zero_source,tmp_path/'bad.sqlite',[('25053',1)],TIME,(('25053',1),))


def test_special_notice_separation_and_conflict_retention(abnormal_source):
    with sqlite3.connect(abnormal_source) as c:
        assert special_notices(c)==[]
        for oid,p in c.execute('SELECT observation_id,payload_json FROM observation').fetchall():
            r=json.loads(p)
            for o in r['options']:
                o.update(raw_sp='1.00',sp=1)
            c.execute('UPDATE observation SET payload_json=? WHERE observation_id=?',(canonical(r),oid))
        c.execute("UPDATE option_sp SET raw_sp='1.00',sp=1")
        c.execute("UPDATE finding SET code='full_domain_all_one'")
        c.commit()
        notices=special_notices(c)
        assert len(notices)==1 and not notices[0]['official_notice_verified']
        persist_decisions(c,{'reviewed_at':TIME,'decisions':[],'special_notices':notices})
        assert c.execute('SELECT count(*) FROM effective_finding').fetchone()[0]==0
        assert c.execute('SELECT count(*) FROM finding').fetchone()[0]==5
        assert c.execute('SELECT count(*) FROM special_settlement_notice').fetchone()[0]==1
        c.execute('UPDATE option_sp SET sp=2 WHERE observation_id=(SELECT min(observation_id) FROM observation)')
        assert special_notices(c)==[]


def test_zero_cli(zero_source,tmp_path,capsys):
    main(['--source-db',str(zero_source),'--output',str(tmp_path/'cli.sqlite'),'--target','25053:1','--zero-target','25053:1','--reviewed-at',TIME])
    assert json.loads(capsys.readouterr().out)['reviewed_original_zero_options']==2
    with pytest.raises(SystemExit):
        main(['--source-db',str(zero_source),'--output',str(tmp_path/'bad.sqlite'),'--target','25053:1','--zero-target','bad','--reviewed-at',TIME])


def test_clean_qmd_render(source,tmp_path):
    """Offline synthetic snapshot exercises the real report without private data."""
    import os
    from pathlib import Path
    import shutil
    import subprocess
    quarto=os.environ.get('QUARTO_BIN') or shutil.which('quarto')
    if not quarto:
        pytest.skip('Quarto unavailable; CI requires an explicit Quarto installation')
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE derivation_receipt(payload_json TEXT)')
        c.execute('INSERT INTO derivation_receipt VALUES(?)',(canonical({'approved_derivations':0,'production_enabled':False}),))
    snapshot=tmp_path/'render.sqlite'
    apply_decisions(source,snapshot,[('25053',1)],TIME)
    root=Path(__file__).resolve().parents[1]
    output=tmp_path/'html'
    result=subprocess.run([quarto,'render','quarto/05_nowscore_internal_audit.qmd','--execute','--no-cache',
                           '--output-dir',str(output),'-P','audit_db:'+str(snapshot)],cwd=root,capture_output=True,text=True,timeout=180)
    assert result.returncode==0,result.stdout+result.stderr
    rendered=list(output.rglob('05_nowscore_internal_audit.html'))
    assert len(rendered)==1
    text=rendered[0].read_text()
    assert 'original_raw_sp' in text and '当前样本待处理结算异常' in text
