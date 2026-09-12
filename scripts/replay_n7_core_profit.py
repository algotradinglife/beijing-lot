"""Freeze probability-core searches, then settle all four policies."""
import argparse,gzip,hashlib,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.n7_core_profit import core_profit_plans
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);args=cli.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    origin=Path('data/derived/fundamentals_417/n7-profit-periods-v1')
    poolroot=Path('data/derived/fundamentals_417/n7-probability-gate-v2/pools')
    raw=(origin/'plans-frozen.json').read_bytes();frozen=json.loads(raw);r=frozen['receipt']
    if stable_json_hash(r)!=frozen['seal']:raise ValueError('Source freeze changed')
    verify_implementation_closure(Path.cwd(),r['implementation'])
    implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_core_profit'],distributions=['numpy','pandas','scipy'])
    sources={**r['source_hashes'],**r['plan_hashes'],str(origin/'plans-frozen.json'):hashlib.sha256(raw).hexdigest()}
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source bytes changed: '+path)
    hashes={};finished=0
    with ProcessPoolExecutor(max_workers=4) as executor:
        for offset in range(0,len(r['issues']),4):
            jobs={}
            for issue in r['issues'][offset:offset+4]:
                path=poolroot/f'{issue}.json.gz';raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=sources[str(path)]:raise ValueError('Pool changed')
                pool=json.loads(gzip.decompress(raw));cuts={s:Cutoff.decision_epoch(issue,t) for s,t in pool['cutoffs'].items()}
                for seed in r['seeds']:
                    path=origin/'plans'/f'{issue}_{seed}_5_PROFIT.json.gz';raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=sources[str(path)]:raise ValueError('Start changed')
                    old=json.loads(gzip.decompress(raw))
                    jobs[executor.submit(core_profit_plans,pool,old,cutoffs=cuts,seed=seed,
                        training_worlds=20000,evaluation_worlds=50000,core_fractions=[.25,.5,.75],
                        proposal_width=16,joint_attempts=1024,min_probability=.0005,payout_stress=[.8,1.,1.2],
                        budget_cny=1024,unit_cny=2,payout_factor=.65)]=(issue,seed)
            for job in as_completed(jobs):
                issue,seed=jobs.pop(job)
                for plan in job.result():
                    fraction=plan['parameters']['core_fraction'];ranking=plan['parameters']['ranking'];tag=ranking if fraction is None else f'{ranking}_{round(fraction*100)}'
                    path=out/'plans'/f'{issue}_{seed}_{tag}.json.gz'
                    raw=gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0);path.write_bytes(raw);hashes[str(path)]=hashlib.sha256(raw).hexdigest()
                finished+=1
            print(f'Frozen {finished}/300 issue-seed runs',flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    receipt=dict(issues=r['issues'],seeds=r['seeds'],counts=[5],source_hashes=sources,plan_hashes=hashes,
        implementation=implementation,historical_admission=False,
        parameters=dict(training_worlds=20000,evaluation_worlds=50000,core_fractions=[.25,.5,.75],proposal_width=16,joint_attempts=1024,payout_stress=[.8,1.,1.2],
            n=7,budget_cny=1024,unit_cny=2,payout_factor=.65))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt));(out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    print('All 3300 plans frozen before settlement',flush=True)
    raw=(origin/'evaluation-receipt.json').read_bytes();prior_er=json.loads(raw);(out/'prior-evaluation-snapshot.json').write_bytes(raw)
    prior_er_hash=hashlib.sha256(raw).hexdigest()
    if prior_er['freeze_sha256']!=sources[str(origin/'plans-frozen.json')]:raise ValueError('Prior receipt mismatch')
    raw=Path(prior_er['audit_path']).read_bytes();audit_path=out/'audit-snapshot.json';audit_path.write_bytes(raw)
    audit_hash=hashlib.sha256(raw).hexdigest()
    if audit_hash!=prior_er['audit_sha256']:raise ValueError('Prior audit mismatch')
    audit=pd.DataFrame(json.loads(raw)['rows']);audit.issue=audit.issue.astype(str);rows=[]
    for ordinal,issue in enumerate(r['issues'],1):
        for seed in r['seeds']:
            for tag in ['PROB','PROFIT']+[f'{kind}_{frac}' for kind in ('FIXED','GAP','JOINT') for frac in (25,50,75)]:
                path=out/'plans'/f'{issue}_{seed}_{tag}.json.gz';raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=hashes[str(path)]:raise ValueError('Plan changed')
                p=json.loads(gzip.decompress(raw));z=settle_single_tickets(p,audit[audit.issue==issue])
                if z['status'] not in ('COMPLETE','NO_BET'):raise ValueError('Incomplete settlement')
                rows.append(dict(issue=issue,model='C005',policy=f'{tag}_{seed}',tag=tag,
                    ranking=p['parameters']['ranking'],fraction=p['parameters']['core_fraction'],seed=seed,
                    stake=z['stake'],gross=z['gross'],net=z['net'],groups=z['groups'],hits=z['hits'],expected_net=p['expected_net'],
                    train_coverage=p['simulation']['training_hit_rate'],eval_coverage=p['simulation']['evaluation_hit_rate'],
                    train_profit=p['simulation']['training_profit_rate'],eval_profit=p['simulation']['evaluation_profit_rate'],
                    stress_low=p['simulation']['payout_stress'][0]['profit'],stress_high=p['simulation']['payout_stress'][2]['profit'],
                    accepted=p['search'].get('accepted',0)))
        if ordinal%10==0:print(f'Settled {ordinal}/100 issues',flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    raw=json.dumps(dict(rows=rows,issue_order=r['issues'],freeze_seal=freeze['seal'])).encode();(out/'results.json').write_bytes(raw)
    er=dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),result_sha256=hashlib.sha256(raw).hexdigest(),
        audit_path=str(audit_path),audit_sha256=audit_hash,prior_receipt_sha256=prior_er_hash)
    (out/'evaluation-receipt.json').write_text(json.dumps(er));print('Completed 3300 plans',flush=True)
