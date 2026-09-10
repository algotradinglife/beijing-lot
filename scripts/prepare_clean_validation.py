"""Prepare fixed new-period inputs from approved local cleaning, without labels."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_clean_validation import read_clean_validation_release,clean_validation_forms,clean_validation_market,validation_predictor_clocks
from src.fundamentals_roster_handicap import roster_handicaps
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--inventories',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable new validation directory required')
 inv=json.loads(Path(a.inventories).read_text());cuts={r['issue']:r['cutoffs'] for r in inv}
 release=read_clean_validation_release(a.study,cutoffs=cuts)
 contract=dict(issues=list(cuts),scope='NEW48_FIXED_RULE_DIAGNOSTIC',source_policy='APPROVED_TITAN_PRIMARY',window=10,minimum=10,
  draw_version='1.1.0',draw_weight=.5,high_version='0.1.0_FROZEN_PRIOR32',high_weight=.5,
  depths=[1,2],quality=['TOP2','COMPRESSED'],overlap=['STRICT','FREE'],max_gaps=[.02,.05,.10,1.],
  preserve_prefix=True,cash_policy='HOLD',n=7,budget_cny=1024,unit_cny=2,payout_factor=.65,
  learning='NONE',historical_admission=False,target_labels_opened=False,
  evidence='HISTORICAL_PROXY_NEW_RULE_HOLDOUT_NOT_PROSPECTIVE',prior_strategy_issues_end='100401')
 if any(i<='100401' for i in cuts):raise ValueError('Target overlaps old strategy periods')
 closure=implementation_closure(Path.cwd(),['src.fundamentals_clean_validation','scripts.prepare_clean_validation'])
 out.mkdir(parents=True);(out/'inputs').mkdir();(out/'contract.json').write_text(json.dumps(contract,indent=2))
 input_hashes={str(Path(a.inventories)):hashlib.sha256(Path(a.inventories).read_bytes()).hexdigest(),**release['source_hashes']}
 rows=[];files={}
 for r in inv:
  issue=r['issue'];payload=release['payloads'][issue]
  path=next(p for p in release['manifest']['analysis_paths'] if Path(p).stem==issue)
  sources={path:release['source_hashes'][path],str(Path(a.study)/'cleanup-manifest.json'):release['source_hashes'][str(Path(a.study)/'cleanup-manifest.json')]}
  h=roster_handicaps(r['roster_path'],issue=issue,slots=[int(s) for s in cuts[issue]])
  forms=clean_validation_forms(payload,h,cutoffs=cuts[issue],window=10,minimum=10,source_hashes=sources,repository_root=Path.cwd())
  market=clean_validation_market(payload,release['markets'],cutoffs=cuts[issue],source_hashes=sources,repository_root=Path.cwd())
  clocks=validation_predictor_clocks(forms['context'],market,cutoffs=cuts[issue])
  value=dict(issue=issue,cutoffs=cuts[issue],handicaps=h,forms=forms,market=market,clocks=clocks,roster_path=r['roster_path'])
  path=out/'inputs'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(value,separators=(',',':')).encode(),mtime=0));files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  for f in forms['windows']:
   m=next(x for x in market['rows'] if x['slot']==f['slot'])
   rows.append(dict(issue=issue,slot=f['slot'],provider_id=f['provider_id'],form_status=f['status'],market_status=m['status'],
    ready=f['status']=='OK_DIAGNOSTIC' and m['status']=='READY',home_n=len(f['home_window']),away_n=len(f['away_window'])))
  print('PREPARED',issue,sum(x['ready'] for x in rows if x['issue']==issue),'/',len(h),flush=True)
 receipt=dict(contract=contract,source_hashes=input_hashes,files=files,implementation=closure,cutoffs=cuts)
 (out/'prepared.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt),readiness=rows),indent=2))
 print('COMPLETE',len(rows),sum(r['ready'] for r in rows),flush=True)
