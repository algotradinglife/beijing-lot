"""Package bound post-settlement category inputs; no selection or fitting."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable diagnostic required')
 paths=[Path('data/derived/fundamentals_417/new48-pure-baseline-v1/factors.json'),Path('data/derived/fundamentals_417/missed-events-v1/events.json'),Path('data/derived/fundamentals_417/missed25-rescue-v1/results.json'),Path('data/derived/fundamentals_417/missed25-rescue-v1/frozen.json')]
 factors,event,data,frozen=[json.loads(p.read_text()) for p in paths]
 assert stable_json_hash(frozen['receipt'])==frozen['seal']==data['freeze_seal']
 for hashes in [factors['source_hashes'],event['source_hashes'],data['audit_hash']]:verify_clean_file_bindings(hashes,repository_root=Path.cwd())
 keys=['issue','slot','provider_id'];fields=keys+['status','competition','cup','expected_total','market_total','giving_venue_ppg','home_venue_n','away_venue_n']
 rows=[r for r in data['rows'] if r['policy']=='H0_R000_N7_C2_TOP1'];assert len(rows)==48 and sum(r['hits']==0 for r in rows)==25
 result=dict(rows=rows,factors=factors['rows'],features=[{k:r[k] for k in fields} for r in event['features']],legs=data['base_legs'],audit=data['audit'],upstream_freeze_seal=frozen['seal'],historical_admission=False)
 out.mkdir(parents=True);(out/'results.json').write_text(json.dumps(result))
 reports=['quarto/91_category_diagnostics.qmd','r/fundamentals_category_diagnostics.R','r/fundamentals_missed_issues.R','r/fundamentals_pure_report.R','scripts/package_category_diagnostics.py']
 receipt=dict(scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',plan_freeze_seal=frozen['seal'],generated_at_utc=datetime.now(timezone.utc).isoformat(),
  implementation=implementation_closure(Path.cwd(),['scripts.package_category_diagnostics']),
  source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
  report_files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in reports},result_sha256=hashlib.sha256((out/'results.json').read_bytes()).hexdigest())
 canonical=json.dumps(receipt,sort_keys=True,separators=(',',':'));(out/'plans-frozen.json').write_text(json.dumps(dict(canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())))
 files={p:(out/p).read_text() for p in ['results.json','plans-frozen.json']}
 Path('tests/fixtures/category_diagnostics.json.gz').write_bytes(gzip.compress(json.dumps(dict(files=files,hashes={p:hashlib.sha256(v.encode()).hexdigest() for p,v in files.items()})).encode(),mtime=0))
 print('PACKAGED2561 fixtures,48 original issue outcomes,original holdings')
