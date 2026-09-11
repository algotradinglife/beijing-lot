"""Paired replay of existing uncapped N5/N6 groups with 10% single swaps."""
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
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    sources={5:Path('data/derived/fundamentals_417/n5-single-swaps-v1'),6:Path('data/derived/fundamentals_417/n6-uncapped-v1')}
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('New immutable output required')
        hashes={};orders=[]
        for source in sources.values():
            old=json.loads((source/'frozen.json').read_text());r=old['receipt'];assert old['seal']==stable_json_hash(r)
            orders.append(r['issues']);hashes.update({**r['source_hashes'],**r['plan_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()})
        assert orders[0]==orders[1];verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        reports=['quarto/117_n5_n6_single10.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
        r=dict(issues=orders[0],seeds=list(range(100)),parameters=dict(single_probability=.1,double_probability=0,budget_cny=1024,unit_cny=2,payout_factor=.65),
            source_hashes=hashes,plan_hashes={},historical_admission=False,
            implementation=implementation_closure(Path.cwd(),['scripts.n5_n6_single10'],distributions=['numpy','pandas']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
        (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        for issue in r['issues']:
            plans={}
            for n,source in sources.items():
                original=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
                base=original['N5_NO_SWAP'] if n==5 else original
                assert base['seal']==stable_json_hash({k:v for k,v in base.items() if k!='seal'})
                if n==6:
                    base.pop('seal');base['double_source']='BASELINE';base['seal']=stable_json_hash(base)
                plans[f'N{n}_NO_SWAP']=base
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in base['cutoffs'].items()}
                for seed in r['seeds']:plans[f'N{n}_S{seed:03}']=random_reuse_plan(base,cutoffs=cuts,seed=seed,group_size=n,**r['parameters'])
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plans).encode(),compresslevel=1,mtime=0));r['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
            print('FROZEN',issue,flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        f=json.loads((out/'frozen.json').read_text());r=f['receipt'];assert f['seal']==stable_json_hash(r)
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        source=sources[5];w=json.loads((source/'plans-frozen.json').read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
        hashes={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(hashes)==1
        hashes[str(source/'results.json')]=w['result_sha256'];verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(k for k in hashes if k.endswith('settlement-audit.json'))).read_text())['rows'])
        old=json.loads((source/'results.json').read_text());assert old['issue_order']==r['issues']
        old_controls={(x['issue'],'N5_NO_SWAP'):x for x in old['rows'] if x['policy']=='N5_NO_SWAP'}
        old_controls.update({(x['issue'],'N6_NO_SWAP'):x for x in old['controls'] if x['policy']=='N6_UNCAPPED'})
        rows=[]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));current=audit[audit.issue==issue];cache={}
            for policy,plan in plans.items():
                assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
                settled=[]
                for part in plan['components']:
                    if part['seal'] not in cache:cache[part['seal']]=settle_n7_baseline(part,current)
                    settled.append(cache[part['seal']])
                assert all(x['status']=='COMPLETE' for x in settled)
                hits=sum(x['hits'] for x in settled);gross=sum(x['gross'] for x in settled);ledger=plan.get('swap_ledger',[])
                row=dict(issue=issue,policy=policy,source_policy=policy[:2],seed=plan.get('seed'),status='COMPLETE' if settled else 'NO_BET',
                    groups=len(settled),hits=hits,stake=plan['stake'],gross=gross,net=gross-plan['stake'],budget_cny=1024,cash_cny=plan['cash_cny'],
                    eligible_single=sum(l['eligible'] and l['single'] for l in ledger),swapped_single=sum(l['swapped'] and l['single'] for l in ledger),
                    swapped_double=sum(l['swapped'] and not l['single'] for l in ledger))
                if policy.endswith('NO_SWAP'):
                    for k in ('groups','hits','stake','gross','net'):assert abs(row[k]-old_controls[issue,policy][k])<1e-7
                rows.append(row)
            print('SETTLED',issue,len(cache),flush=True)
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],seeds=r['seeds'],upstream_freeze_seal=f['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=f['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**hashes},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('DONE',len(rows))
