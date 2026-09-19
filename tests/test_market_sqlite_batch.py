import base64
import hashlib
import json

import pytest

from src.market_sqlite_batch import market_batch_records, verified_market_json


def test_verified_json_mismatch(tmp_path):
    path=tmp_path/'x.json'; path.write_text('{}')
    assert verified_market_json(path,hashlib.sha256(path.read_bytes()).hexdigest())=={}
    with pytest.raises(ValueError):
        verified_market_json(path,'0'*64)


@pytest.mark.parametrize('archived',[False,True])
def test_research_text_is_retained_not_parsed_as_receipt(tmp_path,monkeypatch,archived):
    import src.market_sqlite_batch as module
    url='https://1x2d.titan007.com/123.js'
    receipt=json.dumps(dict(url=url,error='timeout')).encode()
    research='核对依据 https://example.org/report\n主客身份已核对。'.encode()
    bodies={'response.json':receipt,'research.txt':research}
    hashes={name:hashlib.sha256(body).hexdigest() for name,body in bodies.items()}
    if archived:
        monkeypatch.setattr(module,'read_archived_market_sources',lambda *args:bodies)
    else:
        for name,body in bodies.items(): (tmp_path/name).write_bytes(body)
    audit=tmp_path/'audit.json'
    audit.write_text(json.dumps([dict(issue='001',slot=1,market='euro',provider_id='123',
        status='IDENTITY_MISMATCH',capture_path='response.json',source_hashes=hashes)]))
    source=dict(issue='001',path=audit.name,sha256=hashlib.sha256(audit.read_bytes()).hexdigest())
    records=list(market_batch_records(tmp_path,[source]))
    evidence=[r for r in records if r['kind']=='evidence']
    assert len(evidence)==1
    assert evidence[0]['data']['text']==research.decode()
    assert evidence[0]['data']['source_urls']==['https://example.org/report']
    assert evidence[0]['data']['source_sha256']==hashes['research.txt']
    assert 'source_sha256' not in evidence[0]  # Not a transport-source inventory.
    assert any(r['kind']=='anomaly' and r['key'].startswith('transport/') for r in records)
    if not archived:
        (tmp_path/'research.txt').write_text('changed')
        with pytest.raises(ValueError,match='hash mismatch'):
            list(market_batch_records(tmp_path,[source]))


@pytest.mark.parametrize('text_first',[False,True])
def test_research_and_transport_deduplicate_separately(tmp_path,text_first):
    body=json.dumps(dict(url='https://1x2d.titan007.com/123.js',error='timeout')).encode()
    names=['research.txt','response.json'] if text_first else ['response.json','research.txt']
    digest=hashlib.sha256(body).hexdigest()
    for name in names: (tmp_path/name).write_bytes(body)
    audit=tmp_path/'audit.json'
    audit.write_text(json.dumps([dict(issue='001',slot=1,market='euro',provider_id='123',
        status='BAD',capture_path='response.json',source_hashes=dict.fromkeys(names,digest))]))
    source=dict(issue='001',path=audit.name,sha256=hashlib.sha256(audit.read_bytes()).hexdigest())
    records=list(market_batch_records(tmp_path,[source]))
    assert len([r for r in records if r['kind']=='capture'])==1
    assert len([r for r in records if r['key'].startswith('research/')])==1
    assert len([r for r in records if r['key'].startswith('transport/')])==1


def test_research_survives_database_replay_backup_and_inventory(tmp_path):
    from contextlib import closing
    from src.market_sqlite import open_market_database,import_market_batch,backup_market_batch
    from src.market_sqlite_query import query_market_records,query_market_batch_source_inventories
    raw=tmp_path/'response.json'
    raw.write_text(json.dumps(dict(url='https://1x2d.titan007.com/123.js',error='timeout')))
    research=tmp_path/'research.txt'
    research.write_text('独立核对：主队身份已确认\nhttps://example.org/evidence\n')
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (raw,research)}
    issues=[str(i) for i in range(50)]
    sources=[]
    for issue in issues:
        audit=tmp_path/(issue+'.json')
        audit.write_text(json.dumps([dict(issue=issue,slot=1,market='euro',provider_id='123',
            status='IDENTITY_MISMATCH',capture_path=raw.name,source_hashes=hashes)]))
        sources.append(dict(issue=issue,path=audit.name,sha256=hashlib.sha256(audit.read_bytes()).hexdigest()))
    database=tmp_path/'market.sqlite';backup=tmp_path/'backup.sqlite'
    with closing(open_market_database(database)) as db:
        args=dict(batch_id='b',issues=issues,receipt={'input_sha256':'a'*64})
        count=import_market_batch(db,records=market_batch_records(tmp_path,sources),**args)
        assert import_market_batch(db,records=market_batch_records(tmp_path,sources),**args)==count
        backup_market_batch(db,backup,batch_id='b')
    assert len(query_market_batch_source_inventories(database,batch_id='b'))==50
    for issue in issues:
        evidence=query_market_records(database,issue=issue,kind='evidence')
        assert evidence==query_market_records(backup,issue=issue,kind='evidence')
        assert evidence[0]['data']['text']==research.read_text()
        assert evidence[0]['data']['source_sha256']==hashes[research.name]
        assert evidence[0]['data']['source_urls']==['https://example.org/evidence']


@pytest.mark.parametrize('host',['1x2d.titan007.com','1x2.nowscore.com'])
def test_batch_keeps_bad_source_and_audit_details(tmp_path,host):
    body=b'var game=Array("1|record|company|bad|||||||||||||||||||||");'
    url=f'https://{host}/123.js'
    receipt=dict(url=url,final_url=url,status=200,body_base64=base64.b64encode(body).decode(),
                 byte_count=len(body),started_at_utc='2026-09-01T00:00:00Z',received_at_utc='2026-09-01T00:00:01Z')
    p=tmp_path/'response.json';p.write_text(json.dumps(receipt)); sha=hashlib.sha256(p.read_bytes()).hexdigest()
    audit=[dict(issue='001',slot=1,market='euro',provider_id='123',status='IDENTITY_MISMATCH',
                capture_path=p.name,source_hashes={p.name:sha},source_ids=['1','2'],roster_ids=['3','4'])]
    a=tmp_path/'audit.json';a.write_text(json.dumps(audit))
    sources=[dict(issue='001',path=a.name,sha256=hashlib.sha256(a.read_bytes()).hexdigest())]
    rows=list(market_batch_records(tmp_path,sources))
    assert any(r['kind']=='quote' and r['data']['fields'][3]=='bad' for r in rows)
    assert any(r['kind']=='anomaly' and r['data'].get('source_ids')==['1','2'] for r in rows)
    assert all('body_base64' not in r['data'].get('metadata',{}) for r in rows)
    p.write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        list(market_batch_records(tmp_path,sources))


def test_embedded_attempts_preserve_metadata_without_bodies():
    from src.market_sqlite_batch import market_transport_attempts
    from src.market_sqlite import canonical_market_record
    body=b'quote payload'
    response=dict(url='https://1x2d.titan007.com/123.js',final_url='https://1x2d.titan007.com/123.js',status=200,
                  body_base64=base64.b64encode(body).decode(),byte_count=len(body),
                  sha256=hashlib.sha256(body).hexdigest(),
                  started_at_utc='2026-09-01T00:00:00Z',received_at_utc='2026-09-01T00:00:01Z')
    outer=dict(response,attempt_receipts=[dict(response),dict(url=response['url'],error='timeout')])
    attempts=list(market_transport_attempts(outer))
    assert [a[0] for a in attempts]==['response','response/attempt-0','response/attempt-1']
    assert [a[2] for a in attempts]==[body,body,None]
    for _,meta,_ in attempts:
        canonical_market_record(meta)
        assert 'attempt_receipts' not in meta
    outer['attempt_receipts'][0]['sha256']='0'*64
    with pytest.raises(ValueError):
        list(market_transport_attempts(outer))
    with pytest.raises(ValueError,match='invalid embedded'):
        list(market_transport_attempts(dict(response,attempt_receipts={})))
    with pytest.raises(ValueError,match='neither body nor error'):
        list(market_transport_attempts({}))


def test_archive_audit_preflight(tmp_path):
    import io
    import tarfile
    from src.market_sqlite_batch import load_market_issue_audits
    body=b'[{"issue":"001"}]'
    archive=tmp_path/'audits.tar'
    with tarfile.open(archive,'w') as out:
        info=tarfile.TarInfo('audit.json'); info.size=len(body)
        out.addfile(info,io.BytesIO(body))
    source=dict(issue='001',archive=archive.name,
                archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                member='audit.json',sha256=hashlib.sha256(body).hexdigest())
    assert load_market_issue_audits(tmp_path,[source])=={'001':[{'issue':'001'}]}
    with pytest.raises(ValueError,match='duplicate'):
        load_market_issue_audits(tmp_path,[source,source])
    with pytest.raises(ValueError,match='archived audit hash'):
        load_market_issue_audits(tmp_path,[dict(source,sha256='0'*64)])


def test_peer_source_identity_is_preserved():
    from src.market_sqlite_batch import market_storage_source_key
    assert market_storage_source_key('https://1x2.nowscore.com/001.js')=='euro:001'
    assert market_storage_source_key('https://1x2d.titan007.com/001.js')=='euro:001'
    assert market_storage_source_key('https://cp.nowscore.com/buy/DanChang.aspx') is None
    assert market_storage_source_key('https://evil.example/001.js') is None


def test_identical_receipt_aliases_emit_unique_records(tmp_path):
    body=b'var game=Array("1|record|company|bad|||||||||||||||||||||");'
    url='https://1x2d.titan007.com/123.js'
    receipt=dict(url=url,final_url=url,status=200,body_base64=base64.b64encode(body).decode(),
        byte_count=len(body),started_at_utc='2026-09-01T00:00:00Z',received_at_utc='2026-09-01T00:00:01Z')
    content=json.dumps(receipt).encode();digest=hashlib.sha256(content).hexdigest()
    for name in ['original.json','copy.json']:
        (tmp_path/name).write_bytes(content)
    rows=[dict(issue='001',slot=1,market='euro',provider_id='123',status='BAD',
               capture_path='original.json',source_hashes={'original.json':digest,'copy.json':digest})]
    path=tmp_path/'audit.json';path.write_text(json.dumps(rows))
    source=dict(issue='001',path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    records=list(market_batch_records(tmp_path,[source]))
    assert len({(r['kind'],r['key']) for r in records})==len(records)
    captures=[r for r in records if r['kind']=='capture']
    assert len(captures)==1
    assert captures[0]['data']['path_aliases']==['copy.json','original.json']
    (tmp_path/'copy.json').write_text('{}')
    with pytest.raises(ValueError,match='hash mismatch'):
        list(market_batch_records(tmp_path,[source]))


def test_migrate_reused_source_after_raw_retirement(tmp_path):
    from src.market_sqlite import open_market_database, import_market_batch
    from src.market_sqlite_query import query_market_records
    url='https://1x2d.titan007.com/123.js'
    body=b'var game=Array("1|record|company|bad|||||||||||||||||||||");'
    raw=tmp_path/'raw.json'
    raw.write_text(json.dumps(dict(url=url,final_url=url,status=200,
        body_base64=base64.b64encode(body).decode(),byte_count=len(body),
        started_at_utc='2026-09-01T00:00:00Z',received_at_utc='2026-09-01T00:00:01Z')))
    digest=hashlib.sha256(raw.read_bytes()).hexdigest()
    issues=[str(i) for i in range(50)]
    sources=[]
    for issue in issues:
        audit=tmp_path/(issue+'.json')
        audit.write_text(json.dumps([dict(issue=issue,slot=1,market='euro',provider_id='123',
            status='IDENTITY_MISMATCH',capture_path=raw.name,source_hashes={raw.name:digest})]))
        sources.append(dict(issue=issue,path=audit.name,sha256=hashlib.sha256(audit.read_bytes()).hexdigest()))
    database=tmp_path/'db.sqlite';db=open_market_database(database)
    import_market_batch(db,batch_id='first',issues=issues,records=market_batch_records(tmp_path,sources),
                        receipt={'input_sha256':'a'*64});db.close()
    main=query_market_records(database,issue='0',kind='capture')[0]
    acceptance=tmp_path/'accepted.json'
    from src.market_sqlite_query import market_source_inventory
    acceptance.write_text(json.dumps(dict(state='SQLITE_BATCH_ACCEPTED',batch_id='first',
        issues=issues,database=str(database),source_inventories={main['record_key']:
        market_source_inventory(query_market_records(database,issue='0',source_sha256=digest))})))
    reference=dict(database=str(database),issue='0',batch_id='first',capture_key=main['record_key'],
        record_sha256=main['record_sha256'],source_url=url,acceptance=dict(path=str(acceptance),
        sha256=hashlib.sha256(acceptance.read_bytes()).hexdigest()))
    raw.unlink()
    next_audit=tmp_path/'next.json'
    row=dict(issue='100',slot=2,market='euro',provider_id='123',status='IDENTITY_MISMATCH',
             capture_path=raw.name,source_hashes={raw.name:digest},storage=reference)
    next_audit.write_text(json.dumps([row]))
    following=[dict(issue='100',path=next_audit.name,sha256=hashlib.sha256(next_audit.read_bytes()).hexdigest())]
    copied=list(market_batch_records(tmp_path,following))
    originals=query_market_records(database,issue='0',source_sha256=digest)
    assert len(copied)==len(originals)+2
    assert all(r['issue']=='100' for r in copied)
    assert [r['data']['fields'] for r in copied if r['kind']=='quote']==[
        r['data']['fields'] for r in originals if r['kind']=='quote']
    assert all('reused_source' in r['data'] for r in copied if r.get('source_sha256'))
    db=open_market_database(database)
    db.execute("DELETE FROM market_record WHERE issue='0' AND kind='quote'")
    db.commit();db.close()
    with pytest.raises(ValueError,match='inventory mismatch'):
        list(market_batch_records(tmp_path,following))
    acceptance.write_text('{}')
    with pytest.raises(ValueError,match='acceptance hash'):
        list(market_batch_records(tmp_path,following))
