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


@pytest.mark.parametrize('kind',['ineligible','unaffordable','control','shared_depth'])
def test_empty_union_stage_has_typed_tables_and_cash(tmp_path,kind):
    repo=Path(__file__).resolve().parents[1]
    e=json.loads(gzip.decompress((repo/'tests/fixtures/n7_sleeve_numerical.json.gz').read_bytes()))['enumeration']
    ranked=sorted(range(2187),key=lambda i:(-e['probability'][i],-e['expected_contribution'][i],i))
    bundle=dict(issue=e['issue'],cutoffs=e['cutoffs'],historical_admission=False,seal='test',
      expanded_pool=dict(fixtures=e['fixtures']),sleeves=[dict(id=0,fixture_indices=list(range(7)),origin='TEST',enumeration=e,
        options=dict(PROB=dict(status='COMPLETE',state_ids=ranked[:64])))])
    if kind=='shared_depth':
        fixture=json.loads(gzip.decompress((repo/'tests/fixtures/n7_core433_shared_depth.json.gz').read_bytes()))
        bundle=fixture['bundle'];e=bundle
    bp=tmp_path/'bundle.json.gz';bp.write_bytes(gzip.compress(json.dumps(bundle).encode()));bsha=hashlib.sha256(bp.read_bytes()).hexdigest()
    prior=tmp_path/'prior';prior.mkdir()
    raw=json.dumps(dict(seal='prior',receipt=dict(issues=[e['issue']],source_hashes={str(bp):bsha},cutoffs={e['issue']:e['cutoffs']}))).encode()
    (prior/'plans-frozen.json').write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
    rank='issue,sleeve_id,actual_rank,actual_gross_cny\n'+''.join(f"{e['issue']},{s['id']},2187,2\n" for s in bundle['sleeves'])
    (prior/'ranks.csv').write_text(rank)
    (prior/'receipt.json').write_text(json.dumps(dict(sources=[dict(study=str(prior),seal='prior',freeze_sha256=sha)],outputs={'ranks.csv':hashlib.sha256(rank.encode()).hexdigest()})))
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps(dict(issues=[dict(issue=e['issue'],cohort='test',path=str(bp),sha256=bsha)],bindings={str(prior/'plans-frozen.json'):sha})))
    output=tmp_path/'output'
    cfg=dict(stage='empty',catalog=str(catalog),rank_dir=str(prior),repository_root=str(repo),python=sys.executable,
      output_dir=str(output),targets=[.25],cap_cny=2 if kind=='ineligible' else 4374,depths=[1,2,64],seeds=[1],
      allocation_worlds=2,evaluation_worlds=5,evaluation_seed_offset=100,modes=['BREADTH'],budgets=[2],model_id='fixture')
    script='scripts/run_n7_sweet_union.R'
    if kind in ('control','shared_depth'):
        original=dict(unit_cny=2,payout_factor=.65,allocation_order='OPEN_AFFORDABLE_CORE_FIRST_THEN_DEEPEN_OR_COPY',model_id='fixture',
          feature_targets=[.15,.25],group_cap_cny=30,core_open_coverage=.15,depths=[1,2,64],training_worlds=2,evaluation_worlds=5,
          evaluation_seed_offset=100,max_actions=256,policies=[dict(name='C1',core_count=1,mode='DEPTH',objective='any_hit',opportunity_cap_cny=0,opportunity_rule='PROB',max_copies=1)])
        if kind=='shared_depth':original=fixture['config'];cfg.update(seeds=[42501],budgets=[1024])
        path=tmp_path/'original.json';path.write_text(json.dumps(original));cfg.update(original_config=str(path),policies=['C1'])
        if kind=='shared_depth':cfg['policies']=[fixture['plans'][0]['arm']]
        script='scripts/run_n7_union_budget_controls.R'
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    env=os.environ.copy();env['PYTHONPATH']=str(repo)
    result=subprocess.run([os.environ['RSCRIPT'],script,str(config)],cwd=repo,env=env,capture_output=True,text=True,timeout=120)
    assert result.returncode==0,result.stderr
    rows=list(csv.DictReader((output/'results.csv').open()));assert len(rows)==1
    if kind=='shared_depth':
        expected=fixture['plans'][0]
        assert float(rows[0]['stake'])==expected['stake']
        keys=[k for layer in expected['layers'] for k in layer['sleeve_keys']]
        funded=list(csv.DictReader((output/'funded.csv').open()))
        assert {(int(r['sleeve_id']),int(r['depth'])) for r in funded}=={(k['sleeve_id'],k['depth']) for k in keys}
    else:
        assert float(rows[0]['stake'])==0 and float(rows[0]['cash'])==2 and float(rows[0]['gross'])==0
        for name in ('funded.csv','actions.csv'):
            reader=csv.DictReader((output/name).open());assert {'issue','arm','seed'}<=set(reader.fieldnames);assert list(reader)==[]
    for command in ([sys.executable,'scripts/check_n7_sweet_union.py',str(output),str(output/'check.json')],
                    [os.environ['RSCRIPT'],'scripts/replay_n7_sweet_union.R',str(output),str(output/'allocation.json')]):
        result=subprocess.run(command,cwd=repo,env=env,capture_output=True,text=True,timeout=120)
        assert result.returncode==0,result.stderr
