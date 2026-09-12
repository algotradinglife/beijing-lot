"""Freeze variable-depth cap plans beside immutable fixed64 controls."""
import argparse,gzip,hashlib,json
from pathlib import Path
import pandas as pd
from src.n7_sleeve_probability_cap import sample_capped_sleeves
from src.n7_single_ticket_sampling import settle_single_tickets
from src.temporal_learning import Cutoff,verify_implementation_closure
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    cli=argparse.ArgumentParser();cli.add_argument('--output',required=True)
    cli.add_argument('--config',default='config/n7_sleeve_probability_cap.json');args=cli.parse_args()
    cfgraw=Path(args.config).read_bytes();cfg=json.loads(cfgraw);origin=Path(cfg['origin'])
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False);(out/'plans').mkdir()
    raw=(origin/'plans-frozen.json').read_bytes();parent=json.loads(raw);fr=parent['receipt']
    if parent['seal']!=stable_json_hash(fr):raise ValueError('Parent freeze changed')
    for key in ('model','seeds','coverage_floor','evaluation_worlds','budget_cny','unit_cny','payout_factor'):
        if cfg[key]!=fr['parameters'][key]:raise ValueError(f'Control/cap contract differs: {key}')
    if not cfg['pool_sizes'] or not set(cfg['pool_sizes'])<=set(fr['parameters']['pool_sizes']):raise ValueError('Unknown candidate pool')
    if not cfg['policies'] or len({p['arm'] for p in cfg['policies']})!=len(cfg['policies']) or any(p['arm']=='FIXED64' for p in cfg['policies']):raise ValueError('Invalid policy grid')
    verify_implementation_closure(Path.cwd(),fr['implementation'])
    irraw=(origin/'independent-replay.json').read_bytes();ir=json.loads(irraw)
    if ir['freeze']!=parent['seal'] or ir['checked']!=1800 or ir['candidates']!=96000:raise ValueError('Parent not fully checked')
    verify_implementation_closure(Path.cwd(),ir['implementation'])
    sources={args.config:hashlib.sha256(cfgraw).hexdigest(),str(origin/'plans-frozen.json'):hashlib.sha256(raw).hexdigest(),
        str(origin/'independent-replay.json'):hashlib.sha256(irraw).hexdigest(),**fr['source_hashes']}
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Parent source changed')
    implementation=implementation_closure(Path.cwd(),['scripts.replay_n7_sleeve_probability_cap'],distributions=['numpy','pandas','scipy'])
    money={k:cfg[k] for k in ('budget_cny','unit_cny','payout_factor')};entries=[];hashes={};issues=fr['issues']
    for issue in issues:
        path=origin/'bundles'/f'{issue}.json.gz';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest!=fr['bundle_hashes'][str(path)]:raise ValueError('Candidate source changed')
        sources[str(path)]=digest;b=json.loads(gzip.decompress(raw));cuts={s:Cutoff.decision_epoch(issue,t) for s,t in b['cutoffs'].items()}
        for size in cfg['pool_sizes']:
            for seed in cfg['seeds']:
                for policy in cfg['policies']:
                    z=sample_capped_sleeves(b,cutoffs=cuts,pool_size=size,coverage_floor=cfg['coverage_floor'],coverage_cap=cfg['coverage_cap'],
                        seed=seed,evaluation_worlds=cfg['evaluation_worlds'],max_fixture_reuse=policy['max_fixture_reuse'],max_pair_overlap=policy['max_pair_overlap'],**money)
                    path=out/'plans'/f'{issue}_{size}_{seed}_{policy['arm']}.json.gz';raw=gzip.compress(json.dumps(z,sort_keys=True).encode(),mtime=0)
                    path.write_bytes(raw);hashes[str(path)]=hashlib.sha256(raw).hexdigest()
                    entries.append(dict(issue=issue,pool_size=size,seed=seed,arm=policy['arm'],path=str(path)))
                control=origin/'plans'/f'{issue}_{size}_EXPECTED_GROSS_{seed}.json.gz'
                digest=hashlib.sha256(control.read_bytes()).hexdigest()
                if digest!=fr['plan_hashes'][str(control)]:raise ValueError('Fixed64 control changed')
                hashes[str(control)]=digest;entries.append(dict(issue=issue,pool_size=size,seed=seed,arm='FIXED64',path=str(control)))
        print(f'Frozen {issue}: {len(entries)} plans',flush=True)
    if len(entries)!=len(issues)*len(cfg['pool_sizes'])*len(cfg['seeds'])*(len(cfg['policies'])+1):raise ValueError('Incomplete grid')
    for path,digest in {**sources,**hashes}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Input/plan changed during freeze')
    verify_implementation_closure(Path.cwd(),implementation)
    receipt=dict(issues=issues,parameters=cfg,source_hashes=sources,plan_hashes=hashes,entries=entries,
        implementation=implementation,historical_admission=False)
    frozen=dict(receipt=receipt,seal=stable_json_hash(receipt));(out/'plans-frozen.json').write_text(json.dumps(frozen,sort_keys=True))
    print('ALL PLANS FROZEN; opening settlement',flush=True)
    raw=(origin/'evaluation-receipt.json').read_bytes();old_er=json.loads(raw)
    (out/'prior-evaluation-snapshot.json').write_bytes(raw);prior_hash=hashlib.sha256(raw).hexdigest()
    if old_er['freeze_sha256']!=sources[str(origin/'plans-frozen.json')]:raise ValueError('Audit receipt mismatch')
    raw=Path(old_er['audit_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=old_er['audit_sha256']:raise ValueError('Audit changed')
    auditpath=out/'audit-snapshot.json';auditpath.write_bytes(raw);audit=pd.DataFrame(json.loads(raw)['rows']);audit.issue=audit.issue.astype(str)
    rows=[]
    for entry in entries:
        raw=Path(entry['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=hashes[entry['path']]:raise ValueError('Frozen plan changed')
        z=json.loads(gzip.decompress(raw));settled=settle_single_tickets(z,audit[audit.issue==entry['issue']])
        if settled['status'] not in ('COMPLETE','NO_BET'):raise ValueError('Incomplete settlement')
        count=len(z['sleeves']) if entry['arm']!='FIXED64' else len(z['sleeve_ids'])
        rows.append(dict(**settled,arm=entry['arm'],pool_size=entry['pool_size'],seed=entry['seed'],sleeve_count=count,
            eval_coverage=z['eval_coverage'],expected_roi=z['expected_roi'],eligible_count=z['eligible_count'],unspent_reason=z.get('unspent_reason'),
            max_fixture_reuse=max([sum(i in g['fixture_indices'] for g in z['sleeves']) for i in range(len(z['fixtures']))],default=0) if entry['arm']!='FIXED64' else None,
            max_pair_overlap=max([len(set(a['fixture_indices'])&set(b['fixture_indices'])) for j,a in enumerate(z['sleeves']) for b in z['sleeves'][:j]],default=0) if entry['arm']!='FIXED64' else None))
    verify_implementation_closure(Path.cwd(),implementation)
    raw=json.dumps(dict(rows=rows,issue_order=issues,freeze_seal=frozen['seal'])).encode();(out/'results.json').write_bytes(raw)
    (out/'evaluation-receipt.json').write_text(json.dumps(dict(freeze_sha256=hashlib.sha256((out/'plans-frozen.json').read_bytes()).hexdigest(),
        result_sha256=hashlib.sha256(raw).hexdigest(),audit_path=str(auditpath),audit_sha256=old_er['audit_sha256'],prior_receipt_sha256=prior_hash)))
    print(f'COMPLETE {len(rows)} plans',flush=True)
