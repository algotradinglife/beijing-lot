"""Freeze uncapped N5 base and 100 fixed single-only swap seeds, then settle."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_candidate_exclusion import exclude_zero_top2_disagreement
from src.fundamentals_consensus_portfolio import independent_consensus_portfolio
from src.fundamentals_reuse_random import random_reuse_plan
from src.fundamentals_n7_baseline import settle_n7_baseline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    source=Path('data/derived/fundamentals_417/n6-uncapped-v1');pure=Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json')
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('New immutable output required')
        old=json.loads((source/'frozen.json').read_text());assert old['seal']==stable_json_hash(old['receipt'])
        hashes={**old['receipt']['source_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()}
        assert str(pure) in hashes;verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        data=json.loads(pure.read_text());frame=pd.DataFrame(data['rows'])
        assembly=dict(group_size=5,budget_cny=1024,unit_cny=2,payout_factor=.65,minimum_anchor_market=.5,max_pair_overlap=4,seed=0,conversion_budget_fraction=0,max_uses=64)
        swaps=dict(group_size=5,budget_cny=1024,unit_cny=2,payout_factor=.65,single_probability=.25,double_probability=0)
        reports=['quarto/114_n5_single_swaps.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R']
        r=dict(issues=old['receipt']['issues'],seeds=list(range(100)),assembly=assembly,swaps=swaps,source_hashes=hashes,
            implementation=implementation_closure(Path.cwd(),['scripts.n5_single_swaps'],distributions=['numpy','pandas','scipy']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports},historical_admission=False,
            reuse_policy='NO_BINDING_U_CAP_WITHIN_BUDGET',plan_hashes={},exclusions={})
        (out/'plans').mkdir(parents=True);(out/'contract.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
        for issue in r['issues']:
            current=frame[frame.issue==issue].copy();cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in current.slot}
            current,exclusion=exclude_zero_top2_disagreement(current,cutoffs=cuts);cuts={str(s):cuts[str(s)] for s in current.slot}
            base=independent_consensus_portfolio(current,cutoffs=cuts,**assembly)
            base.pop('seal');base['double_source']='BASELINE';base['seal']=stable_json_hash(base)
            plans={'N5_NO_SWAP':base}
            for seed in r['seeds']:plans[f'N5_SWAP_S{seed:03}']=random_reuse_plan(base,cutoffs=cuts,seed=seed,**swaps)
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plans).encode(),compresslevel=1,mtime=0))
            r['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest();r['exclusions'][issue]=exclusion
            print('FROZEN',issue,len(base['components']),base['stake'],flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=r,seal=stable_json_hash(r))))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        f=json.loads((out/'frozen.json').read_text());r=f['receipt'];assert f['seal']==stable_json_hash(r)
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        w=json.loads((source/'plans-frozen.json').read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
        hashes={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(hashes)==1
        hashes[str(source/'results.json')]=w['result_sha256'];verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(k for k in hashes if k.endswith('settlement-audit.json'))).read_text())['rows'])
        controls=json.loads((source/'results.json').read_text());assert controls['issue_order']==r['issues'];rows=[]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));current=audit[audit.issue==issue];cache={}
            for policy,plan in plans.items():
                assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
                settled=[]
                for part in plan['components']:
                    # Issue-local exact component receipt includes cutoff, source,
                    # actual supports and implementation-bound freeze provenance.
                    if part['seal'] not in cache:cache[part['seal']]=settle_n7_baseline(part,current)
                    settled.append(cache[part['seal']])
                assert all(x['status']=='COMPLETE' for x in settled)
                hits=sum(x['hits'] for x in settled);gross=sum(x['gross'] for x in settled);ledger=plan.get('swap_ledger',[])
                rows.append(dict(issue=issue,policy=policy,seed=plan.get('seed'),status='COMPLETE' if settled else 'NO_BET',
                    groups=len(settled),hits=hits,stake=plan['stake'],gross=gross,net=gross-plan['stake'],budget_cny=1024,cash_cny=plan['cash_cny'],
                    eligible_single=sum(l['eligible'] and l['single'] for l in ledger),swapped_single=sum(l['swapped'] and l['single'] for l in ledger),
                    swapped_double=sum(l['swapped'] and not l['single'] for l in ledger)))
            print('SETTLED',issue,len(cache),flush=True)
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,controls=controls['rows'],issue_order=r['issues'],seeds=r['seeds'],upstream_freeze_seal=f['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=f['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**hashes},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('DONE',len(rows))
