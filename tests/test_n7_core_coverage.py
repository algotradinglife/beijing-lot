"""Fixed-role marginal coverage: overlaps, copies, empty sides and source binds."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import pytest
from src.n7_core_coverage import core_role_coverage, package_core_coverage
from src.temporal_learning.core import stable_json_hash

ROOT=Path(__file__).resolve().parents[1]


def example():
    cutoff={'fixture':'2010-01-01T00:00:00Z'}
    worlds={kind:[[0]*7,[1]*7,[2]*7,[2]*7] for kind in ('training','evaluation')}
    layers=[]
    for role,states in [('CORE',[0,1093]),('OPPORTUNITY',[1093,2186]),('CORE',[0,1093])]:
        layers.append(dict(role=role,cutoffs=cutoff,copy_index=2 if len(layers)==2 else 1,
            sleeve_keys=[dict(fixture_indices=list(range(7)),state_ids=states,depth=2)],
            training=dict(any_hit=.75 if role=='OPPORTUNITY' else .5),
            evaluation=dict(any_hit=.75 if role=='OPPORTUNITY' else .5)))
    return dict(issue='001',seed=1,arm='A',fixtures=[{}]*7,cutoffs=cutoff,layers=layers,
        training=dict(any_hit=1.),evaluation=dict(any_hit=1.)),worlds


def test_fixed_core_union_increment_copies_and_no_labels():
    plan,worlds=example();rows=core_role_coverage(plan,worlds,cutoffs=plan['cutoffs'])
    for r in rows:
        assert (r['core_hits'],r['opportunity_hits'],r['shared_hits'],r['incremental_hits'])==(2,3,1,2)
        assert r['incremental_probability']==r['union_probability']-r['core_probability']==.5
    changed=deepcopy(plan);changed['actual_outcome']='L';changed['settlement_sp']=999
    assert core_role_coverage(changed,worlds,cutoffs=plan['cutoffs'])==rows
    plan['layers']=[]
    for kind in worlds:plan[kind]['any_hit']=0.
    assert all(r['union_hits']==r['incremental_hits']==0 for r in core_role_coverage(plan,worlds,cutoffs=plan['cutoffs']))


def test_bad_cutoff_worlds_identity_and_original_r_metrics_fail():
    plan,worlds=example()
    with pytest.raises(ValueError,match='cutoff'):core_role_coverage(plan,worlds,cutoffs={'x':'future'})
    bad=deepcopy(worlds);bad['evaluation'][0][0]=3
    with pytest.raises(ValueError,match='worlds'):core_role_coverage(plan,bad,cutoffs=plan['cutoffs'])
    bad=deepcopy(plan);bad['layers'][0]['sleeve_keys'][0]['state_ids']=[0,0]
    with pytest.raises(ValueError,match='identity'):core_role_coverage(bad,worlds,cutoffs=plan['cutoffs'])
    bad=deepcopy(plan);bad['layers'][0]['evaluation']['any_hit']=.9
    with pytest.raises(ValueError,match='R role'):core_role_coverage(bad,worlds,cutoffs=plan['cutoffs'])
    bad=deepcopy(plan);bad['evaluation']['any_hit']=.9
    with pytest.raises(ValueError,match='R parent'):core_role_coverage(bad,worlds,cutoffs=plan['cutoffs'])


def test_saved_original_r_layers_are_independently_reproduced():
    x=json.loads(gzip.decompress((ROOT/'tests/fixtures/n7_core433_replay.json.gz').read_bytes()))
    for plan in x['plans']:
        rows=core_role_coverage(plan,x['worlds'],cutoffs=x['bundle']['cutoffs'])
        assert all(0<=r['incremental_probability']<=r['opportunity_probability'] for r in rows)


def test_package_complete_binding_and_no_success_on_mutation(tmp_path):
    plan,worlds=example();study=tmp_path/'study';(study/'plans').mkdir(parents=True)
    plan_path=study/'plans/001_1_A.json.gz';plan_path.write_bytes(gzip.compress(json.dumps(plan).encode()))
    raw_path=study/'raw.gz';raw_path.write_bytes(gzip.compress(json.dumps(dict(plans=[plan],worlds=[dict(seed=1,**worlds)])).encode()))
    receipt=dict(raw_hashes={str(raw_path):hashlib.sha256(raw_path.read_bytes()).hexdigest()},
        plan_hashes={str(plan_path):hashlib.sha256(plan_path.read_bytes()).hexdigest()},cutoffs={'001':plan['cutoffs']})
    seal=stable_json_hash(receipt);(study/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=seal)))
    body=json.dumps(dict(freeze_seal=seal,historical_admission=False,independent_replay=dict(status='PASS'),
        settlement_replay=dict(status='PASS'),rows=[dict(issue='001',seed=1,arm='A',reference=False)],
        issue_order=['001'],parameters=dict(seeds=[1])))
    digest=hashlib.sha256(body.encode()).hexdigest();archive=tmp_path/'report.gz'
    archive.write_bytes(gzip.compress(json.dumps(dict(schema='bj433_core_report_v1',body=body,sha256=digest)).encode()))
    out=tmp_path/'coverage.gz';kw=dict(repository_root=str(ROOT),expected_report_sha256=digest)
    # argparse supplies strings, including the source root used for provenance.
    result=package_core_coverage(str(study),str(archive),str(out),**kw)
    wrapper=json.loads(gzip.decompress(out.read_bytes()))
    assert result['plans']==1 and result['sha256']==hashlib.sha256(wrapper['body'].encode()).hexdigest()
    with pytest.raises(ValueError,match='overwrite'):package_core_coverage(study,archive,out,**kw)
    raw_path.write_bytes(raw_path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='raw changed'):package_core_coverage(study,archive,tmp_path/'bad.gz',**kw)
    assert not (tmp_path/'bad.gz').exists()
