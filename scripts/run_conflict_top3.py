"""Freeze user-declared conflict Top3 plans before reading archived R settlement."""
import argparse,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_conflict_top3 import conflict_top3_plan
from src.fundamentals_conflict_portfolios import settle_conflict_protection
from src.fundamentals_n7_baseline import settle_n7_baseline
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 source=Path(a.source);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable output already exists')
 contract=json.loads((source/'contract.json').read_text());parent=Path(contract['parent_study'])
 receipt=json.loads((source/'study-receipt.json').read_text());assert stable_json_hash(receipt['receipt'])==receipt['seal']
 scores=json.loads((source/'scores.json').read_text());inputs=json.loads((parent/'inputs.json').read_text())
 assert stable_json_hash({k:v for k,v in inputs.items() if k!='seal'})==inputs['seal']
 hashes={**inputs['source_hashes'],**scores['source_hashes'],**scores['implementation_hashes']}
 for path in [source/'scores.json',source/'contract.json',parent/'inputs.json']:
  digest=hashlib.sha256(path.read_bytes()).hexdigest();assert receipt['receipt']['file_hashes'][str(path)]==digest
  hashes[str(path)]=digest
 for path,digest in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
 assert scores['cutoffs']==inputs['cutoffs']
 frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 closure=implementation_closure(Path.cwd(),['src.fundamentals_conflict_top3','scripts.run_conflict_top3','src.fundamentals_conflict_portfolios'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();plans={};plan_hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot}
  grids={s:scores['grids'][f'{issue}/{s}'] for s in cuts}
  bundle=conflict_top3_plan(f,grids,cutoffs=cuts,max_groups=6,unit_cny=2,payout_factor=.65,allocation_seed=0)
  path=parent/'plans'/f'{issue}-CURRENT.json';raw=path.read_bytes()
  assert receipt['receipt']['file_hashes'][str(path)]==hashlib.sha256(raw).hexdigest()
  assert bundle['base']==json.loads(raw)['plan']
  hashes[str(path)]=hashlib.sha256(raw).hexdigest()
  plans[issue]=bundle;path=out/'plans'/f'{issue}.json';path.write_text(json.dumps(bundle,indent=2));plan_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
 frozen=dict(source_hashes=hashes,plan_hashes=plan_hashes,implementation=closure,cutoffs=inputs['cutoffs'],
  contract=dict(rule='ALL_CONFLICTS_EXACT_SCORE_TOP3_NONCONFLICT_N7',tie_order='p_desc_home_asc_away_asc',
   unit_cny=2,payout_factor=.65,max_groups=6,draw_version=contract['draw_version'],draw_weight=.5,high_weight=.5,
   budget='ACTUAL_UNITS_NO_REINVESTMENT',learning='NONE',historical_admission=False))
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=frozen,seal=stable_json_hash(frozen)),indent=2))
 # All decisions sealed before accessing outcomes or final SP.
 results=[];audit_hashes={}
 for partition,name in [('TRAINING24','training'),('VALIDATION8','validation'),('TEST8','test')]:
  path=parent/f'{name}-audit.json';raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
  assert receipt['receipt']['file_hashes'][str(path)]==digest;audit_hashes[str(path)]=digest
  audit=pd.DataFrame(json.loads(raw))
  members=inputs['contract']['test_issues'] if partition=='TEST8' else inputs['contract']['validation_issues'] if partition=='VALIDATION8' else sorted(set(plans)-set(inputs['contract']['test_issues']+inputs['contract']['validation_issues']))
  for issue in members:
   bundle=plans[issue];observed=audit[audit.issue==issue];combined=settle_conflict_protection(bundle['plan'],observed)
   if combined['status']=='NO_BET' and combined['stake']>0:combined['status']='COMPLETE'
   assert combined['status'] in ['COMPLETE','NO_BET']
   for policy,plan in [('CURRENT',bundle['base']),('NONCONFLICT_N7',bundle['plan']['main']),('CONFLICT_TOP3',None),('SPLIT_TOP3',None)]:
    if plan is not None:result=settle_n7_baseline(plan,observed)
    elif policy=='SPLIT_TOP3':result=dict(combined)
    else:
     stake=combined['score_stake'];gross=combined['score_gross']
     result=dict(issue=issue,stake=stake,gross=gross,net=gross-stake,roi=gross/stake-1 if stake else None,
      hits=0,groups=0,status='COMPLETE' if stake else 'NO_BET',score_bets=combined['score_bets'],score_hits=combined['score_hits'])
    assert result['status'] in ['COMPLETE','NO_BET']
    result.update(policy=policy,partition=partition,conflict_matches=sum(r['conflict'] for r in bundle['plan']['ledger']),
       eligible_matches=len(bundle['plan']['ledger']))
    results.append(result)
 verify_implementation_closure(Path.cwd(),closure)
 for path,digest in {**hashes,**plan_hashes,**audit_hashes}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(frozen)),indent=2))
 print('COMPLETE',len(plans),'issues',len(results),'rows')
