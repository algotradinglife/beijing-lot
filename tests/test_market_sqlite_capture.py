import hashlib
import json
import pytest
from src.market_sqlite import open_market_database,import_market_batch
from src.market_sqlite_query import query_market_records
from src.market_sqlite_capture import read_market_storage_receipt


def test_explicit_storage_receipt_requires_acceptance_and_exact_binding(tmp_path):
    path=tmp_path/'db.sqlite';db=open_market_database(path)
    issues=[str(i) for i in range(50)];url='https://1x2d.titan007.com/123.js';sha='a'*64
    records=[dict(kind='capture',key=i+'/response',issue=i,source_sha256=sha,source_url=url,
                  data={'metadata':{'url':url,'status':200}}) for i in issues]
    records.append(dict(kind='capture',key='0/response/attempt-1',issue='0',source_sha256=sha,source_url=url,
                        data={'metadata':{'url':url,'status':200}}))
    records.extend(dict(kind='evidence',key='parsed/'+i+'/response',issue=i,source_sha256=sha,source_url=url,
                        data={'normalized':{'provider_id':'123'}}) for i in issues)
    import_market_batch(db,batch_id='b',issues=issues,records=records,receipt={'input_sha256':'b'*64});db.close()
    stored=query_market_records(path,issue='0')[0]
    acceptance=tmp_path/'accepted.json'
    from src.market_sqlite_query import market_source_inventory
    acceptance.write_text(json.dumps(dict(state='SQLITE_BATCH_ACCEPTED',batch_id='b',issues=issues,database=str(path),
        source_inventories={'0/response':market_source_inventory(query_market_records(path,issue='0'))})))
    ref=dict(database=str(path),issue='0',batch_id='b',capture_key='0/response',record_sha256=stored['record_sha256'],
             acceptance={'path':str(acceptance),'sha256':hashlib.sha256(acceptance.read_bytes()).hexdigest()})
    assert read_market_storage_receipt(ref,expected_sha256=sha,expected_url=url)['status']==200
    frozen=acceptance.read_bytes()
    missing_inventory=json.loads(frozen);missing_inventory.pop('source_inventories')
    acceptance.write_text(json.dumps(missing_inventory))
    unbound=dict(ref,acceptance=dict(path=str(acceptance),sha256=hashlib.sha256(acceptance.read_bytes()).hexdigest()))
    with pytest.raises(ValueError,match='accepted source inventory missing'):
        read_market_storage_receipt(unbound,expected_sha256=sha,expected_url=url)
    acceptance.write_bytes(frozen)
    retry=next(r for r in query_market_records(path,issue='0',kind='capture') if r['record_key'].endswith('attempt-1'))
    with pytest.raises(ValueError,match='selected main capture'):
        read_market_storage_receipt(dict(ref,capture_key=retry['record_key'],record_sha256=retry['record_sha256']),
                                    expected_sha256=sha,expected_url=url)
    from src.market_sqlite_capture import read_market_storage_parsed
    assert read_market_storage_parsed(ref,expected_sha256=sha,expected_url=url)[1]=={'provider_id':'123'}
    from src.fundamentals_market_history import verify_selected_market_receipt
    selected=dict(path='deleted-raw.json',sha256=sha,storage=dict(ref,source_url=url))
    assert verify_selected_market_receipt(selected,'euro:123')['status']==200
    with pytest.raises(ValueError,match='identity mismatch'):
        verify_selected_market_receipt(selected,'euro:456')
    with pytest.raises(ValueError,match='binding missing'):
        read_market_storage_receipt(ref,expected_sha256='c'*64,expected_url=url)
    with pytest.raises(ValueError,match='binding changed'):
        read_market_storage_receipt(dict(ref,record_sha256='0'*64),expected_sha256=sha,expected_url=url)
    db=open_market_database(path)
    db.execute("DELETE FROM market_record WHERE kind='evidence' AND issue='0'")
    db.commit();db.close()
    from src.market_sqlite_capture import MarketNormalizationUnavailable
    with pytest.raises(ValueError,match='inventory mismatch') as missing:
        read_market_storage_parsed(ref,expected_sha256=sha,expected_url=url)
    assert not isinstance(missing.value,MarketNormalizationUnavailable)
    acceptance.write_text('{}')
    with pytest.raises(ValueError,match='acceptance hash'):
        read_market_storage_receipt(ref,expected_sha256=sha,expected_url=url)


def test_index_binding_preserves_paths_and_only_matches_exact_sources():
    from src.market_sqlite_capture import bind_market_capture_index
    sha='a'*64
    index={'euro:123':{'selected':{'path':'old.json','sha256':sha,'status':200},
                      'attempts':[{'path':'retry.json','sha256':'b'*64}]}}
    record=dict(kind='capture',record_key='0/hash/response',issue='0',batch_id='b',
                source_url='https://1x2d.titan007.com/123.js',source_sha256=sha,record_sha256='c'*64)
    result=bind_market_capture_index(index,[record],database='db.sqlite',acceptance={'path':'a.json','sha256':'d'*64})
    assert result['changed_references']==1
    assert 'storage' not in index['euro:123']['selected']
    assert result['index']['euro:123']['selected']['path']=='old.json'
    assert 'storage' not in result['index']['euro:123']['attempts'][0]
    assert bind_market_capture_index(result['index'],[record],database='db.sqlite',
                                    acceptance={'path':'a.json','sha256':'d'*64})['changed_references']==0


def test_http_success_with_transport_error_remains_unavailable(monkeypatch):
    import src.market_sqlite_capture as capture
    import src.market_sqlite_query as query
    metadata={'status':200,'error':'body read interrupted'}
    monkeypatch.setattr(capture,'read_market_storage_receipt',lambda *args,**kwargs:metadata)
    monkeypatch.setattr(query,'query_market_capture',lambda *args,**kwargs:{
        'evidence':[],'anomalies':[{'record_key':'transport/0/response',
                                   'data':{'code':'TRANSPORT_OR_HTTP_FAILURE'}}]})
    with pytest.raises(capture.MarketNormalizationUnavailable,match='TRANSPORT_OR_HTTP_FAILURE'):
        capture.read_market_storage_parsed({'capture_key':'0/response','database':'unused','issue':'0'},
                                          expected_sha256='a'*64,expected_url='https://example.invalid')
