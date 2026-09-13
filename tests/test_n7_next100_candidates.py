"""Exercise the actual CLI when an entire requested batch is unavailable."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from src.temporal_learning.core import stable_json_hash

ROOT = Path(__file__).resolve().parents[1]


def test_empty_prediction_batch_preserves_requested_scope(tmp_path):
    pred = tmp_path / 'predictions.json'
    issues=['101121']+[str(101122+i) for i in range(98)]+['110513']
    scope=tmp_path/'scope.json';scope.write_text(json.dumps(dict(issues=issues)))
    reference=tmp_path/'reference.json';reference.write_text('{}')
    pred.write_text(json.dumps(dict(rows=[],models={},issue_order=issues,
        publication_coverage=[dict(issue=i,status='NOT_PUBLISHED') for i in issues],
        source_hashes={},historical_admission=False)))
    cfg=tmp_path/'config.json'
    config=json.loads((ROOT/'config/n7_next100_435.json').read_text())
    config['model']['reference_model_sha256']=hashlib.sha256(reference.read_bytes()).hexdigest()
    cfg.write_text(json.dumps(config))
    out = tmp_path / 'candidates'
    completed = subprocess.run([sys.executable,'-m','scripts.build_n7_next100_candidates',
        '--predictions',str(pred),'--predictions-sha256',hashlib.sha256(pred.read_bytes()).hexdigest(),
        '--config',str(cfg),'--config-sha256',hashlib.sha256(cfg.read_bytes()).hexdigest(),
        '--reference-model',str(reference),'--scope-manifest',str(scope),
        '--scope-sha256',hashlib.sha256(scope.read_bytes()).hexdigest(),'--repository-root',str(ROOT),'--output',str(out),'--workers','1'],
        cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert completed.returncode == 0, completed.stderr
    saved = json.loads((out/'candidate-manifest.json').read_text())
    r = saved['receipt']
    assert saved['seal'] == stable_json_hash(r)
    assert r['requested_issues'] == issues and r['issues'] == []
    assert r['unavailable'] == {i:'NOT_PUBLISHED' for i in issues}
    assert r['bundle_hashes'] == {} and not r['full_scope_available']
    assert not (out/'plans-frozen.json').exists()
    truncated=json.loads(pred.read_text());truncated['issue_order']=issues[:-1]
    pred.write_text(json.dumps(truncated))
    command=list(completed.args)
    command[command.index('--predictions-sha256')+1]=hashlib.sha256(pred.read_bytes()).hexdigest()
    command[command.index('--output')+1]=str(tmp_path/'truncated')
    rejected=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert rejected.returncode != 0
    assert 'declared study scope' in rejected.stderr
    assert not (tmp_path/'truncated'/'candidate-manifest.json').exists()
