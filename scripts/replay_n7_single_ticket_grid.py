"""Fixed27-cell x5-seed all-single replay, plans frozen before audited labels."""
import argparse,gzip,hashlib,json,itertools,io
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.n7_single_ticket_sampling import single_ticket_plan,settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);args=cli.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    origin=Path('data/derived/fundamentals_417/market-foundation-n7-v1')
    implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_single_ticket_grid'],distributions=['numpy','pandas','scipy'])
    origin_bytes=(origin/'plans-frozen.json').read_bytes();frozen=json.loads(origin_bytes);r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal'];verify_implementation_closure(Path.cwd(),r['implementation'])
    sources={**r['source_hashes'],**r['plan_hashes'],str(origin/'plans-frozen.json'):hashlib.sha256(origin_bytes).hexdigest()}
    for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    prediction_path='data/derived/fundamentals_417/market-balance-draw-v1/predictions.csv'
    prediction_bytes=Path(prediction_path).read_bytes();assert hashlib.sha256(prediction_bytes).hexdigest()==sources[prediction_path]
    data=pd.read_csv(io.BytesIO(prediction_bytes),dtype={'issue':str,'provider_id':str})
    seeds=[41901,41902,41903,41904,41905]
    variants={f'T{int(t*100):02d}_A{a}_B{b}':(t,a,b) for t,a,b in itertools.product((0.,.20,.25),(1,2,4),(1,2,4))}
    hashes={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for ordinal,issue in enumerate(r['issues'],1):
            x=data[data.issue==issue]
            frame=x[['issue','slot','provider_id','handicap','new_W','new_D','new_L','q_W','q_D','q_L']].rename(columns={f'new_{d}':f'p_{d}' for d in 'WDL'})
            base_path=origin/'plans'/f'{issue}_CAL_U3.json.gz';base_bytes=base_path.read_bytes()
            assert hashlib.sha256(base_bytes).hexdigest()==sources[str(base_path)]
            base=json.loads(gzip.decompress(base_bytes))
            cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()};jobs={}
            for seed in seeds:
                for policy,(tau,alpha,beta) in variants.items():
                    jobs[pool.submit(single_ticket_plan,frame,cutoffs=cuts,seed=seed,third_threshold=tau,
                        outcome_power=alpha,fixture_power=beta,max_attempts=4096,budget_cny=1024,unit_cny=2,payout_factor=.65)]=(seed,policy)
            for job in as_completed(jobs):
                seed,policy=jobs.pop(job);plan=job.result();path=out/'plans'/f'{issue}_{seed}_{policy}.json.gz'
                path.write_bytes(gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            if ordinal%10==0:print(f'Frozen candidate files: {ordinal}/100 issues',flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    receipt=dict(issues=r['issues'],seeds=seeds,variants=variants,ev_record_only=True,source_hashes=sources,plan_hashes=hashes,
        historical_admission=False,parameters=dict(max_attempts=4096,budget_cny=1024,unit_cny=2,payout_factor=.65),
        implementation=implementation)
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt));(out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    print(f'All {len(hashes)} plans frozen before settlement',flush=True)
    audit_path=Path('data/derived/fundamentals_417/updated100-strategies-v1/settlement-audit.json')
    audit_bytes=audit_path.read_bytes();audit_path=out/'audit-snapshot.json';audit_path.write_bytes(audit_bytes)
    audit=pd.DataFrame(json.loads(audit_bytes)['rows']);audit.issue=audit.issue.astype(str)
    rows=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for ordinal,issue in enumerate(r['issues'],1):
            jobs={}
            for seed in seeds:
                for policy in variants:
                    path=out/'plans'/f'{issue}_{seed}_{policy}.json.gz';raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==hashes[str(path)]
                    plan=json.loads(gzip.decompress(raw))
                    jobs[pool.submit(settle_single_tickets,plan,audit[audit.issue==issue])]=(seed,policy,plan)
            for job in as_completed(jobs):
                seed,policy,p=jobs.pop(job);z=job.result();assert z['status'] in ('COMPLETE','NO_BET')
                tau,alpha,beta=variants[policy]
                rows.append(dict(issue=issue,model=policy,policy=str(seed),tau=tau,alpha=alpha,beta=beta,
                    stake=z['stake'],gross=z['gross'],net=z['net'],groups=z['groups'],hits=z['hits'],
                    attempts=p['attempts'],duplicates=p['duplicates'],max_reuse=p['max_reuse'],
                    mean_coverage=p['mean_coverage'],expected_roi=p['expected_roi']))
            if ordinal%10==0:print(f'Settled: {ordinal}/100 issues',flush=True)
    control_bytes=(origin/'results.json').read_bytes();control_path=out/'controls-snapshot.json';control_path.write_bytes(control_bytes)
    prior=json.loads(control_bytes)
    controls=[dict(issue=z['issue'],model=z['policy'],policy='CONTROL',stake=z['stake'],gross=z['gross'],net=z['net'],
        groups=z['groups'],hits=z['hits']) for z in prior['rows'] if z['policy'].startswith('CAL')]
    assert len(controls)==200
    verify_implementation_closure(Path.cwd(),implementation)
    payload=dict(rows=sorted(rows,key=lambda z:(z['model'],z['policy'],z['issue'])),controls=controls,issue_order=r['issues'],freeze_seal=freeze['seal'])
    (out/'results.json').write_text(json.dumps(payload))
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        audit_path=str(audit_path),audit_sha256=hashlib.sha256(audit_bytes).hexdigest(),
        controls_path=str(control_path),controls_sha256=hashlib.sha256(control_bytes).hexdigest(),
        result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())))
    print(json.dumps(dict(rows=len(rows),controls=len(controls))))
