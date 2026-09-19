import hashlib
import json
import pytest
from src.market_sqlite_audit import collect_market_audit_evidence


def test_retains_full_ledger_and_detects_missing_or_changed_evidence(tmp_path):
    ledger=tmp_path/'ledger.json'
    ledger.write_text(json.dumps({'rows':[{'issue':'001','reason':'bad odds'},{'issue':'002','decision':'pending'}]}))
    receipt=tmp_path/'acceptance.json'
    binding={'path':ledger.name,'sha256':hashlib.sha256(ledger.read_bytes()).hexdigest()}
    acceptance=dict(status='ACCEPTED_DIAGNOSTIC_BATCH',issues=['001','002'],anomaly_ledger=binding)
    receipt.write_text(json.dumps(acceptance))
    result=collect_market_audit_evidence(tmp_path,[receipt.name],issues=['001'])
    assert result[0]['issues']==['001']
    assert len(result[0]['documents']['anomaly_ledger']['data']['rows'])==2
    assert collect_market_audit_evidence(tmp_path,[receipt.name],issues=['003'])==[]
    ledger.write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        collect_market_audit_evidence(tmp_path,[receipt.name],issues=['001'])
    acceptance.pop('anomaly_ledger');receipt.write_text(json.dumps(acceptance))
    with pytest.raises(ValueError,match='missing anomaly'):
        collect_market_audit_evidence(tmp_path,[receipt.name],issues=['001'])


def test_store_requires_full_scope_and_exact_replay(tmp_path):
    from src.market_sqlite import open_market_database,import_market_batch
    from src.market_sqlite_audit import store_market_audit_evidence
    db=open_market_database(tmp_path/'db.sqlite')
    issues=[str(n) for n in range(50)]
    try:
        import_market_batch(db,batch_id='b',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues],
            receipt={'input_sha256':'a'*64})
        evidence=[dict(acceptance_path='acceptance.json',issues=issues,documents={'anomaly_ledger':{'data':[]}})]
        assert store_market_audit_evidence(db,batch_id='b',evidence=evidence)==1
        assert store_market_audit_evidence(db,batch_id='b',evidence=evidence)==1
        with pytest.raises(ValueError,match='incomplete'):
            store_market_audit_evidence(db,batch_id='b',evidence=[])
        changed=[dict(evidence[0],documents={'changed':True})]
        with pytest.raises(ValueError,match='replay changed'):
            store_market_audit_evidence(db,batch_id='b',evidence=changed)
        assert store_market_audit_evidence(db,batch_id='b',evidence=evidence)==1
        assert not db.in_transaction
    finally:
        db.close()


def test_audit_reader_distinguishes_absent_evidence_from_no_anomalies(tmp_path):
    from src.market_sqlite import open_market_database,import_market_batch
    from src.market_sqlite_audit import store_market_audit_evidence
    from src.market_sqlite_query import query_market_audit_evidence
    path=tmp_path/'db.sqlite';db=open_market_database(path)
    issues=[str(n) for n in range(50)]
    try:
        import_market_batch(db,batch_id='b',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues],
            receipt={'input_sha256':'a'*64})
        with pytest.raises(ValueError,match='not stored'):
            query_market_audit_evidence(path,batch_id='b')
        evidence=[dict(acceptance_path='a.json',issues=issues,documents={'anomaly_ledger':{'data':[]}})]
        store_market_audit_evidence(db,batch_id='b',evidence=evidence)
        assert query_market_audit_evidence(path,batch_id='b')==evidence
        db.execute("UPDATE market_audit_evidence SET evidence_json='{}'");db.commit()
        with pytest.raises(ValueError,match='hash mismatch'):
            query_market_audit_evidence(path,batch_id='b')
    finally:
        db.close()


@pytest.mark.parametrize('scope_role',['manifest','market_summary'])
def test_archived_audit_keeps_original_decisions(tmp_path,scope_role):
    import io
    import tarfile
    from src.market_sqlite_audit import collect_archived_market_audit
    archive=tmp_path/'audit.tar'
    manifest={'issues':['001'] if scope_role=='manifest' else [{'issue':'001'}]}
    acceptance={'status':'ACCEPTED_DIAGNOSTIC_BATCH',scope_role:{'sha256':hashlib.sha256(json.dumps(manifest).encode()).hexdigest()}}
    with tarfile.open(archive,'w') as out:
        for name,data in [('acceptance.json',acceptance),('manifest.json',manifest),('anomalies.json',[{'issue':'001','decision':'isolate'}])]:
            raw=json.dumps(data).encode();info=tarfile.TarInfo(name);info.size=len(raw)
            out.addfile(info,io.BytesIO(raw))
    result=collect_archived_market_audit(tmp_path,archive=archive.name,
        archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),acceptance_member='acceptance.json',
        document_members={'anomaly_ledger':'anomalies.json',scope_role:'manifest.json'},issues=['001'])
    assert result['acceptance']==acceptance
    assert result['documents']['anomaly_ledger']['data'][0]['decision']=='isolate'

    with pytest.raises(ValueError,match='outside accepted manifest'):
        collect_archived_market_audit(tmp_path,archive=archive.name,
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),acceptance_member='acceptance.json',
            document_members={'anomaly_ledger':'anomalies.json',scope_role:'manifest.json'},issues=['999'])

    with pytest.raises(ValueError,match='exactly one scope'):
        collect_archived_market_audit(tmp_path,archive=archive.name,
            archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),acceptance_member='acceptance.json',
            document_members={'anomaly_ledger':'anomalies.json','manifest':'manifest.json','market_summary':'manifest.json'},issues=['001'])
