"""Orchestrate nested Top64 expansion; freeze all plans before settlement access."""
import argparse,gzip,hashlib,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import pandas as pd
from src.n7_sleeve_expansion import expand_top64,sample_top64
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True)
    cli.add_argument('--config',default='config/n7_sleeve_expansion.json');args=cli.parse_args()
    cfgraw=Path(args.config).read_bytes();cfg=json.loads(cfgraw)
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    (out/'bundles').mkdir();(out/'plans').mkdir()
    origin=Path(cfg['origin']);old=Path(cfg['prior_study'])
    sources={args.config:hashlib.sha256(cfgraw).hexdigest()};receipts=[]
    for base in (origin,old):
        path=base/'plans-frozen.json';raw=path.read_bytes();fr=json.loads(raw)
        if fr['seal']!=stable_json_hash(fr['receipt']):raise ValueError('Prior freeze changed')
        verify_implementation_closure(Path.cwd(),fr['receipt']['implementation'])
        sources[str(path)]=hashlib.sha256(raw).hexdigest();receipts.append(fr['receipt'])
    prior,previous=receipts;issues=prior['issues']
    if previous['issues']!=issues:raise ValueError('Mismatched issue universes')
    implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_sleeve_expansion'],distributions=['numpy','pandas','scipy'])
    money={k:cfg[k] for k in ('budget_cny','unit_cny','payout_factor')}
    bundles={};plans={};candidate_rows=[]
    with ProcessPoolExecutor(max_workers=cfg['workers']) as executor:
        for offset in range(0,len(issues),cfg['workers']):
            jobs={}
            for issue in issues[offset:offset+cfg['workers']]:
                path=Path(cfg['pool_root'])/f'{issue}.json.gz';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
                if digest!=prior['source_hashes'][str(path)]:raise ValueError('Pool changed')
                sources[str(path)]=digest;pool=json.loads(gzip.decompress(raw))
                path=old/'bundles'/f'{issue}.json.gz';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
                if digest!=previous['bundle_hashes'][str(path)]:raise ValueError('Original sleeve bundle changed')
                sources[str(path)]=digest;original=json.loads(gzip.decompress(raw))
                if original['prior_pool_seal']!=pool['seal'] or original['cutoffs']!=pool['cutoffs']:
                    raise ValueError('Original sleeve/pool mismatch')
                groups=[s['fixture_indices'] for s in original['sleeves']]
                if len(groups)!=24:raise ValueError('Expected original24')
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in pool['cutoffs'].items()}
                jobs[executor.submit(expand_top64,pool,cutoffs=cuts,original_groups=groups,
                    candidate_count=max(cfg['pool_sizes']),seed=cfg['candidate_seed'],
                    maximum_attempts=cfg['maximum_attempts'],**money)]=issue
            for job in as_completed(jobs):
                issue=jobs[job];bundle=job.result()
                path=out/'bundles'/f'{issue}.json.gz';raw=gzip.compress(json.dumps(bundle,sort_keys=True).encode(),mtime=0)
                path.write_bytes(raw);bundles[str(path)]=hashlib.sha256(raw).hexdigest()
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in bundle['cutoffs'].items()}
                for size in cfg['pool_sizes']:
                    ss=bundle['sleeves'][:size];eligible=[s for s in ss if s['coverage']>cfg['coverage_floor']]
                    candidate_rows.append(dict(issue=issue,pool_size=size,actual=len(ss),eligible=len(eligible),
                        min_coverage=min(s['coverage'] for s in ss),max_coverage=max(s['coverage'] for s in ss),
                        mean_coverage=sum(s['coverage'] for s in ss)/len(ss)))
                    for weighting in cfg['weightings']:
                        for seed in cfg['seeds']:
                            plan=sample_top64(bundle,cutoffs=cuts,pool_size=size,coverage_floor=cfg['coverage_floor'],
                                weighting=weighting,seed=seed,evaluation_worlds=cfg['evaluation_worlds'],**money)
                            path=out/'plans'/f'{issue}_{size}_{weighting}_{seed}.json.gz'
                            raw=gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0)
                            path.write_bytes(raw);plans[str(path)]=hashlib.sha256(raw).hexdigest()
                print(f'Expanded and frozen {issue}: '+', '.join(f'{r["pool_size"]}:{r["eligible"]} eligible' for r in candidate_rows[-3:]),flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during build')
    expected={str(out/'plans'/f'{i}_{n}_{w}_{s}.json.gz') for i in issues for n in cfg['pool_sizes'] for w in cfg['weightings'] for s in cfg['seeds']}
    if set(plans)!=expected:raise ValueError('Incomplete frozen grid')
    receipt=dict(issues=issues,parameters=cfg,implementation=implementation,source_hashes=sources,
        bundle_hashes=bundles,plan_hashes=plans,historical_admission=False)
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt))
    (out/'plans-frozen.json').write_text(json.dumps(frozen,sort_keys=True))
    print('ALL PLANS FROZEN; opening settlement snapshot',flush=True)
    raw=(origin/'evaluation-receipt.json').read_bytes();old_er=json.loads(raw)
    (out/'prior-evaluation-snapshot.json').write_bytes(raw);prior_receipt_hash=hashlib.sha256(raw).hexdigest()
    if old_er['freeze_sha256']!=sources[str(origin/'plans-frozen.json')]:raise ValueError('Settlement receipt mismatch')
    raw=Path(old_er['audit_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=old_er['audit_sha256']:raise ValueError('Audit changed')
    audit_path=out/'audit-snapshot.json';audit_path.write_bytes(raw)
    audit=pd.DataFrame(json.loads(raw)['rows']);audit.issue=audit.issue.astype(str);rows=[]
    for path,digest in sorted(plans.items()):
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Plan changed')
        p=json.loads(gzip.decompress(raw));z=settle_single_tickets(p,audit[audit.issue==p['issue']])
        if z['status'] not in ('COMPLETE','NO_BET'):raise ValueError('Incomplete settlement')
        rows.append(dict(**z,**p['parameters'],arm=f'POOL{p["parameters"]["pool_size"]}_{p["parameters"]["weighting"]}',
            eligible_count=p['eligible_count'],eval_coverage=p['eval_coverage'],expected_roi=p['expected_roi'],
            selected_mean_coverage=p['selected_mean_coverage'],independent_counterfactual=p['independent_counterfactual']))
    verify_implementation_closure(Path.cwd(),implementation)
    raw=json.dumps(dict(rows=rows,candidates=candidate_rows,issue_order=issues,freeze_seal=frozen['seal'])).encode()
    (out/'results.json').write_bytes(raw)
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256(raw).hexdigest(),audit_path=str(audit_path),audit_sha256=old_er['audit_sha256'],
        prior_receipt_sha256=prior_receipt_hash)))
    print(f'COMPLETE {len(rows)} plans',flush=True)
