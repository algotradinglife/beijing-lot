import numpy as np
import pandas as pd
import pytest
import json
import os
from pathlib import Path
import subprocess
import sys
import hashlib
from src.temporal_learning.provenance import implementation_closure
from src.n7_probability_gate import probability_gate_candidates
from src.n7_incremental_coverage import incremental_coverage_plans
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def test_greedy_budget_union_and_independent_evaluation():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=.6,p_D=.3,p_L=.1,q_W=.6,q_D=.3,q_L=.1) for i in range(1,10)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=700,tradeoffs=[0.,'PROBABILITY'])
    args=dict(cutoffs=cuts,seed=42,training_worlds=1000,evaluation_worlds=3000,
        min_probabilities=[0.,.1],budget_cny=1024,unit_cny=2,payout_factor=.65)
    plans=incremental_coverage_plans(pool,**args)
    assert len(plans)==6
    coverage=plans[0];prob=plans[2];ev=plans[3]
    assert coverage['groups']==512 and coverage['stake']==1024 and ev['groups']==0
    assert coverage['simulation']['training_hit_rate']>=prob['simulation']['training_hit_rate']
    # Recreate training worlds independently; brute greedy gain/tie argmax at each step.
    rng=np.random.default_rng(np.random.SeedSequence(42).spawn(2)[0])
    outcomes=np.array([np.searchsorted(np.array([.6,.9,1.]),rng.random(1000),side='right') for _ in range(9)])
    codes=np.array(pool['encoded_tickets']);hit=np.all(outcomes[codes//3]==(codes%3)[:,:,None],axis=1)
    mass=np.prod(np.array([.6,.3,.1])[codes%3],axis=1)
    roi=.65*np.prod(np.array([.6,.3,.1])[codes%3]/np.array([.6,.3,.1])[codes%3],axis=1)-1
    available=set(range(len(codes)));covered=np.zeros(1000,dtype=bool)
    for position,(idx,ds) in enumerate(zip(coverage['fixture_indices'],coverage['outcomes'])):
        gains=np.sum(hit & ~covered,axis=1)
        best=min(available,key=lambda j:(-int(gains[j]),-roi[j],-mass[j],j))
        assert list(codes[best])==[3*i+d for i,d in zip(idx,ds)]
        assert coverage['marginal_training_counts'][position]==gains[best]
        covered|=hit[best];available.remove(best)
    assert coverage['simulation']['training_hit_rate']==pytest.approx(covered.mean())
    changed=incremental_coverage_plans(pool,**dict(args,evaluation_worlds=4000))
    assert changed[0]['fixture_indices']==coverage['fixture_indices'] and changed[0]['outcomes']==coverage['outcomes']
    for p in plans:
        assert stable_json_hash({k:v for k,v in p.items() if k!='seal'})==p['seal']
        assert 0<=p['simulation']['evaluation_hit_rate']<=1
    audit=f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='READY')
    assert settle_single_tickets(coverage,audit)['status']=='COMPLETE'
    assert plans[1]['groups']==0 and plans[1]['simulation']['evaluation_hit_rate']==0
    with pytest.raises(ValueError):incremental_coverage_plans(pool,**dict(args,seed=-1))
    with pytest.raises(ValueError):incremental_coverage_plans(pool,**dict(args,cutoffs={}))
    with pytest.raises(ValueError):incremental_coverage_plans(pool,**dict(args,training_worlds=0))


def test_certain_shared_worlds_are_not_added_as_independent_tickets():
    f=pd.DataFrame([dict(issue='001',slot=i,provider_id=str(i),handicap=0,
        p_W=1.,p_D=0.,p_L=0.,q_W=.8,q_D=.1,q_L=.1) for i in range(1,9)])
    cuts={str(i):Cutoff.decision_epoch('001','2010-01-01') for i in f.slot}
    pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=20,tradeoffs=[0.])
    plans=incremental_coverage_plans(pool,cutoffs=cuts,seed=1,training_worlds=17,evaluation_worlds=23,
        min_probabilities=[1.],budget_cny=1024,unit_cny=2,payout_factor=.65)
    assert all(p['groups']==8 and p['simulation']['evaluation_hit_rate']==1 for p in plans)
    assert plans[0]['marginal_training_counts']==[17]+[0]*7


@pytest.mark.parametrize('script',['replay_n7_incremental_coverage.py','check_n7_incremental_coverage.py'])
def test_optimized_cli_rejects_tampered_freeze(tmp_path,script):
    project=Path(__file__).resolve().parents[1]
    origin=tmp_path/'data/derived/fundamentals_417/n7-probability-gate-v2'
    origin.mkdir(parents=True)
    (origin/'plans-frozen.json').write_text(json.dumps({'receipt':{},'seal':'tampered'}))
    flag,value=('--output',str(tmp_path/'output')) if script.startswith('replay') else ('--study',str(origin))
    result=subprocess.run([sys.executable,'-O',str(project/'scripts'/script),flag,value],cwd=tmp_path,
        env={**os.environ,'PYTHONPATH':str(project)},text=True,capture_output=True)
    assert result.returncode!=0 and 'ValueError: Integrity contract failed' in result.stderr


@pytest.mark.parametrize('rankings',[['COVERAGE','COVERAGE','EV'],['COVERAGE','EV']])
def test_checker_rejects_duplicate_or_missing_grid_rows(tmp_path,rankings):
    project=Path(__file__).resolve().parents[1]
    receipt=dict(issues=['001'],seeds=[1],counts=[0],source_hashes={},plan_hashes={},
        implementation=implementation_closure(project,['src.n7_incremental_coverage'],distributions=['numpy']))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (tmp_path/'plans-frozen.json').write_text(json.dumps(freeze))
    (tmp_path/'results.json').write_text(json.dumps(dict(freeze_seal=freeze['seal'],rows=[
        dict(issue='001',seed=1,count=0,ranking=ranking) for ranking in rankings])))
    (tmp_path/'audit.json').write_text(json.dumps(dict(rows=[])))
    (tmp_path/'prior-evaluation-snapshot.json').write_text('{}')
    er=dict(freeze_sha256=hashlib.sha256((tmp_path/'plans-frozen.json').read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256((tmp_path/'results.json').read_bytes()).hexdigest(),
        audit_path=str(tmp_path/'audit.json'),audit_sha256=hashlib.sha256((tmp_path/'audit.json').read_bytes()).hexdigest(),
        prior_receipt_sha256=hashlib.sha256((tmp_path/'prior-evaluation-snapshot.json').read_bytes()).hexdigest())
    (tmp_path/'evaluation-receipt.json').write_text(json.dumps(er))
    result=subprocess.run([sys.executable,'-O','-m','scripts.check_n7_incremental_coverage','--study',str(tmp_path)],
        cwd=project,text=True,capture_output=True)
    assert result.returncode!=0 and 'Incomplete or duplicate issue/seed/gate/ranking grid' in result.stderr
