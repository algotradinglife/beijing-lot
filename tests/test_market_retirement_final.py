import pytest
from src.market_retirement_final import verify_final_retirement


def test_scoped_or_missing_review_cannot_authorize_retirement(tmp_path):
    for review in ({}, {'state':'SCOPED_CODEX_REVIEW_PASSED','findings':[]},
                   {'state':'FINAL_RETIREMENT_REVIEW_PASSED','findings':['open defect']}):
        with pytest.raises(ValueError,match='final retirement review required'):
            verify_final_retirement(tmp_path,tmp_path,{},bundle={},review=review)


@pytest.mark.parametrize('relocated', [False, True])
def test_final_gate_composes_checks_and_binds_inputs(tmp_path, monkeypatch, relocated):
    import hashlib
    import json
    import src.market_retirement_final as module
    (tmp_path/'registry').mkdir()
    (tmp_path/'registry/markets-current.json').write_text('{}')
    (tmp_path/'index.json').write_text('{}')
    plan={'batch_id':'b','candidates':[]}
    mapped_target = str(tmp_path / ('markets/raw/verified-responses/' + 'a' * 64 + '.json'))
    if relocated:
        mp = tmp_path / 'path-map.json'
        mp.write_text(json.dumps({'/old/mapped.json': mapped_target}))
        plan['relocation'] = dict(path=mp.name, sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),
                                  original_root='/old')
    documents={'plan':plan,'acceptance':{'batch_id':'b'},'deployment':{},
               'index':{'index_path':str(tmp_path/'index.json')},
               'references':{'protected_paths':['markets/raw/protected.json']}}
    if relocated:
        documents['acceptance'].update(issues=['1'], database=str(tmp_path / 'unused.sqlite'))
        monkeypatch.setattr(module, 'query_market_records', lambda *args, **kwargs: [
            dict(kind='capture', source_sha256='a' * 64, data=dict(
                path='mapped.json', path_aliases=['mapped.json', 'markets/raw/protected.json']))])
    refs={}
    for role,doc in documents.items():
        path=tmp_path/(role+'-proof.json');path.write_text(json.dumps(doc))
        refs[role]={'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    snapshots={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()
               for name in ['registry/markets-current.json','index.json']}
    bundle={role:refs[role] for role in ['plan','acceptance','deployment','index']}
    bundle.update(references=[refs['references']],snapshots=snapshots,program_manifest_sha256='frozen',effective_configuration={},reference_membership=[dict(directory='registry',pattern='*.missing',members={})])
    code={'module':'code'}
    monkeypatch.setattr(module,'implementation_closure',lambda *args: {'files':code})
    calls=[]

    def references(root, actual_plan, *, snapshots, protected_paths):
        assert root==tmp_path and actual_plan==plan
        assert 'registry/markets-current.json' in snapshots
        if relocated:
            assert {'markets/raw/protected.json', mapped_target}.issubset(protected_paths)
        else:
            assert protected_paths == {'markets/raw/protected.json'}
        if relocated:
            assert snapshots['path-map.json'] == plan['relocation']['sha256']
        calls.append('references')
        return {'state':'passed'}

    def consumers(root, **kwargs):
        assert kwargs['index_evidence']==documents['index']
        assert kwargs['program_manifest_sha256']=='frozen'
        calls.append('consumers')
        return {'state':'passed'}

    def content(root, actual_plan, *, acceptance_reference):
        assert acceptance_reference==refs['acceptance']
        calls.append('content')
        return {'state':'passed'}

    monkeypatch.setattr(module,'verify_retirement_reference_exclusion',references)
    monkeypatch.setattr(module,'verify_retirement_collector',consumers)
    monkeypatch.setattr(module,'verify_retirement_content',content)
    review=dict(state='FINAL_RETIREMENT_REVIEW_PASSED',findings=[],implementation_hashes=code,
                bundle_sha256=hashlib.sha256(json.dumps(bundle,sort_keys=True,separators=(',',':')).encode()).hexdigest())
    result=module.verify_final_retirement(tmp_path,tmp_path,plan,bundle=bundle,review=review)
    assert result['state']=='FINAL_RETIREMENT_GATES_PASSED'
    assert calls==['references','consumers','content']
    with pytest.raises(ValueError,match='implementation changed'):
        module.verify_final_retirement(tmp_path,tmp_path,plan,bundle=bundle,review=dict(review,implementation_hashes={}))
    with pytest.raises(ValueError,match='plan mismatch'):
        module.verify_final_retirement(tmp_path,tmp_path,dict(plan,batch_id='other'),bundle=bundle,review=review)
    (tmp_path/'references-proof.json').write_text('{}')
    with pytest.raises(ValueError):
        module.verify_final_retirement(tmp_path,tmp_path,plan,bundle=bundle,review=review)


def test_retirement_command_closure_includes_layout_and_all_gates():
    from pathlib import Path
    from src.temporal_learning.provenance import implementation_closure
    root=Path(__file__).resolve().parents[1]
    files=implementation_closure(root,('scripts.retire_market_sqlite_batch',))['files']
    assert {'src/persistent_data_layout.py','src/market_retirement_final.py',
            'src/market_retirement_gate.py','src/market_retirement_consumers.py',
            'src/market_sqlite_retirement.py','scripts/retire_market_sqlite_batch.py'}.issubset(files)


def test_package_initializer_mutation_invalidates_final_review(tmp_path, monkeypatch):
    import json,hashlib
    import src.market_retirement_final as module
    (tmp_path/'src').mkdir()
    initializer=tmp_path/'src/__init__.py';initializer.write_text('original')
    bundle={}
    review=dict(state='FINAL_RETIREMENT_REVIEW_PASSED',findings=[],
        bundle_sha256=hashlib.sha256(json.dumps(bundle,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        implementation_hashes={'src/worker.py':'code','src/__init__.py':hashlib.sha256(b'original').hexdigest()})
    monkeypatch.setattr(module,'implementation_closure',lambda *args:{'files':{'src/worker.py':'code'}})
    with pytest.raises(ValueError,match='complete retirement bundle'):
        module.verify_final_retirement(tmp_path,tmp_path,{},bundle=bundle,review=review)
    initializer.write_text('changed')
    with pytest.raises(ValueError,match='implementation changed'):
        module.verify_final_retirement(tmp_path,tmp_path,{},bundle=bundle,review=review)
