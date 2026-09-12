import hashlib
import json
import sqlite3

import pytest

from src.settlement_sp_supplement import parse_500_bf, build_sp_supplement
from src.settlement_sp_update import apply_sp_update


@pytest.fixture
def update_case(tmp_path):
    db=tmp_path/'source.sqlite'; raw=tmp_path/'500.html'; ledger=tmp_path/'ledger.json'
    html=''.join(f'''<tr class="vs_lines" fid="{s}" value="{{index:'{s}',homeTeam:'A',guestTeam:'B',leagueName:'L',scheduleDate:'2010-02-27'}}">
    <td></td><td></td><td title="比赛时间：20:30"></td><td><a title="析" class="red eng">2:2</a></td>
    <td class="h_br"><span class="eng red">13.03</span></td></tr>''' for s in (12,13))
    raw.write_bytes(html.encode('gb18030'))
    observations=[dict(issue='100213',play='bf',slot=s,home='A',away='B',league='L',kickoff_time='02-27 20:30',
        score='2-2',expected_option='2:2',native_match_id=str(s),source_sha256='b'*64,
        options=[dict(option='2:2',raw_sp='',sp=None)]) for s in (12,13)]
    result=build_sp_supplement(observations,parse_500_bf(raw.read_bytes()),issue='100213',
        source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),aliases={})
    result['receipt']={'source_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source_url':'https://trade.500.com/bjdc/project_fq_bf.php?expect=100213'}
    ledger.write_text(json.dumps(result))
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE observation(observation_id INTEGER,issue TEXT,slot INTEGER,play TEXT,payload_json TEXT,expected_option TEXT,source_sha256 TEXT,native_match_id TEXT,score TEXT)')
        c.execute('CREATE TABLE option_sp(observation_id INTEGER,option TEXT,raw_sp TEXT,sp REAL)')
        c.execute('CREATE TABLE receipt(payload_json TEXT)')
        c.execute('INSERT INTO receipt VALUES (?)',(json.dumps({'source':'nowscore','production_enabled':False}),))
        for n in observations:
            c.execute('INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?)',(n['slot'],'100213',n['slot'],'bf',json.dumps(n),'2:2','b'*64,str(n['slot']),'2-2'))
            c.execute('INSERT INTO option_sp VALUES (?,?,?,?)',(n['slot'],'2:2','',None))
    return db,ledger,raw,tmp_path/'backup.sqlite'


def test_update_backup_audit_and_repeat(update_case):
    db,ledger,raw,backup=update_case
    assert apply_sp_update(*update_case, approval_note="approved test ledger")['updated']==2
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT sp FROM option_sp').fetchall()==[(13.03,),(13.03,)]
        assert c.execute('SELECT old_sp FROM sp_correction').fetchall()==[(None,),(None,)]
        assert c.execute('SELECT raw_html FROM sp_correction_batch').fetchone()[0]==raw.read_bytes()
        assert json.loads(c.execute('SELECT payload_json FROM receipt').fetchone()[0])['source_pure'] is False
    with sqlite3.connect(backup) as c:
        assert c.execute('SELECT sp FROM option_sp').fetchall()==[(None,),(None,)]
    assert apply_sp_update(*update_case, approval_note="approved test ledger")['status']=='already_applied'


def test_mid_transaction_failure_rolls_back(update_case):
    db,_,_,backup=update_case
    with sqlite3.connect(db) as c:
        c.execute("CREATE TRIGGER fail_second BEFORE UPDATE ON option_sp WHEN OLD.observation_id=13 BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError,match='injected'):apply_sp_update(*update_case, approval_note="approved test ledger")
    with sqlite3.connect(db) as c:
        assert c.execute('SELECT sp FROM option_sp').fetchall()==[(None,),(None,)]
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name='sp_correction'").fetchall()
    assert backup.exists()


def test_changed_original_or_evidence_fails_closed(update_case):
    db,ledger,raw,backup=update_case
    with sqlite3.connect(db) as c:c.execute('UPDATE option_sp SET sp=1')
    with pytest.raises(ValueError,match='original'):apply_sp_update(*update_case, approval_note="approved test ledger")
    assert not backup.exists()
    raw.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash'):apply_sp_update(*update_case, approval_note="approved test ledger")


def test_update_requires_explicit_approval_and_correct_source(update_case):
    with pytest.raises(ValueError, match='approval'):
        apply_sp_update(*update_case, approval_note='')
    db, ledger, raw, backup = update_case
    with pytest.raises(ValueError, match='distinct'):
        apply_sp_update(db, ledger, raw, db, approval_note='approved')
    data=json.loads(ledger.read_text());data['receipt']['source_url']='https://example.com'
    ledger.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='source identity'):
        apply_sp_update(*update_case, approval_note='approved')
    assert not backup.exists()


def test_update_cli_explicit_external_root(update_case, capsys):
    from scripts.apply_settlement_sp_update import main
    db, ledger, raw, backup = update_case
    main(['--database',str(db),'--ledger',str(ledger),'--raw',str(raw),
          '--backup',str(backup),'--data-root',str(db.parent),'--approval-note','test CLI approval'])
    assert json.loads(capsys.readouterr().out)['updated']==2
    with sqlite3.connect(db) as con:
        assert con.execute('SELECT DISTINCT note FROM sp_correction').fetchall()==[('test CLI approval',)]
