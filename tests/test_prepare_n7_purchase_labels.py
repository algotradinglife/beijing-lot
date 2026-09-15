"""Entry contract tests; synthetic replay receipts never authorize real labels."""
import gzip
import hashlib
import json
import runpy
import sys
from pathlib import Path
import pytest


@pytest.fixture
def entry_config(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    cfg = {'repository_root': str(root), 'original_issues': ['001'],
           'roster_directory': str(tmp_path / 'rosters'), 'output': str(tmp_path / 'output')}
    fixture = dict(issue='001', slot=1, provider_id='42', handicap=0)
    bundle = tmp_path / 'bundle.json.gz'
    bundle.write_bytes(gzip.compress(json.dumps(dict(issue='001', expanded_pool={'fixtures': [fixture]})).encode()))
    plan = tmp_path / 'plan.rds'
    plan.write_bytes(b'synthetic identity only; no real plan claim')
    plan_hash = hashlib.sha256(plan.read_bytes()).hexdigest()
    main = dict(status='FROZEN_NOT_SETTLED', scope=['001'], policies=[{'id': 'JOINT'}],
                closure={}, code={}, bindings={'001': {'file': plan.name, 'sha256': plan_hash, 'source_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest()}})
    for name in ('main', 'structure'):
        payload = dict(main)
        if name == 'structure':
            payload['parent_receipt_sha256'] = cfg['main']['sha256']
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(payload))
        cfg[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    payloads = {
        'main_replay': dict(status='PASS', receipt_sha256=cfg['main']['sha256'], issues=1, allocations=1),
        'structure_replay': dict(status='PASS', receipt_sha256=cfg['structure']['sha256'], issues=1, allocations=1),
        'gates': dict(status='PASS', main_receipt_sha256=cfg['main']['sha256'], structure_receipt_sha256=cfg['structure']['sha256'], gates=1),
        'catalog': {'issues': [dict(issue='001', path=str(bundle), sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())]},
        'inputs': {'roster_bindings': {}}}
    for name, payload in payloads.items():
        path = tmp_path / (name + '.json'); path.write_text(json.dumps(payload))
        cfg[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    main_path = Path(cfg['main']['path'])
    main_receipt = json.loads(main_path.read_bytes())
    main_receipt['catalog_sha256'] = cfg['catalog']['sha256']
    main_path.write_text(json.dumps(main_receipt))
    cfg['main']['sha256'] = hashlib.sha256(main_path.read_bytes()).hexdigest()
    structure_path = Path(cfg['structure']['path'])
    structure = json.loads(structure_path.read_bytes())
    structure['parent_receipt_sha256'] = cfg['main']['sha256']
    structure_path.write_text(json.dumps(structure))
    cfg['structure']['sha256'] = hashlib.sha256(structure_path.read_bytes()).hexdigest()
    for name in ('main_replay', 'structure_replay', 'gates'):
        path = Path(cfg[name]['path']); data = json.loads(path.read_bytes())
        if name == 'gates':
            data.update(main_receipt_sha256=cfg['main']['sha256'], structure_receipt_sha256=cfg['structure']['sha256'])
        else:
            data['receipt_sha256'] = cfg[name.removesuffix('_replay')]['sha256']
        path.write_text(json.dumps(data)); cfg[name]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    labels = tmp_path / 'labels.csv'
    labels.write_text('issue,slot,provider_id,handicap,home,away,actual_home,actual_away\n001,1,42,0,H,A,1,0\n')
    cfg['old_labels'] = {'path': str(labels), 'sha256': hashlib.sha256(labels.read_bytes()).hexdigest()}
    # Shared closure semantics are tested by temporal_learning's own suite.
    monkeypatch.setattr('src.temporal_learning.verify_implementation_closure', lambda *args: None)
    return root, cfg


def test_entry_binds_original_outcome_and_sources(entry_config, tmp_path, monkeypatch):
    root, cfg = entry_config
    path = tmp_path / 'config.json'; path.write_text(json.dumps(cfg))
    monkeypatch.setattr(sys, 'argv', ['entry', str(path)])
    runpy.run_path(str(root / 'scripts/prepare_n7_purchase_labels.py'), run_name='__main__')
    output = Path(cfg['output'])
    rows = json.loads((output / 'labels.json').read_bytes())
    assert rows[0]['issue'] == '001' and rows[0]['actual_home'] == 1
    assert rows[0]['provider_id'] == '42' and rows[0]['cohort'] == 'ORIGINAL'
    receipt = json.loads((output / 'receipt.json').read_bytes())
    assert receipt['files']['labels.json'] == hashlib.sha256((output / 'labels.json').read_bytes()).hexdigest()
    assert receipt['historical_admission'] is False


def test_incomplete_replay_fails_before_opening_labels(entry_config, tmp_path, monkeypatch):
    root, cfg = entry_config
    proof = Path(cfg['main_replay']['path'])
    data = json.loads(proof.read_bytes()); data['allocations'] = 0
    proof.write_text(json.dumps(data)); cfg['main_replay']['sha256'] = hashlib.sha256(proof.read_bytes()).hexdigest()
    Path(cfg['old_labels']['path']).unlink()
    path = tmp_path / 'config.json'; path.write_text(json.dumps(cfg))
    monkeypatch.setattr(sys, 'argv', ['entry', str(path)])
    with pytest.raises(ValueError, match='Incomplete independent allocation replay'):
        runpy.run_path(str(root / 'scripts/prepare_n7_purchase_labels.py'), run_name='__main__')
    assert not Path(cfg['output']).exists()


@pytest.mark.parametrize('case', ['replacement_catalog', 'damaged_bundle'])
def test_source_change_fails_before_opening_labels(entry_config, tmp_path, monkeypatch, case):
    root, cfg = entry_config
    catalog_path = Path(cfg['catalog']['path'])
    catalog = json.loads(catalog_path.read_bytes())
    if case == 'replacement_catalog':
        catalog['note'] = 'different bytes with identical issue IDs'
        catalog_path.write_text(json.dumps(catalog))
        cfg['catalog']['sha256'] = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
        expected = 'Catalog differs from frozen purchase source'
    else:
        Path(catalog['issues'][0]['path']).write_bytes(b'corrupt')
        expected = 'Diagnostic bundle changed'
    Path(cfg['old_labels']['path']).unlink()
    path = tmp_path / 'config.json'; path.write_text(json.dumps(cfg))
    monkeypatch.setattr(sys, 'argv', ['entry', str(path)])
    with pytest.raises(ValueError, match=expected):
        runpy.run_path(str(root / 'scripts/prepare_n7_purchase_labels.py'), run_name='__main__')
    assert not Path(cfg['output']).exists()
