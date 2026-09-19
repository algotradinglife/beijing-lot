import hashlib
import json
import pytest
from src.market_sqlite_acceptance import prepare_market_storage_acceptance


def test_acceptance_requires_review_report_scope_and_does_not_authorize_deletion(tmp_path,monkeypatch):
    issues=[str(i) for i in range(50)];code={'src/test.py':'a'*64}
    (tmp_path/'db').touch()
    (tmp_path/'backup').touch()
    import sqlite3
    monkeypatch.setattr('src.market_sqlite_acceptance.open_market_database',lambda *a: sqlite3.connect(':memory:'))
    monkeypatch.setattr('src.market_sqlite_acceptance.verify_market_batch_backup',lambda *a,**k:'d'*64)
    inventories={i+'/response':{'records':1,'sha256':'b'*64} for i in issues}
    monkeypatch.setattr('src.market_sqlite_acceptance.query_market_batch_source_inventories',
                        lambda *args,**kwargs:inventories)
    for name in ('report.html','review.txt','publication.json'):(tmp_path/name).write_text(name)
    hashes={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()
            for name in ('report.html','review.txt','publication.json')}
    docs={
        'import':dict(state='REPLAYED_BACKED_UP_PENDING_CUTOVER_REVIEW',issues=issues,database=str(tmp_path/'db')),
        'inventory':dict(state='SOURCE_INVENTORIES_BACKUP_VERIFIED_NOT_ACCEPTED',database=str(tmp_path/'db'),
                         backup=str(tmp_path/'backup'),backup_sha256='d'*64,
                         source_inventories={i+'/response':{'records':1,'sha256':'b'*64} for i in issues}),
        'publication':dict(state='PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED',issues=issues,
                           publication='publication.json',sha256=hashes['publication.json']),
        'review':dict(state='CODEX_REVIEW_PASSED',findings=[],implementation_hashes=code,
                      review_output='review.txt',review_output_sha256=hashes['review.txt']),
        'report':dict(state='QMD_RENDER_VERIFIED',implementation_hashes=code,issues=issues,database=str(tmp_path/'db'),
                      html='report.html',html_sha256=hashes['report.html'])}
    refs={}
    for name,doc in docs.items():
        doc['batch_id']='b';p=tmp_path/(name+'-receipt.json');p.write_text(json.dumps(doc))
        refs[name]=dict(path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    report_path=tmp_path/refs['report']['path']
    report=json.loads(report_path.read_text())
    report['input_evidence']={name:refs[name] for name in ('import','inventory','publication')}
    report_path.write_text(json.dumps(report))
    refs['report']['sha256']=hashlib.sha256(report_path.read_bytes()).hexdigest()
    result=prepare_market_storage_acceptance(tmp_path,evidence=refs,implementation_hashes=code)
    assert result['state']=='SQLITE_BATCH_ACCEPTED'
    assert result['raw_deletion_authorized'] is False and result['consumer_cutover_complete'] is False
    monkeypatch.setattr('src.market_sqlite_acceptance.verify_market_batch_backup',lambda *a,**k:'e'*64)
    with pytest.raises(ValueError,match='complete batch backup hash mismatch'):
        prepare_market_storage_acceptance(tmp_path,evidence=refs,implementation_hashes=code)
    monkeypatch.setattr('src.market_sqlite_acceptance.verify_market_batch_backup',lambda *a,**k:'d'*64)
    missing=inventories.pop('0/response')
    with pytest.raises(ValueError,match='live source inventories differ'):
        prepare_market_storage_acceptance(tmp_path,evidence=refs,implementation_hashes=code)
    inventories['0/response']=missing
    with pytest.raises(ValueError,match='current implementation review'):
        prepare_market_storage_acceptance(tmp_path,evidence=refs,implementation_hashes={'src/test.py':'c'*64})
    with pytest.raises(ValueError,match='complete acceptance evidence'):
        prepare_market_storage_acceptance(tmp_path,evidence={},implementation_hashes=code)
    mutations=[('inventory','source_inventories',{'0/response':{'records':1,'sha256':'b'*64}},'exact batch scope'),
               ('publication','issues',issues[:-1],'scope mismatch'),
               ('review','findings',['unresolved'],'current implementation review'),
               ('report','state','RENDER_FAILED','state/batch mismatch'),
               ('report','issues',issues[:-1],'report database/scope mismatch'),
               ('report','database',str(tmp_path/'other-db'),'report database/scope mismatch'),
               ('inventory','source_inventories',{k:dict(v,records=2) for k,v in inventories.items()},'report input evidence mismatch'),
               ('report','input_evidence',{},'report input evidence mismatch'),
               ('inventory','database',str(tmp_path/'other-db'),'database mismatch')]
    for role,field,value,message in mutations:
        path=tmp_path/refs[role]['path'];original=path.read_bytes()
        changed=json.loads(original);changed[field]=value;path.write_text(json.dumps(changed))
        altered=dict(refs);altered[role]=dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        with pytest.raises(ValueError,match=message):
            prepare_market_storage_acceptance(tmp_path,evidence=altered,implementation_hashes=code)
        path.write_bytes(original)
    (tmp_path/'report.html').write_text('changed')
    with pytest.raises(ValueError,match='artifact changed'):
        prepare_market_storage_acceptance(tmp_path,evidence=refs,implementation_hashes=code)


def test_shared_implementation_identity_includes_consumers_and_report():
    from pathlib import Path
    from src.market_sqlite_acceptance import market_storage_implementation
    root=Path(__file__).resolve().parents[1]
    code=market_storage_implementation(root)
    for name in ('src/market_sqlite_capture.py','src/market_sqlite_acceptance.py',
                 'scripts/accept_market_sqlite_batch.py','r/market_sqlite_report.R',
                 'quarto/market_sqlite_migration.qmd','src/fundamentals_scope_market.py',
                 'src/persistent_data_layout.py','src/__init__.py'):
        assert code[name]==hashlib.sha256((root/name).read_bytes()).hexdigest()


def test_entry_dependency_and_package_changes_invalidate_identity(tmp_path):
    import shutil
    from pathlib import Path
    from src.market_sqlite_acceptance import market_storage_implementation
    root=Path(__file__).resolve().parents[1]
    before=market_storage_implementation(root)
    for name in before:
        target=tmp_path/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/name,target)
    assert market_storage_implementation(tmp_path)==before
    for name in ('src/persistent_data_layout.py','src/__init__.py'):
        target=tmp_path/name
        original=target.read_bytes()
        target.write_bytes(original+b'\nPROVENANCE_REGRESSION_SENTINEL = True\n')
        assert market_storage_implementation(tmp_path)!=before
        target.write_bytes(original)
