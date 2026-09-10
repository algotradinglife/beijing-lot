"""Independent support/scenario/settlement verifier; does not call new planners."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();root=Path(a.study);frozen=json.loads((root/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation']);result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**f['surface_hashes'],**result['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());observed={(r['issue'],r['policy']):r for r in result['rows']};assert len(observed)==len(result['rows'])==4560;labels={}
 for path in result['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in labels;labels[key]=r
 leg_data=json.loads(gzip.decompress((root/'legs.json.gz').read_bytes()));leg_hashes={(r['issue'],r['policy'],r['group'],r['slot']):stable_json_hash(r) for r in leg_data};assert len(leg_hashes)==len(leg_data);del leg_data
 checked=0;checked_legs=0
 for path in f['plan_hashes']:
  issue=Path(path).name.split('.')[0];rows=sorted([r for r in inputs['rows'] if r['issue']==issue and r['weight']==.5],key=lambda r:r['slot']);by_slot={r['slot']:r for r in rows};prob=np.array([[r['p_'+d] for d in 'WDL'] for r in rows]);q=np.array([[r['q_'+d] for d in 'WDL'] for r in rows]);top=np.argsort(-prob,axis=1,kind='stable');indices=np.arange(len(rows));p1=prob[indices,top[:,0]];p2=prob[indices,top[:,1]];coverage=p1+p2
  surfaces=json.loads(gzip.decompress((root/'surfaces'/f'{issue}.json.gz').read_bytes()));matrices={}
  for key,entry in surfaces.items():
   s=entry['surface'];assert stable_json_hash({k:v for k,v in s.items() if k!='seal'})==s['seal'];pool=s['pool'];assert stable_json_hash({k:v for k,v in pool.items() if k!='seal'})==pool['seal'];groups=pool['groups'];assert all(utc(t)==utc(f['cutoffs'][issue][slot]) for slot,t in pool['cutoffs'].items());assert len(groups)==512 and len({tuple(g) for g in groups})==512
   rng=np.random.default_rng(s['seed']);mass=[];masks=[];values=[]
   for gi,group in enumerate(groups):
    assert len(group)==len(set(group))==7 and group==sorted(group) and all(0<=i<len(rows) for i in group)
    score={'TOP1':p1,'RETENTION':p1/coverage,'ABS_LOSS':-p2,'VALUE_RETENTION':(p1/q[indices,top[:,0]])/(p1/q[indices,top[:,0]]+p2/q[indices,top[:,1]])}
    chosen=set(map(int,rng.choice(group,s['depth'],replace=False))) if s['rule']=='RANDOM' else set(sorted(group,key=lambda i:(-score[s['rule']][i],rows[i]['slot']))[:s['depth']])
    mask=[int(1<<int(top[i,0])) if i in chosen else int((1<<int(top[i,0]))|(1<<int(top[i,1]))) for i in group];assert mask==s['masks'][gi];masks.append(mask)
    mass.append(math.prod(p1[i] if i in chosen else coverage[i] for i in group));values.append(math.prod(p1[i]/q[i,top[i,0]] if i in chosen else p1[i]/q[i,top[i,0]]+p2[i]/q[i,top[i,1]] for i in group))
    for i,l in zip(group,s['ledger'][gi]):
     assert l['slot']==rows[i]['slot'] and l['single']==(i in chosen)
     assert abs(l['retention']-p1[i]/coverage[i])<1e-12 and abs(l['p2']-p2[i])<1e-12
   assert np.allclose(mass,s['mass'],atol=1e-14,rtol=0) and np.allclose(values,s['value_factor'],atol=1e-10,rtol=0)
   sims={}
   for name in ['design','evaluation']:
    receipt=entry[name];assert receipt['seed']==f['contract']['design_seed' if name=='design' else 'evaluation_seed'];assert receipt['draws']==f['contract']['design_draws' if name=='design' else 'evaluation_draws'];assert stable_json_hash({k:v for k,v in receipt.items() if k!='seal'})==receipt['seal'];assert receipt['cutoffs']==pool['cutoffs'];assert receipt['shape']==[512,receipt['draws']];u=np.random.default_rng(receipt['seed']).random((len(rows),receipt['draws']));outcome=(u>=prob[:,0,None]).astype(int)+(u>=(prob[:,0]+prob[:,1])[:,None]).astype(int);bits=1<<outcome
    hit=np.asarray([np.all((bits[g]&np.asarray(m)[:,None])>0,axis=0) for g,m in zip(groups,masks)])
    assert hashlib.sha256(hit.tobytes()).hexdigest()==receipt['sha256'] and receipt['surface_seal']==s['seal'];sims[name]=hit
   assert entry['design']['seed']!=entry['evaluation']['seed'];matrices[key]=sims
  bundle=json.loads(gzip.decompress(Path(path).read_bytes()));assert len(bundle)==114
  for policy,entry in bundle.items():
   p=entry['plan'];s=surfaces[entry['surface_key']]['surface'];sims=matrices[entry['surface_key']];o=observed[issue,policy];assert stable_json_hash({k:v for k,v in p.items() if k!='seal'})==p['seal'];assert p['surface_seal']==s['seal'];groups=s['pool']['groups'];depth=s['depth'];eligible=sorted(range(512),key=lambda i:(-s['mass'][i],groups[i]))[:128];count=p['budget_cny']//(2*2**(7-depth))
   if p['breadth']=='REPEAT':expected=[groups.index(g) for g in s['pool']['original']];units=2**depth
   elif p['breadth']=='QUALITY':expected=eligible[:count];units=1
   elif p['breadth']=='RANDOM':expected=list(map(int,np.random.default_rng(p['seed']).choice(eligible,count,replace=False)));units=1
   else:
    expected=[];remaining=list(eligible);uncovered=np.ones(1024,dtype=bool)
    for _ in range(count):
     gains=(sims['design'][remaining]&uncovered).sum(axis=1);i=remaining.pop(int(np.argmax(gains)));expected.append(i);uncovered&=~sims['design'][i]
    units=1
   assert expected==p['selected_candidates'];assert p['groups']==len(expected);assert p['stake']==p['budget_cny']==o['stake']==256*min(6,len(rows)//7)
   for slot,epoch in p['cutoffs'].items():assert utc(epoch)==utc(f['cutoffs'][issue][slot])
   gross=0.;hits=0;identities=set();exposures=Counter();outcomes=Counter();misses=[];sets=[];single_counts=Counter()
   for gi,candidate in enumerate(expected,1):
    legs=sorted([l for l in p['legs'] if l['group']==gi],key=lambda r:r['slot']);assert [l['slot'] for l in legs]==[rows[i]['slot'] for i in groups[candidate]];sets.append({l['slot'] for l in legs})
    for l,mask in zip(legs,s['masks'][candidate]):
     assert l['support']==''.join(code for b,code in enumerate('310') if mask&(1<<b));raw=by_slot[l['slot']];assert all(l[k]==raw[k] for k in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L'])
     if len(l['support'])==1:single_counts[l['slot']]+=1
     ledger=next(z for z in p['contraction_ledger'] if z['group']==gi and z['slot']==l['slot']);label=labels[issue,l['slot'],l['provider_id']]['actual_direction'];expected_leg=dict(issue=issue,partition=o['partition'],policy=policy,**ledger,covered=dict(W='3',D='1',L='0')[label] in l['support']);assert stable_json_hash(expected_leg)==leg_hashes[issue,policy,gi,l['slot']];checked_legs+=1
    assert sum(len(l['support'])==1 for l in legs)==depth
    tickets=[t for t in p['tickets'] if t['group']==gi];codes={''.join(c) for c in itertools.product(*(l['support'] for l in legs))};assert len(tickets)==len(codes)==2**(7-depth) and {t['code'] for t in tickets}==codes and all(t['units']==units for t in tickets)
    for t in tickets:
     identity=tuple((issue,l['slot'],l['provider_id'],code) for l,code in zip(legs,t['code']));assert identity not in identities;identities.add(identity)
     for l,code in zip(legs,t['code']):exposures[l['slot']]+=units;outcomes[l['slot'],code]+=units
    obs=[labels[issue,l['slot'],l['provider_id']] for l in legs];assert all(l['handicap']==r['handicap'] for l,r in zip(legs,obs));actual=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in obs);misses.append(sum(code not in l['support'] for l,code in zip(legs,actual)))
    if actual in codes:hits+=1;gross+=2*.65*units*math.prod(r['spf_sp'] for r in obs)
   union=sims['evaluation'][expected].any(axis=0).mean();total=sum(exposures.values());hhi=sum((v/total)**2 for v in exposures.values());ohhi=sum((v/total)**2 for v in outcomes.values());overlap=max((len(a&b) for a,b in itertools.combinations(sets,2)),default=0)
   assert len(identities)==p['unique_tickets']==o['unique_tickets'] and sum(t['units'] for t in p['tickets'])==p['paid_ticket_units']==p['stake']//2
   assert p['repeat_units']==p['paid_ticket_units']-p['unique_tickets']
   assert abs(gross-o['gross'])<1e-7 and abs(gross-p['stake']-o['net'])<1e-7 and hits==o['hits'] and o['miss_distance']==min(misses)
   assert abs(union-o['model_union'])<1e-12 and abs(hhi-o['fixture_hhi'])<1e-12 and abs(ohhi-o['outcome_hhi'])<1e-12 and overlap==o['max_pair_overlap'] and max(single_counts.values(),default=0)==o['max_single_groups']
   assert abs(p['model_proxy_gross']-2*.65*units*sum(s['value_factor'][i] for i in expected))<1e-7
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==4560 and checked_legs==len(leg_hashes)
 print('PASS',checked,'plans; compression, matched units, duplicates, scenario union, exposure, prices and settlement')
