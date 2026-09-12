"""Exercise both command boundaries with real numerical/settlement functions."""
import concurrent.futures
import gzip,hashlib,json,runpy,sys
from pathlib import Path
import pandas as pd
import pytest
import src.temporal_learning
import src.temporal_learning.provenance
from src.n7_probability_gate import probability_gate_candidates
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash


def test_independent_replay_and_rehashed_result_mutations(tmp_path,monkeypatch):
    cfg=json.loads(Path('config/n7_sleeve_424.json').read_text())
    origin=tmp_path/'origin';pools=tmp_path/'pools';origin.mkdir();pools.mkdir()
    cfg.update(origin=str(origin),pool_root=str(pools),candidate_count=9,
        frontier_points=[['F80_R35',.8,-.35]],seeds=[42],training_worlds=300,evaluation_worlds=400,return_passes=1)
    sources={};audit=[]
    for issue in ('001','002'):
        f=pd.DataFrame([dict(issue=issue,slot=i,provider_id=str(i),handicap=0,
            p_W=.6,p_D=.3,p_L=.1,q_W=.5,q_D=.3,q_L=.2) for i in range(8)])
        cuts={str(i):Cutoff.decision_epoch(issue,'2010-01-01') for i in f.slot}
        pool=probability_gate_candidates(f,cutoffs=cuts,n=7,depth=600,tradeoffs=['PROBABILITY',0.])
        path=pools/f'{issue}.json.gz';raw=gzip.compress(json.dumps(pool).encode());path.write_bytes(raw)
        sources[str(path)]=hashlib.sha256(raw).hexdigest()
        audit.extend(f[['issue','slot','provider_id','handicap']].assign(actual_direction='W',spf_sp=2.,status='COMPLETE').to_dict('records'))
    receipt=dict(issues=['001','002'],source_hashes=sources,implementation={})
    raw=json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))).encode();(origin/'plans-frozen.json').write_bytes(raw)
    auditpath=origin/'audit.json';auditpath.write_text(json.dumps(dict(rows=audit)))
    er=dict(freeze_sha256=hashlib.sha256(raw).hexdigest(),audit_path=str(auditpath),audit_sha256=hashlib.sha256(auditpath.read_bytes()).hexdigest())
    (origin/'evaluation-receipt.json').write_text(json.dumps(er))
    config=tmp_path/'config.json';config.write_text(json.dumps(cfg));output=tmp_path/'out'
    class ImmediateExecutor:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def submit(self,fn,*args,**kwargs):
            f=concurrent.futures.Future();f.set_result(fn(*args,**kwargs));return f
    monkeypatch.setattr(concurrent.futures,'ProcessPoolExecutor',ImmediateExecutor)
    monkeypatch.setattr(src.temporal_learning,'verify_implementation_closure',lambda *args:None)
    monkeypatch.setattr(src.temporal_learning.provenance,'implementation_closure',lambda *args,**kwargs:{})
    monkeypatch.setattr(sys,'argv',['runner','--output',str(output),'--config',str(config)])
    runpy.run_module('scripts.replay_n7_sleeves',run_name='__main__')
    monkeypatch.setattr(sys,'argv',['checker','--study',str(output)])
    runpy.run_module('scripts.check_n7_sleeves',run_name='__main__')
    proof=json.loads((output/'independent-replay.json').read_text())
    assert proof['checked']==22 and len(proof['diagnostics'])==2
    original=(output/'results.json').read_text()
    evaluation=json.loads((output/'evaluation-receipt.json').read_text())
    # A fully resealed old 1/64 mean must fail semantic replay, not just hashing.
    pp=next((output/'plans').glob('*_8x64_PROB.json.gz'))
    saved_plan=pp.read_bytes();saved_freeze=(output/'plans-frozen.json').read_bytes()
    saved_er=(output/'evaluation-receipt.json').read_bytes()
    plan=json.loads(gzip.decompress(saved_plan));plan['mean_coverage']/=64
    plan['seal']=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
    raw=gzip.compress(json.dumps(plan).encode());pp.write_bytes(raw)
    freeze=json.loads(saved_freeze);freeze['receipt']['plan_hashes'][str(pp)]=hashlib.sha256(raw).hexdigest()
    freeze['seal']=stable_json_hash(freeze['receipt']);raw=json.dumps(freeze).encode()
    (output/'plans-frozen.json').write_bytes(raw)
    changed=json.loads(original);changed['freeze_seal']=freeze['seal'];rr=json.dumps(changed).encode()
    (output/'results.json').write_bytes(rr)
    er2=dict(evaluation,freeze_sha256=hashlib.sha256(raw).hexdigest(),result_sha256=hashlib.sha256(rr).hexdigest())
    (output/'evaluation-receipt.json').write_text(json.dumps(er2))
    with pytest.raises(ValueError,match='Sleeve-level mean coverage'):
        runpy.run_module('scripts.check_n7_sleeves',run_name='__main__')
    pp.write_bytes(saved_plan);(output/'plans-frozen.json').write_bytes(saved_freeze)
    (output/'results.json').write_text(original);(output/'evaluation-receipt.json').write_bytes(saved_er)
    for field in ('gross','fixture_hhi','eval_coverage','decision_year'):
        changed=json.loads(original);changed['rows'][0][field]='2099' if field=='decision_year' else changed['rows'][0][field]+1
        raw=json.dumps(changed).encode();(output/'results.json').write_bytes(raw)
        evaluation['result_sha256']=hashlib.sha256(raw).hexdigest()
        (output/'evaluation-receipt.json').write_text(json.dumps(evaluation))
        with pytest.raises(ValueError):runpy.run_module('scripts.check_n7_sleeves',run_name='__main__')
    # Rehash an internally consistent artifact chain while leaving the original
    # fixture source unchanged: the checker must still reject identity drift.
    frozen=json.loads((output/'plans-frozen.json').read_text())
    bp=output/'bundles'/'001.json.gz';bundle=json.loads(gzip.decompress(bp.read_bytes()))
    e=bundle['sleeves'][0]['enumeration'];e['fixtures'][0]['provider_id']='wrong-provider'
    e['seal']=stable_json_hash({k:v for k,v in e.items() if k!='seal'})
    for option in bundle['sleeves'][0]['options'].values():
        option['enumeration_seal']=e['seal'];option['seal']=stable_json_hash({k:v for k,v in option.items() if k!='seal'})
    bundle['seal']=stable_json_hash({k:v for k,v in bundle.items() if k!='seal'})
    raw=gzip.compress(json.dumps(bundle).encode());bp.write_bytes(raw)
    frozen['receipt']['bundle_hashes'][str(bp)]=hashlib.sha256(raw).hexdigest()
    for path in frozen['receipt']['plan_hashes']:
        plan=json.loads(gzip.decompress(Path(path).read_bytes()))
        if plan['issue']!='001':continue
        plan['bundle_seal']=bundle['seal'];plan['seal']=stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
        raw=gzip.compress(json.dumps(plan).encode());Path(path).write_bytes(raw)
        frozen['receipt']['plan_hashes'][path]=hashlib.sha256(raw).hexdigest()
    frozen['seal']=stable_json_hash(frozen['receipt']);raw=json.dumps(frozen).encode();(output/'plans-frozen.json').write_bytes(raw)
    evaluation['freeze_sha256']=hashlib.sha256(raw).hexdigest()
    changed=json.loads(original);changed['freeze_seal']=frozen['seal'];raw=json.dumps(changed).encode();(output/'results.json').write_bytes(raw)
    evaluation['result_sha256']=hashlib.sha256(raw).hexdigest();(output/'evaluation-receipt.json').write_text(json.dumps(evaluation))
    with pytest.raises(ValueError,match='Enumeration fixture identity'):
        runpy.run_module('scripts.check_n7_sleeves',run_name='__main__')
