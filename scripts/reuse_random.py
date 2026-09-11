"""Predeclare 100 seeds, freeze all repeated-use swaps, then settle separately."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_reuse_random import random_reuse_plan
from src.fundamentals_n7_baseline import settle_n7_baseline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);p.add_argument('--group-size',type=int,choices=[6,7],required=True);a=p.parse_args()
    out=Path(a.study);source=Path('data/derived/fundamentals_417')/('double-source-v1' if a.group_size==7 else 'consensus-n6-n7-v2')
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('New immutable study required')
        old=json.loads((source/'frozen.json').read_text());r=old['receipt'];assert old['seal']==stable_json_hash(r)
        hashes={**r['source_hashes'],**r['plan_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()}
        verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        reports=['quarto/112_reuse_random.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R','r/fundamentals_missed_summary.R']
        receipt=dict(issues=r['issues'],seeds=list(range(100)),parameters=dict(group_size=a.group_size,probability=.3,budget_cny=1024,unit_cny=2,payout_factor=.65),source_hashes=hashes,
            implementation=implementation_closure(Path.cwd(),['scripts.reuse_random'],distributions=['numpy','pandas']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports},historical_admission=False,plan_hashes={})
        (out/'plans').mkdir(parents=True)
        (out/'contract.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        for issue in r['issues']:
            source_plans=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));plans={}
            for policy,base in source_plans.items():
                if a.group_size==6:
                    if not policy.startswith('N6_'):continue
                    policy+='_BASELINE'
                    base.pop('seal');base['double_source']='BASELINE';base['seal']=stable_json_hash(base)
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
                plans[policy]={str(seed):random_reuse_plan(base,cutoffs=cuts,seed=seed,**receipt['parameters']) for seed in receipt['seeds']}
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plans).encode(),compresslevel=1,mtime=0));receipt['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
            print('FROZEN',issue,flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        print('SEALED all seeds before this settlement')
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt'];assert frozen['seal']==stable_json_hash(r)
        assert r['parameters']['group_size']==a.group_size
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        pointer=source/'plans-frozen.json';w=json.loads(pointer.read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
        audit_hashes={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(audit_hashes)==1
        verify_clean_file_bindings(audit_hashes,repository_root=Path.cwd())
        assert hashlib.sha256((source/'results.json').read_bytes()).hexdigest()==w['result_sha256']
        controls=json.loads((source/'results.json').read_text())
        if a.group_size==6:
            controls['rows']=[dict(x,policy=x['policy']+'_BASELINE') for x in controls['rows'] if x['policy'].startswith('N6_')]
        audit=pd.DataFrame(json.loads(Path(next(iter(audit_hashes))).read_text())['rows'])
        rows=[]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));current=audit[audit.issue==issue];cache={}
            for policy,variants in plans.items():
                for seed,plan in variants.items():
                    assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
                    settled=[]
                    for part in plan['components']:
                        # Exact sealed component includes source, cutoff, support, and funding.
                        # Cache exists only inside this issue and implementation invocation.
                        key=part['seal']
                        if key not in cache:cache[key]=settle_n7_baseline(part,current)
                        settled.append(cache[key])
                    assert all(x['status']=='COMPLETE' for x in settled)
                    hits=sum(x['hits'] for x in settled);gross=sum(x['gross'] for x in settled)
                    ledger=plan['swap_ledger']
                    rows.append(dict(issue=issue,source_policy=policy,seed=int(seed),policy=f'{policy}_S{int(seed):03}',
                        status='COMPLETE' if settled else 'NO_BET',groups=len(settled),hits=hits,n6_hits=hits if a.group_size==6 else 0,n7_hits=hits if a.group_size==7 else 0,
                        stake=plan['stake'],gross=gross,net=gross-plan['stake'],budget_cny=1024,cash_cny=plan['cash_cny'],
                        eligible_single=sum(l['eligible'] and l['single'] for l in ledger),eligible_double=sum(l['eligible'] and not l['single'] for l in ledger),
                        swapped_single=sum(l['swapped'] and l['single'] for l in ledger),swapped_double=sum(l['swapped'] and not l['single'] for l in ledger)))
            print('SETTLED',issue,'unique group settlements',len(cache),flush=True)
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,controls=controls['rows'],issue_order=r['issues'],seeds=r['seeds'],group_size=a.group_size,upstream_freeze_seal=frozen['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**audit_hashes,str(source/'results.json'):w['result_sha256']},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('DONE',len(rows))
