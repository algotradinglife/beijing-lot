"""Independently check C1/C2 frozen sources, gates, physical tickets and payouts."""
import argparse,gzip,hashlib,itertools,json,math,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import verify_implementation_closure
from src.fundamentals_clean_receipts import verify_clean_file_bindings

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 saved=json.loads((out/'freeze-receipt.json').read_text());r=saved['receipt'];assert stable_json_hash(r)==saved['seal']
 verify_implementation_closure(Path.cwd(),r['implementation']);verify_clean_file_bindings({**r['source_hashes'],**r['plan_hashes']},repository_root=Path.cwd())
 report=json.loads((out/'plans-frozen.json').read_text());assert hashlib.sha256(report['canonical_json'].encode()).hexdigest()==report['seal']
 receipt=json.loads(report['canonical_json']);assert hashlib.sha256((out/'results.json').read_bytes()).hexdigest()==receipt['result_sha256']
 verify_clean_file_bindings(receipt['source_hashes'],repository_root=Path.cwd())
 paths=[k for k in receipt['source_hashes'] if k.endswith('settlement-audit.json')];assert len(paths)==1
 audit=json.loads(Path(paths[0]).read_text())['rows'];labels={(z['issue'],z['slot'],z['provider_id']):z for z in audit};assert len(labels)==len(audit)
 results=json.loads((out/'results.json').read_text())['rows'];observed={(z['issue'],z['policy']):z for z in results};assert len(observed)==len(results)==384
 checked=0
 for issue in r['issues']:
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
  originals=json.loads(gzip.decompress((Path(r['source'])/'plans'/f'{issue}.json.gz').read_bytes()))
  for depth,overlap in itertools.product([1,2],['FREE','STRICT']):
   case=f'D{depth}_TOP2_{overlap}';base=bundle[case+'_BASE']['plan'];assert base==originals[case+'_BASE']['plan'];base_hits=[]
   for rule in ['BASE','SINGLE75']:
    policy=case+'_'+rule;plan=bundle[policy]['plan'];assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
    for key in ['groups','stake','cash_cny','budget_cny','cutoffs','group_units','single_count']:assert plan[key]==base[key]
    cost=2*2**(7-depth);assert plan['stake']==cost*plan['groups'] and plan['stake']+plan['cash_cny']==1024
    seen=Counter();sets=[];gross=0.;wins=[];changes=0;ticket_ids=set()
    for g in range(1,plan['groups']+1):
     old=sorted([z for z in base['legs'] if z['group']==g],key=lambda z:z['slot']);new=sorted([z for z in plan['legs'] if z['group']==g],key=lambda z:z['slot'])
     assert len(new)==7 and sorted(len(z['support']) for z in new)==[1]*depth+[2]*(7-depth)
     slots={z['slot'] for z in new};assert len(slots)==7 and slots not in sets
     if overlap=='STRICT':assert all(len(slots&s)<=2 for s in sets)
     sets.append(slots)
     for b,z in zip(old,new):
      support=b['support'];order=sorted('WDL',key=lambda d:(-b['p_'+d],'WDL'.index(d)))
      if rule=='SINGLE75' and seen[b['slot']] and len(support)==1 and b['p_'+order[0]]<=.75+1e-12:support=dict(W='3',D='1',L='0')[order[1]]
      assert z==dict(b,support=support);changes+=support!=b['support'];seen[b['slot']]+=1
     ts=[t for t in plan['tickets'] if t['group']==g];assert len(ts)==2**(7-depth) and all(t['units']==1 for t in ts)
     assert {t['code'] for t in ts}=={''.join(c) for c in itertools.product(*(z['support'] for z in new))}
     for t in ts:
      identity=tuple((z['slot'],c) for z,c in zip(new,t['code']));assert identity not in ticket_ids;ticket_ids.add(identity)
     truth=[labels[issue,z['slot'],z['provider_id']] for z in new]
     assert all(q['status']=='READY' and q['handicap']==z['handicap'] for q,z in zip(truth,new))
     win=all(dict(W='3',D='1',L='0')[q['actual_direction']] in z['support'] for q,z in zip(truth,new));wins.append(win)
     if win:gross+=2*.65*math.prod(q['spf_sp'] for q in truth)
    if overlap=='STRICT':assert max(seen.values())<=2
    if rule=='BASE':base_hits=wins
    z=observed[issue,policy];assert abs(z['gross']-gross)<1e-7 and abs(z['net']-(gross-plan['stake']))<1e-7
    assert z['hits']==sum(wins) and z['changed_legs']==changes
    assert z['gained_groups']==sum(a and not b for a,b in zip(wins,base_hits)) and z['lost_groups']==sum(b and not a for a,b in zip(wins,base_hits))
    checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==384
 print('PASS 384 plans: immutable sources, C1/C2 roles/costs, repeated-single gates, caps, tickets, payouts and matched changes')
