import pytest
from src.market_sqlite import open_market_database, import_market_batch
from src.market_sqlite_query import query_market_records


def test_readonly_query_preserves_identity_and_detects_corruption(tmp_path):
    path=tmp_path/'market.sqlite'
    issues=[f'{n:06}' for n in range(50)]
    db=open_market_database(path)
    try:
        import_market_batch(db,batch_id='test',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={'issue':i,'value':None}) for i in issues],
            receipt={'input_sha256':'a'*64})
        result=query_market_records(path,issue='000001',kind='fixture_market')
        assert len(result)==1
        assert result[0]['data']=={'issue':'000001','value':None}
        assert result[0]['import_state']=='IMPORTED_PENDING_ACCEPTANCE'
        assert query_market_records(path,issue='000001',kind='anomaly')==[]
        assert query_market_records(path,issue='999999')==[]
        db.execute("UPDATE market_record SET record_json='{}' WHERE issue='000001'")
        db.commit()
        with pytest.raises(ValueError,match='hash mismatch'):
            query_market_records(path,issue='000001')
    finally:
        db.close()
    with pytest.raises(ValueError):
        query_market_records(path,issue=1)
    with pytest.raises(ValueError):
        query_market_records(path,issue='000001',kind='invalid')
    missing=tmp_path/'missing.sqlite'
    with pytest.raises(FileNotFoundError):
        query_market_records(missing,issue='000001')
    assert not missing.exists()


def test_reject_unrelated_database(tmp_path):
    import sqlite3
    path=tmp_path/'other.sqlite'
    sqlite3.connect(path).close()
    with pytest.raises(ValueError,match='identity'):
        query_market_records(path,issue='001')


def test_capture_query_exact_provenance(tmp_path):
    from src.market_sqlite_query import query_market_capture
    path=tmp_path/'market.sqlite'
    issues=[str(n) for n in range(50)]
    sha='b'*64
    url='https://1x2d.titan007.com/123.js'
    records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues]
    for kind,key in [('capture','0/hash/response'),('capture','0/hash/response/attempt-0'),
                     ('quote','0/hash/response/0'),('anomaly','transport/0/hash/response')]:
        records.append(dict(kind=kind,key=key,issue='0',source_sha256=sha,source_url=url,data={}))
    db=open_market_database(path)
    try:
        import_market_batch(db,batch_id='batch',issues=issues,records=records,
                            receipt={'input_sha256':'a'*64})
    finally:
        db.close()
    result=query_market_capture(path,issue='0',source_sha256=sha,source_url=url)
    assert len(result['retries'])==len(result['quotes'])==len(result['anomalies'])==1
    assert result['evidence']==[]
    with pytest.raises(ValueError,match='one stored'):
        query_market_capture(path,issue='0',source_sha256='c'*64,source_url=url)
    with pytest.raises(ValueError,match='one stored'):
        query_market_capture(path,issue='0',source_sha256=sha,source_url=url+'x')
    with pytest.raises(ValueError,match='SHA256'):
        query_market_capture(path,issue='0',source_sha256='bad',source_url=url)


def test_batch_counts_require_complete_registered_scope(tmp_path):
    from src.market_sqlite_query import query_market_batch_counts
    path=tmp_path/'db.sqlite';db=open_market_database(path)
    issues=[f'{i:03}' for i in range(50)]
    try:
        import_market_batch(db,batch_id='b',issues=issues,
            records=[dict(kind='fixture_market',key=i,issue=i,data={}) for i in issues],
            receipt={'input_sha256':'a'*64})
    finally:db.close()
    counts=query_market_batch_counts(path,batch_id='b')
    assert [r['issue'] for r in counts]==issues
    assert all(r['records']==1 and r['kind']=='fixture_market' for r in counts)
    with pytest.raises(ValueError,match='50-issue'):
        query_market_batch_counts(path,batch_id='missing')


def test_fixture_view_comparison_requires_full_scope_and_exact_rows(tmp_path):
    from src.market_sqlite import open_market_database,import_market_batch
    from src.market_sqlite_query import verify_market_fixture_views
    path=tmp_path/'views.sqlite';db=open_market_database(path)
    issues=[str(i) for i in range(50)]
    originals={i:[{'issue':i,'slot':1,'market':'euro'}] for i in issues}
    import_market_batch(db,batch_id='b',issues=issues,
        records=[dict(kind='fixture_market',key=i,issue=i,data=originals[i][0]) for i in issues],
        receipt={'input_sha256':'a'*64});db.close()
    result=verify_market_fixture_views(path,batch_id='b',issue_audits=originals)
    assert len(result)==50 and sum(r['records'] for r in result)==50
    with pytest.raises(ValueError,match='exact batch scope'):
        verify_market_fixture_views(path,batch_id='b',issue_audits={'0':originals['0']})
    originals['0']=originals['0']*2
    with pytest.raises(ValueError,match='view mismatch'):
        verify_market_fixture_views(path,batch_id='b',issue_audits=originals)
