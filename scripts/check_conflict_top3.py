"""Independent diagnostic replay; does not call the new planner or settlement APIs."""
import argparse,hashlib,itertools,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure
from src.nowscore_settlement import expected_option

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();out=Path(a.study)
 sealed=json.loads((out/'plans-frozen.json').read_text());f=sealed['receipt'];assert stable_json_hash(f)==sealed['seal']
 verify_implementation_closure(Path.cwd(),f['implementation'])
 result=json.loads((out/'results.json').read_text());assert result['freeze_seal']==sealed['seal']
 for name,h in {**f['source_hashes'],**f['plan_hashes'],**result['audit_hashes']}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
 score_path=next(k for k in f['source_hashes'] if k.endswith('conflict-actions-v1/scores.json'))
 input_path=next(k for k in f['source_hashes'] if k.endswith('decision-chain-conflict-v1/inputs.json'))
 grids=json.loads(Path(score_path).read_text())['grids'];inputs=json.loads(Path(input_path).read_text())
 rows=[r for r in inputs['rows'] if r['weight']==.5]
 audits={}
 for name in result['audit_hashes']:
  for r in json.loads(Path(name).read_text()):
   key=(r['issue'],r['slot'],r['provider_id']);assert key not in audits;audits[key]=r
 observed={(r['issue'],r['policy']):r for r in result['rows']};conflicts=score_hits=0
 for name in f['plan_hashes']:
  b=json.loads(Path(name).read_text());plan=b['plan'];base=b['base'];issue=base['issue']
  for z in [base,plan,plan['main']]:assert stable_json_hash({k:v for k,v in z.items() if k!='seal'})==z['seal']
  pool=[r for r in rows if r['issue']==issue];clean=[];expected_scores=[]
  for r in pool:
   order=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)));top=max('WDL',key=lambda d:r['q_'+d])
   if top in order[:2]:clean.append(r);continue
   conflicts+=1;options=[]
   for g in grids[f"{issue}/{r['slot']}"]:
    option=f"{int(g['home_goals'])}:{int(g['away_goals'])}"
    if expected_option(dict(play='bf',score=option))==option and g['p']>0 and g['q']>0:options.append(g)
   assert len(options)>=3
   for g in sorted(options,key=lambda g:(-g['p'],g['home_goals'],g['away_goals']))[:3]:expected_scores.append((r['slot'],r['provider_id'],f"{int(g['home_goals'])}:{int(g['away_goals'])}",g['p'],g['q']))
  got=[(r['slot'],r['provider_id'],r['option'],r['p_score'],r['q_score']) for r in plan['scores']]
  assert sorted(got)==sorted(expected_scores)
  ranked=sorted(clean,key=lambda r:(-sum(sorted([r['p_'+d] for d in 'WDL'],reverse=True)[:2]),r['slot'],r['provider_id']))
  main=plan['main'];count=min(6,len(clean)//7);assert main['groups']==count
  for group in range(1,count+1):
   expected=sorted(r['slot'] for r in ranked[(group-1)*7:group*7])
   assert sorted(r['slot'] for r in main['legs'] if r['group']==group)==expected
  main_gross={}
  for policy,z in [('CURRENT',base),('NONCONFLICT_N7',main)]:
   gross=0;hits=0
   for group in range(1,z['groups']+1):
    legs=sorted([r for r in z['legs'] if r['group']==group],key=lambda r:r['slot'])
    for r in legs:
     order=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)))[:2]
     assert r['support']==''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in order)
    tickets=[t for t in z['tickets'] if t['group']==group]
    assert sorted(t['code'] for t in tickets)==sorted(''.join(c) for c in itertools.product(*(r['support'] for r in legs)))
    assert len(tickets)==128 and all(t['units']==1 for t in tickets)
    labels=[audits[(issue,r['slot'],r['provider_id'])] for r in legs]
    actual=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in labels)
    if actual in {t['code'] for t in tickets}:gross+=2*.65*math.prod(r['spf_sp'] for r in labels);hits+=1
   main_gross[policy]=gross;o=observed[issue,policy]
   assert o['stake']==z['groups']*256 and abs(o['gross']-gross)<1e-7 and o['hits']==hits
  bf=0;hits=0
  for r in plan['scores']:
   assert r['stake']==2 and utc(r['cutoff'])==utc(f['cutoffs'][issue][str(r['slot'])])
   label=audits[issue,r['slot'],r['provider_id']]
   actual=expected_option(dict(play='bf',score=f"{int(label['actual_home'])}:{int(label['actual_away'])}"))
   assert actual==label['bf_option'] and label['handicap']==r['handicap']
   if actual==r['option']:bf+=2*.65*label['bf_sp'];hits+=1
  score_hits+=hits;o=observed[issue,'CONFLICT_TOP3'];assert o['stake']==len(expected_scores)*2 and abs(o['gross']-bf)<1e-7 and o['score_hits']==hits
  o=observed[issue,'SPLIT_TOP3'];assert o['stake']==count*256+len(expected_scores)*2 and abs(o['gross']-main_gross['NONCONFLICT_N7']-bf)<1e-7
  for policy in ['CURRENT','NONCONFLICT_N7','CONFLICT_TOP3','SPLIT_TOP3']:
   o=observed[issue,policy];assert abs(o['net']-(o['gross']-o['stake']))<1e-7
 print('PASS',len(f['plan_hashes']),'plans',conflicts,'conflicts',score_hits,'score hits')
