"""Exercise freeze/check command contracts with deterministic seven-fixture inputs."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from src.temporal_learning.core import stable_json_hash


@pytest.mark.parametrize('mutation',['none','support','cash','identity','missing_policy','cutoff','cutoff_scope'])
def test_grid_freeze_and_independent_check(tmp_path,mutation):
    root=Path(__file__).resolve().parents[1]
    fixtures=[dict(issue='001',slot=s,provider_id=str(s),handicap=0,
        p_W=.6,p_D=.25,p_L=.15,q_W=.5,q_D=.3,q_L=.2) for s in range(1,8)]
    bundle=tmp_path/'bundle.gz'
    bundle.write_bytes(gzip.compress(json.dumps(dict(issue='001',expanded_pool=dict(fixtures=fixtures),
        cutoffs={str(s):'2010-01-01' for s in range(1,8)})).encode()))
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps(dict(issues=[dict(issue='001',path=str(bundle),sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())])))
    out=tmp_path/'study';env={**os.environ,'PYTHONPATH':str(root)}
    run=subprocess.run([sys.executable,'scripts/replay_legacy_market_grid.py','--catalog',str(catalog),
        '--catalog-sha256',hashlib.sha256(catalog.read_bytes()).hexdigest(),'--output',str(out)],cwd=root,env=env,capture_output=True,text=True)
    assert run.returncode==0,run.stderr
    target=out/'plans/001.json.gz';plans=json.loads(gzip.decompress(target.read_bytes()))
    key='RAW_C1_U3'
    if mutation=='support':plans[key]['legs'][0]['support']='0'
    if mutation=='cash':plans[key]['cash_cny']+=2
    if mutation=='identity':plans[key]['legs'][0]['provider_id']='wrong'
    if mutation=='missing_policy':del plans[key]
    if mutation=='cutoff':plans[key]['cutoffs']['1']='2099-01-01T00:00:00+00:00'
    if mutation=='cutoff_scope':del plans[key]['cutoffs']['1']
    if mutation!='none':
        if key in plans:plans[key]['seal']=stable_json_hash({k:v for k,v in plans[key].items() if k!='seal'})
        target.write_bytes(gzip.compress(json.dumps(plans).encode()))
        f=out/'plans-frozen.json';r=json.loads(f.read_text());r['receipt']['plan_hashes'][str(target)]=hashlib.sha256(target.read_bytes()).hexdigest();r['seal']=stable_json_hash(r['receipt']);f.write_text(json.dumps(r))
    check=subprocess.run([sys.executable,'scripts/check_legacy_market_grid.py','--study',str(out),'--output',str(tmp_path/'proof.json')],cwd=root,env=env,capture_output=True,text=True)
    assert (check.returncode==0)==(mutation=='none'),check.stderr
    if mutation=='none':
        proof=json.loads((tmp_path/'proof.json').read_text());assert proof['plans']==8 and proof['tickets']==384

        import pandas as pd
        audit=tmp_path/'audit.csv'
        pd.DataFrame(fixtures)[['issue','slot','provider_id','handicap']].assign(
            actual_direction='W',spf_sp=2.,status='READY').to_csv(audit,index=False)
        command=[sys.executable,'scripts/settle_legacy_market_grid.py','--study',str(out),
            '--proof',str(tmp_path/'proof.json'),'--audit',str(audit),
            '--audit-sha256',hashlib.sha256(audit.read_bytes()).hexdigest()]
        settled=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
        assert settled.returncode==0,settled.stderr
        result=json.loads((out/'results.json').read_text())
        assert len(result['rows'])==8
        for row in result['rows']:
            assert row['hits']==1 and row['gross']==pytest.approx(2*.65*2**7)
            assert row['net']==pytest.approx(row['gross']-row['stake'])
        duplicate=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True)
        assert duplicate.returncode!=0
