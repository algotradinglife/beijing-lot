"""Accounting regression for the independent #439 script (no live inputs)."""
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from tests.test_n7_union_inputs import union_sources
from src.n7_union_inputs import bind_union_inputs


@pytest.mark.parametrize('corruption',[None,'gross','budget','missing_plan'])
@pytest.mark.parametrize('scalar',[False,True])
def test_independent_union_accounting(tmp_path,corruption,scalar,union_sources):
    """Even rehashed malformed evidence cannot pass accounting/coverage checks."""
    files={
      'ranks.csv':[dict(issue='01',sleeve_id='0',actual_rank=1,actual_gross_cny=13)],
      'funded.csv':[dict(issue='01',arm='T250_BREADTH_B4',seed='1',sleeve_id='0',depth=1,stake=2,coverage=.25)],
      'results.csv':[dict(issue='01',arm='T250_BREADTH_B4',seed='1',target=.25,mode='BREADTH',budget_cny=4,stake=2,cash=2,groups=1,hits=1,gross=13,net=11)]}
    if corruption=='gross':files['results.csv'][0].update(gross=20,net=18)
    if corruption=='budget':files['results.csv'][0].update(budget_cny=1,cash=-1)
    hashes={}
    for name,rows in files.items():
        text=io.StringIO();writer=csv.DictWriter(text,fieldnames=rows[0]);writer.writeheader()
        if not (corruption=='missing_plan' and name=='results.csv'):writer.writerows(rows)
        raw=text.getvalue().encode();(tmp_path/name).write_bytes(raw);hashes[name]=hashlib.sha256(raw).hexdigest()
    catalog,rank_dir,repo=union_sources
    (rank_dir/'ranks.csv').write_bytes((tmp_path/'ranks.csv').read_bytes())
    receipt=json.loads((rank_dir/'receipt.json').read_text());receipt['outputs']['ranks.csv']=hashes['ranks.csv']
    (rank_dir/'receipt.json').write_text(json.dumps(receipt))
    freeze=dict(historical_admission=False,metadata={'01':{}},files={'funded.csv':hashes['funded.csv']},
      input_binding=bind_union_inputs(*union_sources),
      config=dict(catalog=str(catalog),repository_root=str(repo),rank_dir=str(rank_dir),cap_cny=256,targets=[.25],modes=['BREADTH'],budgets=[4],seeds=[1]))
    if scalar:
        for name in ('budgets','targets','modes','seeds'):freeze['config'][name]=freeze['config'][name][0]
    raw=json.dumps(freeze).encode();(tmp_path/'plans-frozen.json').write_bytes(raw)
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps(dict(plans=1,
      freeze_sha256=hashlib.sha256(raw).hexdigest(),ranks_sha256=hashes['ranks.csv'],results_sha256=hashes['results.csv'])))
    script=Path(__file__).resolve().parents[1]/'scripts/check_n7_sweet_union.py'
    result=subprocess.run([sys.executable,str(script),str(tmp_path),str(tmp_path/'check.json')],capture_output=True,text=True)
    assert (result.returncode==0)==(corruption is None),result.stderr
