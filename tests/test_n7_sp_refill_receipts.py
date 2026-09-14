"""CLI regression checks reject mixed or overwritten experiment evidence."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import pytest


@pytest.mark.parametrize('changed',['results.csv','plans-frozen.json'])
def test_independent_checker_rejects_changed_comparison(tmp_path,changed):
    receipt={}
    for name,key in [('results.csv','results_sha256'),('plans-frozen.json','freeze_sha256')]:
        raw=b'original';(tmp_path/name).write_bytes(raw);receipt[key]=hashlib.sha256(raw).hexdigest()
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps(receipt))
    (tmp_path/changed).write_bytes(b'replaced but internally consistent')
    root=Path(__file__).resolve().parents[1]
    run=subprocess.run([sys.executable,'-m','scripts.check_n7_sp_refill','--refill',str(tmp_path),
        '--replay',str(tmp_path),'--comparison',str(tmp_path),'--repository',str(root)],
        cwd=root,capture_output=True,text=True)
    assert run.returncode!=0 and 'Comparison output binding changed' in run.stderr
    assert not (tmp_path/'independent-check.json').exists()


def test_settlement_rejects_control_from_different_freeze(tmp_path):
    for name in ['prediction-freeze.json','plans-frozen.json']:
        (tmp_path/name).write_text(json.dumps({'files':{}}))
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps({'freeze_sha256':'other run'}))
    output=tmp_path/'output'
    run=subprocess.run([sys.executable,'-m','scripts.settle_n7_sp_refill','--refill',str(tmp_path),
        '--control',str(tmp_path),'--audit-study',str(tmp_path),'--output',str(output)],
        cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert run.returncode!=0 and 'Control settlement freeze binding changed' in run.stderr
    assert not output.exists()
