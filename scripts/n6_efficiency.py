"""Freeze twelve fixed-source efficiency plans, then settle the sealed cohort."""
import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n6_efficiency import n6_efficiency_catalog,n6_efficiency_plan
from src.fundamentals_missed_portfolio import settle_missed_portfolio


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True)
    args=p.parse_args();out=Path(args.study)
    source=Path('data/derived/fundamentals_417/high-hit-filter-v1')
    pointer=Path('data/derived/fundamentals_417/cap-depth-grid-v1/plans-frozen.json')
    if args.phase=='freeze':
        if out.exists():raise FileExistsError('New immutable study required')
        old=json.loads((source/'frozen.json').read_text());r=old['receipt']
        assert stable_json_hash(r)==old['seal']
        hashes={**r['source_hashes'],**r['plan_hashes'],
            str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest(),
            str(pointer):hashlib.sha256(pointer.read_bytes()).hexdigest()}
        verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        methods=[('ORIGINAL',1024),('EXTRA_PROB',1024),('EXTRA_VALUE',1024)]+[
            (method,cap) for method in ('PROBABILITY','MARGINAL','EXPECTED_NET') for cap in (256,512,768)]
        reports=['quarto/106_n6_efficiency.qmd','r/fundamentals_pure_report.R',
            'r/fundamentals_equity_curves.R','r/fundamentals_missed_summary.R','r/fundamentals_hit_improvement.R']
        receipt=dict(issues=r['issues'],source_hashes=hashes,
            scope='EXPOSED_FIXED_SOURCE_N6_EFFICIENCY_12',historical_admission=False,
            parameters=dict(methods=methods,budget_cny=1024,unit_cny=2,payout_factor=.65,
                scenario_seed=419106,scenario_draws=32768,initial_capital_cny=100000),
            implementation=implementation_closure(Path.cwd(),['scripts.n6_efficiency'],distributions=['numpy','pandas','scipy']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
        (out/'plans').mkdir(parents=True)
        (out/'contract.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        plan_hashes={}
        for issue in r['issues']:
            prior=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))['N6_ORIGINAL']
            plan=prior['reconstruction']['shape_plan']
            cuts={s:Cutoff.decision_epoch(issue,t) for s,t in plan['cutoffs'].items()}
            catalog=n6_efficiency_catalog(plan,cutoffs=cuts,unit_cny=2,payout_factor=.65,scenario_seed=419106,scenario_draws=32768)
            bundles={}
            for method,cap in methods:
                z=n6_efficiency_plan(catalog,cutoffs=cuts,method=method,spend_cap_cny=cap,
                    budget_cny=1024,unit_cny=2,payout_factor=.65)
                if method=='ORIGINAL':
                    for k in ('legs','tickets','stake','cash_cny','groups'):
                        assert z['shape_plan'][k]==plan[k],(issue,k)
                name=method if method in ('ORIGINAL','EXTRA_PROB','EXTRA_VALUE') else f'{method}_{cap}'
                bundles[name]=z
            target=out/'plans'/f'{issue}.json.gz'
            target.write_bytes(gzip.compress(json.dumps(dict(catalog=catalog,bundles=bundles)).encode(),mtime=0))
            plan_hashes[str(target)]=hashlib.sha256(target.read_bytes()).hexdigest()
            print('FROZEN',issue,flush=True)
        receipt['plan_hashes']=plan_hashes
        (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        print('SEALED576 plans before target settlement')
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt']
        assert stable_json_hash(r)==frozen['seal']
        verify_implementation_closure(Path.cwd(),r['implementation'])
        verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        witness=json.loads(pointer.read_text())
        assert hashlib.sha256(witness['canonical_json'].encode()).hexdigest()==witness['seal']
        audits={k:v for k,v in json.loads(witness['canonical_json'])['source_hashes'].items() if k.endswith('settlement-audit.json')}
        assert len(audits)==1
        verify_clean_file_bindings(audits,repository_root=Path.cwd())
        audit=pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())['rows'])
        rows=[]
        for issue in r['issues']:
            data=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
            for policy,z in data['bundles'].items():
                s=settle_missed_portfolio(z['plan'],audit[audit.issue==issue])
                assert s['status']=='COMPLETE'
                rows.append(dict(s,policy=policy,method=z['method'],spend_cap_cny=z['spend_cap_cny']))
        target=out/'results.json'
        target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],parameters=r['parameters'],
            upstream_freeze_seal=frozen['seal'],historical_admission=False)))
        verification=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',
            plan_freeze_seal=frozen['seal'],result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            source_hashes={**r['source_hashes'],**r['plan_hashes'],**audits},
            implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(verification,sort_keys=True,separators=(',',':'))
        (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('SETTLED',len(rows),'policy/issue rows')
