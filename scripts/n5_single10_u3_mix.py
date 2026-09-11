"""Freeze complete-group equal-wallet N5single10/U3 portfolios, then settle."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_missed_portfolio import flatten_component_groups,fixed_n67_wallets
from src.fundamentals_n7_baseline import settle_n7_baseline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    root=Path('data/derived/fundamentals_417');five=root/'n5-n6-single10-v1';seven=root/'double-source-v1';prior=root/'n5-single-swaps-v1'
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('New immutable output required')
        hashes={};orders=[]
        for source in (five,seven):
            f=json.loads((source/'frozen.json').read_text());r=f['receipt'];assert f['seal']==stable_json_hash(r)
            orders.append(r['issues']);hashes.update({**r['source_hashes'],**r['plan_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()})
        assert orders[0]==orders[1]
        for source in (five,seven,prior):
            w=json.loads((source/'plans-frozen.json').read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];body=json.loads(w['canonical_json'])
            hashes[str(source/'results.json')]=body['result_sha256']
            hashes[str(source/'plans-frozen.json')]=hashlib.sha256((source/'plans-frozen.json').read_bytes()).hexdigest()
        verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        reports=['quarto/119_n5_single10_u3_mix.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
        r=dict(issues=orders[0],seeds=list(range(100)),wallets=dict(N5=512,U3=512),constants=dict(budget_cny=1024,unit_cny=2,payout_factor=.65),
            source_hashes=hashes,plan_hashes={},historical_admission=False,
            implementation=implementation_closure(Path.cwd(),['scripts.n5_single10_u3_mix'],distributions=['numpy','pandas']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
        (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        for issue in r['issues']:
            n5=json.loads(gzip.decompress((five/'plans'/f'{issue}.json.gz').read_bytes()))
            n7=json.loads(gzip.decompress((seven/'plans'/f'{issue}.json.gz').read_bytes()))['U3_BASELINE']
            cuts={s:Cutoff.decision_epoch(issue,t) for s,t in n7['cutoffs'].items()}
            flat7=flatten_component_groups(n7,cutoffs=cuts,n=7,**r['constants']);plans={}
            for seed in r['seeds']:
                flat5=flatten_component_groups(n5[f'N5_S{seed:03}'],cutoffs=cuts,n=5,**r['constants'])
                plans[str(seed)]=fixed_n67_wallets(dict(N5=flat5,U3=flat7),cutoffs=cuts,wallets=r['wallets'],**r['constants'])
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plans).encode(),compresslevel=1,mtime=0));r['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
            print('FROZEN',issue,plans['0']['stake'],flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        f=json.loads((out/'frozen.json').read_text());r=f['receipt'];assert f['seal']==stable_json_hash(r)
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        w=json.loads(json.loads((seven/'plans-frozen.json').read_text())['canonical_json'])
        hashes={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(hashes)==1;verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(iter(hashes))).read_text())['rows'])
        controls=json.loads((five/'results.json').read_text())['rows']
        old=json.loads((prior/'results.json').read_text());controls += [dict(x,source_policy='N5_25') for x in old['rows'] if x['policy'].startswith('N5_SWAP_S')]
        controls += [dict(x,source_policy=x['policy']) for x in old['controls'] if x['policy'] in ('U3_BASELINE','U6_BASELINE')]
        rows=[]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));current=audit[audit.issue==issue];cache={}
            for seed,plan in plans.items():
                assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
                settled=[]
                for part in plan['components']:
                    key=part['plan']['seal']
                    if key not in cache:cache[key]=settle_n7_baseline(part['plan'],current)
                    settled.append(cache[key])
                assert all(x['status']=='COMPLETE' for x in settled)
                gross=sum(x['gross'] for x in settled);hits=sum(x['hits'] for x in settled)
                rows.append(dict(issue=issue,policy=f'MIX_S{int(seed):03}',source_policy='MIX',seed=int(seed),status='COMPLETE' if settled else 'NO_BET',
                    groups=len(settled),hits=hits,stake=plan['stake'],gross=gross,net=gross-plan['stake'],budget_cny=1024,cash_cny=plan['cash_cny'],
                    n5_stake=sum(c['plan']['stake'] for c in plan['components'] if c['source']=='N5'),
                    u3_stake=sum(c['plan']['stake'] for c in plan['components'] if c['source']=='U3')))
            print('SETTLED',issue,flush=True)
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,controls=controls,issue_order=r['issues'],seeds=r['seeds'],upstream_freeze_seal=f['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=f['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**hashes},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
