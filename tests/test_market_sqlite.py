import sqlite3

import pytest

from src.market_sqlite import canonical_market_record, open_market_database, import_market_batch, backup_market_database


def test_transaction_replay_rollback_and_backup(tmp_path):
    issues = [f'1001{i:02}' for i in range(50)]
    rows = [dict(kind='anomaly',key=i,issue=i,data={'reason':'unavailable','source_url':'https://example.org/'+i}) for i in issues]
    receipt = dict(input_sha256='a'*64)
    db = open_market_database(tmp_path/'market.sqlite')
    args = dict(batch_id='first50',issues=issues,records=rows,receipt=receipt)
    assert import_market_batch(db,**args) == 50
    assert import_market_batch(db,**args) == 50
    with pytest.raises(ValueError,match='changed'):
        import_market_batch(db,**dict(args,records=rows[:-1]+[dict(rows[-1],data={'reason':'changed'})]))
    with pytest.raises(ValueError):
        import_market_batch(db,**dict(args,records=rows[:-1]))
    assert db.execute('SELECT count(*) FROM market_record').fetchone()[0] == 50
    dest = tmp_path/'backup.sqlite'
    assert len(backup_market_database(db,dest)) == 64
    with sqlite3.connect(dest) as copy:
        assert copy.execute('SELECT count(*) FROM market_record').fetchone()[0] == 50
    with pytest.raises(FileExistsError):
        backup_market_database(db,dest)
    db.close()
    db = open_market_database(tmp_path/'market.sqlite')
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()


def test_failed_first_import_is_fully_rolled_back(tmp_path):
    db = open_market_database(tmp_path/'market.sqlite')
    issues = [str(i) for i in range(50)]
    rows = [dict(kind='quote',key='x',issue='0',data={'odds':2.2})]*2
    with pytest.raises(ValueError,match='duplicate'):
        import_market_batch(db,batch_id='x',issues=issues,records=rows,receipt={'input_sha256':'a'*64})
    assert db.execute('SELECT count(*) FROM migration_batch').fetchone()[0] == 0
    assert db.execute('SELECT count(*) FROM market_record').fetchone()[0] == 0
    db.close()


@pytest.mark.parametrize('value',[{'body_base64':'x'},{'nested':[{'raw_html':'x'}]},float('nan')])
def test_body_and_nonfinite_rejected(value):
    with pytest.raises(ValueError):
        canonical_market_record(value)


def test_canonical_and_unrelated_schema(tmp_path):
    assert canonical_market_record({'b':None,'a':'001'}) == '{"a":"001","b":null}'
    path=tmp_path/'other.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE other (id INTEGER)')
    with pytest.raises(ValueError,match='unrelated'):
        open_market_database(path)


def test_existing_backup_replay_verification(tmp_path):
    from src.market_sqlite import verify_market_batch_backup
    db=open_market_database(tmp_path/'live.sqlite')
    issues=[str(i) for i in range(50)]
    try:
        import_market_batch(db,batch_id='b',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues],
            receipt={'input_sha256':'a'*64})
        path=tmp_path/'backup.sqlite'
        digest=backup_market_database(db,path)
        assert verify_market_batch_backup(db,path,batch_id='b')==digest
        db.execute("UPDATE market_record SET source_url='changed' WHERE issue='0'");db.commit()
        with pytest.raises(ValueError,match='content mismatch'):
            verify_market_batch_backup(db,path,batch_id='b')
    finally:
        db.close()


def test_backup_verifier_includes_later_audit_evidence(tmp_path):
    from src.market_sqlite import verify_market_batch_backup
    from src.market_sqlite_audit import store_market_audit_evidence
    db=open_market_database(tmp_path/'live.sqlite')
    issues=[str(i) for i in range(50)]
    try:
        import_market_batch(db,batch_id='b',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues],receipt={'input_sha256':'a'*64})
        old=tmp_path/'old.sqlite';backup_market_database(db,old)
        other=[str(i) for i in range(50,100)]
        import_market_batch(db,batch_id='other',issues=other,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in other],receipt={'input_sha256':'c'*64})
        store_market_audit_evidence(db,batch_id='other',evidence=[dict(acceptance_path='other.json',issues=other,documents={})])
        assert verify_market_batch_backup(db,old,batch_id='b')
        store_market_audit_evidence(db,batch_id='b',evidence=[dict(acceptance_path='a.json',issues=issues,documents={})])
        with pytest.raises(ValueError,match='audit evidence table mismatch'):
            verify_market_batch_backup(db,old,batch_id='b')
        fresh=tmp_path/'fresh.sqlite';digest=backup_market_database(db,fresh)
        assert verify_market_batch_backup(db,fresh,batch_id='b')==digest
        db.execute("UPDATE market_audit_evidence SET evidence_json='{}'");db.commit()
        with pytest.raises(ValueError,match='content mismatch'):
            verify_market_batch_backup(db,fresh,batch_id='b')
    finally:db.close()


def test_batch_backup_does_not_duplicate_previous_history(tmp_path):
    from src.market_sqlite import backup_market_batch,verify_market_batch_backup
    from src.market_sqlite_audit import store_market_audit_evidence
    db=open_market_database(tmp_path/'live.sqlite')
    try:
        for offset,batch in [(0,'a'),(50,'b')]:
            issues=[str(i) for i in range(offset,offset+50)]
            import_market_batch(db,batch_id=batch,issues=issues,
                records=[dict(kind='fixture_market',key=i,issue=i,data={'issue':i}) for i in issues],receipt={'input_sha256':'a'*64})
        store_market_audit_evidence(db,batch_id='b',evidence=[dict(acceptance_path='b.json',issues=issues,documents={})])
        path=tmp_path/'batch.sqlite';digest=backup_market_batch(db,path,batch_id='b')
        assert verify_market_batch_backup(db,path,batch_id='b')==digest
        with sqlite3.connect(path) as backup:
            assert backup.execute('SELECT batch_id FROM migration_batch').fetchall()==[('b',)]
            assert backup.execute('SELECT count(*) FROM batch_issue').fetchone()[0]==50
            assert backup.execute('SELECT count(*) FROM market_audit_evidence').fetchone()[0]==1
        with pytest.raises(FileExistsError):backup_market_batch(db,path,batch_id='b')
        with pytest.raises(ValueError,match='missing'):backup_market_batch(db,tmp_path/'bad.sqlite',batch_id='missing')
        assert not (tmp_path/'bad.sqlite').exists()
        assert not db.in_transaction
    finally:db.close()
