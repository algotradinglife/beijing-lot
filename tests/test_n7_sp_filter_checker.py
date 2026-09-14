"""Independent checker: reject coherent-but-wrong gate and paired-control data."""
import csv
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('mutation',[None,'admission','funded','control','threshold'])
@pytest.mark.parametrize('unboxed',[False,True])
def test_sp_filter_checker(tmp_path,mutation,unboxed):
    fixtures=[dict(p_W=.8,p_D=.1,p_L=.1,q_W=.8,q_D=.1,q_L=.1,slot=i+1,provider_id=str(i)) for i in range(7)]
    bundle=dict(cutoffs={'a':'epoch'},expanded_pool=dict(fixtures=fixtures),
                sleeves=[dict(id=0,fixture_indices=list(range(7)))])
    bundle_path=tmp_path/'bundle.json.gz'
    bundle_path.write_bytes(gzip.compress(json.dumps(bundle).encode()))
    catalog=tmp_path/'catalog.json'
    catalog.write_text(json.dumps(dict(issues=[dict(issue='001',path=str(bundle_path),
        sha256=hashlib.sha256(bundle_path.read_bytes()).hexdigest())])))
    baseline=dict(issue='001',arm='T250_TEST_B512',seed='1',stake='2',cash='510',
                  groups='1',budget_cny='512',hits='0',net='-2',gross='0')
    control=tmp_path/'control';study=tmp_path/'study';control.mkdir();study.mkdir()
    original_funded=dict(issue='001',arm='T250_TEST_B512',seed='1',sleeve_id='0',depth='1',copies='1')
    original_action=dict(issue='001',arm='T250_TEST_B512',seed='1',step='1')
    results=[];funded=[];actions=[]
    for t in (1,1.1,1.2,1.3,1.5):
        keep=t<=1.25;arm=f'T250_SP{round(t*100):03d}_TEST_B512'
        results.append(dict(baseline,arm=arm,minimum_sp=t,eligible_fixtures=7 if keep else 0,
            total_fixtures=7,eligible_groups=int(keep),total_groups=1,
            removed_top1_mass=0 if keep else 5.6,stake='2' if keep else '0',
            cash='510' if keep else '512',groups=str(int(keep)),net='-2' if keep else '0'))
        if keep:
            funded.append(dict(original_funded,arm=arm));actions.append(dict(original_action,arm=arm))
    if mutation=='threshold':results[1]['minimum_sp']=1.2
    if mutation=='admission':results[1]['eligible_fixtures']=6
    if mutation=='funded':funded.append(dict(original_funded,arm='T250_SP150_TEST_B512'))
    if mutation=='control':results[0]['net']='-1'
    for directory,tables in ((control,{'results.csv':[baseline],'predictions.csv':[baseline],
        'funded.csv':[original_funded],'actions.csv':[original_action]}),
        (study,{'results.csv':results,'predictions.csv':results,'funded.csv':funded,'actions.csv':actions})):
        for filename,rows in tables.items():
            with (directory/filename).open('w') as f:
                writer=csv.DictWriter(f,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
        freeze=dict(config=dict(catalog=str(catalog),targets=[.25],budgets=[512],policies=[dict(id=f'SP{round(t*100):03d}_TEST',minimum_sp=t) for t in (1,1.1,1.2,1.3,1.5)]),
            cutoffs={'001':{'a':'epoch'}},source_catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
            files={n:hashlib.sha256((directory/n).read_bytes()).hexdigest() for n in ('predictions.csv','funded.csv','actions.csv')})
        if unboxed:
            freeze['config']['targets']=.25
            freeze['config']['budgets']=512
        (directory/'plans-frozen.json').write_text(json.dumps(freeze))
        (directory/'evaluation-receipt.json').write_text(json.dumps(dict(
            freeze_sha256=hashlib.sha256((directory/'plans-frozen.json').read_bytes()).hexdigest(),
            results_sha256=hashlib.sha256((directory/'results.csv').read_bytes()).hexdigest())))
    repo=Path(__file__).resolve().parents[1]
    out=tmp_path/'check.json'
    run=subprocess.run([sys.executable,str(repo/'scripts/check_n7_sp_filter.py'),str(study),str(control),str(out)],capture_output=True,text=True)
    if mutation is None:
        assert run.returncode==0,run.stderr
        receipt=json.loads(out.read_text())
        assert receipt['status']=='PASS' and receipt['plans']==5
        assert receipt['control_rows']=={'results.csv':1,'funded.csv':1,'actions.csv':1}
        assert len(receipt['excluded_fixtures'])==14
        assert all(x['estimated_sp']==1.25 and x['top1']=='W' for x in receipt['excluded_fixtures'])
    else:
        assert run.returncode!=0 and not out.exists()
