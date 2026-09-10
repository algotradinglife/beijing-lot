"""Exercise the real thin runner with tiny saved inputs and mutated outcomes."""
import gzip,hashlib,json,subprocess,sys
from pathlib import Path
import pandas as pd
from src.temporal_learning.core import stable_json_hash


def test_cli_freezes_before_audit_and_outcomes_do_not_change_any_plan(tmp_path):
    root=Path(__file__).resolve().parents[1]
    contract=dict(policies={'CURRENT':dict(policy='KEEP',fallback_weight=0),
        'CONFLICT_REDUCE_025':dict(policy='REDUCE',fallback_weight=.25),
        'CONFLICT_REVERT_0':dict(policy='REDUCE',fallback_weight=0),
        'CONFLICT_SKIP':dict(policy='SKIP',fallback_weight=0)},
        max_groups=6,unit_cny=2,payout_factor=.65,test_issues=[],validation_issues=[])
    rows=[]
    for slot in range(1,15):
        for w in [0,.25,.5]:
            p=[.2,.4,.4] if slot<=7 and w==.5 else [.5,.3,.2]
            rows.append(dict(issue='100101',slot=slot,provider_id=f'{slot:04}',weight=w,handicap=0,
                **dict(zip(['p_W','p_D','p_L'],p)),q_W=.5,q_D=.3,q_L=.2))
    bound=tmp_path/'fixed-source.json';bound.write_text(json.dumps(rows))
    pack=dict(rows=rows,cutoffs={'100101':{str(s):'2010-01-01T00:00:00Z' for s in range(1,15)}},
        source_hashes={str(bound):hashlib.sha256(bound.read_bytes()).hexdigest()},contract=contract)
    pack['seal']=stable_json_hash(pack)
    outputs=[]
    for i,direction in enumerate(['W','L','MISSING']):
        out=tmp_path/str(i);out.mkdir();audit=tmp_path/f'audit-{i}';audit.mkdir()
        (out/'inputs.json').write_text(json.dumps(pack));(out/'contract.json').write_text(json.dumps(contract))
        if direction!='MISSING':
            labels=[dict(issue='100101',slot=s,provider_id=f'{s:04}',handicap=0,
                actual_direction=direction,spf_sp=3. if i==0 else 99.,status='READY') for s in range(1,15)]
            (audit/'training-audit.json').write_text(json.dumps(labels))
            for part in ['validation','test']:(audit/f'{part}-audit.json').write_text('[]')
        command=[sys.executable,'scripts/run_decision_chain_comparison.py','--study',str(out),'--audit-source',str(audit)]
        completed=subprocess.run(command,cwd=root,capture_output=True,text=True)
        assert completed.returncode==(1 if direction=='MISSING' else 0),completed.stderr
        assert (out/'plans-frozen.json').exists()
        assert len(list((out/'plans').glob('*.json')))==5
        outputs.append(out)
        if direction!='MISSING':
            assert subprocess.run(command,cwd=root,capture_output=True).returncode!=0
    for path in (outputs[0]/'plans').glob('*.json'):
        first=json.loads(path.read_text())
        for out in outputs[1:]:
            other=json.loads((out/'plans'/path.name).read_text())
            assert first['plan']==other['plan']
            if 'routing' in first:
                assert first['routing']['rows']==other['routing']['rows']
                assert first['routing']['ledger']==other['routing']['ledger']
    assert json.loads((outputs[0]/'results.json').read_text())['rows']!=json.loads((outputs[1]/'results.json').read_text())['rows']


def test_archived_report_fixture_contract_and_no_overwrite(tmp_path):
    root=Path(__file__).resolve().parents[1]
    saved=json.loads(gzip.decompress((root/'tests/fixtures/decision_chain_report.json.gz').read_bytes()))
    assert saved['original_check']['plans_checked']==200
    for name,body in saved['files'].items():assert hashlib.sha256(body.encode()).hexdigest()==saved['hashes'][name]
    out=tmp_path/'report';command=[sys.executable,'scripts/prepare_decision_chain_report_fixture.py','--output',str(out)]
    subprocess.run(command,cwd=root,check=True,capture_output=True)
    check=json.loads((out/'independent-check.json').read_text())
    assert check['fixture_mode']=='ARCHIVED_RENDER_ONLY_NOT_FRESH_REPLAY'
    assert hashlib.sha256((out/'results.json').read_bytes()).hexdigest()==check['source_hashes'][str(out/'results.json')]
    assert subprocess.run(command,cwd=root,capture_output=True).returncode!=0
