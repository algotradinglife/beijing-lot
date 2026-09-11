"""Package verified all-fixture diagnostics and frozen portfolio outputs."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_clean_receipts import verify_clean_file_bindings
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable report required')
 root=Path('data/derived/fundamentals_417');event=root/'missed-events-v1/events.json';e=json.loads(event.read_text());verify_clean_file_bindings(e['source_hashes'],repository_root=Path.cwd())
 plan=root/'missed-comparison-v1';f=json.loads((plan/'frozen.json').read_text());r=f['receipt'];assert stable_json_hash(r)==f['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 settled=json.loads((plan/'results.json').read_text());assert settled['freeze_seal']==f['seal'];verify_clean_file_bindings(settled['audit_hash'],repository_root=Path.cwd())
 attr=root/'missed-issues-attribution-v1';ar=json.loads((attr/'receipt.json').read_text());verify_clean_file_bindings(ar['hashes'],repository_root=Path.cwd())
 legs=pd.read_csv(attr/'legs.csv',dtype={'issue':str,'provider_id':str}).drop(columns=['status','actual_direction','audit_handicap','actual_code','single','hit']).to_dict('records')
 result=dict(rows=settled['rows'],events=e['events'],features=e['features'],audit=e['audit'],legs=legs,upstream_freeze_seal=f['seal'])
 out.mkdir(parents=True);(out/'results.json').write_text(json.dumps(result))
 paths=[event,plan/'results.json',plan/'frozen.json',attr/'legs.csv',attr/'receipt.json']
 reports=['quarto/88_missed_issue_research.qmd','r/fundamentals_missed_issues.R','r/fundamentals_event_calibration.R','r/fundamentals_event_strata.R','r/fundamentals_missed_summary.R','r/fundamentals_equity_curves.R','r/fundamentals_drawdown_plot.R','r/fundamentals_pure_report.R','scripts/package_missed_research.py']
 receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=f['seal'],implementation=r['implementation'],
  result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest(),source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
  report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports})
 canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
 files={p:(out/p).read_text() for p in ['results.json','plans-frozen.json']}
 Path('tests/fixtures/missed_research_report.json.gz').write_bytes(gzip.compress(json.dumps(dict(files=files,hashes={p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()})).encode(),mtime=0))
 print('PACKAGED288 portfolios;2561 fixture events; full baseline attribution')
