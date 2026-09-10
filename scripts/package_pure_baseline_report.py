"""Package checked pure/expert results with report implementation bindings."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--fixture',required=True);a=p.parse_args()
 source=Path(a.source);out=Path(a.output)
 if out.exists() or Path(a.fixture).exists():raise FileExistsError('Immutable new report required')
 frozen=json.loads((source/'plans-frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 result=json.loads((source/'results.json').read_text());assert result['freeze_seal']==frozen['seal'];verify_clean_file_bindings(result['source_hashes'],repository_root=Path.cwd())
 paths=[str(source/n) for n in ['factors.json','results.json','plans-frozen.json']]
 report_files=['quarto/76_pure_baseline_variants.qmd','r/fundamentals_pure_report.R','r/fundamentals_expanded_comparison.R','r/fundamentals_repeated_double.R','r/fundamentals_compression_bridge.R','r/fundamentals_integration_weight.R']
 result['upstream_freeze_seal']=result.pop('freeze_seal')
 result_body=json.dumps(result,indent=2)
 receipt=dict(scope=r['scope'],model=r['model'],parameters=r['parameters'],generated_at=datetime.now(timezone.utc).isoformat(),
  source_hashes={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths},
  report_files={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in report_files},
  implementation=implementation_closure(Path.cwd(),['scripts.package_pure_baseline_report']),
  plan_freeze_seal=frozen['seal'],result_sha256=hashlib.sha256(result_body.encode()).hexdigest())
 canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
 seal=hashlib.sha256(canonical.encode()).hexdigest()
 files={'results.json':result_body,'plans-frozen.json':json.dumps(dict(canonical_json=canonical,seal=seal),indent=2)}
 out.mkdir(parents=True)
 for name,body in files.items():(out/name).write_text(body)
 archive=dict(files=files,hashes={n:hashlib.sha256(b.encode()).hexdigest() for n,b in files.items()})
 Path(a.fixture).write_bytes(gzip.compress(json.dumps(archive).encode(),mtime=0))
 print('PACKAGED',len(result['rows']),'pure/expert pairs',flush=True)
