"""Build unchanged candidate universes from explicit frozen research predictions."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from src.n7_study_model_contract import verify_n7_frozen_model
from src.n7_study_scope import n7_study_scope
from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_candidates import build_sleeve_candidates
from src.probability_foundation_draw import predict_draw_foundation
from src.temporal_learning import Cutoff, verify_implementation_closure
from src.temporal_learning.provenance import implementation_closure
from src.temporal_learning.core import stable_json_hash


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('predictions','predictions-sha256','config','config-sha256','repository-root','output','reference-model','scope-manifest','scope-sha256'):
        cli.add_argument('--'+name,required=True)
    cli.add_argument('--workers',type=int,required=True)
    args=cli.parse_args()
    if not 1<=args.workers<=8:raise ValueError('Explicit bounded workers required')
    root=Path(args.repository_root).resolve();out=Path(args.output).resolve()
    if out.exists():raise ValueError('Output already exists')
    sources={str(Path(args.predictions).resolve()):args.predictions_sha256,
             str(Path(args.config).resolve()):args.config_sha256}
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Input changed')
    pred=json.loads(Path(args.predictions).read_text());cfg=json.loads(Path(args.config).read_text())
    for path,digest in {**pred['source_hashes'],**{str(root/p):h for p,h in cfg['configs'].items()}}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Inherited input changed')
        sources[path]=digest
    reference_path=Path(args.reference_model).resolve()
    reference_raw=reference_path.read_bytes()
    reference_sha=hashlib.sha256(reference_raw).hexdigest()
    if reference_sha!=cfg['model']['reference_model_sha256']:raise ValueError('Reference model hash mismatch')
    reference=json.loads(reference_raw);sources[str(reference_path)]=reference_sha
    scope_path=Path(args.scope_manifest).resolve();scope_raw=scope_path.read_bytes()
    if hashlib.sha256(scope_raw).hexdigest()!=args.scope_sha256:raise ValueError('Scope manifest hash mismatch')
    declared=json.loads(scope_raw)['issues'];sources[str(scope_path)]=args.scope_sha256
    if (pred['issue_order']!=declared or len(declared)!=cfg['scope']['issue_count'] or
            declared[0]!=cfg['scope']['first'] or declared[-1]!=cfg['scope']['last']):
        raise ValueError('Requested inventory differs from declared study scope')
    candidate_cfg=json.loads((root/'config/n7_sleeve_424.json').read_text())
    if (cfg['n'],cfg['budget_cny'],cfg['unit_cny'],cfg['payout_factor'])!=(7,1024,2,.65):
        raise ValueError('Fixed study money contract differs')
    frame=pd.DataFrame(pred['rows'],columns=['issue','slot','provider_id','handicap',
        'fixture_decision_ts','q_W','q_D','q_L','new_W','new_D','new_L'])
    issues=[i for i in pred['issue_order'] if i in pred['models']]
    coverage={r['issue']:r['status'] for r in pred['publication_coverage']}
    unavailable={i:('NO_USABLE_MARKET_PROBABILITIES' if coverage[i]=='PUBLISHED_DETAIL_VERIFIED'
                    else coverage[i]) for i in pred['issue_order'] if i not in pred['models']}
    scope=n7_study_scope(pred['issue_order'],issues,unavailable)
    if set(frame.issue)!=set(issues):raise ValueError('Prediction scope mismatch')
    for issue in issues:
        entry=pred['models'][issue];mp=Path(entry['path']);raw=mp.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Frozen model changed')
        sources[str(mp)]=entry['sha256'];model=json.loads(raw);x=frame[frame.issue==issue]
        verify_n7_frozen_model(model,reference,cfg['model'],reference_sha256=reference_sha)
        cutoff=Cutoff.decision_epoch(issue,model['receipt']['cutoff_ts'])
        checked=predict_draw_foundation(model,x[['issue','slot','provider_id','handicap','fixture_decision_ts','q_W','q_D','q_L']],cutoff,repository_root=root)
        if not np.allclose(checked[['new_W','new_D','new_L']],x[['new_W','new_D','new_L']],atol=1e-14,rtol=0):
            raise ValueError('Frozen prediction replay differs')
    implementation=implementation_closure(root,('scripts.build_n7_next100_candidates',),distributions=('numpy','pandas','scipy'))
    out.mkdir();(out/'pools').mkdir();(out/'bundles').mkdir()
    pool_hashes={};bundle_hashes={};cuts={};pool_jobs={};bundle_jobs={}
    with ProcessPoolExecutor(max_workers=args.workers) as workers:
        for issue in issues:
            x=frame[frame.issue==issue]
            cuts[issue]={str(r.slot):Cutoff.decision_epoch(issue,r.fixture_decision_ts) for r in x.itertuples()}
            values=x[['issue','slot','provider_id','handicap','new_W','new_D','new_L','q_W','q_D','q_L']].rename(columns={f'new_{d}':f'p_{d}' for d in 'WDL'})
            pool_jobs[workers.submit(probability_gate_candidates,values,cutoffs=cuts[issue],n=cfg['n'],**cfg['pool'])]=issue
        for job in as_completed(pool_jobs):
            issue=pool_jobs.pop(job);pool=job.result();path=out/'pools'/f'{issue}.json.gz'
            path.write_bytes(gzip.compress(json.dumps(pool,sort_keys=True).encode(),mtime=0));pool_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            kwargs={k:candidate_cfg[k] for k in ('candidate_count','maximum_attempts','frontier_points','solver_seconds','solver_relative_gap','solver_feasibility_tolerance','budget_cny','unit_cny','payout_factor')}
            bundle_jobs[workers.submit(build_sleeve_candidates,pool,cutoffs=cuts[issue],seed=candidate_cfg['candidate_seed'],**kwargs)]=issue
            print('Pool complete',issue,flush=True)
            del pool,job
        for job in as_completed(bundle_jobs):
            issue=bundle_jobs.pop(job);bundle=job.result();path=out/'bundles'/f'{issue}.json.gz'
            path.write_bytes(gzip.compress(json.dumps(bundle,sort_keys=True).encode(),mtime=0));bundle_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            print('Candidates complete',issue,bundle['actual_candidate_count'],flush=True)
            del bundle,job
    verify_implementation_closure(root,implementation)
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during build')
    receipt=dict(issues=scope['modeled_issues'],requested_issues=scope['requested_issues'],
        unavailable=unavailable,publication_coverage=pred['publication_coverage'],
        source_hashes=sources,pool_hashes=pool_hashes,bundle_hashes=bundle_hashes,implementation=implementation,
        historical_admission=False,state='CANDIDATES_ONLY_NO_TICKETS_OR_SETTLEMENT',
        full_scope_available=len(issues)==len(pred['issue_order']))
    (out/'candidate-manifest.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
