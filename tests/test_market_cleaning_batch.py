"""Market preparation consumes only explicit rosters and transport receipts."""
import hashlib
import json
import pytest
from src.market_cleaning_batch import prepare_market_batch
from tests.test_nowscore_settlement import page


def test_market_batch_without_fundamentals_and_corruption(tmp_path, monkeypatch):
    from src import market_cleaning_batch as module
    raw = page(8)
    (tmp_path/'roster').write_bytes(raw)
    (tmp_path/'capture').write_text('saved transport')
    roster_hash = hashlib.sha256(raw).hexdigest()
    capture_hash = hashlib.sha256((tmp_path/'capture').read_bytes()).hexdigest()
    native = {'issues': [{'issue': '25053'}]}
    (tmp_path/'inventory.json').write_text(json.dumps(native))
    scope = {'issue':'25053','roster_path':'roster','roster_sha256':roster_hash,
             'fixtures':[{'issue':'25053','slot':1,'provider_id':'123'}], 'quarantined_slots':[]}
    plan = {'inventory_path':'inventory.json',
            'inventory_sha256':hashlib.sha256((tmp_path/'inventory.json').read_bytes()).hexdigest(),
            'reused_issues':[scope], 'batches':[]}
    (tmp_path/'plan.json').write_text(json.dumps(plan))
    rows = [{'slot':1,'market':m,'provider_id':'123','path':'capture',
             'sha256':capture_hash,'state':'CAPTURED','status':200} for m in ('euro','total')]
    receipt = {'issue':'25053','state':'CAPTURE_ATTEMPTED','rows':rows}
    rp = tmp_path/'25053-receipt.json'
    rp.write_text(json.dumps(receipt))
    monkeypatch.setattr(module, 'read_response', lambda p: ({},p.read_bytes()))
    verified = []
    monkeypatch.setattr(module, 'verify_market_receipt', lambda p,k,h: verified.append((k,h)))
    result = prepare_market_batch(tmp_path,'plan.json','.', 'output')
    assert result['issues'] == ['25053']
    assert len(verified) == 2
    output = json.loads((tmp_path/'output/scope.json').read_text())
    assert output['fixtures'][0]['decision_ts'] == '2025-05-13T15:25:00+00:00'
    assert output['inventories'][0]['original_fixture_count'] == 1
    with pytest.raises(ValueError, match='already exists'):
        prepare_market_batch(tmp_path,'plan.json','.', 'output')
    plan['reused_issues'][0]['fixtures'] *= 2
    (tmp_path/'plan.json').write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='Duplicate declared'):
        prepare_market_batch(tmp_path,'plan.json','.', 'duplicate-scope')
    plan['reused_issues'][0]['fixtures'].pop()
    (tmp_path/'plan.json').write_text(json.dumps(plan))
    receipt['rows'].pop()
    rp.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match='coverage'):
        prepare_market_batch(tmp_path,'plan.json','.', 'missing')
    assert not (tmp_path/'missing').exists()
    (tmp_path/'roster').write_bytes(raw+b'changed')
    with pytest.raises(ValueError, match='Roster hash'):
        prepare_market_batch(tmp_path,'plan.json','.', 'corrupt')


def test_partial_anomaly_ledger_preserves_evidence(tmp_path):
    from src.market_cleaning_batch import snapshot_market_anomalies
    audit = tmp_path/'audit'
    audit.mkdir()
    rows = [dict(issue='110509',slot=1,status='IDENTITY_MISMATCH',source_ids=['1','2'],rows=[]),
            dict(issue='110509',slot=2,status='QUOTES_PRIOR_DIAGNOSTIC')]
    p = audit/'110509.json'
    p.write_text(json.dumps(rows))
    result = snapshot_market_anomalies(audit,tmp_path/'ledger.json')
    assert result['state'] == 'PARTIAL_DIAGNOSTIC_SNAPSHOT'
    assert result['completed_issue_files'] == 1
    assert result['rows'][0]['source_ids'] == ['1','2']
    assert len(result['rows']) == 1
    assert result['input_hashes']['110509.json'] == hashlib.sha256(p.read_bytes()).hexdigest()
    rows[0]['issue'] = '110510'
    p.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match='identity mismatch'):
        snapshot_market_anomalies(audit,tmp_path/'ledger.json')


def test_decision_replay_rejects_changed_evidence_and_duplicates(tmp_path, monkeypatch):
    from src.temporal_learning import provenance
    monkeypatch.setattr(provenance, "implementation_closure", lambda *args: {"files": {}})
    from src.market_cleaning_batch import replay_market_decisions
    evidence = tmp_path/'raw'
    evidence.write_bytes(b'changed')
    decision = dict(issue='110512',slot=87,market='euro',roster_path='raw',capture_path='raw',files={'raw':'0'*64})
    p = tmp_path/'decisions.json'
    p.write_text(json.dumps([decision]))
    with pytest.raises(ValueError,match='evidence hash mismatch'):
        replay_market_decisions(tmp_path,'decisions.json','output.json')
    assert not (tmp_path/'output.json').exists()
    unbound=dict(decision,files={})
    p.write_text(json.dumps([unbound]))
    with pytest.raises(ValueError,match='must be hash-bound'):
        replay_market_decisions(tmp_path,'decisions.json','output.json')
    p.write_text(json.dumps([decision,decision]))
    with pytest.raises(ValueError,match='decision identities'):
        replay_market_decisions(tmp_path,'decisions.json','output.json')


def test_merge_market_audits_verifies_disjoint_exact_rows(tmp_path):
    from src.market_cleaning_batch import merge_market_audits
    entries=[]
    for issue in ('110508','110509'):
        directory=tmp_path/issue
        directory.mkdir()
        row=dict(issue=issue,slot=1,market='euro',provider_id='123',status='QUOTES_PRIOR_DIAGNOSTIC')
        p=directory/(issue+'.json')
        records=[row,dict(row,market='total')]
        p.write_text(json.dumps([dict(r,rows=[],source_hashes={}) for r in records]))
        scope=directory/'scope.json'
        scope.write_text(json.dumps({'fixtures':[{'issue':issue,'slot':1,'provider_id':'123'}]}))
        summary=dict(issues=[dict(issue=issue)],rows=records,fixture_market_rows=2,fixture_count=1,source_hashes={str(scope.relative_to(tmp_path)):hashlib.sha256(scope.read_bytes()).hexdigest()},
                     output_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()},historical_admission=False)
        sp=directory/'summary.json'
        sp.write_text(json.dumps(summary))
        entries.append(dict(scope_path=str(scope.relative_to(tmp_path)),path=str(sp.relative_to(tmp_path)),sha256=hashlib.sha256(sp.read_bytes()).hexdigest()))
    result=merge_market_audits(tmp_path,entries,'merged.json')
    assert result['issues']==['110508','110509']
    assert result['fixture_market_rows']==4
    assert result['historical_admission'] is False
    with pytest.raises(ValueError,match='Overlapping'):
        merge_market_audits(tmp_path,[entries[0],entries[0]],'duplicate.json')
    sp=tmp_path/'110509/summary.json'
    source=tmp_path/'110509/110509.json'
    changed=json.loads(sp.read_text()); detail=json.loads(source.read_text())
    for r in changed['rows']: r['provider_id']='999'
    for r in detail: r['provider_id']='999'
    source.write_text(json.dumps(detail)); changed['output_hashes'][source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
    sp.write_text(json.dumps(changed)); entries[1]['sha256']=hashlib.sha256(sp.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='fixture market coverage'):
        merge_market_audits(tmp_path,entries,'wrong-provider.json')
    scope=tmp_path/'110509/scope.json'
    scope.write_text(json.dumps({'fixtures':[{'issue':'110509','slot':1,'provider_id':'123'},{'issue':'110509','slot':2,'provider_id':'456'}]}))
    sp=tmp_path/'110509/summary.json'
    changed=json.loads(sp.read_text())
    changed['source_hashes']['110509/scope.json']=hashlib.sha256(scope.read_bytes()).hexdigest()
    sp.write_text(json.dumps(changed))
    entries[1]['sha256']=hashlib.sha256(sp.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='fixture market coverage'):
        merge_market_audits(tmp_path,entries,'incomplete.json')
    (tmp_path/'110509/110509.json').write_text('[]')
    with pytest.raises(ValueError,match='output hash'):
        merge_market_audits(tmp_path,entries,'corrupt.json')


def test_apply_decisions_preserves_unaffected_rows(tmp_path,monkeypatch):
    from src import market_cleaning_batch as module
    from src.temporal_learning import provenance
    monkeypatch.setattr(provenance,'implementation_closure',lambda *a: {'files':{}})
    (tmp_path/'data/derived').mkdir(parents=True)
    a=tmp_path/'audit'; a.mkdir()
    rows=[dict(issue='110512',slot=s,market='euro',status='IDENTITY_MISMATCH',source_hashes={'raw/roster/response.json':'hash'},provider_id='123',cutoff_utc='2011-05-14T12:00:00Z',roster_ids=['1','2'],original_status='完场') for s in (1,2)]
    p=a/'110512.json';p.write_text(json.dumps(rows))
    summary=dict(issues=[dict(issue='110512',fixture_count=2)],output_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()},source_hashes={},implementation_hashes={})
    (a/'summary.json').write_text(json.dumps(summary))
    (tmp_path/'decisions.json').write_text(json.dumps([dict(issue='110512',slot=1,market='euro',roster_path='raw/roster/response.json')]))
    corrected=dict(rows[0],status='QUOTES_PRIOR_DIAGNOSTIC')
    monkeypatch.setattr(module,'replay_market_decisions',lambda *a:[corrected])
    result=module.apply_market_decisions(tmp_path,'audit','decisions.json','corrected')
    actual=json.loads((tmp_path/'corrected/110512.json').read_text())
    assert actual==[corrected,rows[1]]
    assert result['counts']=={'QUOTES_PRIOR_DIAGNOSTIC':1,'IDENTITY_MISMATCH':1}
    assert p.read_text()==json.dumps(rows)
    with pytest.raises(ValueError,match='already exists'):
        module.apply_market_decisions(tmp_path,'audit','decisions.json','corrected')

    monkeypatch.setattr(module,'replay_market_decisions',lambda *a:[dict(corrected,provider_id='999')])
    with pytest.raises(ValueError,match='frozen fixture context'):
        module.apply_market_decisions(tmp_path,'audit','decisions.json','changed-provider')
    monkeypatch.setattr(module,'replay_market_decisions',lambda *a:[dict(corrected,source_hashes={})])
    with pytest.raises(ValueError,match='frozen roster evidence'):
        module.apply_market_decisions(tmp_path,'audit','decisions.json','changed-roster')

    del rows[0]['roster_ids']
    p.write_text(json.dumps(rows))
    summary['output_hashes'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (a/'summary.json').write_text(json.dumps(summary))
    monkeypatch.setattr(module,'read_response',lambda *a: ({},b'roster'))
    monkeypatch.setattr(module,'parse_page',lambda *a: [dict(slot=1,native_match_id='123',home_id='1',away_id='2')])
    monkeypatch.setattr(module,'replay_market_decisions',lambda *a:[corrected])
    result=module.apply_market_decisions(tmp_path,'audit','decisions.json','missing-ids')
    assert result['counts']['QUOTES_PRIOR_DIAGNOSTIC']==1
    monkeypatch.setattr(module,'parse_page',lambda *a: [dict(slot=1,native_match_id='123',home_id='9',away_id='2')])
    with pytest.raises(ValueError,match='frozen roster identity'):
        module.apply_market_decisions(tmp_path,'audit','decisions.json','wrong-ids')
