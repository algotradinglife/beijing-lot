"""Freeze updated-period tickets before opening authoritative R/SQLite settlement."""
import argparse,gzip,hashlib,json,subprocess,sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_updated_freeze import freeze_updated_issue
from src.fundamentals_home_away import roster_observed_results
from src.fundamentals_n7_baseline import settle_n7_baseline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);p.add_argument('--db');a=p.parse_args();out=Path(a.study)
    fp=out/'factors.json';data=json.loads(fp.read_text());frame=pd.DataFrame(data['rows'])
    if a.phase=='freeze':
        if (out/'plans').exists():raise FileExistsError('Immutable plans required')
        prepared=json.loads((out/'prepared.json').read_text())
        assert stable_json_hash(prepared['receipt'])==prepared['seal']
        verify_implementation_closure(Path.cwd(),prepared['receipt']['implementation'])
        hashes={**data['source_hashes'],**data['implementation'],str(fp):hashlib.sha256(fp.read_bytes()).hexdigest()}
        verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        old=Path('data/derived/fundamentals_417/n5-single10-u3-mix-v1')
        witness=json.loads((old/'plans-frozen.json').read_text());assert hashlib.sha256(witness['canonical_json'].encode()).hexdigest()==witness['seal']
        assert hashlib.sha256((old/'results.json').read_bytes()).hexdigest()==json.loads(witness['canonical_json'])['result_sha256']
        hashes.update({str(old/f):hashlib.sha256((old/f).read_bytes()).hexdigest() for f in ('results.json','plans-frozen.json')})
        reports=['quarto/120_updated_strategy_comparison.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
        r=dict(issues=data['issues'],seeds=list(range(100)),source_hashes=hashes,plan_hashes={},
            parameters=dict(budget_cny=1024,unit_cny=2,payout_factor=.65),historical_admission=False,learning='NONE',
            implementation=implementation_closure(Path.cwd(),['scripts.replay_updated_strategies'],distributions=['numpy','pandas','scipy']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
        (out/'plans').mkdir();(out/'contract.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        with ProcessPoolExecutor(max_workers=4) as pool:
            pending={}
            for issue in r['issues']:
                current=frame[frame.issue==issue];cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in current.slot}
                job=pool.submit(freeze_updated_issue,current,cutoffs=cuts,seeds=r['seeds'],output_path=out/'plans'/(issue+'.json.gz'),**r['parameters']);pending[job]=issue
            for job in as_completed(pending):
                result=job.result();r['plan_hashes'][result['path']]=result['sha256'];print('FROZEN',pending[job],result['policies'],flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        # The authoritative R query only accepts a pre-existing freeze marker.
        (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        labels=[]
        for issue in r['issues']:
            current=frame[frame.issue==issue]
            if current.empty:continue
            inp=json.loads(gzip.decompress((out/'inputs'/(issue+'.json.gz')).read_bytes()))
            actual={o['slot']:o for o in roster_observed_results(inp['roster_path'],issue=issue,slots=list(map(int,current.slot)))}
            for z in current.to_dict('records'):
                o=actual[z['slot']];assert o['provider_id']==z['provider_id']
                labels.append(dict(**{k:z[k] for k in ('issue','slot','provider_id','handicap','home','away')},**{k:o[k] for k in ('actual_home','actual_away','result_state')}))
        (out/'labels.json').write_text(json.dumps(labels));subprocess.run(['Rscript','--vanilla','scripts/query_clean_validation.R',str(out),a.db],check=True)
        audit_path=out/'settlement-audit.json';audit=pd.DataFrame(json.loads(audit_path.read_text())['rows']);rows=[]
        policies=['N5_NO_SWAP','N6_NO_SWAP','U3_BASELINE','U6_BASELINE']+[f'{prefix}{s:03}' for s in r['seeds'] for prefix in ('N5_S','N5_SWAP_S','N6_S','MIX_S')]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/(issue+'.json.gz')).read_bytes()))['plans'];cache={};observed=audit[audit.issue==issue]
            for policy in policies:
                plan=plans.get(policy);parts=[] if plan is None else [c['plan'] if policy.startswith('MIX') else c for c in plan['components']]
                z=[]
                for part in parts:
                    if part['seal'] not in cache:cache[part['seal']]=settle_n7_baseline(part,observed)
                    z.append(cache[part['seal']])
                complete=all(x['status']=='COMPLETE' for x in z)
                gross=sum(x['gross'] for x in z) if complete else None;stake=plan['stake'] if plan else 0
                seed=int(policy[-3:]) if '_S' in policy and not policy.endswith('SWAP') else None
                source='MIX' if policy.startswith('MIX') else 'N5_25' if policy.startswith('N5_SWAP_S') else 'N5' if policy.startswith('N5') else 'N6' if policy.startswith('N6') else policy
                rows.append(dict(issue=issue,policy=policy,source_policy=source,seed=seed,stake=stake,gross=gross,net=None if gross is None else gross-stake,
                    groups=len(parts),hits=sum(x['hits'] for x in z) if complete else None,status='NO_BET' if not parts else 'COMPLETE' if complete else 'PENDING',budget_cny=1024,cash_cny=1024-stake))
            print('SETTLED',issue,flush=True)
        old=json.loads(Path('data/derived/fundamentals_417/n5-single10-u3-mix-v1/results.json').read_text())
        readiness=json.loads((out/'prepared.json').read_text())['readiness']
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],seeds=r['seeds'],prior_rows=old['rows']+old['controls'],prior_issue_order=old['issue_order'],readiness=readiness,upstream_freeze_seal=frozen['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],str(audit_path):hashlib.sha256(audit_path.read_bytes()).hexdigest()},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
