"""Thin archived-study runner: freeze all decisions before opening audit labels."""
import argparse,gzip,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_compression_breadth import breadth_candidates,compression_surface,breadth_scenarios,compression_breadth_plan,breadth_metrics,settle_breadth_bundle
from src.fundamentals_n7_single import settle_n7_single
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--parent',required=True);p.add_argument('--output',required=True);a=p.parse_args();parent=Path(a.parent);out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable output directory required')
 old=json.loads((parent/'plans-frozen.json').read_text());assert stable_json_hash(old['receipt'])==old['seal'];sources=dict(old['receipt']['source_hashes']);input_path=next(k for k in sources if k.endswith('/inputs.json'))
 for path,h in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(input_path).read_text());frame=pd.DataFrame(inputs['rows']);frame=frame[frame.weight.eq(.5)].drop(columns='weight')
 contract=dict(scope='EXPOSED_40_ISSUE_DIAGNOSTIC_ADAPTATION_OF_419_NOT_ISSUE_ACCEPTANCE',budget='ORIGINAL_CURRENT_PER_ISSUE_STAKE_MATCHED_EXACTLY',depths=[0,1,2,3],rules=['TOP1','RETENTION','ABS_LOSS','VALUE_RETENTION','RANDOM'],breadth=['REPEAT','QUALITY','UNION','RANDOM'],random_seeds=[0,1,2],candidate_pool=512,quality_pool=128,candidate_seed=41900,design_seed=41901,evaluation_seed=41902,design_draws=1024,evaluation_draws=8192,unit_cny=2,payout_factor=.65,capital_cny=100000,draw_version='1.1.0',draw_weight=.5,high_weight=.5,learning='NONE',historical_admission=False,scenario_assumption='INDEPENDENT_FIXTURES_SHARED_OUTCOMES_ACROSS_GROUPS',random_control='THREE_FIXED_SEEDS_NOT_CONFIDENCE_INTERVALS',quality_gate='TOP128_COMPRESSED_MASS_WITHIN_SAME512_CANDIDATES')
 closure=implementation_closure(Path.cwd(),['src.fundamentals_compression_breadth','src.fundamentals_n7_single','scripts.run_compression_breadth'],distributions=['numpy','pandas','scipy','scikit-learn'])
 out.mkdir(parents=True);(out/'plans').mkdir();(out/'surfaces').mkdir();hashes={};surface_hashes={}
 for issue,f in frame.groupby('issue',sort=True):
  cuts={str(s):Cutoff.decision_epoch(issue,inputs['cutoffs'][issue][str(s)]) for s in f.slot};path=parent/'plans'/f'{issue}-CURRENT.json';raw=path.read_bytes();h=hashlib.sha256(raw).hexdigest();assert old['receipt']['plan_hashes'][str(path)]==h;sources[str(path)]=h;base=json.loads(raw);budget=base['stake']
  pool=breadth_candidates(f,cutoffs=cuts,seed=41900,pool_size=512);bundle={};surfaces={}
  for depth in range(4):
   for rule in (['TOP1'] if depth==0 else contract['rules']):
    for cseed in ([0,1,2] if rule=='RANDOM' else [0]):
     surface=compression_surface(f,pool,cutoffs=cuts,depth=depth,rule=rule,seed=cseed)
     design=breadth_scenarios(f,surface,cutoffs=cuts,seed=41901,draws=1024);evaluation=breadth_scenarios(f,surface,cutoffs=cuts,seed=41902,draws=8192)
     skey=f'D{depth}_{rule}_C{cseed}';surfaces[skey]=dict(surface=surface,design={k:v for k,v in design.items() if k!='hits'},evaluation={k:v for k,v in evaluation.items() if k!='hits'})
     for breadth in contract['breadth']:
      bseeds=([cseed] if rule=='RANDOM' else [0,1,2]) if breadth=='RANDOM' else [0]
      for bseed in bseeds:
       policy=f'D{depth}_{rule}_{breadth}_C{cseed}_B{bseed}'
       plan=compression_breadth_plan(f,surface,design,cutoffs=cuts,breadth=breadth,seed=bseed,budget_cny=budget,quality_pool_size=128,unit_cny=2,payout_factor=.65)
       if depth==0 and breadth=='REPEAT':
        assert plan['tickets']==base['tickets'] and [(r['slot'],r['support']) for r in plan['legs']]==[(r['slot'],r['support']) for r in base['legs']]
       bundle[policy]=dict(plan=plan,metrics=breadth_metrics(plan,evaluation,cutoffs=cuts),surface_key=skey)
  assert len(bundle)==114
  for folder,obj,ledger in [('plans',bundle,hashes),('surfaces',surfaces,surface_hashes)]:
   path=out/folder/f'{issue}.json.gz';path.write_bytes(gzip.compress(json.dumps(obj,separators=(',',':')).encode(),mtime=0));ledger[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
  print('FROZEN',issue,len(bundle),flush=True)
 receipt=dict(contract=contract,cutoffs=inputs['cutoffs'],source_hashes=sources,plan_hashes=hashes,surface_hashes=surface_hashes,implementation=closure,parent_freeze_seal=old['seal'])
 (out/'plans-frozen.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 # Target decisions and model-only evaluation are frozen before audit access.
 previous=json.loads((parent/'results.json').read_text());audits=[];audit_hashes=previous['audit_hashes']
 for path,h in audit_hashes.items():
  raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==h;audits.extend(json.loads(raw))
 audit=pd.DataFrame(audits);results=[];leg_rows=[]
 for issue in sorted(frame.issue.unique()):
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));obs=audit[audit.issue==issue];labels=obs.set_index(['slot','provider_id']);partition='TEST8' if issue in inputs['contract']['test_issues'] else 'VALIDATION8' if issue in inputs['contract']['validation_issues'] else 'TRAINING24'
  settled=settle_breadth_bundle(bundle,obs)
  for policy,entry in bundle.items():
   plan=entry['plan'];r=settled[policy];assert r['status']=='COMPLETE'
   distances=[]
   for g in range(1,plan['groups']+1):
    distance=0
    for leg in [l for l in plan['legs'] if l['group']==g]:
     actual=labels.loc[(leg['slot'],leg['provider_id']),'actual_direction'];hit=dict(W='3',D='1',L='0')[actual] in leg['support'];distance+=not hit
     ledger=next(l for l in plan['contraction_ledger'] if l['group']==g and l['slot']==leg['slot'])
     leg_rows.append(dict(issue=issue,partition=partition,policy=policy,**ledger,covered=bool(hit)))
    distances.append(distance)
   r.update(policy=policy,partition=partition,depth=plan['single_count'],rule=plan['single_rule'],breadth=plan['breadth'],compression_seed=int(entry['surface_key'].split('_C')[-1]),breadth_seed=plan['seed'],budget_cny=plan['budget_cny'],cash_cny=0,budget_return=r['net']/plan['budget_cny'],unique_tickets=plan['unique_tickets'],paid_ticket_units=plan['paid_ticket_units'],repeat_units=plan['repeat_units'],nominal_groups=plan['nominal_groups'],model_proxy_net=plan['model_proxy_gross']-plan['stake'],miss_distance=min(distances),**entry['metrics']);results.append(r)
  print('SETTLED',issue,flush=True)
 verify_implementation_closure(Path.cwd(),closure)
 for path,h in {**sources,**hashes,**surface_hashes,**audit_hashes}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 (out/'results.json').write_text(json.dumps(dict(rows=results,audit_hashes=audit_hashes,freeze_seal=stable_json_hash(receipt)),indent=2))
 (out/'legs.json.gz').write_bytes(gzip.compress(json.dumps(leg_rows,separators=(',',':')).encode(),mtime=0));print('COMPLETE',len(results),flush=True)
