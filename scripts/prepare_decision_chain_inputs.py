"""Freeze a label-free subset of the accepted integration-weight archive."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 source=Path(a.source);out=Path(a.output)
 if out.exists():raise FileExistsError('New immutable study directory required')
 upstream=json.loads((source/'study-receipt.json').read_text())
 if stable_json_hash(upstream['receipt'])!=upstream['seal']:raise ValueError('Upstream receipt changed')
 selected={}
 for name in ['candidates.json','endpoints.json','contract.json','scope-exclusions.json']:
  path=source/name;raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  if upstream['receipt']['file_hashes'][str(path)]!=digest:raise ValueError('Accepted input changed: '+str(path))
  selected[name]=json.loads(raw)
 model=selected['contract.json']
 if model['draw_version']!='1.1.0' or model['high_weight']!=.5:raise ValueError('Frozen comparison versions differ')
 endpoints=selected['endpoints.json'];candidates=selected['candidates.json']
 hashes={str(source/n):hashlib.sha256((source/n).read_bytes()).hexdigest() for n in selected}
 hashes[str(source/'study-receipt.json')]=hashlib.sha256((source/'study-receipt.json').read_bytes()).hexdigest()
 if candidates['endpoints_sha256']!=hashes[str(source/'endpoints.json')]:raise ValueError('Endpoint binding mismatch')
 # Historical expert/market derivation is inventoried evidence, not re-executed.
 for name,digest in candidates['input_hashes'].items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('Historical source changed: '+name)
  hashes[name]=digest
 high=Path(model['high_model'])
 if hashlib.sha256(high.read_bytes()).hexdigest()!=model['high_model_sha256']:raise ValueError('High model changed')
 hashes[str(high)]=model['high_model_sha256']
 metadata={}
 for study in ['train-eight-test-eight-v2','cv-sixteen-test-sixteen-v1','cv-thirtytwo-test-sixteen-v1']:
  path=Path('data/derived/fundamentals_417')/study/'predictions.json';raw=path.read_bytes()
  digest=hashlib.sha256(raw).hexdigest()
  if candidates['input_hashes'].get(str(path))!=digest:raise ValueError('Unbound metadata source')
  for r in json.loads(raw)['features']:
   key=(r['issue'],r['slot'],r['provider_id'])
   if key in metadata and metadata[key]!=r['handicap']:raise ValueError('Conflicting handicap')
   metadata[key]=r['handicap']
 rows=[dict(r,handicap=metadata[(r['issue'],r['slot'],r['provider_id'])]) for r in candidates['rows'] if r['weight'] in [0,.25,.5]]
 contract=dict(draw_version=model['draw_version'],draw_release_seal=endpoints['model_receipt']['release_seal'],
  high_model_sha256=model['high_model_sha256'],high_weight=.5,current_draw_weight=.5,
  policies={'CURRENT':{'policy':'KEEP','fallback_weight':0},'CONFLICT_REDUCE_025':{'policy':'REDUCE','fallback_weight':.25},'CONFLICT_REVERT_0':{'policy':'REDUCE','fallback_weight':0},'CONFLICT_SKIP':{'policy':'SKIP','fallback_weight':0}},
  conflict='MARKET_TOP1_EXCLUDED_BY_CURRENT_MODEL_TOP2',selection='COVERAGE',grouping='CONCENTRATED',
  n=7,max_groups=6,unit_cny=2,payout_factor=.65,score_protection=False,
  budget='SAME_CAP_1536; SAME_UNIT_2; UNSPENT_CASH_NOT_REINVESTED',
  matched_control='FIRST_K_CURRENT_GROUPS_WHERE_K_IS_SKIP_GROUP_COUNT',
  validation_issues=model['validation_issues'],test_issues=model['test_issues'],
  historical_admission=False,expert_training=False,rule_tuning=False,
  scope='EXPOSED_40_ISSUE_DIAGNOSTIC_NOT_ORIGINAL_V333_REPLAY',
  chronology='FIXTURE_RELATIVE_ARCHIVED_ENDPOINTS_NOT_COMMON_TICKET_TIME')
 pack=dict(rows=rows,cutoffs=candidates['cutoffs'],source_hashes=hashes,contract=contract,
  upstream_receipt=upstream['seal'],upstream_input_implementation=candidates['implementation_hashes'])
 pack['seal']=stable_json_hash(pack)
 out.mkdir(parents=True)
 (out/'inputs.json').write_text(json.dumps(pack,indent=2))
 (out/'contract.json').write_text(json.dumps(contract,indent=2))
 (out/'scope-exclusions.json').write_text(json.dumps(selected['scope-exclusions.json'],indent=2))
 print('FROZEN',len(rows),'weight rows',len(set(r['issue'] for r in rows)),'issues; no settlement opened')
