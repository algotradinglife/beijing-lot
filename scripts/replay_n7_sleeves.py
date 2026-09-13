"""Freeze #424 sleeves and all portfolios before loading target settlement."""
import argparse,gzip,hashlib,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor,as_completed
import numpy as np
import pandas as pd
from src.n7_sleeve_candidates import build_sleeve_candidates
from src.n7_sleeve_portfolio import sleeve_portfolios
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True)
    cli.add_argument('--config',default='config/n7_sleeve_424.json');args=cli.parse_args()
    cfgraw=Path(args.config).read_bytes();cfg=json.loads(cfgraw)
    if (cfg['n'],cfg['sleeves_per_issue'],cfg['tickets_per_sleeve'])!=(7,8,64):raise ValueError('Fixed N7 8x64 contract required')
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    (out/'bundles').mkdir();(out/'plans').mkdir()
    origin=Path(cfg['origin']);raw=(origin/'plans-frozen.json').read_bytes();prior=json.loads(raw)
    if prior['seal']!=stable_json_hash(prior['receipt']):raise ValueError('Prior freeze changed')
    verify_implementation_closure(Path.cwd(),prior['receipt']['implementation'])
    issues=prior['receipt']['issues'];implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_sleeves'],distributions=['numpy','pandas','scipy'])
    sources={str(origin/'plans-frozen.json'):hashlib.sha256(raw).hexdigest(),args.config:hashlib.sha256(cfgraw).hexdigest()}
    hashes={};bundlehashes={};money={k:cfg[k] for k in ('budget_cny','unit_cny','payout_factor')}
    with ProcessPoolExecutor(max_workers=cfg['candidate_workers']) as executor:
        for offset in range(0,len(issues),cfg['candidate_workers']):
            jobs={}
            for issue in issues[offset:offset+cfg['candidate_workers']]:
                path=Path(cfg['pool_root'])/f'{issue}.json.gz';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
                if digest!=prior['receipt']['source_hashes'][str(path)]:raise ValueError('Probability pool changed')
                sources[str(path)]=digest;pool=json.loads(gzip.decompress(raw))
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in pool['cutoffs'].items()}
                jobs[executor.submit(build_sleeve_candidates,pool,cutoffs=cuts,**money,
                    **{k:cfg[k] for k in ('candidate_count','maximum_attempts','frontier_points','solver_seconds','solver_relative_gap','solver_feasibility_tolerance')},seed=cfg['candidate_seed'])]=issue
            for job in as_completed(jobs):
                issue=jobs[job];bundle=job.result();path=out/'bundles'/f'{issue}.json.gz'
                raw=gzip.compress(json.dumps(bundle,sort_keys=True).encode(),mtime=0);path.write_bytes(raw)
                bundlehashes[str(path)]=hashlib.sha256(raw).hexdigest()
            print(f'Candidate bundles {min(offset+cfg['candidate_workers'],len(issues))}/{len(issues)}',flush=True)
    finished=0;sleeve_rows=[]
    with ProcessPoolExecutor(max_workers=cfg['portfolio_workers']) as executor:
        for issue in issues:
            path=out/'bundles'/f'{issue}.json.gz';raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=bundlehashes[str(path)]:raise ValueError('Bundle changed')
            bundle=json.loads(gzip.decompress(raw));cuts={s:Cutoff.decision_epoch(issue,t) for s,t in bundle['cutoffs'].items()}
            jobs={executor.submit(sleeve_portfolios,bundle,cutoffs=cuts,seed=seed,**money,
                **{k:cfg[k] for k in ('training_worlds','evaluation_worlds','primary_frontier','overlap_penalty','return_union_fraction','return_passes')}):seed for seed in cfg['seeds']}
            for job in as_completed(jobs):
                seed=jobs[job];z=job.result()
                if len(z['plans'])!=len(cfg['arms']) or {p['arm'] for p in z['plans']}!=set(cfg['arms']):raise ValueError('Incomplete arm grid')
                for plan in z['plans']:
                    path=out/'plans'/f'{issue}_{seed}_{plan["arm"]}.json.gz'
                    raw=gzip.compress(json.dumps(plan,sort_keys=True).encode(),mtime=0);path.write_bytes(raw)
                    hashes[str(path)]=hashlib.sha256(raw).hexdigest()
                sleeve_rows.extend(dict(issue=issue,seed=seed,**s) for s in z['sleeve_simulation'])
                finished+=1
            print(f'Frozen portfolios {finished}/{len(issues)*len(cfg["seeds"])}',flush=True)
    verify_implementation_closure(Path.cwd(),implementation)
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Inputs changed during build')
    expected_paths={str(out/'plans'/f'{issue}_{seed}_{arm}.json.gz') for issue in issues for seed in cfg['seeds'] for arm in cfg['arms']}
    if set(hashes)!=expected_paths:raise ValueError('Incomplete freeze grid')
    receipt=dict(issues=issues,requested_issues=list(issues),unavailable={},seeds=cfg['seeds'],parameters=cfg,source_hashes=sources,bundle_hashes=bundlehashes,
        plan_hashes=hashes,implementation=implementation,historical_admission=False)
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt));(out/'plans-frozen.json').write_text(json.dumps(frozen,sort_keys=True))
    print('ALL PLANS FROZEN; opening settlement snapshot',flush=True)
    raw=(origin/'evaluation-receipt.json').read_bytes();old_er=json.loads(raw);(out/'prior-evaluation-snapshot.json').write_bytes(raw)
    if old_er['freeze_sha256']!=sources[str(origin/'plans-frozen.json')]:raise ValueError('Prior settlement receipt mismatch')
    prior_receipt_hash=hashlib.sha256(raw).hexdigest();raw=Path(old_er['audit_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=old_er['audit_sha256']:raise ValueError('Audit snapshot changed')
    audit_path=out/'audit-snapshot.json';audit_path.write_bytes(raw);audit=pd.DataFrame(json.loads(raw)['rows']);audit.issue=audit.issue.astype(str)
    rows=[]
    for path,digest in sorted(hashes.items()):
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Frozen plan changed')
        plan=json.loads(gzip.decompress(raw));a=audit[audit.issue==plan['issue']]
        settled=settle_single_tickets(plan,a)
        if settled['status'] not in ('COMPLETE','NO_BET'):raise ValueError('Incomplete settlement')
        idx=np.array(plan['fixture_indices'],dtype=int).reshape(-1,7)
        codes=np.array(plan['outcomes'],dtype=int).reshape(-1,7)
        uses=np.bincount(idx.ravel(),minlength=len(plan['fixtures']));outcome_uses=np.bincount((3*idx+codes).ravel(),minlength=3*len(plan['fixtures']))
        sets=[set(idx[j*64]) for j in range(8)] if plan['sleeve_keys'] else []
        overlaps=[len(sets[i]&sets[j]) for i in range(len(sets)) for j in range(i)]
        sleeve_uses=[sum(i in g for g in sets) for i in range(len(plan['fixtures']))]
        rows.append(dict(issue=plan['issue'],seed=plan['simulation']['seed'],arm=plan['arm'],status=settled['status'],
            decision_year=min(plan['cutoffs'].values())[:4],stake=settled['stake'],gross=settled['gross'],net=settled['net'],
            hits=settled['hits'],groups=settled['groups'],hit_sleeves=settled['hits'] if sets else None,
            expected_net=plan['expected_net'],expected_roi=plan['expected_roi'],
            train_coverage=plan['simulation']['training_hit_rate'],eval_coverage=plan['simulation']['evaluation_hit_rate'],
            fixture_hhi=float(np.sum((uses/uses.sum())**2)) if uses.sum() else 0.,
            outcome_hhi=float(np.sum((outcome_uses/outcome_uses.sum())**2)) if outcome_uses.sum() else 0.,
            max_overlap=max(overlaps,default=0),max_sleeve_reuse=max(sleeve_uses,default=0),
            physical_ticket_identities=len(idx),no_bet_reason=plan.get('no_bet_reason')))
    verify_implementation_closure(Path.cwd(),implementation)
    raw=json.dumps(dict(rows=rows,issue_order=issues,freeze_seal=frozen['seal'],sleeve_simulation=sleeve_rows)).encode()
    (out/'results.json').write_bytes(raw)
    er=dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),result_sha256=hashlib.sha256(raw).hexdigest(),
        audit_path=str(audit_path),audit_sha256=old_er['audit_sha256'],prior_receipt_sha256=prior_receipt_hash)
    (out/'evaluation-receipt.json').write_text(json.dumps(er));print(f'COMPLETE {len(rows)} plans',flush=True)
