"""Independent replay: preserved cap groups, single75 gates, tickets and payouts."""
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
 wrapped=json.loads((out/'plans-frozen.json').read_text());assert hashlib.sha256(wrapped['canonical_json'].encode()).hexdigest()==wrapped['seal']
 receipt=json.loads(wrapped['canonical_json']);assert hashlib.sha256((out/'results.json').read_bytes()).hexdigest()==receipt['result_sha256']
 verify_clean_file_bindings(receipt['source_hashes'],repository_root=Path.cwd())
 audit_paths=[k for k in receipt['source_hashes'] if k.endswith('settlement-audit.json')];assert len(audit_paths)==1
 audit=json.loads(Path(audit_paths[0]).read_text())['rows'];labels={(z['issue'],z['slot'],z['provider_id']):z for z in audit};assert len(labels)==len(audit)
 results=json.loads((out/'results.json').read_text())['rows'];observed={(z['issue'],z['policy']):z for z in results};assert len(observed)==len(results)==576
 count=0
 for issue in r['issues']:
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()))
  source=json.loads(gzip.decompress((Path(r['source'])/'plans'/f'{issue}.json.gz').read_bytes()))
  for uses,pair in r['parameters']['caps']:
   case=f'U{uses}_P{pair}';base=bundle[case+'_BASE']['plan'];assert base==source[case+'_CAPPED']['plan'];base_hits=[]
   for rule in ['BASE','SINGLE75']:
    policy=case+'_'+rule;plan=bundle[policy]['plan'];assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
    for key in ['groups','stake','cash_cny','budget_cny','cutoffs','group_units','max_uses','max_pair_overlap']:assert plan[key]==base[key]
    assert plan['stake']==64*plan['groups'] and plan['stake']+plan['cash_cny']==1024
    seen=Counter();sets=[];wins=[];gross=0.;changes=0;ticket_ids=set()
    for g in range(1,plan['groups']+1):
     old=sorted([z for z in base['legs'] if z['group']==g],key=lambda z:z['slot']);new=sorted([z for z in plan['legs'] if z['group']==g],key=lambda z:z['slot'])
     assert len(new)==7 and sorted(len(z['support']) for z in new)==[1,1,2,2,2,2,2]
     slots={z['slot'] for z in new};assert len(slots)==7 and all(len(slots&s)<=pair for s in sets);sets.append(slots)
     for b,z in zip(old,new):
      support=b['support'];order=sorted('WDL',key=lambda d:(-b['p_'+d],'WDL'.index(d)))
      if rule=='SINGLE75' and seen[b['slot']] and len(support)==1 and b['p_'+order[0]]<=.75+1e-12:
       support=dict(W='3',D='1',L='0')[order[1]]
      assert z==dict(b,support=support);changes+=support!=b['support'];seen[b['slot']]+=1
     tickets=[t for t in plan['tickets'] if t['group']==g]
     assert len(tickets)==32 and all(t['units']==1 for t in tickets)
     assert {t['code'] for t in tickets}=={''.join(c) for c in itertools.product(*(z['support'] for z in new))}
     for t in tickets:
      identity=tuple((z['slot'],c) for z,c in zip(new,t['code']));assert identity not in ticket_ids;ticket_ids.add(identity)
     truth=[labels[issue,z['slot'],z['provider_id']] for z in new]
     assert all(q['status']=='READY' and q['handicap']==z['handicap'] for q,z in zip(truth,new))
     win=all(dict(W='3',D='1',L='0')[q['actual_direction']] in z['support'] for q,z in zip(truth,new));wins.append(win)
     if win:gross+=2*.65*math.prod(q['spf_sp'] for q in truth)
    assert max(seen.values())<=uses
    if rule=='BASE':base_hits=wins
    result=observed[issue,policy]
    assert abs(result['gross']-gross)<1e-7 and abs(result['net']-(gross-plan['stake']))<1e-7
    assert result['hits']==sum(wins) and result['changed_legs']==changes
    assert result['gained_groups']==sum(a and not b for a,b in zip(wins,base_hits))
    assert result['lost_groups']==sum(b and not a for a,b in zip(wins,base_hits))
    if uses==1:assert changes==0 and plan['tickets']==base['tickets']
    count+=1
  print('VERIFIED',issue,flush=True)
 assert count==576
 print('PASS 576 plans: exact frozen groups/caps/cash, single75 only, physical tickets, payouts and gained/lost groups')
