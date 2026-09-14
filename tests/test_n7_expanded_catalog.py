"""Frozen candidate catalog contracts and post-freeze label access guard."""
import gzip
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest
import src.temporal_learning
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('mutation',['none','bundle','seal','scope'])
def test_expanded_catalog(tmp_path,monkeypatch,mutation):
    candidates=tmp_path/'candidates';candidates.mkdir()
    bundle=candidates/'001.json.gz';bundle.write_bytes(gzip.compress(b'{"issue":"001"}'))
    candidate=dict(issues=['001'],requested_issues=['001'],unavailable={},source_hashes={},pool_hashes={},
                   bundle_hashes={str(bundle):hashlib.sha256(bundle.read_bytes()).hexdigest()},
                   implementation={},historical_admission=False)
    wrapper=dict(receipt=candidate,seal=stable_json_hash(candidate))
    if mutation=='seal':wrapper['seal']='bad'
    cp=candidates/'candidate-manifest.json';cp.write_text(json.dumps(wrapper))
    receipt=dict(issues=['002'] if mutation=='scope' else ['001'],files={'candidates/candidate-manifest.json':hashlib.sha256(cp.read_bytes()).hexdigest()})
    (tmp_path/'batch-receipt.json').write_text(json.dumps(receipt))
    if mutation=='bundle':bundle.write_bytes(b'changed')
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    monkeypatch.setattr(sys,'argv',['catalog',str(tmp_path),str(Path.cwd())])
    script='scripts/catalog_n7_expanded_batch.py'
    if mutation!='none':
        with pytest.raises(ValueError):runpy.run_path(script,run_name='__main__')
        assert not (tmp_path/'catalog.json').exists()
    else:
        runpy.run_path(script,run_name='__main__')
        c=json.loads((tmp_path/'catalog.json').read_text())
        assert c['requested_issues']==['001'] and c['issues'][0]['issue']=='001'
        with pytest.raises(ValueError):runpy.run_path(script,run_name='__main__')


def test_target_labels_cannot_open_without_complete_freeze(tmp_path,monkeypatch):
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(study=str(tmp_path))))
    monkeypatch.setattr(sys,'argv',['labels',str(config)])
    with pytest.raises(FileNotFoundError,match='all-plans-frozen'):
        runpy.run_path('scripts/prepare_n7_expanded_labels.py',run_name='__main__')
    assert not (tmp_path/'settlement-inputs').exists()


def test_changed_plan_content_stops_before_outcome_access(tmp_path,monkeypatch):
    batch=tmp_path/'batch/allocations';batch.mkdir(parents=True)
    cat=tmp_path/'catalog.json';cat.write_text('{"requested_issues":["001"]}')
    plan=batch/'predictions.csv';plan.write_text('original')
    frozen=dict(config=dict(catalog=str(cat),catalog_sha256=hashlib.sha256(cat.read_bytes()).hexdigest()),
                files={'predictions.csv':hashlib.sha256(plan.read_bytes()).hexdigest()},source_hashes={},implementation={})
    fp=batch/'plans-frozen.json';fp.write_text(json.dumps(frozen))
    rp=batch/'prediction-replay.json';rp.write_text(json.dumps(dict(status='PASS',freeze_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),implementation={})))
    master=dict(status='ALL_PREDICTIONS_FROZEN_BEFORE_TARGET_SETTLEMENT',requested_issues=['001'],
                files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [fp,rp]})
    (tmp_path/'all-plans-frozen.json').write_text(json.dumps(master))
    plan.write_text('changed after frozen receipt')
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(study=str(tmp_path),repository_root=str(Path.cwd()))))
    monkeypatch.setattr(sys,'argv',['labels',str(config)])
    with pytest.raises(ValueError,match='allocation content changed'):
        runpy.run_path('scripts/prepare_n7_expanded_labels.py',run_name='__main__')
    assert not (tmp_path/'settlement-inputs').exists()


def test_changed_upstream_closure_stops_before_outcomes(tmp_path,monkeypatch):
    from src.temporal_learning import implementation_closure
    root=tmp_path/'repo';root.mkdir();module=root/'candidate.py';module.write_text('VALUE=1\n')
    closure=implementation_closure(root,['candidate'])
    batch=tmp_path/'batch/allocations';batch.mkdir(parents=True)
    candidates=batch.parent/'candidates';candidates.mkdir()
    c=dict(implementation=closure)
    (candidates/'candidate-manifest.json').write_text(json.dumps(dict(receipt=c,seal=stable_json_hash(c))))
    cat=tmp_path/'catalog.json';cat.write_text('{"requested_issues":["001"]}')
    frozen=dict(config=dict(catalog=str(cat),catalog_sha256=hashlib.sha256(cat.read_bytes()).hexdigest()),
                files={},source_hashes={},implementation={})
    fp=batch/'plans-frozen.json';fp.write_text(json.dumps(frozen))
    rp=batch/'prediction-replay.json';rp.write_text(json.dumps(dict(status='PASS',freeze_sha256=hashlib.sha256(fp.read_bytes()).hexdigest(),implementation={})))
    master=dict(status='ALL_PREDICTIONS_FROZEN_BEFORE_TARGET_SETTLEMENT',requested_issues=['001'],
                files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [fp,rp]})
    (tmp_path/'all-plans-frozen.json').write_text(json.dumps(master))
    module.write_text('VALUE=2\n')
    config=tmp_path/'config.json';config.write_text(json.dumps(dict(study=str(tmp_path),repository_root=str(root))))
    monkeypatch.setattr(sys,'argv',['labels',str(config)])
    with pytest.raises(ValueError,match='implementation closure differs'):
        runpy.run_path('scripts/prepare_n7_expanded_labels.py',run_name='__main__')
    assert not (tmp_path/'settlement-inputs').exists()
