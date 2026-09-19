import hashlib
import pytest
from src.market_sqlite_retirement import plan_market_raw_retirement


def test_retirement_candidates_exclude_shared_and_verify_bytes(tmp_path):
    raw=tmp_path/'markets/raw';raw.mkdir(parents=True)
    path=raw/'a.json';path.write_bytes(b'{}')
    item=dict(kind='capture',source_sha256=hashlib.sha256(b'{}').hexdigest(),
              source_url='https://1x2d.titan007.com/1.js',data={'path':'markets/raw/a.json'})
    result=plan_market_raw_retirement(tmp_path,[item,item],protected_paths=[])
    assert len(result['candidates'])==1 and path.exists()
    result=plan_market_raw_retirement(tmp_path,[item],protected_paths=['markets/raw/a.json'])
    assert not result['candidates']
    assert result['excluded'][0]['reason']=='ACTIVE_OR_SHARED_REFERENCE'
    path.write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        plan_market_raw_retirement(tmp_path,[item],protected_paths=[])
    outside=dict(item,data={'path':'fundamentals/raw/a.json'})
    assert not plan_market_raw_retirement(tmp_path,[outside],protected_paths=[])['candidates']
    for aliases in ('markets/raw/a.json', [None], ['']):
        invalid=dict(item,data={'path':'markets/raw/a.json','path_aliases':aliases})
        with pytest.raises(ValueError,match='invalid capture aliases'):
            plan_market_raw_retirement(tmp_path,[invalid],protected_paths=[])


def test_each_alias_has_independent_reference_protection(tmp_path):
    raw=tmp_path/'markets/raw';raw.mkdir(parents=True)
    aliases=['markets/raw/a.json','markets/raw/b.json']
    for name in aliases:(tmp_path/name).write_bytes(b'{}')
    item=dict(kind='capture',source_sha256=hashlib.sha256(b'{}').hexdigest(),
              source_url='https://1x2d.titan007.com/1.js',data={'path':aliases[0],'path_aliases':aliases})
    result=plan_market_raw_retirement(tmp_path,[item],protected_paths=[aliases[1]])
    assert [r['path'] for r in result['candidates']]==[aliases[0]]
    assert [r['path'] for r in result['excluded']]==[aliases[1]]
    assert all((tmp_path/name).exists() for name in aliases)


def test_reference_inventory_protects_retries_and_unconverted_peers():
    from src.market_sqlite_retirement import market_reference_paths
    index={'euro:1':{'selected':{'path':'selected'},'attempts':[{'path':'retry'}]}}
    rows=[{'capture_path':'capture','source_hashes':{'capture':'a','peer':'b'}}]
    assert market_reference_paths([index],rows)==['capture','peer','retry','selected']
    with pytest.raises(ValueError,match='path missing'):
        market_reference_paths([{'euro:1':{'attempts':[{}]}}],[])
    with pytest.raises(ValueError,match='references missing'):
        market_reference_paths([], [{}])
    with pytest.raises(ValueError,match='source bindings'):
        market_reference_paths([], [{'capture_path':'other','source_hashes':{'capture':'a'}}])


def test_reference_inventory_releases_only_verified_sqlite_references(monkeypatch):
    from src.market_sqlite_retirement import market_reference_paths
    import src.fundamentals_market_history as history
    calls=[]
    def verify(reference,key):
        calls.append((reference['path'],key))
        if reference['storage']=='bad':
            raise ValueError('storage acceptance hash mismatch')
        return {'status':200}
    monkeypatch.setattr(history,'verify_selected_market_receipt',verify)
    index={'euro:1':{'selected':{'path':'shared','storage':'accepted'},
                     'attempts':[{'path':'retry'}]}}
    assert market_reference_paths([index],[])==['retry']
    assert calls==[('shared','euro:1')]
    # Another consumer or issue still using raw bytes retains the same file.
    second={'euro:2':{'selected':{'path':'shared'}}}
    assert market_reference_paths([index,second],[])==['retry','shared']
    assert market_reference_paths([index],[{'source_hashes':{'shared':'hash'}}])==['retry','shared']
    index['euro:1']['selected']['storage']='bad'
    with pytest.raises(ValueError,match='acceptance hash'):
        market_reference_paths([index],[])


def test_unconverted_audit_releases_verified_capture_but_protects_peer(monkeypatch):
    from src.market_sqlite_retirement import market_reference_paths
    import src.fundamentals_market_history as history
    calls=[]
    def verify(reference,key):
        calls.append((reference,key))
        if reference['storage']=='invalid':
            raise ValueError('invalid storage binding')
    monkeypatch.setattr(history,'verify_selected_market_receipt',verify)
    row=dict(market='euro',provider_id='123',capture_path='old.json',
             source_hashes={'old.json':'a'*64,'peer.json':'b'*64},storage='accepted')
    assert market_reference_paths([],[row])==['peer.json']
    assert calls[0][1]=='euro:123'
    assert calls[0][0]['sha256']=='a'*64
    row['storage']='invalid'
    with pytest.raises(ValueError,match='invalid storage'):
        market_reference_paths([],[row])
    row.pop('capture_path')
    with pytest.raises(ValueError,match='capture path missing'):
        market_reference_paths([],[row])


def test_retirement_executor_gates_preflight_and_resume(tmp_path):
    from src.market_sqlite_retirement import execute_market_raw_retirement
    raw=tmp_path/'markets/raw';raw.mkdir(parents=True)
    audit=tmp_path/'audits/market-sqlite/b';audit.mkdir(parents=True)
    (tmp_path/'runtime/state').mkdir(parents=True)
    captures=[]
    for name in ('a.json','b.json'):
        (raw/name).write_bytes(b'{}')
        captures.append(dict(kind='capture',source_sha256=hashlib.sha256(b'{}').hexdigest(),
            source_url='https://1x2d.titan007.com/1.js',data={'path':'markets/raw/'+name}))
    plan=plan_market_raw_retirement(tmp_path,captures,protected_paths=[])
    journal=audit/'retirement.json'
    def reject(plan):raise ValueError('review pending')
    with pytest.raises(ValueError,match='review pending'):
        execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=reject)
    assert (raw/'a.json').exists() and not journal.exists()
    (raw/'b.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=lambda p:None)
    assert (raw/'a.json').exists()
    (raw/'b.json').write_bytes(b'{}')
    result=execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=lambda p:None)
    assert result['removed_files']==2 and not list(raw.iterdir())
    assert execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=lambda p:None)==result
    with pytest.raises(ValueError,match='plan mismatch'):
        execute_market_raw_retirement(tmp_path,dict(plan,candidates=[]),journal_path=journal,verify_acceptance=lambda p:None)


def test_retirement_resumes_after_unlink_before_completion_journal(tmp_path,monkeypatch):
    import json
    import src.market_storage as storage
    from src.market_sqlite_retirement import execute_market_raw_retirement
    raw=tmp_path/'markets/raw';raw.mkdir(parents=True)
    audit=tmp_path/'audits/market-sqlite/b';audit.mkdir(parents=True)
    (tmp_path/'runtime/state').mkdir(parents=True)
    path=raw/'a.json';path.write_bytes(b'{}')
    capture=dict(kind='capture',source_sha256=hashlib.sha256(b'{}').hexdigest(),
                 source_url='https://1x2d.titan007.com/1.js',data={'path':'markets/raw/a.json'})
    plan=plan_market_raw_retirement(tmp_path,[capture],protected_paths=[])
    journal=audit/'journal.json'
    publish=storage._publish_json
    def interrupt(path,value):
        if 'REMOVED' in value['entries'].values():raise OSError('simulated power interruption')
        publish(path,value)
    monkeypatch.setattr(storage,'_publish_json',interrupt)
    with pytest.raises(OSError,match='power interruption'):
        execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=lambda p:None)
    assert not path.exists()
    assert json.loads(journal.read_text())['entries']['markets/raw/a.json']=='DELETE_INTENT'
    monkeypatch.setattr(storage,'_publish_json',publish)
    result=execute_market_raw_retirement(tmp_path,plan,journal_path=journal,verify_acceptance=lambda p:None)
    assert result['removed_files']==1
    assert json.loads(journal.read_text())['entries']['markets/raw/a.json']=='REMOVED'


def test_decision_replay_dependencies_remain_protected():
    from src.market_sqlite_retirement import market_reference_paths
    decision=dict(capture_path='capture',roster_path='roster',peer_path='peer',
                  files={'capture':'a','roster':'b','peer':'c','independent':'d'})
    assert market_reference_paths([],[],replay_decisions=[decision])==[
        'capture','independent','peer','roster']
    decision['files'].pop('peer')
    with pytest.raises(ValueError,match='decision replay source bindings'):
        market_reference_paths([],[],replay_decisions=[decision])
