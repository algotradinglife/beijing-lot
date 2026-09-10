"""Independent factorial selection, physical ticket and settlement enumeration."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();root=Path(a.study)
 frozen=json.loads((root/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation'])
 result=json.loads((root/'results.json').read_text());assert result['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**f['surface_hashes'],**result['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());observed={(r['issue'],r['policy']):r for r in result['rows']};assert len(observed)==len(result['rows'])==1440
 labels={}
 for path in result['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=r['issue'],r['slot'],r['provider_id'];assert key not in labels;labels[key]=r
 checked=0
 for path in f['plan_hashes']:
  issue=Path(path).name.split('.')[0];bundle=json.loads(gzip.decompress(Path(path).read_bytes()));assert len(bundle)==36
  rows=sorted([r for r in inputs['rows'] if r['issue']==issue and r['weight']==.5],key=lambda r:r['slot']);slots=[r['slot'] for r in rows];by_slot={r['slot']:r for r in rows};prob=np.array([[r['p_'+d] for d in 'WDL'] for r in rows]);top=np.argsort(-prob,axis=1,kind='stable');coverage=np.take_along_axis(prob,top[:,:2],axis=1).sum(axis=1)
  rank=sorted(range(len(rows)),key=lambda i:(-coverage[i],slots[i],rows[i]['provider_id']))
  base={tuple(sorted(rank[i*7:(i+1)*7])) for i in range(min(6,len(rows)//7))}
  for i in range(min(len(rows),512)):
   if len(base)>=512:break
   base.add(tuple(sorted(rank[(i+j)%len(rows)] for j in range(7))))
  rng=np.random.default_rng(41900)
  while len(base)<512:base.add(tuple(sorted(map(int,rng.choice(len(rows),7,replace=False)))))
  old={d:json.loads(Path(next(k for k in f['source_hashes'] if k.endswith(f'/{issue}-SINGLE_{d}.json'))).read_text()) for d in (1,2)}
  old_sets={d:[tuple(sorted(slots.index(l['slot']) for l in old[d]['legs'] if l['group']==g)) for g in range(1,old[d]['groups']+1)] for d in (1,2)}
  expected_pool=sorted(base|set(old_sets[1])|set(old_sets[2]))
  surfaces=json.loads(gzip.decompress((root/'surfaces'/f'{issue}.json.gz').read_bytes()));matrix={}
  for key,entry in surfaces.items():
   s=entry['surface'];assert stable_json_hash({k:v for k,v in s.items() if k!='seal'})==s['seal'];pool=s['pool'];assert stable_json_hash({k:v for k,v in pool.items() if k!='seal'})==pool['seal'];assert list(map(tuple,pool['groups']))==expected_pool
   assert all(utc(v)==utc(f['cutoffs'][issue][k]) for k,v in pool['cutoffs'].items());d=int(key)
   assert s['prefix']==[pool['groups'].index(list(g)) for g in old_sets[d][:old[d]['disjoint_groups']]]
   mass=[];masks=[]
   for g in pool['groups']:
    single=set(sorted(g,key=lambda i:(-prob[i,top[i,0]],slots[i]))[:d]);mask=[int(1<<int(top[i,0])) if i in single else int((1<<int(top[i,0]))|(1<<int(top[i,1]))) for i in g];masks.append(mask);mass.append(math.prod(prob[i,top[i,0]] if i in single else coverage[i] for i in g))
   assert masks==s['masks'] and np.allclose(mass,s['mass'],rtol=0,atol=1e-14)
   for name,seed,draws in [('design',41901,1024),('evaluation',41902,8192)]:
    receipt=entry[name];assert receipt['seed']==seed and receipt['draws']==draws;assert receipt['surface_seal']==s['seal'] and receipt['cutoffs']==pool['cutoffs'];assert stable_json_hash({k:v for k,v in receipt.items() if k!='seal'})==receipt['seal']
    u=np.random.default_rng(seed).random((len(rows),draws));bits=1<<((u>=prob[:,0,None]).astype(int)+(u>=(prob[:,0]+prob[:,1])[:,None]).astype(int));hits=np.asarray([np.all((bits[g]&np.asarray(m)[:,None])>0,axis=0) for g,m in zip(pool['groups'],masks)])
    assert receipt['shape']==list(hits.shape) and receipt['sha256']==hashlib.sha256(hits.tobytes()).hexdigest()
    if name=='evaluation':matrix[d]=hits
  recent_path=next(k for k in f['source_hashes'] if k.endswith(f'/plans/{issue}.json.gz'));recent=json.loads(gzip.decompress(Path(recent_path).read_bytes()))
  for policy,entry in bundle.items():
   p=entry['plan'];d=entry['depth'];o=observed[issue,policy];assert stable_json_hash({k:v for k,v in p.items() if k!='seal'})==p['seal'];s=surfaces[str(d)]['surface'];groups=s['pool']['groups'];cost=2*2**(7-d)
   if entry['kind']=='RECENT':assert p==recent[f'D{d}_TOP1_QUALITY_C0_B0']['plan'];expected=p['selected_candidates'];mult=[1]*len(expected)
   elif entry['kind']=='OLD':
    assert p['legs']==old[d]['legs'] and p['tickets']==old[d]['tickets'];expected=[groups.index(list(g)) for g in old_sets[d]];mult=[1]*len(expected)
   else:
    a=p['factors'];scores=s['mass'] if a['quality']=='COMPRESSED' else [math.prod(coverage[i] for i in g) for g in groups]
    order=sorted(range(len(groups)),key=lambda i:(-math.log(scores[i])+(1e-10*sum(groups[i]) if a['quality']=='TOP2' else 0),groups[i]));expected=list(s['prefix']) if a['preserve_prefix'] else []
    while len(expected)<p['budget_cny']//cost:
     uses=Counter(j for i in expected for j in groups[i]);eligible=[i for i in order if i not in expected and (a['overlap']=='FREE' or all(uses[j]<2 for j in groups[i]) and all(len(set(groups[i])&set(groups[k]))<=2 for k in expected))]
     if not eligible:break
     expected.append(eligible[0])
    mult=[1]*len(expected)
    if a['cash_policy']=='REPEAT_BEST':mult[min(range(len(expected)),key=lambda j:(-s['mass'][expected[j]],groups[expected[j]]))]+=(p['budget_cny']-len(expected)*cost)//cost
   assert p['selected_candidates']==expected and p['groups']==len(expected);assert p['stake']==sum(mult)*cost and p['cash_cny']==p['budget_cny']-p['stake'] and p['stake']==o['stake'];gross=0.;won=0;identities=set();fixture=Counter();outcomes=Counter();sets=[]
   for g,u in enumerate(mult,1):
    legs=sorted([l for l in p['legs'] if l['group']==g],key=lambda r:r['slot']);sets.append({l['slot'] for l in legs});assert len(legs)==7 and sum(len(l['support'])==1 for l in legs)==d
    if entry['kind']!='RECENT':assert [l['slot'] for l in legs]==[slots[i] for i in groups[expected[g-1]]]
    chosen=set(l['slot'] for l in sorted(legs,key=lambda l:(-max(l['p_'+z] for z in 'WDL'),l['slot']))[:d])
    for l in legs:
     raw=by_slot[l['slot']];assert all(l[k]==raw[k] for k in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L']);order=sorted('WDL',key=lambda z:(-raw['p_'+z],'WDL'.index(z)));support=set(order[:1 if l['slot'] in chosen else 2]);assert set(l['support'])=={dict(W='3',D='1',L='0')[z] for z in support}
    tickets=[t for t in p['tickets'] if t['group']==g];codes={''.join(z) for z in itertools.product(*(l['support'] for l in legs))};assert len(tickets)==len(codes) and {t['code'] for t in tickets}==codes and all(t['units']==u for t in tickets)
    for t in tickets:
     identity=tuple((l['slot'],code) for l,code in zip(legs,t['code']));assert identity not in identities;identities.add(identity)
     for l,code in zip(legs,t['code']):fixture[l['slot']]+=u;outcomes[l['slot'],code]+=u
    labels_group=[labels[issue,l['slot'],l['provider_id']] for l in legs];assert all(l['handicap']==r['handicap'] for l,r in zip(legs,labels_group));actual=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in labels_group)
    if actual in codes:won+=1;gross+=2*.65*u*math.prod(r['spf_sp'] for r in labels_group)
   assert abs(gross-o['gross'])<1e-7 and abs(gross-p['stake']-o['net'])<1e-7 and won==o['hits'];assert len(identities)==o['unique_tickets'];assert sum(t['units']-1 for t in p['tickets'])==o['repeat_units'];total=sum(fixture.values())
   assert abs(sum((v/total)**2 for v in fixture.values())-o['fixture_hhi'])<1e-12 and abs(sum((v/total)**2 for v in outcomes.values())-o['outcome_hhi'])<1e-12
   assert max((len(a&b) for a,b in itertools.combinations(sets,2)),default=0)==o['max_pair_overlap']
   if entry['kind']!='RECENT':assert float(matrix[d][expected].any(axis=0).mean())==o['model_union']
   else:assert o['model_union']==recent[f'D{d}_TOP1_QUALITY_C0_B0']['metrics']['model_union']
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==1440;print('PASS',checked,'plans; controls, candidate pool, factorial selection, cash, supports, union and settlement')
