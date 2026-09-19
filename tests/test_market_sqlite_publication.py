import hashlib
import json
import pytest
from src.market_sqlite import open_market_database,import_market_batch
from src.market_sqlite_publication import prepare_market_sqlite_publication
from src.n7_published_markets import read_n7_published_markets


def test_full_batch_publication_cutover_preserves_rows(tmp_path):
    issues=[f'{i:03}' for i in range(50)]
    rows=[];sources=[];records=[]
    for issue in issues:
        row=dict(issue=issue,slot=1,provider_id='123',market='euro',status='NO_PRIOR_QUOTES',
                 cutoff_utc='2010-01-01T00:00:00Z',prior_companies=0,rows=[],historical_admission=False)
        rows.append(row)
        p=tmp_path/(issue+'.json');p.write_text(json.dumps([row]))
        sources.append(dict(issue=issue,path=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        records.append(dict(issue=issue,kind='fixture_market',key=issue,data=row))
    merged=dict(issues=issues,issue_sources=sources,rows=rows,historical_admission=False)
    old=tmp_path/'old.json';old.write_text(json.dumps(merged))
    db=open_market_database(tmp_path/'db.sqlite')
    import_market_batch(db,batch_id='b',issues=issues,records=records,receipt={'input_sha256':'a'*64});db.close()
    args=dict(merged_path=old.name,merged_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),database='db.sqlite',batch_id='b')
    result=prepare_market_sqlite_publication(tmp_path,**args)
    assert result['rows']==rows and all('sqlite' in s for s in result['issue_sources'])
    assert json.loads(old.read_text())==merged
    # A well-formed, hash-valid SQLite row still must equal the published view.
    from src.market_sqlite import canonical_market_record
    db=open_market_database(tmp_path/'db.sqlite')
    changed=dict(rows[0],provider_id='999')
    encoded=canonical_market_record(changed)
    db.execute('UPDATE market_record SET record_json=?,record_sha256=? WHERE issue=?',
               (encoded,hashlib.sha256(encoded.encode()).hexdigest(),issues[0]))
    db.commit()
    with pytest.raises(ValueError,match='detail mismatch'):
        prepare_market_sqlite_publication(tmp_path,**args)
    encoded=canonical_market_record(rows[0])
    db.execute('UPDATE market_record SET record_json=?,record_sha256=? WHERE issue=?',
               (encoded,hashlib.sha256(encoded.encode()).hexdigest(),issues[0]))
    db.commit();db.close()
    for source in sources:(tmp_path/source['path']).unlink()
    new=tmp_path/'new.json';new.write_text(json.dumps(result))
    read=read_n7_published_markets(data_root=tmp_path,merged_path=new.name,
         expected_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),issues=issues)
    assert read['rows']==rows
    with pytest.raises(ValueError,match='publication hash'):
        prepare_market_sqlite_publication(tmp_path,**dict(args,merged_sha256='0'*64))


def test_release_reference_keeps_data_acceptance_lineage():
    from src.market_sqlite_publication import market_sqlite_release_reference
    issues=[str(i) for i in range(50)]
    registry=dict(current_release=dict(path='old',sha256='a'*64,receipt='old-receipt'),
                  historical_admission=False,index='index',capture_root='raw',ledger='ledger')
    previous=dict(status='ACCEPTED_DIAGNOSTIC_BATCH_PUBLISHED',merged_sha256='a'*64,
                  acceptance={'path':'cleaning-acceptance','sha256':'b'*64},files=[{'path':'original'}])
    staged=dict(state='PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED',batch_id='b',issues=issues,sha256='c'*64)
    accepted=dict(state='SQLITE_BATCH_ACCEPTED',batch_id='b',issues=issues)
    args=dict(staged_receipt=staged,acceptance=accepted,acceptance_reference={'path':'storage','sha256':'d'*64},
              publication_path='markets/releases/new/merged.json',receipt_path='markets/releases/new/receipt.json')
    result=market_sqlite_release_reference(registry,previous,**args)
    assert result['receipt']['acceptance']==previous['acceptance']
    assert result['registry']['ledger']=='ledger' and result['registry']['index']=='index'
    assert result['receipt']['storage_conversion']['prior_release']==registry['current_release']
    assert registry['current_release']['path']=='old' and previous['merged_sha256']=='a'*64
    assert result['receipt']['storage_conversion']['raw_deletion_authorized'] is False
    with pytest.raises(ValueError,match='formal publication'):
        market_sqlite_release_reference(registry,previous,**dict(args,publication_path='audits/staged.json'))
    with pytest.raises(ValueError,match='prior publication'):
        market_sqlite_release_reference(registry,dict(previous,merged_sha256='e'*64),**args)
    with pytest.raises(ValueError,match='accepted staged'):
        market_sqlite_release_reference(registry,previous,**dict(args,acceptance=dict(accepted,batch_id='other')))


def test_activation_resume_rejects_partial_or_changed_bindings():
    from src.market_sqlite_publication import verify_market_publication_activation
    reference={'path':'accepted','sha256':'a'*64}
    staged={'sha256':'b'*64,'batch_id':'b'}
    registry=dict(current_release=dict(path='new',sha256='b'*64,receipt='receipt'),historical_admission=False)
    receipt=dict(status='ACCEPTED_DIAGNOSTIC_BATCH_PUBLISHED',merged_sha256='b'*64,
        storage_conversion=dict(batch_id='b',acceptance=reference,historical_admission=False,prior_release={'path':'old'}))
    kwargs=dict(staged_receipt=staged,acceptance_reference=reference,publication_path='new',receipt_path='receipt')
    assert verify_market_publication_activation(registry,receipt,**kwargs)
    with pytest.raises(ValueError,match='activated publication'):
        verify_market_publication_activation(dict(registry,current_release={}),receipt,**kwargs)
    with pytest.raises(ValueError,match='activated publication'):
        verify_market_publication_activation(registry,dict(receipt,storage_conversion={}),**kwargs)
