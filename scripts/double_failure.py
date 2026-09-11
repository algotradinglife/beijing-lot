"""Extract settled leg support membership from immutable double-source plans."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    source=Path(a.source);out=Path(a.output)
    if out.exists():raise FileExistsError('New immutable diagnostic required')
    frozen=json.loads((source/'frozen.json').read_text());r=frozen['receipt'];assert frozen['seal']==stable_json_hash(r)
    verify_implementation_closure(Path.cwd(),r['implementation'])
    hashes={**r['source_hashes'],**r['plan_hashes']};verify_clean_file_bindings(hashes,repository_root=Path.cwd())
    w=json.loads((source/'plans-frozen.json').read_text());assert hashlib.sha256(w['canonical_json'].encode()).hexdigest()==w['seal'];w=json.loads(w['canonical_json'])
    assert w['plan_freeze_seal']==frozen['seal'];assert hashlib.sha256((source/'results.json').read_bytes()).hexdigest()==w['result_sha256']
    verify_clean_file_bindings(w['source_hashes'],repository_root=Path.cwd())
    paths=[s for s in w['source_hashes'] if s.endswith('settlement-audit.json')];assert len(paths)==1
    audit=json.loads(Path(paths[0]).read_text())['rows'];keys=[(x['issue'],x['slot'],x['provider_id']) for x in audit];assert len(keys)==len(set(keys))
    labels=dict(zip(keys,audit,strict=True));legs=[]
    previous=json.loads((source/'results.json').read_text())
    for issue in previous['issue_order']:
        plans=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
        for policy,plan in plans.items():
            for group,part in enumerate(plan['components'],1):
                for l in part['legs']:
                    label=labels[(issue,l['slot'],l['provider_id'])];actual=dict(W='3',D='1',L='0')[label['actual_direction']]
                    legs.append(dict(issue=issue,policy=policy,group=group,slot=l['slot'],provider_id=l['provider_id'],
                        role=l['role'],support=l['support'],actual=actual,hit=actual in l['support']))
    out.mkdir(parents=True);target=out/'results.json'
    target.write_text(json.dumps(dict(rows=previous['rows'],legs=legs,issue_order=previous['issue_order'],upstream_freeze_seal=frozen['seal'],historical_admission=False)))
    reports=['quarto/111_double_failure.qmd','r/fundamentals_double_failure.R','r/fundamentals_pure_report.R']
    binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],
        result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),source_hashes={**w['source_hashes'],**{str(source/f):hashlib.sha256((source/f).read_bytes()).hexdigest() for f in ['results.json','frozen.json','plans-frozen.json']}},
        implementation=implementation_closure(Path.cwd(),['scripts.double_failure'],distributions=[]),
        report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
    canonical=json.dumps(binding,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
    print('EXTRACTED',len(legs),'leg occurrences')
