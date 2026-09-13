"""Build unchanged candidate universes from explicit frozen research predictions."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from src.n7_probability_gate import probability_gate_candidates
from src.n7_sleeve_candidates import build_sleeve_candidates
from src.probability_foundation_draw import predict_draw_foundation
from src.temporal_learning import Cutoff, verify_implementation_closure
from src.temporal_learning.provenance import implementation_closure
from src.temporal_learning.core import stable_json_hash


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    for name in ('predictions','predictions-sha256','config','config-sha256','repository-root','output'):
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
    candidate_cfg=json.loads((root/'config/n7_sleeve_424.json').read_text())
    if (cfg['n'],cfg['budget_cny'],cfg['unit_cny'],cfg['payout_factor'])!=(7,1024,2,.65):
        raise ValueError('Fixed study money contract differs')
    frame=pd.DataFrame(pred['rows']);issues=[i for i in pred['issue_order'] if i in pred['models']]
    if set(frame.issue)!=set(issues):raise ValueError('Prediction scope mismatch')
    for issue in issues:
        entry=pred['models'][issue];mp=Path(entry['path']);raw=mp.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=entry['sha256']:raise ValueError('Frozen model changed')
        sources[str(mp)]=entry['sha256'];model=json.loads(raw);x=frame[frame.issue==issue]
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
    receipt=dict(issues=issues,requested_issues=pred['issue_order'],publication_coverage=pred['publication_coverage'],
        source_hashes=sources,pool_hashes=pool_hashes,bundle_hashes=bundle_hashes,implementation=implementation,
        historical_admission=False,state='CANDIDATES_ONLY_NO_TICKETS_OR_SETTLEMENT',
        full_scope_available=len(issues)==len(pred['issue_order']))
    (out/'candidate-manifest.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
