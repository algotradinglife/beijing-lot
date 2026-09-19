import pytest
from src.market_sqlite_query import market_source_inventory,verify_market_source_inventory


def test_frozen_inventory_detects_missing_added_and_modified_members():
    common=dict(batch_id='b',issue='001',provider_id='123',market='euro',source_url='https://example.test',
                source_sha256='a'*64,record_sha256='b'*64)
    rows=[dict(common,kind='capture',record_key='001/hash/response'),
          dict(common,kind='quote',record_key='001/hash/response/0'),
          dict(common,kind='anomaly',record_key='extract/001/hash/response/0')]
    frozen=market_source_inventory(rows)
    assert verify_market_source_inventory(list(reversed(rows)),frozen)==frozen
    for changed in (rows[:2],rows+[dict(rows[1],record_key='001/hash/response/1')],
                    [rows[0],dict(rows[1],record_sha256='c'*64),rows[2]],
                    [rows[0],dict(rows[1],provider_id='456'),rows[2]]):
        with pytest.raises(ValueError,match='inventory mismatch'):
            verify_market_source_inventory(changed,frozen)
    for invalid in ([],rows+rows,[rows[1]],rows+[dict(rows[1],issue='002')]):
        with pytest.raises(ValueError):market_source_inventory(invalid)


def test_batch_inventory_checks_every_issue_and_payload(tmp_path):
    from src.market_sqlite import open_market_database,import_market_batch
    from src.market_sqlite_query import query_market_batch_source_inventories
    issues=[str(i) for i in range(50)]
    rows=[dict(issue=i,kind='capture',key=i+'/response',source_sha256='a'*64,
               source_url='https://example.test',data={'status':200}) for i in issues]
    path=tmp_path/'db.sqlite';db=open_market_database(path)
    import_market_batch(db,batch_id='b',issues=issues,records=rows,receipt={'input_sha256':'b'*64})
    assert len(query_market_batch_source_inventories(path,batch_id='b'))==50
    db.execute("UPDATE market_record SET record_json='{}' WHERE issue='49'");db.commit()
    with pytest.raises(ValueError,match='record hash mismatch'):
        query_market_batch_source_inventories(path,batch_id='b')
    db.close()
