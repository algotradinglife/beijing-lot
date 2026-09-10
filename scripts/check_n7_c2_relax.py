"""Independent enumeration of reuse caps, diversity choices, tickets and cash."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 frozen=json.loads((out/'plans-frozen.json').read_text());f=frozen['receipt'];assert stable_json_hash(f)==frozen['seal'];verify_implementation_closure(Path.cwd(),f['implementation'])
 results=json.loads((out/'results.json').read_text());assert results['freeze_seal']==frozen['seal']
 for path,h in {**f['source_hashes'],**f['plan_hashes'],**results['audit_hashes']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 inputs=json.loads(Path(next(k for k in f['source_hashes'] if k.endswith('/inputs.json'))).read_text());source={(r['issue'],r['slot']):r for r in inputs['rows'] if r['weight']==.5};labels={}
 for path in results['audit_hashes']:
  for r in json.loads(Path(path).read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in labels;labels[key]=r
 observed={(r['issue'],r['policy']):r for r in results['rows']};checked=0
 for path in f['plan_hashes']:
  bundle=json.loads(gzip.decompress(Path(path).read_bytes()));issue=next(iter(bundle.values()))['issue']
  ranked=sorted([r for (i,s),r in source.items() if i==issue],key=lambda r:(-sum(sorted([r['p_'+d] for d in 'WDL'],reverse=True)[:2]),r['slot'],r['provider_id']))
  for policy,plan in bundle.items():
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal'];o=observed[issue,policy];sets=[];gross=0;hits=0;unique_tickets=set();history=defaultdict(lambda:dict(W=0,D=0,L=0));changed=0;expected=0;covered=0
   cap=plan.get('max_uses',1);k=plan.get('single_count',0);diverse=policy.endswith('DIVERSE')
   original=bundle['U2_P2']
   if policy!='U2_P2':
    assert plan['extension_source_seal']==original['seal'] and plan['preserved_groups']==original['groups']
    assert plan['legs'][:len(original['legs'])]==original['legs'] and plan['tickets'][:len(original['tickets'])]==original['tickets']
   assert k==2 and not diverse and plan['budget_cny']==original['budget_cny']
   assert o['added_groups']==plan['groups']-original['groups'] and o['added_stake']==plan['stake']-original['stake']
   assert o['added_hits']==o['hits']-observed[issue,'U2_P2']['hits']
   assert abs(o['added_net']-o['net']+observed[issue,'U2_P2']['net'])<1e-8
   if diverse:
    fixed=bundle[policy.replace('DIVERSE','FIXED')]
    assert plan['stake']==fixed['stake'] and [(r['group'],r['slot']) for r in plan['legs']]==[(r['group'],r['slot']) for r in fixed['legs']]
   for s,t in plan['cutoffs'].items():assert utc(t)==utc(f['cutoffs'][issue][s])
   for group in range(1,plan['groups']+1):
    legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot']);slots={r['slot'] for r in legs};assert len(slots)==len(legs)==7;sets.append(slots)
    if group<=plan.get('disjoint_groups',plan['groups']):assert slots=={r['slot'] for r in ranked[(group-1)*7:group*7]}
    top=sorted(legs,key=lambda r:(-max(r['p_'+d] for d in 'WDL'),r['slot'],r['provider_id']))[:k];single_slots={r['slot'] for r in top};masses=[]
    for r in legs:
     raw=source[issue,r['slot']];assert all(r[c]==raw[c] for c in ['provider_id','handicap','p_W','p_D','p_L','q_W','q_D','q_L'])
     width=1 if r['slot'] in single_slots else 2
     normal=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))[:width]
     selected=sorted('WDL',key=lambda d:(-r['p_'+d]/(1+history[r['slot']][d]),'WDL'.index(d)))[:width] if diverse else normal
     support=''.join(c for d,c in zip('WDL','310') if d in selected);assert support==r['support']
     changed+=support!=''.join(c for d,c in zip('WDL','310') if d in normal)
     for d in selected:history[r['slot']][d]+=1
     masses.append(sum(r['p_'+d] for d in selected));covered+=labels[issue,r['slot'],r['provider_id']]['actual_direction'] in selected
    expected+=math.prod(masses)
    tickets=[t for t in plan['tickets'] if t['group']==group];cartesian=[''.join(z) for z in itertools.product(*(r['support'] for r in legs))]
    assert len(tickets)==2**(7-k) and sorted(t['code'] for t in tickets)==sorted(cartesian) and all(t['units']==1 for t in tickets)
    for t in tickets:
     identity=tuple((issue,r['slot'],r['provider_id'],c) for r,c in zip(legs,t['code']));assert identity not in unique_tickets;unique_tickets.add(identity)
    obs=[labels[issue,r['slot'],r['provider_id']] for r in legs];assert all(r['handicap']==l['handicap'] for r,l in zip(legs,obs))
    actual=''.join(dict(W='3',D='1',L='0')[l['actual_direction']] for l in obs)
    if actual in cartesian:gross+=2*.65*math.prod(l['spf_sp'] for l in obs);hits+=1
   counts=Counter(s for g in sets for s in g);pairs={(r['slot'],c) for r in plan['legs'] for c in r['support']}
   assert max(counts.values(),default=0)<=cap and all(len(a&b)<=plan['max_pair_overlap'] for a,b in itertools.combinations(sets,2))
   assert o['stake']==len(plan['tickets'])*2 and o['cash_cny']==o['budget_cny']-o['stake']>=0
   assert abs(o['gross']-gross)<1e-7 and abs(o['net']-gross+o['stake'])<1e-7 and o['hits']==hits
   assert o['covered_legs']==covered and o['unique_fixtures']==len(counts) and o['unique_fixture_direction_pairs']==len(pairs)
   assert abs(o['expected_winning_groups']-expected)<1e-9 and o['changed_support_legs']==changed
   if plan['cash_cny']>=64:assert plan['overlap_ledger'][-1]['status']=='PROVEN_INFEASIBLE'
   checked+=1
 assert checked==480
 print('PASS',checked,'plans; caps, unchanged probabilities, diversity, no duplicate full tickets, coverage and settlement')
