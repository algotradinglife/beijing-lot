"""Saved-response end-to-end regression: an entirely unfunded stage is valid."""
import csv
import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize('kind',['ineligible','unaffordable','copies'])
def test_funding_modes_end_to_end(tmp_path,kind):
    repo=Path(__file__).resolve().parents[1]
    e=json.loads(gzip.decompress((repo/'tests/fixtures/n7_sleeve_numerical.json.gz').read_bytes()))['enumeration']
    ranked=sorted(range(2187),key=lambda i:(-e['probability'][i],-e['expected_contribution'][i],i))
    bundle=dict(issue=e['issue'],cutoffs=e['cutoffs'],historical_admission=False,seal='test',
      expanded_pool=dict(fixtures=e['fixtures']),sleeves=[dict(id=0,fixture_indices=list(range(7)),origin='TEST',enumeration=e,
        options=dict(PROB=dict(status='COMPLETE',state_ids=ranked[:64])))])
    bp=tmp_path/'bundle.json.gz';bp.write_bytes(gzip.compress(json.dumps(bundle).encode()));bsha=hashlib.sha256(bp.read_bytes()).hexdigest()
    prior=tmp_path/'prior';prior.mkdir()
    raw=json.dumps(dict(seal='prior',receipt=dict(issues=[e['issue']],source_hashes={str(bp):bsha},cutoffs={e['issue']:e['cutoffs']}))).encode()
    (prior/'plans-frozen.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    state=ranked[-1]
    rank=f"issue,sleeve_id,actual_rank,actual_gross_cny,actual_state_id,actual_probability\n{e['issue']},0,2187,1.3,{state},{e['probability'][state]}\n"
    audit_rows=[dict(issue=f['issue'],slot=f['slot'],provider_id=f['provider_id'],handicap=f['handicap'],actual_direction=['W','D','L'][outcome],spf_sp=1.0,spf_source_sha256='fixture',status='READY') for f,outcome in zip(e['fixtures'],e['states'][state])]
    audit_raw=json.dumps(dict(rows=audit_rows)).encode()
    (prior/'audit-snapshot.json').write_bytes(audit_raw)
    (prior/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=sha,audit_sha256=hashlib.sha256(audit_raw).hexdigest())))
    (prior/'ranks.csv').write_text(rank)
    (prior/'receipt.json').write_text(json.dumps(dict(sources=[dict(study=str(prior),seal='prior',freeze_sha256=sha)],outputs={'ranks.csv':hashlib.sha256(rank.encode()).hexdigest()})))
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps(dict(issues=[dict(issue=e['issue'],cohort='test',path=str(bp),sha256=bsha)],bindings={str(prior/'plans-frozen.json'):sha})))
    output=tmp_path/'output'
    cfg=dict(stage='empty',catalog=str(catalog),rank_dir=str(prior),repository_root=str(repo),python=sys.executable,
      output_dir=str(output),targets=[.25],cap_cny=2 if kind=='ineligible' else 4374,depths=[1,2,64],seeds=[1],
      allocation_worlds=2,evaluation_worlds=5,evaluation_seed_offset=100,modes=['BREADTH'],budgets=[2],model_id='fixture')
    script='scripts/run_n7_funding_modes.R'
    cfg.update(depth_reference_targets=[.25,.3],max_copies=4,max_actions=256,modes=['MULTIPLY'])
    if kind=='copies':cfg['budgets']=[1024]
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    env=os.environ.copy();env['PYTHONPATH']=str(repo)
    result=subprocess.run([os.environ['RSCRIPT'],script,str(config)],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    rows=list(csv.DictReader((output/'results.csv').open()));assert len(rows)==1
    if kind=='copies':
        funded=list(csv.DictReader((output/'funded.csv').open()))
        assert len(funded)==1 and int(funded[0]['copies'])>1
        assert float(rows[0]['stake'])==2*int(funded[0]['depth'])*int(funded[0]['copies'])
    else:
        assert float(rows[0]['stake'])==0 and float(rows[0]['cash'])==2 and float(rows[0]['gross'])==0
        for name in ('funded.csv','actions.csv'):
            reader=csv.DictReader((output/name).open());assert {'issue','arm','seed'}<=set(reader.fieldnames);assert list(reader)==[]
    for command in ([sys.executable,'scripts/check_n7_funding_modes.py',str(output),str(output/'check.json')],
                    [os.environ['RSCRIPT'],'scripts/replay_n7_funding_modes.R',str(output),str(output/'allocation.json')]):
        result=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=120)
        assert result.returncode==0,result.stderr
    attr_cfg=dict(cfg,stages=[str(output)],output_dir=str(tmp_path/'attribution'))
    attr_config=tmp_path/'attribution-config.json';attr_config.write_text(json.dumps(attr_cfg))
    result=subprocess.run([os.environ['RSCRIPT'],'scripts/run_n7_return_attribution.R',str(attr_config)],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    if kind=='copies':
        # A coherent hash rewrite must not hide a wrong model evaluation value.
        predictions=output/'predictions.csv';saved_predictions=predictions.read_bytes()
        pred=list(csv.DictReader(predictions.open()));pred[0]['eval_union']=str(float(pred[0]['eval_union'])+.01)
        with predictions.open('w') as handle:
            writer=csv.DictWriter(handle,fieldnames=pred[0]);writer.writeheader();writer.writerows(pred)
        freeze_path=output/'plans-frozen.json';saved_freeze=freeze_path.read_bytes();frozen=json.loads(saved_freeze)
        frozen['files']['predictions.csv']=hashlib.sha256(predictions.read_bytes()).hexdigest();freeze_path.write_text(json.dumps(frozen))
        result=subprocess.run([os.environ['RSCRIPT'],'scripts/replay_n7_funding_modes.R',str(output),str(output/'bad-model.json')],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
        assert result.returncode!=0 and 'eval_union' in result.stderr
        predictions.write_bytes(saved_predictions);freeze_path.write_bytes(saved_freeze)
        # Same SP with a contradictory actual direction must fail identity checks.
        audit_rows[0]['actual_direction']='D' if audit_rows[0]['actual_direction']!='D' else 'W'
        bad_raw=json.dumps(dict(rows=audit_rows)).encode();(prior/'audit-snapshot.json').write_bytes(bad_raw)
        (prior/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=sha,audit_sha256=hashlib.sha256(bad_raw).hexdigest())))
        attr_cfg['output_dir']=str(tmp_path/'bad-attribution');attr_config.write_text(json.dumps(attr_cfg))
        result=subprocess.run([os.environ['RSCRIPT'],'scripts/run_n7_return_attribution.R',str(attr_config)],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
        assert result.returncode!=0 and 'state ==' in result.stderr
    # Post-freeze label mutation must invalidate settlement replay, never rewrite tickets.
    before=(output/'funded.csv').read_bytes()
    (prior/'ranks.csv').write_text(rank+'\n')
    result=subprocess.run([sys.executable,'scripts/check_n7_funding_modes.py',str(output),str(output/'mutated-check.json')],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode!=0
    assert (output/'funded.csv').read_bytes()==before
