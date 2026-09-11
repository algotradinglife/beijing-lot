"""Package frozen N7 hit-improvement results for reproducible QMD rendering."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable report directory required')
 source=Path('data/derived/fundamentals_417/n7-hit-improvement-v1')
 frozen=json.loads((source/'frozen.json').read_text());r=frozen['receipt'];assert stable_json_hash(r)==frozen['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 result=json.loads((source/'results.json').read_text());assert result['freeze_seal']==frozen['seal'];verify_clean_file_bindings(result['audit_hash'],repository_root=Path.cwd())
 assert len(result['rows'])==1440 and len({(x['issue'],x['policy']) for x in result['rows']})==1440
 result['upstream_freeze_seal']=frozen['seal'];out.mkdir(parents=True);(out/'results.json').write_text(json.dumps(result))
 reports=['quarto/89_n7_hit_improvement.qmd','r/fundamentals_hit_improvement.R','r/fundamentals_missed_summary.R','r/fundamentals_event_calibration.R','r/fundamentals_equity_curves.R','r/fundamentals_drawdown_plot.R','r/fundamentals_pure_report.R','scripts/package_n7_hit_report.py']
 receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],parameters=r['parameters'],implementation=r['implementation'],
  source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [source/'frozen.json',source/'results.json']},
  report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports},result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())
 canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
 files={p:(out/p).read_text() for p in ['results.json','plans-frozen.json']}
 Path('tests/fixtures/n7_hit_report.json.gz').write_bytes(gzip.compress(json.dumps(dict(files=files,hashes={p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()})).encode(),mtime=0))
 print('PACKAGED1440 results and all-fixture calibration inputs')
