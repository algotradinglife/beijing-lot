import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from src.joint_payout_study import (prepare_payout_study, replay_payout_selection,
                                    finalize_payout_freeze, evaluate_payout_study)
from src.temporal_learning import Cutoff

ROOT=Path(__file__).resolve().parents[1]


def test_full_frozen_payout_roundtrip(tmp_path):
    e=json.loads(gzip.decompress((ROOT/'tests/fixtures/n7_sleeve_numerical.json.gz').read_bytes()))['enumeration']
    b=dict(issue=e['issue'],cutoffs=e['cutoffs'],historical_admission=False,seal='test',
           expanded_pool=dict(fixtures=e['fixtures']),sleeves=[dict(id=0,fixture_indices=list(range(7)),
           origin='TEST',enumeration=e,options={})])
    bundle=tmp_path/'b.json.gz';bundle.write_bytes(gzip.compress(json.dumps(b).encode()))
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps(dict(issues=[dict(issue=b['issue'],path=str(bundle),sha256=hashlib.sha256(bundle.read_bytes()).hexdigest())])))
    groups=tmp_path/'groups.csv';groups.write_text(f"issue,policy,sleeve_id,depth\n{b['issue']},JOINT,0,64\n")
    cfg=json.loads((ROOT/'config/research/joint_payout_exposure_v1.json').read_text())
    cfg['payout_floor_grid_cny']=[0,256];cfg['coverage_worlds']=256
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg))
    out=tmp_path/'out'
    with pytest.raises(ValueError,match='source changed'):
        prepare_payout_study(catalog,'0'*64,groups,hashlib.sha256(groups.read_bytes()).hexdigest(),config,ROOT,out)
    prepare_payout_study(catalog,hashlib.sha256(catalog.read_bytes()).hexdigest(),groups,
                         hashlib.sha256(groups.read_bytes()).hexdigest(),config,ROOT,out)
    with pytest.raises(ValueError,match='already exists'):
        prepare_payout_study(catalog,'x',groups,'x',config,ROOT,out)
    python=os.environ['FUNDAMENTALS_PYTHON'];env=dict(os.environ,PYTHONPATH=str(ROOT))
    subprocess.run(['/usr/local/bin/Rscript','--vanilla','scripts/freeze_joint_payout_chunk.R',
                    str(out/'manifest.json'),str(out),python,'1','1','freeze'],cwd=ROOT,env=env,check=True,capture_output=True)
    plan_path=out/'plans'/f"{b['issue']}.json.gz"
    saved=plan_path.read_bytes();bad=json.loads(gzip.decompress(saved))
    bad['plans']['P0_OPEN']['union_coverage']=None
    plan_path.write_bytes(gzip.compress(json.dumps(bad).encode()))
    with pytest.raises(subprocess.CalledProcessError):
        finalize_payout_freeze(out,ROOT,python,'/usr/local/bin/Rscript')
    assert not (out/'plans-frozen.json').exists()
    plan_path.write_bytes(saved)
    freeze=finalize_payout_freeze(out,ROOT,python,'/usr/local/bin/Rscript')
    assert freeze['receipt']['independent_replays']==6
    native={k:Cutoff.decision_epoch(b['issue'],v) for k,v in b['cutoffs'].items()}
    got=replay_payout_selection(b,[dict(sleeve_id=0,depth=64)],native,0,1024,1024,2)
    assert len(got)==64
    assert len(replay_payout_selection(b,[dict(sleeve_id=0,depth=64)],native,0,20,1024,2))==10
    assert replay_payout_selection(b,[],native,0,1024,1024,2)==[]
    with pytest.raises(ValueError):replay_payout_selection(b,[dict(sleeve_id=0,depth=513)],native,0,1024,1024,2)
    with pytest.raises(ValueError):replay_payout_selection(b,[dict(sleeve_id=0,depth=64)],{},0,1024,1024,2)
    # Only now construct/open labels. Mutating labels cannot rewrite frozen plans.
    audit=tmp_path/'audit.csv'
    with audit.open('w') as h:
        writer=csv.DictWriter(h,fieldnames=['issue','slot','provider_id','handicap','actual_direction','spf_sp','status']);writer.writeheader()
        for fixture in b['expanded_pool']['fixtures']:
            writer.writerow({**{k:fixture[k] for k in ['issue','slot','provider_id','handicap']},'actual_direction':'W','spf_sp':2,'status':'READY'})
    digest=hashlib.sha256((out/'plans'/f"{b['issue']}.json.gz").read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='Settlement changed'):
        evaluate_payout_study(out,ROOT,audit,'0'*64)
    receipt=evaluate_payout_study(out,ROOT,audit,hashlib.sha256(audit.read_bytes()).hexdigest())
    assert 'rows.csv' in receipt['files']
    assert hashlib.sha256((out/'plans'/f"{b['issue']}.json.gz").read_bytes()).hexdigest()==digest
    with pytest.raises(ValueError,match='Evaluation exists'):
        evaluate_payout_study(out,ROOT,audit,hashlib.sha256(audit.read_bytes()).hexdigest())

    # A valid issue with no allocated groups must retain full cash in every arm.
    groups.write_text('issue,policy,sleeve_id,depth\n')
    empty=tmp_path/'empty'
    prepare_payout_study(catalog,hashlib.sha256(catalog.read_bytes()).hexdigest(),groups,
                         hashlib.sha256(groups.read_bytes()).hexdigest(),config,ROOT,empty)
    subprocess.run(['/usr/local/bin/Rscript','--vanilla','scripts/freeze_joint_payout_chunk.R',
                    str(empty/'manifest.json'),str(empty),python,'1','1','freeze'],cwd=ROOT,env=env,check=True,capture_output=True)
    finalize_payout_freeze(empty,ROOT,python,'/usr/local/bin/Rscript')
    evaluate_payout_study(empty,ROOT,audit,hashlib.sha256(audit.read_bytes()).hexdigest())
    with (empty/'rows.csv').open() as h:
        zero=list(csv.DictReader(h))
    assert len(zero)==6 and all(float(r['stake'])==0 and float(r['cash_cny'])==1024 for r in zero)
