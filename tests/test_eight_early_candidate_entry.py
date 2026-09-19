"""Offline entry contract: native candidate universe and source-tamper rejection."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('tamper', [False, True])
def test_early_candidate_entry(tmp_path, tamper):
    root = Path(__file__).resolve().parents[1]
    issue = '100101'
    rows = [dict(issue=issue, slot=s, provider_id=f'00{s}', handicap=0,
                 p_W=.6, p_D=.25, p_L=.15, q_W=.6, q_D=.25, q_L=.15)
            for s in range(1, 8)]
    source = tmp_path/'input.json'
    source.write_text(json.dumps(dict(rows=rows, issues=[issue], historical_admission=False,
        probability_version='ARCHIVED_RAW_MARKET',
        cutoffs={issue:{str(s):'2010-01-01T00:00:00Z' for s in range(1,8)}})))
    cfg = dict(repository_root=str(root), input=str(source),
        input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), issues=[issue],
        output=str(tmp_path/'output'), pool=dict(depth=4, tradeoffs=['PROBABILITY']),
        candidate=dict(candidate_count=3, seed=42400, maximum_attempts=10,
            frontier_points=[['F80_R35',.8,-.35]], solver_seconds=.1,
            solver_relative_gap=.001, solver_feasibility_tolerance=1e-9,
            budget_cny=1024, unit_cny=2, payout_factor=.65))
    if tamper:
        source.write_text(source.read_text()+' ')
    config = tmp_path/'config.json';config.write_text(json.dumps(cfg))
    result = subprocess.run([sys.executable, str(root/'scripts/build_eight_strategy_early_candidates.py'),
        str(config)], cwd=root, env={**os.environ,'PYTHONPATH':str(root)},
        capture_output=True, text=True, timeout=60)
    if tamper:
        assert result.returncode != 0
        assert 'Early input changed' in result.stderr
        assert not (tmp_path/'output').exists()
    else:
        assert result.returncode == 0, result.stderr
        receipt = json.loads((tmp_path/'output/scope-inventory.json').read_text())
        assert receipt['requested_issues'] == [issue]
        entry = receipt['issues'][0]
        raw = Path(entry['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry['sha256']
        bundle = json.loads(gzip.decompress(raw))
        assert bundle['actual_candidate_count'] == 1
        assert len(bundle['sleeves'][0]['enumeration']['probability']) == 2187
        assert sum(bundle['sleeves'][0]['enumeration']['probability']) == pytest.approx(1)
