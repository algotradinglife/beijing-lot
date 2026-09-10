"""Independent physical-ticket and settled-return replay of fixed gates."""
import argparse,gzip,hashlib,itertools,json,math,sys
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
 audit_paths=[k for k in receipt['source_hashes'] if k.endswith('settlement-audit.json')];assert len(audit_paths)==1
 labels={(r['issue'],r['slot'],r['provider_id']):r for r in json.loads(Path(audit_paths[0]).read_text())['rows']}
 observed={(r['issue'],r['policy']):r for r in json.loads((out/'results.json').read_text())['rows']};assert len(observed)==288
 checked=0
 for issue in r['issues']:
  bundle=json.loads(gzip.decompress((out/'plans'/f'{issue}.json.gz').read_bytes()));base=bundle['D2_TOP2_FREE_BASE']['plan'];baseline=[]
  for policy,e in bundle.items():
   plan=e['plan'];assert plan['seal']==stable_json_hash({k:v for k,v in plan.items() if k!='seal'})
   for k in ['groups','stake','cash_cny','budget_cny','cutoffs','unit_cny','payout_factor']:assert plan[k]==base[k]
   seen={};gross=0.;hits=[];changes=0;single_changes=0;double_changes=0
   for group in range(1,plan['groups']+1):
    old=sorted([z for z in base['legs'] if z['group']==group],key=lambda z:z['slot'])
    new=sorted([z for z in plan['legs'] if z['group']==group],key=lambda z:z['slot'])
    assert len(new)==7 and len({z['slot'] for z in new})==7
    assert sorted(len(z['support']) for z in new)==[1,1,2,2,2,2,2]
    for b,z in zip(old,new):
     order=sorted('WDL',key=lambda d:(-b['p_'+d],'WDL'.index(d)));support=b['support'];rule=e['rule']
     gap=b['p_'+order[1]]-b['p_'+order[2]]<=.05+1e-12
     conflict=.5*sum(abs(b['p_'+d]-b['q_'+d]) for d in 'WDL')+1e-12>=.15 and b['q_'+order[2]]-b['q_'+order[1]]+1e-12>=.05
     if seen.get(b['slot'],0):
      if len(support)==1 and rule in ['SINGLE','ALL'] and b['p_'+order[0]]<=.75+1e-12:support=dict(W='3',D='1',L='0')[order[1]]
      if len(support)==2 and ((rule in ['GAP','DOUBLE_OR','ALL'] and gap) or (rule in ['MARKET','DOUBLE_OR','ALL'] and conflict)):
       support=''.join(c for d,c in zip('WDL','310') if d in [order[0],order[2]])
     assert z==dict(b,support=support);seen[b['slot']]=seen.get(b['slot'],0)+1
     changes+=support!=b['support'];single_changes+=(support!=b['support'] and len(support)==1);double_changes+=(support!=b['support'] and len(support)==2)
    tickets=[t for t in plan['tickets'] if t['group']==group]
    assert len(tickets)==32 and all(t['units']==1 for t in tickets)
    assert {t['code'] for t in tickets}=={''.join(z) for z in itertools.product(*(z['support'] for z in new))}
    truth=[labels[issue,z['slot'],z['provider_id']] for z in new]
    assert all(q['status']=='READY' and q['handicap']==z['handicap'] for q,z in zip(truth,new))
    win=all(dict(W='3',D='1',L='0')[q['actual_direction']] in z['support'] for q,z in zip(truth,new));hits.append(win)
    if win:gross+=2*.65*math.prod(q['spf_sp'] for q in truth)
   if e['rule']=='BASE':baseline=hits
   result=observed[issue,policy]
   assert abs(result['gross']-gross)<1e-7 and abs(result['net']-(gross-1024))<1e-7 and result['hits']==sum(hits)
   assert result['changed_legs']==changes
   assert result['gained_groups']==sum(x and not y for x,y in zip(hits,baseline))
   assert result['lost_groups']==sum(y and not x for x,y in zip(hits,baseline))
   checked+=1
  print('VERIFIED',issue,flush=True)
 assert checked==288
 print('PASS 288 fixed-plan variants: source identity, thresholds, physical tickets, exact payouts and gained/lost groups')
