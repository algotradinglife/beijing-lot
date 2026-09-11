"""Build no-effective-U-cap N6 controls, then settle against fixed N7 controls."""
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
from src.fundamentals_n7_twocover import settle_n7_twocover

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
    source=Path('data/derived/fundamentals_417/consensus-n6-n7-v2');controls=Path('data/derived/fundamentals_417/double-source-v1')
    pure=Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json')
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('Immutable output required')
        old=json.loads((source/'frozen.json').read_text());assert old['seal']==stable_json_hash(old['receipt'])
        hashes={**old['receipt']['source_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()}
        assert str(pure) in hashes;verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        data=json.loads(pure.read_text());frame=pd.DataFrame(data['rows'])
        params=dict(group_size=6,budget_cny=1024,unit_cny=2,payout_factor=.65,minimum_anchor_market=.5,max_pair_overlap=5,seed=0,conversion_budget_fraction=0)
        reports=['quarto/113_n6_uncapped_correlation.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R','r/fundamentals_missed_summary.R']
        receipt=dict(issues=old['receipt']['issues'],parameters=params,source_hashes=hashes,
            implementation=implementation_closure(Path.cwd(),['scripts.n6_uncapped'],distributions=['numpy','pandas','scipy']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports},
            historical_admission=False,reuse_policy='NO_BINDING_U_CAP_WITHIN_BUDGET',plan_hashes={},exclusions={})
        (out/'plans').mkdir(parents=True)
        for issue in receipt['issues']:
            current=frame[frame.issue==issue].copy();cuts={str(s):Cutoff.decision_epoch(issue,data['cutoffs'][issue][str(s)]) for s in current.slot}
            current,exclusion=exclude_zero_top2_disagreement(current,cutoffs=cuts);cuts={str(s):cuts[str(s)] for s in current.slot}
            # At most32 funded groups exist. A max_uses of32 can never forbid a
            # placement before the wallet is exhausted; it is not a U policy.
            plan=independent_consensus_portfolio(current,cutoffs=cuts,max_uses=params['budget_cny']//(params['unit_cny']*2**(params['group_size']-2)),**params)
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plan).encode(),mtime=0));receipt['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest();receipt['exclusions'][issue]=exclusion
            print('FROZEN',issue,len(plan['components']),plan['stake'],flush=True)
        (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt'];assert frozen['seal']==stable_json_hash(r)
        verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        w=json.loads((controls/'plans-frozen.json').read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
        hashes={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(hashes)==1
        hashes[str(controls/'results.json')]=w['result_sha256'];verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(k for k in hashes if k.endswith('settlement-audit.json'))).read_text())['rows'])
        old=json.loads((controls/'results.json').read_text());assert old['issue_order']==r['issues']
        rows=[x for x in old['rows'] if x['policy'] in ('U3_BASELINE','U6_BASELINE')]
        for issue in r['issues']:
            plan=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));z=settle_n7_twocover(plan,audit[audit.issue==issue]);assert z['status'] in ('COMPLETE','NO_BET')
            rows.append(dict(issue=issue,policy='N6_UNCAPPED',status=z['status'],groups=z['groups'],hits=z['hits'],n6_hits=z['hits'],n7_hits=0,
                stake=z['stake'],gross=z['gross'],net=z['net'],budget_cny=1024,cash_cny=1024-z['stake']))
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],upstream_freeze_seal=frozen['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**hashes},implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('SETTLED',len(rows))
