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
    pred.write_text(json.dumps(dict(rows=[],models={},issue_order=['001','002'],
        publication_coverage=[dict(issue='001',status='NOT_PUBLISHED'),
                              dict(issue='002',status='PUBLISHED_DETAIL_VERIFIED')],
        source_hashes={},historical_admission=False)))
    cfg = ROOT / 'config/n7_next100_435.json'
    out = tmp_path / 'candidates'
    completed = subprocess.run([sys.executable,'-m','scripts.build_n7_next100_candidates',
        '--predictions',str(pred),'--predictions-sha256',hashlib.sha256(pred.read_bytes()).hexdigest(),
        '--config',str(cfg),'--config-sha256',hashlib.sha256(cfg.read_bytes()).hexdigest(),
        '--repository-root',str(ROOT),'--output',str(out),'--workers','1'],
        cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert completed.returncode == 0, completed.stderr
    saved = json.loads((out/'candidate-manifest.json').read_text())
    r = saved['receipt']
    assert saved['seal'] == stable_json_hash(r)
    assert r['requested_issues'] == ['001','002'] and r['issues'] == []
    assert r['unavailable'] == {'001':'NOT_PUBLISHED','002':'NO_USABLE_MARKET_PROBABILITIES'}
    assert r['bundle_hashes'] == {} and not r['full_scope_available']
    assert not (out/'plans-frozen.json').exists()
