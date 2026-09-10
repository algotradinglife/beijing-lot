"""Fixed retrospective conflict comparison: freeze supports, then settle offline."""
import argparse,gzip,hashlib,itertools,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings,verify_clean_validation_receipts
from src.fundamentals_market_conflict import replace_market_conflict_doubles
from src.fundamentals_n7_diversity import evaluate_fixed_supports
from src.fundamentals_compression_breadth import settle_breadth_bundle

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('phase',choices=['freeze','settle']);p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 root=Path.cwd();source=Path(a.source);out=Path(a.output)
 policies={'TAIL05':0.,'TV10':.10,'TV15':.15,'TV20':.20};rules=['BASE','GAP02','GAP05',*policies]
 original=json.loads((source/'plans-frozen.json').read_text());r=original['receipt'];assert stable_json_hash(r)==original['seal']
 verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=root)
 verify_implementation_closure(root,r['implementation'])
 factors=json.loads((source/'factors.json').read_text());frame=pd.DataFrame(factors['rows'])
 if a.phase=='freeze':
  if out.exists():raise FileExistsError('New immutable output required')
  out.mkdir(parents=True);(out/'plans').mkdir();files={}
  contract=dict(source=str(source),source_seal=original['seal'],rules=rules,tv_thresholds=policies,minimum_market_tail_lead=.05,
   issues=r['contract']['issues'],evaluation_seed=41902,evaluation_draws=8192,budget_cny=1024,
   unit_cny=2,payout_factor=.65,scope='POST_EXPOSURE_RETROSPECTIVE_NOT_NEW_HOLDOUT',no_bet=r['no_bet'])
  (out/'contract.json').write_text(json.dumps(contract,indent=2))
  for issue in contract['issues']:
   if issue in r['no_bet']:continue
   old=json.loads(gzip.decompress((source/'plans'/f'{issue}.json.gz').read_bytes()));bundle={};f=frame[frame.issue==issue]
   cuts={str(s):Cutoff.decision_epoch(issue,r['cutoffs'][issue][str(s)]) for s in f.slot}
   for depth,quality,overlap in itertools.product([1,2],['TOP2','COMPRESSED'],['STRICT','FREE']):
    case=f'D{depth}_{quality}_{overlap}';base=old[case+'_BASE']['plan']
    for rule in ['BASE','GAP02','GAP05']:bundle[case+'_'+rule]=old[case+'_'+rule]
    for rule,tv in policies.items():
     plan=replace_market_conflict_doubles(base,cutoffs=cuts,minimum_tv=tv,minimum_market_tail_lead=.05)
     evaluation=evaluate_fixed_supports(f,plan,cutoffs=cuts,seed=41902,draws=8192)
     bundle[case+'_'+rule]=dict(case=case,rule=rule,depth=depth,quality=quality,overlap=overlap,plan=plan,evaluation=evaluation)
   path=out/'plans'/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(bundle,separators=(',',':')).encode(),mtime=0));files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('FROZEN',issue,len(bundle),flush=True)
  receipt=dict(contract=contract,plan_hashes=files,source_hashes={str(source/n):hashlib.sha256((source/n).read_bytes()).hexdigest() for n in ['plans-frozen.json','factors.json']},
   implementation=implementation_closure(root,['scripts.market_conflict_validation'],distributions=['numpy','pandas','scipy']))
  (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2));print('ALL_FROZEN',flush=True)
 else:
  if (out/'results.json').exists():raise FileExistsError('Immutable results already exist')
  frozen=json.loads((out/'plans-frozen.json').read_text());receipt=frozen['receipt'];assert stable_json_hash(receipt)==frozen['seal']
  assert receipt['contract']['source']==str(source) and receipt['contract']['source_seal']==original['seal']
  verify_implementation_closure(root,receipt['implementation']);verify_clean_file_bindings({**receipt['plan_hashes'],**receipt['source_hashes']},repository_root=root)
  verify_clean_validation_receipts(source,repository_root=root)
  audit=pd.DataFrame(json.loads((source/'settlement-audit.json').read_text())['rows']);assert audit.status.eq('READY').all()
  rows=[];changes=[]
  for issue in receipt['contract']['issues']:
   if issue in r['no_bet']:
    for depth,quality,overlap,rule in itertools.product([1,2],['TOP2','COMPRESSED'],['STRICT','FREE'],rules):
     case=f'D{depth}_{quality}_{overlap}'
     rows.append(dict(issue=issue,policy=case+'_'+rule,case=case,rule=rule,depth=depth,quality=quality,overlap=overlap,status='NO_BET',partition='NEW48_EXPOSED',stake=0,cash_cny=1024,budget_cny=1024,gross=0,net=0,roi=None,hits=0,groups=0,model_union=0,fixture_hhi=0,repeat_units=0,changed_legs=0,gained_groups=0,lost_groups=0,mean_group_probability=0,budget_return=0))
    continue
   bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));observed=audit[audit.issue==issue];settled=settle_breadth_bundle(bundle,observed);lookup=observed.set_index(['slot','provider_id']);won={}
   for policy,e in bundle.items():
    plan=e['plan'];won[policy]=[all(dict(W='3',D='1',L='0')[lookup.loc[z['slot'],z['provider_id']].actual_direction] in z['support'] for z in plan['legs'] if z['group']==g) for g in range(1,plan['groups']+1)]
   for policy,e in bundle.items():
    plan=e['plan'];row=settled[policy];base=won[e['case']+'_BASE'];actual=won[policy]
    row.update(**{k:e[k] for k in ['case','rule','depth','quality','overlap']},policy=policy,partition='NEW48_EXPOSED',budget_cny=1024,cash_cny=plan['cash_cny'],budget_return=row['net']/1024,repeat_units=plan['repeat_units'],
     changed_legs=sum(z['changed'] for z in plan.get('diversity_ledger',[])),gained_groups=sum(x and not y for x,y in zip(actual,base)),lost_groups=sum(y and not x for x,y in zip(actual,base)),mean_group_probability=sum(plan['group_probability'])/plan['groups'],**e['evaluation']['metrics']);rows.append(row)
    for z in plan.get('diversity_ledger',[]):
     if z['changed'] and e['rule'] in policies:
      leg=next(l for l in plan['legs'] if l['group']==z['group'] and l['slot']==z['slot'])
      changes.append(dict(issue=issue,policy=policy,case=e['case'],rule=e['rule'],**z,**{k:leg[k] for k in ['p_W','p_D','p_L','q_W','q_D','q_L']}))
   print('SETTLED',issue,flush=True)
  assert len(rows)==48*56 and all(z['status'] in ['COMPLETE','NO_BET'] for z in rows)
  (out/'results.json').write_text(json.dumps(dict(rows=rows,changes=changes,freeze_seal=frozen['seal'],source_hashes={str(source/'settlement-audit.json'):hashlib.sha256((source/'settlement-audit.json').read_bytes()).hexdigest()}),indent=2))
