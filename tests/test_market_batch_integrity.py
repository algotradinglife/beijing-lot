import pytest
from src.market_sqlite import open_market_database, import_market_batch, backup_market_batch, verify_market_batch_backup
from src.market_sqlite_audit import store_market_audit_evidence


@pytest.mark.parametrize('removed',['research','audit'])
def test_inventory_detects_deleted_unlinked_evidence(tmp_path,removed):
    path=tmp_path/'market.sqlite'
    db=open_market_database(path)
    issues=[str(i) for i in range(50)]
    try:
        records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues]
        records.append(dict(kind='evidence',key='research/0',issue='0',data={'text':'independent report'}))
        import_market_batch(db,batch_id='b',issues=issues,records=records,receipt={'input_sha256':'a'*64})
        evidence=[dict(acceptance_path=str(i),issues=issues,documents={'anomaly_ledger':{'data':[]}}) for i in range(2)]
        store_market_audit_evidence(db,batch_id='b',evidence=evidence)
        backup=tmp_path/'backup.sqlite'
        frozen=backup_market_batch(db,backup,batch_id='b')
        assert verify_market_batch_backup(db,backup,batch_id='b')==frozen
        if removed=='research':
            db.execute("DELETE FROM market_record WHERE kind='evidence'")
        else:
            db.execute("DELETE FROM market_audit_evidence WHERE acceptance_path='0'")
        db.commit()
        with pytest.raises(ValueError,match='backup batch content mismatch'):
            verify_market_batch_backup(db,backup,batch_id='b')
    finally:
        db.close()


def test_import_backup_replay_after_audit_retention(tmp_path):
    db=open_market_database(tmp_path/'db.sqlite')
    issues=[str(i) for i in range(50)]
    records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues]
    receipt={'input_sha256':'a'*64}
    try:
        import_market_batch(db,batch_id='b',issues=issues,records=records,receipt=receipt)
        initial=tmp_path/'initial.sqlite'
        digest=backup_market_batch(db,initial,batch_id='b')
        evidence=[dict(acceptance_path='a',issues=issues,documents={'anomaly_ledger':{'data':[]}})]
        store_market_audit_evidence(db,batch_id='b',evidence=evidence)
        complete=tmp_path/'complete.sqlite'
        full_digest=backup_market_batch(db,complete,batch_id='b')
        assert import_market_batch(db,batch_id='b',issues=issues,records=records,receipt=receipt)==50
        assert verify_market_batch_backup(db,initial,batch_id='b',stage='import')==digest
        assert verify_market_batch_backup(db,complete,batch_id='b')==full_digest
        with pytest.raises(ValueError,match='backup .* mismatch'):
            verify_market_batch_backup(db,initial,batch_id='b')
        with pytest.raises(ValueError,match='import backup contains'):
            verify_market_batch_backup(db,complete,batch_id='b',stage='import')
        with pytest.raises(ValueError,match='unknown backup'):
            verify_market_batch_backup(db,initial,batch_id='b',stage='invalid')
        db.execute("DELETE FROM market_record WHERE issue='0'");db.commit()
        with pytest.raises(ValueError,match='backup batch content mismatch'):
            verify_market_batch_backup(db,initial,batch_id='b',stage='import')
    finally:
        db.close()
