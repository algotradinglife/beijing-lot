"""Independent arithmetic reconstruction of all three fixed conflict stages."""
import argparse,copy,hashlib,itertools,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning.core import stable_json_hash,utc
from src.temporal_learning.provenance import verify_implementation_closure
from src.nowscore_settlement import expected_option

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--study',required=True);parser.add_argument('--attribution',required=True);a=parser.parse_args();out=Path(a.study)
 c=json.loads((out/'contract.json').read_text());parent=Path(c['parent_study']);inputs=json.loads((parent/'inputs.json').read_text())
 score_pack=json.loads((out/'scores.json').read_text());score_grids=score_pack['grids']
 current={(r['issue'],r['slot'],r['provider_id']):r for r in inputs['rows'] if r['weight']==.5};issues=sorted(set(k[0] for k in current))
 audits={}
 for part in ['training','validation','test']:
  for row in json.loads((parent/f'{part}-audit.json').read_text()):
   key=tuple(row[k] for k in ['issue','slot','provider_id']);assert key not in audits;audits[key]=row
 expected_offers={};conflicts={}
 for key,r in current.items():
  rank=sorted('WDL',key=lambda d:(-r['p_'+d],'WDL'.index(d)));omitted=rank[-1]
  top=max('WDL',key=lambda d:r['q_'+d]);conflicts[key]=top==omitted
  grid=score_grids[f'{key[0]}/{key[1]}'];valid=[]
  for g in grid:
   net=g['home_goals']-g['away_goals']+r['handicap'];direction='W' if net>0 else 'D' if net==0 else 'L'
   option=f"{g['home_goals']}:{g['away_goals']}"
   if direction==omitted and g['p']>0 and g['q']>0 and expected_option(dict(play='bf',score=option))==option:valid.append(g)
  best=min(valid,key=lambda g:(-g['p'],g['home_goals'],g['away_goals'])) if valid else None
  expected_offers[key]=dict(conflict=conflicts[key],omitted=omitted,best=best)
 total=0;metrics_checked=0;hashes={};stage_counts={}
 for stage in ['reestimate','expand','protect']:
  folder=out/stage;result=json.loads((folder/'results.json').read_text());decisions=json.loads((folder/'decisions.json').read_text());freeze=json.loads((folder/'plans-frozen.json').read_text())
  assert stable_json_hash(freeze['receipt'])==freeze['seal']==result['freeze_seal']
  assert freeze['receipt']['contract']==c==result['contract']
  verify_implementation_closure(Path.cwd(),freeze['receipt']['implementation'])
  for name,digest in {**freeze['receipt']['source_hashes'],**freeze['receipt']['plan_hashes'],**result['audit_hashes']}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
  observed_results={(r['issue'],r['policy']):r for r in result['rows']};assert len(observed_results)==len(result['rows'])
  for offer in decisions['offers']:
   key=(offer['issue'],offer['slot'],offer['provider_id']);e=expected_offers[key]
   assert offer['conflict']==e['conflict'] and offer['omitted']==e['omitted']
   if e['best']:
    assert (offer['score_home'],offer['score_away'],offer['p_score'],offer['q_score'])==(e['best']['home_goals'],e['best']['away_goals'],e['best']['p'],e['best']['q'])
   else:assert offer['status'].startswith('NO_EXACT_SCORE')
  if stage=='protect':
   frozen=json.loads(Path(c['reverse_source']).read_text());receipt=frozen['receipt']
   assert stable_json_hash(receipt)==c['reverse_receipt_seal']==frozen['seal']
   assert sum(x['n'] for x in receipt['leaves'].values())==receipt['expert_rows']
   maximum=max(x['probability'] for x in receipt['leaves'].values());assert maximum<receipt['bounds'][1]==.6
   assert len(decisions['reverse_gates'])==len(current)
   for gate in decisions['reverse_gates']:
    assert gate['status']=='NO_POSITIVE_LEAF' and not gate['per_fixture_prediction'] and gate['maximum_probability']==maximum
    assert utc(gate['cutoff'])>utc(receipt['cutoff_ts'])
  for path in sorted((folder/'plans').glob('*.json')):
   issue=path.name.split('-')[0];policy=path.stem[len(issue)+1:];plan=json.loads(path.read_text());side=policy.startswith('CONFLICT_SCORE')
   assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
   main=plan['main'] if side else plan;assert stable_json_hash({k:v for k,v in main.items() if k!='seal'})==main['seal']
   base=json.loads((parent/'plans'/f'{issue}-CURRENT.json').read_text())['plan']
   wanted_groups=[];wanted_scores=[];expected_budget=None
   if stage=='reestimate':
    weight={'CURRENT':0,'MARKET_MIX_050':.5,'MARKET_MIX_100':1}[policy];rows=[]
    for key,r in current.items():
     if key[0]!=issue:continue
     alpha=weight if conflicts[key] else 0.;z={k:v for k,v in r.items() if k!='weight'}
     for d in 'WDL':z['p_'+d]=(1-alpha)*r['p_'+d]+alpha*r['q_'+d]
     rank=sorted('WDL',key=lambda d:(-z['p_'+d],'WDL'.index(d)))[:2];z['support']=''.join(dict(W='3',D='1',L='0')[d] for d in 'WDL' if d in rank)
     rows.append(z)
    rows.sort(key=lambda z:(-sum(sorted([z['p_'+d] for d in 'WDL'],reverse=True)[:2]),z['slot'],z['provider_id']))
    wanted_groups=[sorted(rows[i*7:(i+1)*7],key=lambda r:r['slot']) for i in range(min(6,len(rows)//7))]
   else:
    original=[sorted([copy.deepcopy(r) for r in base['legs'] if r['group']==g],key=lambda r:r['slot']) for g in range(1,base['groups']+1)]
    if policy in ['CURRENT','REVERSE_POSITIVE_ONLY']:wanted_groups=original
    elif stage=='expand':
     _,mode,funding=policy.split('_');remaining=base['stake']
     for group in original:
      conflict_rows=[r for r in group if conflicts[(issue,r['slot'],r['provider_id'])]]
      conflict_rows.sort(key=lambda r:(-r['q_'+expected_offers[(issue,r['slot'],r['provider_id'])]['omitted']],r['slot'],r['provider_id']))
      selected=conflict_rows[:1] if mode=='ONE' else conflict_rows;slots={r['slot'] for r in selected}
      for r in group:
       if r['slot'] in slots:r['support']='310'
      cost=2*math.prod(len(r['support']) for r in group)
      if funding=='FIXED' and cost>remaining:continue
      remaining-=cost;wanted_groups.append(group)
     if funding=='FIXED' and wanted_groups:expected_budget=base['stake']
    elif side:
     fixed=policy.endswith('FIXED');wanted_groups=original[:-1] if fixed and len(original)>=2 else original
     if not fixed or len(original)>=2:
      for group in wanted_groups:
       for r in group:
        e=expected_offers[(issue,r['slot'],r['provider_id'])]
        if e['conflict'] and e['best']:wanted_scores.append((r,e['best']))
     if not wanted_scores:wanted_groups=original
     elif fixed:expected_budget=base['stake']-2*len(wanted_scores)
   expected_tickets=[]
   for index,group in enumerate(wanted_groups,1):
    legs=sorted([r for r in main['legs'] if r['group']==index],key=lambda r:r['slot'])
    assert [(r['slot'],r['provider_id'],r['support']) for r in legs]==[(r['slot'],r['provider_id'],r['support']) for r in group]
    for actual,wanted in zip(legs,group,strict=True):
     assert all(abs(actual['p_'+d]-wanted['p_'+d])<1e-14 and actual['q_'+d]==wanted['q_'+d] for d in 'WDL')
    for code in itertools.product(*(r['support'] for r in group)):expected_tickets.append(dict(group=index,code=''.join(code),units=1))
   if expected_budget is not None:
    units,remainder=divmod(expected_budget//2,len(expected_tickets));assert units>=1
    ix=sorted(range(len(expected_tickets)),key=lambda i:hashlib.sha256(f"{issue}|{expected_tickets[i]['group']}|{expected_tickets[i]['code']}|{c['allocation_seed']}".encode()).hexdigest());extra=set(ix[:remainder])
    for i,t in enumerate(expected_tickets):t['units']=units+int(i in extra)
   assert expected_tickets==main['tickets'] and main['groups']==len(wanted_groups)
   assert main['stake']==2*sum(t['units'] for t in expected_tickets)
   main_gross=0.;hits=0
   for group in range(1,main['groups']+1):
    legs=sorted([r for r in main['legs'] if r['group']==group],key=lambda r:r['slot'])
    labels=[audits[(issue,r['slot'],r['provider_id'])] for r in legs]
    assert all(r['handicap']==a['handicap'] for r,a in zip(legs,labels,strict=True))
    code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in labels)
    winners=[t for t in expected_tickets if t['group']==group and t['code']==code]
    if winners:main_gross+=2*.65*winners[0]['units']*math.prod(r['spf_sp'] for r in labels);hits+=1
   score_gross=0.;score_hits=0
   if side:
    assert len(plan['scores'])==len(wanted_scores)
    for actual,(r,g) in zip(plan['scores'],wanted_scores,strict=True):
     assert actual['slot']==r['slot'] and actual['stake']==2 and actual['option']==f"{g['home_goals']}:{g['away_goals']}"
     label=audits[(issue,r['slot'],r['provider_id'])]
     if actual['option']==label['bf_option']:score_gross+=2*.65*label['bf_sp'];score_hits+=1
   e=observed_results[(issue,policy)];stake=main['stake']+2*len(wanted_scores)
   assert e['stake']==stake and e['hits']==hits and e['score_hits']==score_hits and e['score_bets']==len(wanted_scores)
   assert abs(e['main_gross']-main_gross)<1e-7 and abs(e['score_gross']-score_gross)<1e-7 and abs(e['net']-(main_gross+score_gross-stake))<1e-7
   if policy in ['CURRENT','REVERSE_POSITIVE_ONLY']:assert main==base
   total+=1
  for r in result['prediction_metrics']:
   key=(r['issue'],r['slot'],r['provider_id']);original=current[key];alpha={'CURRENT':0,'MARKET_MIX_050':.5,'MARKET_MIX_100':1}[r['policy']] if conflicts[key] else 0.
   assert r['conflict']==conflicts[key] and r['applied_market_weight']==alpha
   for d in 'WDL':assert abs(r['p_'+d]-((1-alpha)*original['p_'+d]+alpha*original['q_'+d]))<1e-14
   label=audits[key];assert r['actual_direction']==label['actual_direction']
   cell=[g for g in score_grids[f'{key[0]}/{key[1]}'] if g['home_goals']==label['actual_home'] and g['away_goals']==label['actual_away']]
   exact=(1-alpha)*cell[0]['p']+alpha*cell[0]['q'] if cell else 0.
   assert r['p_actual_score']==exact and r['score_outside_support']==(not bool(cell));metrics_checked+=1
  stage_counts[stage]=len(observed_results)
  for name in ['results.json','decisions.json','plans-frozen.json']:hashes[str(folder/name)]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
 for name in ['contract.json','scores.json']:hashes[str(out/name)]=hashlib.sha256((out/name).read_bytes()).hexdigest()
 attr=Path(a.attribution);freeze=json.loads((attr/'plans-frozen.json').read_text());results=json.loads((attr/'results.json').read_text())
 assert stable_json_hash(freeze['receipt'])==freeze['seal']==results['attribution_freeze_seal']
 verify_implementation_closure(Path.cwd(),freeze['receipt']['implementation'])
 for name,digest in {**freeze['receipt']['source_hashes'],**freeze['receipt']['plan_hashes'],**results['audit_hashes']}.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
 count=0
 for path in sorted((attr/'plans').glob('*.json')):
  plan=json.loads(path.read_text());issue=plan['issue'];assert stable_json_hash({k:v for k,v in plan.items() if k!='seal'})==plan['seal']
  source=json.loads((out/'protect/plans'/f'{issue}-CONFLICT_SCORE_FIXED.json').read_text());fixed=source['main']
  assert [(r['slot'],r['provider_id'],r['support']) for r in plan['legs']]==[(r['slot'],r['provider_id'],r['support']) for r in fixed['legs']]
  assert [(t['group'],t['code']) for t in plan['tickets']]==[(t['group'],t['code']) for t in fixed['tickets']]
  if plan['tickets']:
   units,remainder=divmod(source['base_stake']//2,len(plan['tickets']))
   ordered=sorted(range(len(plan['tickets'])),key=lambda i:hashlib.sha256(f"{issue}|{plan['tickets'][i]['group']}|{plan['tickets'][i]['code']}|{c['allocation_seed']}".encode()).hexdigest());extra=set(ordered[:remainder])
   assert all(t['units']==units+int(i in extra) for i,t in enumerate(plan['tickets']))
  gross=0;hits=0
  for group in range(1,plan['groups']+1):
   legs=sorted([r for r in plan['legs'] if r['group']==group],key=lambda r:r['slot']);labels=[audits[(issue,r['slot'],r['provider_id'])] for r in legs]
   code=''.join(dict(W='3',D='1',L='0')[r['actual_direction']] for r in labels);wins=[t for t in plan['tickets'] if t['group']==group and t['code']==code]
   if wins:gross+=2*.65*wins[0]['units']*math.prod(r['spf_sp'] for r in labels);hits+=1
  r=next(r for r in results['rows'] if r['issue']==issue and r['policy']=='SAME_GROUPS_NO_SCORE')
  assert r['stake']==source['base_stake'] and abs(r['gross']-gross)<1e-7 and r['hits']==hits and r['score_stake']==0
  count+=1
 original={(r['issue'],r['policy']):r for r in json.loads((out/'protect/results.json').read_text())['rows']}
 for r in results['rows']:
  if r['policy']!='SAME_GROUPS_NO_SCORE':
   old=original[(r['issue'],r['policy'])];assert all(r[k]==old[k] for k in ['stake','gross','net','hits','score_stake','score_gross'])
 for name in ['results.json','plans-frozen.json']:hashes[str(attr/name)]=hashlib.sha256((attr/name).read_bytes()).hexdigest()
 payload=dict(status='PASS',plans_checked=total,attribution_plans_checked=count,prediction_metrics_checked=metrics_checked,stage_counts=stage_counts,source_hashes=hashes,historical_admission=False)
 (out/'independent-check.json').write_text(json.dumps(payload,indent=2));print('PASS',total,'plans',metrics_checked,'probability rows')
