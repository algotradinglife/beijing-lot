"""Extract already frozen N6 group settlements for descriptive period diagnosis."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.fundamentals_n7_baseline import settle_n7_baseline

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();source=Path(args.source);out=Path(args.output)
    if out.exists():raise FileExistsError('New immutable diagnostic output required')
    frozen=json.loads((source/'frozen.json').read_text());r=frozen['receipt']
    assert stable_json_hash(r)==frozen['seal']
    verify_implementation_closure(Path.cwd(),r['implementation'])
    verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
    witness=json.loads((source/'plans-frozen.json').read_text())
    assert hashlib.sha256(witness['canonical_json'].encode()).hexdigest()==witness['seal']
    witness=json.loads(witness['canonical_json'])
    assert witness['plan_freeze_seal']==frozen['seal']
    assert witness['result_sha256']==hashlib.sha256((source/'results.json').read_bytes()).hexdigest()
    verify_clean_file_bindings(witness['source_hashes'],repository_root=Path.cwd())
    paths=[f for f in witness['source_hashes'] if f.endswith('settlement-audit.json')];assert len(paths)==1
    audit=pd.DataFrame(json.loads(Path(paths[0]).read_text())['rows'])
    previous=json.loads((source/'results.json').read_text())
    policies=['ORIGINAL','EXTRA_PROB','EXPECTED_NET_768']
    rows=[v for v in previous['rows'] if v['policy'] in policies];groups=[]
    for issue in r['issues']:
        saved=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()))
        for policy in policies:
            bundle=saved['bundles'][policy]
            for number,(component,original_group) in enumerate(zip(bundle['plan']['components'],bundle['selected_source_groups']),1):
                result=settle_n7_baseline(component['plan'],audit[audit.issue==issue])
                assert result['status']=='COMPLETE'
                groups.append(dict(issue=issue,policy=policy,group=number,source_group=original_group,
                    stake=result['stake'],gross=result['gross'],hit=bool(result['hits'])))
    out.mkdir(parents=True)
    target=out/'results.json'
    target.write_text(json.dumps(dict(rows=rows,groups=groups,issue_order=r['issues'],
        upstream_freeze_seal=frozen['seal'],historical_admission=False)))
    reports=['quarto/108_n6_period_returns.qmd','r/fundamentals_period_returns.R','r/fundamentals_pure_report.R']
    binding=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],
        result_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        source_hashes={**witness['source_hashes'],**{str(source/f):hashlib.sha256((source/f).read_bytes()).hexdigest()
            for f in ['results.json','frozen.json','plans-frozen.json']}},
        implementation=implementation_closure(Path.cwd(),['scripts.n6_period_returns'],distributions=['numpy','pandas']),
        report_files={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in reports})
    canonical=json.dumps(binding,sort_keys=True,separators=(',',':'))
    (out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
    print('EXTRACTED',len(rows),'issue rows',len(groups),'group settlements; no selection changes')
