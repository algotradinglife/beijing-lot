"""Thin offline entry: verified early RAW inputs -> existing N7 candidate builders.

No labels, fitting, new chronology code, or alternate candidate implementation.
Usage: project-python scripts/build_eight_strategy_early_candidates.py CONFIG
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_candidates import build_sleeve_candidates
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure

if __name__ == '__main__':
    cfg = json.loads(Path(sys.argv[1]).read_text())
    root = Path(cfg['repository_root'])
    source = Path(cfg['input'])
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != cfg['input_sha256']:
        raise ValueError('Early input changed')
    data = json.loads(raw)
    if data['probability_version'] != 'ARCHIVED_RAW_MARKET' or data['historical_admission'] is not False:
        raise ValueError('Explicit raw-market diagnostic contract required')
    issues = cfg['issues']
    if len(set(issues)) != len(issues) or not set(issues) <= set(data['issues']):
        raise ValueError('Invalid explicit scope')
    frame = pd.DataFrame(data['rows'])
    out = Path(cfg['output'])
    out.mkdir(parents=True, exist_ok=False)
    (out/'bundles').mkdir()
    closure = implementation_closure(root, ['scripts.build_eight_strategy_early_candidates'],
                                     distributions=['numpy','pandas','scipy'])
    entries = []
    for issue in issues:
        x = frame[frame.issue == issue]
        cuts = {str(s): Cutoff.decision_epoch(issue, data['cutoffs'][issue][str(s)]) for s in x.slot}
        pool = probability_gate_candidates(x, cutoffs=cuts, n=7, **cfg['pool'])
        bundle = build_sleeve_candidates(pool, cutoffs=cuts, **cfg['candidate'])
        path = out/'bundles'/f'{issue}.json.gz'
        path.write_bytes(gzip.compress(json.dumps(bundle, sort_keys=True, allow_nan=False).encode(), mtime=0))
        entries.append(dict(issue=issue, path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            probability_version='ARCHIVED_RAW_MARKET'))
        (out/'progress.txt').write_text(f'{len(entries)} {len(issues)} {issue}\n')
        print('CANDIDATES', issue, bundle['actual_candidate_count'], flush=True)
    verify_implementation_closure(root, closure)
    if hashlib.sha256(source.read_bytes()).hexdigest() != cfg['input_sha256']:
        raise ValueError('Source changed during execution')
    receipt = dict(status='BUNDLE_HASHES_VERIFIED', errors=[], issues=entries,
                   requested_issues=issues, unavailable=[], scope_complete=False,
                   reason='Early candidate preparation; settlement and all-history acceptance pending',
                   config=cfg, implementation=closure, historical_admission=False)
    receipt['seal'] = stable_json_hash(receipt)
    (out/'scope-inventory.json').write_text(json.dumps(receipt, indent=2, allow_nan=False))
