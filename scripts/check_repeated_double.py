"""Independent replay of repeated-double replacement and shared support scenarios."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();root=Path(a.study)
 frozen=json.loads((root/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation']);result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**result['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());observed={(r['issue'],r['policy']):r for r in result['rows']};assert len(observed)==len(result['rows'])==640;labels={}
 for path in result['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=r['issue'],r['slot'],r['provider_id'];assert key not in labels;labels[key]=r
 checked=0
 for path in f['plan_hashes']:
  issue=Path(path).name.split('.')[0];bundle=json.loads(gzip.decompress(Path(path).read_bytes()));assert len(bundle)==16
  candidates=[]
  for source in f['source_hashes']:
   if source.endswith(f'/plans/{issue}.json.gz'):
    saved=json.loads(gzip.decompress(Path(source).read_bytes()))
    if 'D1_P1_TOP2_STRICT_HOLD' in saved:candidates.append((source,saved))
  assert len(candidates)==1;parent_path,parent=candidates[0];parent_freeze=json.loads((Path(parent_path).parents[1]/'plans-frozen.json').read_text());assert stable_json_hash(parent_freeze['receipt'])==parent_freeze['seal']==f['parent_seal']
  rows=sorted([r for r in inputs['rows'] if r['issue']==issue and r['weight']==.5],key=lambda r:r['slot']);by_slot={r['slot']:r for r in rows};index={r['slot']:i for i,r in enumerate(rows)};prob=np.array([[r['p_'+d] for d in 'WDL'] for r in rows]);u=np.random.default_rng(41902).random((len(rows),8192));outcome=(u>=prob[:,0,None]).astype(int)+(u>=(prob[:,0]+prob[:,1])[:,None]).astype(int);bits=1<<outcome;group_wins={}
  for policy,entry in bundle.items():
   plan=entry['plan'];o=observed[issue,policy];source=parent[entry['source_policy']]['plan'];case=entry['case'];adjust=entry['action']=='ADJUSTED'
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   if not adjust:assert plan==source
   else:assert plan['source_support_plan_seal']==source['seal'] and 'surface_seal' not in plan and 'selected_candidates' not in plan
   for k in ['stake','cash_cny','budget_cny','groups','single_count','input_sha256','cutoffs']:assert plan[k]==source[k]
   assert all(utc(v)==utc(f['cutoffs'][issue][k]) for k,v in plan['cutoffs'].items());seen=Counter();ledger=[];mat=[];gross=0.;won=[];fixture=Counter();outcomes=Counter();identities=set();masses=[];groups=[];masks=[];proxy=0.
   for g in range(1,plan['groups']+1):
    old_legs=sorted([l for l in source['legs'] if l['group']==g],key=lambda r:r['slot']);legs=sorted([l for l in plan['legs'] if l['group']==g],key=lambda r:r['slot']);assert len(legs)==7 and [l['slot'] for l in legs]==[l['slot'] for l in old_legs]
    for before,after in zip(old_legs,legs):
     raw=by_slot[before['slot']];assert all(after[k]==before[k]==raw[k] for k in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L']);order=sorted('WDL',key=lambda d:(-raw['p_'+d],'WDL'.index(d)));expected=before['support']
     if adjust and seen[before['slot']]>0 and len(expected)==2 and raw['p_'+order[1]]-raw['p_'+order[2]]<=f['contract']['max_gap']+1e-12:expected=''.join(code for d,code in zip('WDL','310') if d in [order[0],order[2]])
     assert after==dict(before,support=expected)
     ledger.append(dict(group=g,slot=before['slot'],provider_id=before['provider_id'],prior_appearances=seen[before['slot']],source_support=before['support'],selected_support=expected,changed=before['support']!=expected,second_third_gap=raw['p_'+order[1]]-raw['p_'+order[2]],original_mass=sum(raw['p_'+d] for d,c in zip('WDL','310') if c in before['support']),selected_mass=sum(raw['p_'+d] for d,c in zip('WDL','310') if c in expected)));seen[before['slot']]+=1
    ts=[t for t in plan['tickets'] if t['group']==g];original_ts=[t for t in source['tickets'] if t['group']==g];codes={''.join(z) for z in itertools.product(*(l['support'] for l in legs))};assert len(ts)==len(codes)==len(original_ts);assert {t['code'] for t in ts}==codes and [t['units'] for t in ts]==[t['units'] for t in original_ts]
    units=ts[0]['units'];assert all(t['units']==units for t in ts)
    if adjust:assert plan['group_units'][g-1]==units
    for t in ts:
     identity=tuple((l['slot'],c) for l,c in zip(legs,t['code']));assert identity not in identities;identities.add(identity)
     for l,c in zip(legs,t['code']):fixture[l['slot']]+=units;outcomes[l['slot'],c]+=units
    group=[index[l['slot']] for l in legs];mask=[sum(1<<b for b,c in enumerate('310') if c in l['support']) for l in legs];groups.append(group);masks.append(mask);mat.append(np.all((bits[group]&np.asarray(mask)[:,None])>0,axis=0));masses.append(math.prod(sum(l['p_'+d] for d,c in zip('WDL','310') if c in l['support']) for l in legs));proxy+=2*.65*units*math.prod(sum(l['p_'+d]/l['q_'+d] for d,c in zip('WDL','310') if c in l['support']) for l in legs)
    obs=[labels[issue,l['slot'],l['provider_id']] for l in legs];assert all(l['handicap']==r['handicap'] for l,r in zip(legs,obs));actual=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in obs);hit=actual in codes;won.append(hit)
    if hit:gross+=2*.65*units*math.prod(r['spf_sp'] for r in obs)
   if adjust:assert ledger==plan['diversity_ledger'] and plan['max_gap']==f['contract']['max_gap']
   assert np.allclose(masses,plan['group_probability'],rtol=0,atol=1e-14);assert abs(proxy-plan['model_proxy_gross'])<1e-7
   receipt=entry['evaluation']['receipt'];assert stable_json_hash({k:v for k,v in receipt.items() if k!='seal'})==receipt['seal'] and receipt['plan_seal']==plan['seal'];surface=receipt['support_surface'];assert surface['pool']['groups']==groups and surface['masks']==masks;assert stable_json_hash({k:v for k,v in surface.items() if k!='seal'})==surface['seal'];assert surface['pool']['cutoffs']==plan['cutoffs'] and surface['pool']['input_sha256']==plan['input_sha256']
   e=receipt['evaluation'];matrix=np.asarray(mat);assert e['seed']==41902 and e['draws']==8192 and e['shape']==list(matrix.shape) and e['sha256']==hashlib.sha256(matrix.tobytes()).hexdigest();assert e['cutoffs']==plan['cutoffs'] and e['surface_seal']==surface['seal'];assert stable_json_hash({k:v for k,v in e.items() if k!='seal'})==e['seal'];assert receipt['original_design_receipt']==source['design_receipt'] and e['seed']!=source['design_receipt']['seed']
   total=sum(fixture.values());assert abs(sum((v/total)**2 for v in fixture.values())-o['fixture_hhi'])<1e-12 and abs(sum((v/total)**2 for v in outcomes.values())-o['outcome_hhi'])<1e-12
   assert abs(gross-o['gross'])<1e-7 and abs(gross-plan['stake']-o['net'])<1e-7 and sum(won)==o['hits'];assert matrix.any(axis=0).mean()==o['model_union'];assert o['changed_legs']==sum(l['changed'] for l in ledger);assert len(identities)==o['unique_tickets'];assert sum(t['units']*2 for t in plan['tickets'])==o['stake'];group_wins[policy]=won;checked+=1
  for policy,entry in bundle.items():
   b=group_wins[entry['case']+'_BASE'];z=group_wins[policy];o=observed[issue,policy];assert sum(a and not c for a,c in zip(z,b))==o['gained_groups'] and sum(c and not a for a,c in zip(z,b))==o['lost_groups']
  print('VERIFIED',issue,flush=True)
 assert checked==640;print('PASS 640 plans; source controls, ordered support replacement, unchanged money/singles, actual-support scenarios and settlement')
