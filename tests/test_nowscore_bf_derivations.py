import copy
import json
import sqlite3

import pytest

from src.nowscore_bf_derivations import apply, make_ledger, main
from src.nowscore_settlement import PLAYS, TYPEID_LABELS, canonical, expected_option, digest


@pytest.fixture
def source_and_ledger():
    con = sqlite3.connect(":memory:")
    con.executescript('''
      CREATE TABLE observation(observation_id INTEGER,issue TEXT,slot INTEGER,play TEXT,payload_json TEXT);
      CREATE TABLE option_sp(observation_id INTEGER,option TEXT,raw_sp TEXT,sp REAL);
      CREATE TABLE finding(issue TEXT,slot INTEGER,play TEXT,code TEXT,detail TEXT,source_sha256 TEXT);
      CREATE TABLE receipt(payload_json TEXT);
    ''')
    for tid, play in PLAYS.items():
        r = dict(issue="25053",slot=61,play=play,status="完场",score="5-2",halftime_score="2-1",
                 handicap=0,native_match_id="123",source_sha256="a"*64,source_url="https://cp.nowscore.com/test",
                 summary_sp_raw="43.3629",summary_sp=43.3629)
        winner = expected_option(r)
        r["options"] = [dict(option=o,raw_sp="2.5" if play!='bf' and o==winner else "",
                           sp=2.5 if play!='bf' and o==winner else None) for o in TYPEID_LABELS[tid]]
        con.execute("INSERT INTO observation VALUES(?,?,?,?,?)", (tid,"25053",61,play,canonical(r)))
        con.executemany("INSERT INTO option_sp VALUES(?,?,?,?)", [(tid,o['option'],o['raw_sp'],o['sp']) for o in r['options']])
    con.execute("INSERT INTO finding VALUES(?,?,?,?,?,?)", ("25053",61,"bf","summary_sp_without_option","","a"*64))
    con.execute("INSERT INTO receipt VALUES(?)", (canonical(dict(source="nowscore")),))
    con.commit()
    v = dict(results_sha256="b"*64,results=[dict(issue="25053",slot=61,classification="无历史记录",
             score="5-2",expected_option="胜其他",summary_sp_raw="43.3629",roster_sha256="a"*64)])
    yield con, make_ledger(con, v)
    con.close()


def test_effective_views_and_immutable_raw_tables(source_and_ledger,tmp_path):
    con, ledger = source_and_ledger
    result = apply(con,ledger,tmp_path/'derived.sqlite')
    assert result['approved_derivations']==1
    with sqlite3.connect(tmp_path/'derived.sqlite') as dest:
        for t in ('observation','option_sp','finding','receipt'):
            assert con.execute(f'SELECT * FROM {t}').fetchall()==dest.execute(f'SELECT * FROM {t}').fetchall()
        assert dest.execute('SELECT count(*) FROM effective_finding').fetchone()[0]==0
        assert dest.execute("SELECT option,sp,effective_sp,evidence_class FROM effective_option_sp WHERE decision_id IS NOT NULL").fetchone()==('胜其他',None,43.3629,'user_confirmed_score_summary_derivation')
        assert dest.execute("SELECT count(*) FROM option_sp WHERE observation_id=8 AND sp IS NULL").fetchone()[0]==25
    replay = json.loads(canonical(ledger))
    assert apply(con,replay,tmp_path/'replay.sqlite')==result


@pytest.mark.parametrize('field,value', [('score','4-2'),('derived_option','负其他'),('derived_sp',1),
    ('review_status','pending'),('native_match_id','999'),('summary_sp_raw','99'),('official_notice_verified',True)])
def test_invalid_decisions_fail_closed(source_and_ledger,tmp_path,field,value):
    con, ledger = source_and_ledger
    bad = copy.deepcopy(ledger)
    bad['decisions'][0][field]=value
    with pytest.raises(ValueError):
        apply(con,bad,tmp_path/'bad.sqlite')
    assert not (tmp_path/'bad.sqlite').exists()


def test_no_overwriting_existing_options_or_additional_flags(source_and_ledger,tmp_path):
    con,ledger=source_and_ledger
    con.execute("UPDATE option_sp SET sp=2,raw_sp='2' WHERE observation_id=8 AND option='胜其他'")
    with pytest.raises(ValueError,match='empty'):
        apply(con,ledger,tmp_path/'bad.sqlite')
    con.execute("UPDATE option_sp SET sp=NULL,raw_sp='' WHERE observation_id=8")
    con.execute("INSERT INTO finding VALUES('25053',61,'spf','cross_play_score','','')")
    with pytest.raises(ValueError,match='additional'):
        apply(con,ledger,tmp_path/'bad.sqlite')


@pytest.fixture
def supported(source_and_ledger,tmp_path):
    from tests.test_verify_nowscore_bf_history import page, vector
    from scripts.verify_nowscore_bf_history import parse_history, verify
    con, old = source_and_ledger
    body = page([vector('胜其他','43.36')]).replace(b'26082',b'25053').replace('第23场'.encode(),'第61场'.encode())
    sha = digest(body)
    (tmp_path/'raw').mkdir()
    (tmp_path/'raw'/f'{sha}.html').write_bytes(body)
    target = dict(issue='25053',slot=61,score='5-2',expected_option='胜其他',summary_sp_raw='43.3629',roster_sha256='a'*64)
    result = {**verify(target,parse_history(body,'25053',61)), 'history_sha256':sha}
    return con, dict(results=[result],results_sha256=digest(canonical([result]).encode())), tmp_path


def test_supported_raw_replay_and_precision(supported):
    con,v,root = supported
    ledger=make_ledger(con,v,root)
    assert ledger['decisions'][0]['derived_sp']==43.3629
    assert ledger['decisions'][0]['evidence_class']=='history_supported_score_summary_derivation'
    a=apply(con,ledger,root/'a.sqlite',root)
    assert a==apply(con,ledger,root/'b.sqlite',root)
    with pytest.raises(FileExistsError):
        apply(con,ledger,root/'a.sqlite',root)
    with pytest.raises(ValueError,match='raw evidence'):
        apply(con,ledger,root/'bad.sqlite')


def test_supported_tampering_fails(supported):
    con,v,root=supported
    bad=copy.deepcopy(v)
    bad['results'][0]['single_sp_raw']='99'
    with pytest.raises(ValueError,match='evidence conflict'):
        make_ledger(con,bad,root)
    path=root/'raw'/(v['results'][0]['history_sha256']+'.html')
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='hash mismatch'):
        make_ledger(con,v,root)


def test_cli_supported(supported,capsys):
    con,v,root=supported
    with sqlite3.connect(root/'source.sqlite') as dest:
        con.backup(dest)
    (root/'verification.json').write_text(canonical(v))
    main(['--source-db',str(root/'source.sqlite'),'--approved-verification',str(root/'verification.json'),
          '--history-root',str(root),'--output',str(root/'cli.sqlite')])
    assert json.loads(capsys.readouterr().out)['approved_derivations']==1


def test_failed_publish_cleans_temporary_output(source_and_ledger,tmp_path,monkeypatch):
    from src import nowscore_bf_derivations as module
    con,ledger=source_and_ledger
    def fail(*args):
        raise OSError('publication failed')
    monkeypatch.setattr(module.os,'link',fail)
    with pytest.raises(OSError,match='publication failed'):
        apply(con,ledger,tmp_path/'failed.sqlite')
    assert list(tmp_path.iterdir())==[]
