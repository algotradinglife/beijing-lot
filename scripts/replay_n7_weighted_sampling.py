"""Freeze fixed multi-seed sampling plans, then settle from bound R/SQLite export."""
import argparse,gzip,hashlib,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.n7_weighted_sampling import weighted_n7_plan
from src.market_conditional_reuse import settle_conditional_reuse
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True);args=cli.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    origin=Path('data/derived/fundamentals_417/market-foundation-n7-v1')
    frozen=json.loads((origin/'plans-frozen.json').read_text());r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal'];verify_implementation_closure(Path.cwd(),r['implementation'])
    sources={**r['source_hashes'],**r['plan_hashes'],str(origin/'plans-frozen.json'):hashlib.sha256((origin/'plans-frozen.json').read_bytes()).hexdigest()}
    for path,digest in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    prediction=Path('data/derived/fundamentals_417/market-balance-draw-v1/predictions.csv')
    data=pd.read_csv(prediction,dtype={'issue':str,'provider_id':str})
    seeds=[41901,41902,41903,41904,41905]
    variants={'BASE':(0.,None,None,'ALLOW')}
    for rate in (.05,.10):
        suffix=f'{int(rate*100):02d}'
        variants.update({f'ANY{suffix}':(rate,None,None,'ALLOW'),
            f'G10_{suffix}':(rate,.10,.10,'GAP'),f'G20_{suffix}':(rate,.20,.20,'GAP'),
            f'SIGNAL{suffix}':(rate,.10,None,'STRENGTH_TOP2'),f'JOINT{suffix}':(rate,.10,.20,'JOINT')})
    jobs={};hashes={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for issue in r['issues']:
            x=data[data.issue==issue]
            frame=x[['issue','slot','provider_id','handicap','new_W','new_D','new_L','q_W','q_D','q_L','p_W','p_D','p_L']].rename(
                columns={**{f'p_{d}':f'strength_{d}' for d in 'WDL'},**{f'new_{d}':f'p_{d}' for d in 'WDL'}})
            base=json.loads(gzip.decompress((origin/'plans'/f'{issue}_CAL_U3.json.gz').read_bytes()))
            cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
            for seed in seeds:
                for policy,(rate,sg,dg,condition) in variants.items():
                    jobs[pool.submit(weighted_n7_plan,frame,cutoffs=cuts,seed=seed,single_threshold=.5,
                        single_alternative_probability=rate,double_alternative_probability=rate,
                        single_gap_limit=sg,double_gap_limit=dg,double_condition=condition,
                        max_attempts=500,single_pool_count=2,budget_cny=1024,unit_cny=2,payout_factor=.65)]=(issue,seed,policy)
        for job in as_completed(jobs):
            issue,seed,policy=jobs[job];plan=job.result();path=out/'plans'/f'{issue}_{seed}_{policy}.json.gz'
            path.write_bytes(gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0));hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    receipt=dict(issues=r['issues'],seeds=seeds,variants=variants,exclusive_pools=True,ev_record_only=True,source_hashes=sources,plan_hashes=hashes,
        historical_admission=False,parameters=dict(single_threshold=.5,max_attempts=500,single_pool_count=2,
            budget_cny=1024,unit_cny=2,payout_factor=.65),
        implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_weighted_sampling'],distributions=['numpy','pandas','scipy']))
    freeze=dict(receipt=receipt,seal=stable_json_hash(receipt));(out/'plans-frozen.json').write_text(json.dumps(freeze,sort_keys=True))
    print(f'All {len(hashes)} plans frozen before settlement',flush=True)
    audit_path=Path('data/derived/fundamentals_417/updated100-strategies-v1/settlement-audit.json')
    audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);audit.issue=audit.issue.astype(str)
    rows=[];jobs={}
    with ProcessPoolExecutor(max_workers=4) as pool:
        for path,digest in hashes.items():
            raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
            plan=json.loads(gzip.decompress(raw));seed=plan['parameters']['seed']
            policy=Path(path).name[:-8].split('_',2)[2]
            jobs[pool.submit(settle_conditional_reuse,plan,audit[audit.issue==plan['issue']])]=(plan,seed,policy)
        for job in as_completed(jobs):
            z=job.result();p,seed,policy=jobs[job];assert z['status'] in ('COMPLETE','NO_BET')
            gm=p['group_metrics']
            observed=audit[audit.issue==p['issue']].set_index('slot').actual_direction.to_dict()
            exposure={}
            for pool_name in ('S','B'):
                holdings=[z for z in p['legs'] if z['pool']==pool_name]
                alt=[z for z in holdings if z['alternative_used']]
                exposure.update({f'{pool_name}_positions':len(holdings),f'{pool_name}_eligible':sum(z['alternative_eligible'] for z in holdings),
                    f'{pool_name}_alternatives':len(alt),f'{pool_name}_alt_hits':sum({'W':'3','D':'1','L':'0'}[observed[z['slot']]] in z['support'] for z in alt)})
            rows.append(dict(issue=p['issue'],model=policy,policy=str(seed),stake=z['stake'],gross=z['gross'],net=z['net'],
                groups=z['groups'],hits=z['hits'],cash=p['cash_cny'],attempts=p['attempts'],
                expected_roi=sum(g['cost']*g['expected_roi'] for g in gm)/p['stake'] if p['stake'] else None,
                mean_coverage=sum(g['coverage'] for g in gm)/len(gm) if gm else None,
                max_reuse=p['max_fixture_reuse'],repeated_elementary=p['repeated_elementary'],
                rejections=p['rejections'],**exposure))
    prior=json.loads((origin/'results.json').read_text())
    controls=[dict(issue=z['issue'],model=z['policy'],policy='CONTROL',stake=z['stake'],gross=z['gross'],net=z['net'],
        groups=z['groups'],hits=z['hits']) for z in prior['rows'] if z['policy'].startswith('CAL')]
    assert len(controls)==200
    control_path=origin/'results.json'
    payload=dict(rows=sorted(rows,key=lambda z:(z['model'],z['policy'],z['issue'])),controls=controls,
        issue_order=r['issues'],freeze_seal=freeze['seal'])
    (out/'results.json').write_text(json.dumps(payload))
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        audit_path=str(audit_path),audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        controls_path=str(control_path),controls_sha256=hashlib.sha256(control_path.read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())))
    print(json.dumps(dict(rows=len(rows),controls=len(controls))))
