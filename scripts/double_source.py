"""Freeze fixed-group double-source ablation, then separately settle it."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_double_source import paired_double_source
from src.fundamentals_n7_twocover import settle_n7_twocover

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--study',required=True);a=p.parse_args()
    out=Path(a.study);source=Path('data/derived/fundamentals_417/high-hit-filter-v1')
    if a.phase=='freeze':
        if out.exists():raise FileExistsError('Immutable study required')
        original=json.loads((source/'frozen.json').read_text());r=original['receipt']
        assert original['seal']==stable_json_hash(r)
        hashes={**r['source_hashes'],**r['plan_hashes'],str(source/'frozen.json'):hashlib.sha256((source/'frozen.json').read_bytes()).hexdigest()}
        verify_clean_file_bindings(hashes,repository_root=Path.cwd())
        reports=['quarto/109_double_source.qmd','r/fundamentals_pure_report.R','r/fundamentals_equity_curves.R','r/fundamentals_missed_summary.R']
        receipt=dict(issues=r['issues'],source_hashes=hashes,parameters=dict(budget_cny=1024,unit_cny=2,payout_factor=.65),
            implementation=implementation_closure(Path.cwd(),['scripts.double_source'],distributions=['numpy','pandas','scipy']),
            report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports},
            historical_admission=False,scope='FIXED_GROUP_DOUBLE_SOURCE_EXPOSED_DIAGNOSTIC',plan_hashes={})
        (out/'plans').mkdir(parents=True)
        for issue in r['issues']:
            old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));plans={}
            for u in (3,6):
                plan=old[f'U{u}_ORIGINAL']['plan']
                cuts={s:Cutoff.decision_epoch(issue,t) for s,t in plan['cutoffs'].items()}
                for mode in ('BASELINE','MARKET'):
                    plans[f'U{u}_{mode}']=paired_double_source(plan,cutoffs=cuts,double_source=mode,**receipt['parameters'])
                b=plans[f'U{u}_BASELINE'];m=plans[f'U{u}_MARKET']
                assert b['stake']==m['stake']==plan['stake']
                for x,y,z in zip(plan['components'],b['components'],m['components'],strict=True):
                    assert x['tickets']==y['tickets']
                    assert [(l['slot'],l['role']) for l in x['legs']]==[(l['slot'],l['role']) for l in z['legs']]
                    assert sum(i['support']!=j['support'] for i,j in zip(y['legs'],z['legs'],strict=True))==1
            f=out/'plans'/f'{issue}.json.gz';f.write_bytes(gzip.compress(json.dumps(plans).encode(),mtime=0));receipt['plan_hashes'][str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
        (out/'frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt))))
        print('FROZEN 192 fixed-group plans; no settlement opened')
    else:
        if (out/'results.json').exists():raise FileExistsError('Immutable results')
        frozen=json.loads((out/'frozen.json').read_text());r=frozen['receipt'];assert frozen['seal']==stable_json_hash(r)
        verify_implementation_closure(Path.cwd(),r['implementation'])
        verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes'],**r['report_files']},repository_root=Path.cwd())
        pointer=source/'plans-frozen.json';w=json.loads(pointer.read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
        audits={k:v for k,v in w['source_hashes'].items() if k.endswith('settlement-audit.json')};assert len(audits)==1
        verify_clean_file_bindings(audits,repository_root=Path.cwd());audit=pd.DataFrame(json.loads(Path(next(iter(audits))).read_text())['rows'])
        rows=[]
        for issue in r['issues']:
            plans=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
            for policy,plan in plans.items():
                z=settle_n7_twocover(plan,audit[audit.issue==issue]);assert z['status'] in ('COMPLETE','NO_BET')
                rows.append(dict(issue=issue,policy=policy,status=z['status'],stake=z['stake'],gross=z['gross'],net=z['net'],
                    groups=z['groups'],hits=z['hits'],n6_hits=0,n7_hits=z['hits'],budget_cny=1024,cash_cny=1024-z['stake']))
        target=out/'results.json';target.write_text(json.dumps(dict(rows=rows,issue_order=r['issues'],upstream_freeze_seal=frozen['seal'],historical_admission=False)))
        binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],
            result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source_hashes={**r['source_hashes'],**r['plan_hashes'],**audits},
            implementation=r['implementation'],report_files=r['report_files'])
        canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
        print('SETTLED',len(rows),'policy/issue rows')
