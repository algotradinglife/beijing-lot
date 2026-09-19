"""End-to-end audit CLI regression for Quarto's singleton JSON unboxing."""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('empty', [False, True])
def test_singleton_or_cash_only_report(tmp_path, empty):
    source = tmp_path / 'input'
    source.mkdir()
    fixtures = [dict(issue='001', slot=i+1, provider_id=str(i), handicap=0,
                     p_W=.5, p_D=.3, p_L=.2, q_W=.5, q_D=.3, q_L=.2)
                for i in range(7)]
    with (source / 'fixture-audit.csv').open('w') as out:
        writer = csv.DictWriter(out, fieldnames=['issue', 'slot', 'provider_id', 'handicap', 'actual_direction', 'spf_sp'])
        writer.writeheader()
        writer.writerows(dict(issue='001', slot=i+1, provider_id=str(i), handicap=0, actual_direction='W', spf_sp=2) for i in range(7))
    audit_sha = hashlib.sha256((source/'fixture-audit.csv').read_bytes()).hexdigest()
    (source/'receipt.json').write_text(json.dumps({'files': {'fixture-audit.csv': audit_sha}}))
    plan = dict(issue='001', fixtures=fixtures, options=[[1, 2]]*7,
                groups=[] if empty else [list(range(1, 8))],
                selected={'TOP2_PROB': [] if empty else 1},
                union_probability={'TOP2_PROB': [] if empty else .8**7})
    plan_path = tmp_path/'plan.json'
    plan_path.write_text(json.dumps(plan))
    (tmp_path/'freeze.json').write_text(json.dumps(dict(
        source_receipt=hashlib.sha256((source/'receipt.json').read_bytes()).hexdigest(),
        plans={str(plan_path): hashlib.sha256(plan_path.read_bytes()).hexdigest()})))
    with (tmp_path/'groups.csv').open('w') as out:
        writer = csv.DictWriter(out, fieldnames=['issue','policy','group','gross','stake'])
        writer.writeheader()
        if not empty:
            writer.writerow(dict(issue='001', policy='TOP2_PROB', group=1, gross=2*.65*2**7, stake=256))
    files={n:hashlib.sha256((tmp_path/n).read_bytes()).hexdigest() for n in ('freeze.json','groups.csv')}
    (tmp_path/'receipt.json').write_text(json.dumps(dict(files=files,config=dict(input=str(source)))))
    script=Path(__file__).resolve().parents[1]/'scripts/check_top2_fresh_replay.py'
    result=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['settled_groups']==int(not empty)
    if not empty:
        # Rehash an internally coherent, but illegally truncated selection.
        plan['selected']['TOP2_PROB'] = []
        plan['union_probability']['TOP2_PROB'] = []
        plan_path.write_text(json.dumps(plan))
        frozen=json.loads((tmp_path/'freeze.json').read_text())
        frozen['plans'][str(plan_path)]=hashlib.sha256(plan_path.read_bytes()).hexdigest()
        (tmp_path/'freeze.json').write_text(json.dumps(frozen))
        (tmp_path/'groups.csv').write_text('issue,policy,group,gross,stake\n')
        altered=json.loads((tmp_path/'receipt.json').read_text())
        for name in altered['files']:
            altered['files'][name]=hashlib.sha256((tmp_path/name).read_bytes()).hexdigest()
        (tmp_path/'receipt.json').write_text(json.dumps(altered))
        rejected=subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True,text=True)
        assert rejected.returncode != 0
        assert 'min(4, len(gs))' in rejected.stderr
    plan_path.write_text('{}')
    assert subprocess.run([sys.executable,str(script),str(tmp_path)],capture_output=True).returncode != 0
