#!/usr/bin/env python3
"""Frozen pre-outcome candidate sensitivity and canonical settlement for #119."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,os,shutil,tempfile
from collections import defaultdict,Counter
from decimal import Decimal,getcontext
from pathlib import Path
getcontext().prec=80

def root(p):
 for x in (p.resolve().parent,*p.resolve().parents):
  if (x/'.git').exists(): return x
 raise RuntimeError('repository root not found')
ROOT=root(Path(__file__)); A106=ROOT/'results/bj106_gate_a_preoutcome_v2r1'; B106=ROOT/'results/bj106_gate_b_outcome_settlement_v1'; M101=ROOT/'results/bj101_gate_a_preoutcome_v1r1'; OUTCOMES=ROOT/'results/bj95_gate_b_outcome_settlement_v2r8'
GA=ROOT/'results/bj119_gate_a_preoutcome_v1r1'; GB=ROOT/'results/bj119_gate_b_outcome_settlement_v1r3'
MAN={'a106':'fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d','b106':'d112cc1f1c8b538b7a36e0c4b03de70aa9532f1cd2d9f38598afbd21b7223c86','m101':'86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447','out':'fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc'}
# Gate B refuses a different Gate-A frontier, even when that alternate package
# happens to be self-consistent.
EXPECTED_GATE_A_MANIFEST='bc2684f6e38dac76af6943e0fbd134613dbb3d2af9d80160a6505354e5311983'
FACTOR=Decimal('.65'); TAX=Decimal('.20'); TAX_CLIFF=Decimal('10000'); Q=Decimal('.000001')
VARIANTS={
 'STRICT_106_PROMOTED':None,
 'RELAX_Q090_P20':(Decimal('.90'),Decimal('.20'),None,None),
 'RELAX_Q100_P20':(Decimal('1.00'),Decimal('.20'),None,None),
 'RELAX_Q110_P20':(Decimal('1.10'),Decimal('.20'),None,None),
 'RELAX_Q090_P35':(Decimal('.90'),Decimal('.35'),None,None),
 'RELAX_Q090_LOW_ENTROPY':(Decimal('.90'),Decimal('.20'),Decimal('1.08'),None),
 'RELAX_Q090_STABLE_SP':(Decimal('.90'),Decimal('.20'),None,Decimal('.85')),
 'FUNDAMENTAL_DECISION_CHAIN_UNAVAILABLE':None,
}
ARMS=('NO_BET_CONTROL','SINGLE_N4','FULL_COVER_N4','SINGLE_N7','FULL_COVER_N7','SINGLE_DYNAMIC_4_7','FULL_COVER_DYNAMIC_4_7')
POOL_FIELDS=('issue','fold','year','pool_id','segment_index','pool_disposition','eligible_match_count','pool_match_count','first_kickoff_ts','last_kickoff_ts','window_hours','terminal_remainder')
FRONT_FIELDS=POOL_FIELDS+('variant_id','arm','candidate_match_count','candidate_outcome_count','candidate_code_concentration','selected_n','selected_match_ids','selected_codes','formula_k','stake_yuan','disposition','reason')
ASSIGN_FIELDS=('variant_id','issue','fold','year','pool_id','match_id','match_idx','candidate_code','p_cal','q_hat','q_lb','entropy','sp_stability_ratio','rank')
SET_FIELDS=FRONT_FIELDS+('settlement_status','coverage_hit','final_sp_product','gross_yuan','tax_yuan','after_tax_gross_yuan','net_yuan')

def sha(p):
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def dec(x): return Decimal(str(x))
def money(x): return format(x.quantize(Q),'f')
def manifest(d,expected,needed=()):
 p=d/'SHA256SUMS.json'
 if sha(p)!=expected: raise RuntimeError(f'manifest mismatch {d}')
 m=json.loads(p.read_text())
 for n in needed:
  if n not in m or sha(d/n)!=m[n]: raise RuntimeError(f'payload mismatch {d/n}')
 return m
def write(p,fields,rows):
 with p.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def csvread(p,fields):
 with p.open(newline='',encoding='utf8') as f:
  r=csv.DictReader(f)
  if tuple(r.fieldnames or ())!=fields:raise RuntimeError(f'schema {p}')
  return list(r)
def ids(r):return (r['issue'],r['pool_id'])
def vkey(r):return (r['variant_id'],r['arm'])
def chronology_key(r):
 # Issue identifiers changed width after 2019, so they are identifiers rather
 # than a sortable calendar.  The frozen pool timestamp is the authoritative
 # chronology; year, segment and pool ID make the ordering total/deterministic.
 return (int(r['year']),r['first_kickoff_ts'],int(r['segment_index']),r['pool_id'])

def validate_gate_a():
 ma=manifest(A106,MAN['a106'],('gate_a_card.json','q_atlas.csv.gz'));mb=manifest(B106,MAN['b106'],('settlement_card.json',));mm=manifest(M101,MAN['m101'],('issue_pool_census.csv','issue_pool_membership.csv'))
 card=json.loads((B106/'settlement_card.json').read_text())
 if card.get('terminal_disposition')!='NO_PROMOTION' or card.get('nominated_strata')!=[]:raise RuntimeError('#106 terminal control drift')
 return {'a106':MAN['a106'],'b106':MAN['b106'],'m101':MAN['m101'],'payloads':{'atlas':ma['q_atlas.csv.gz'],'terminal':mb['settlement_card.json'],'pools':mm['issue_pool_census.csv'],'membership':mm['issue_pool_membership.csv']}}

def candidates():
 mem={r['match_id']:r for r in csv.DictReader((M101/'issue_pool_membership.csv').open())}
 chosen={k:{} for k in VARIANTS}
 with gzip.open(A106/'q_atlas.csv.gz','rt',newline='') as f:
  for r in csv.DictReader(f):
   if r['match_id'] not in mem:continue
   for name,rule in VARIANTS.items():
    if rule is None:continue
    q,p,e,s=rule; stable=dec(r['q_lb'])/dec(r['q_hat'])
    if dec(r['q_lb'])<q or dec(r['p_cal'])<p or dec(r['stratum_support'])<500 or int(r['stratum_year_count'])<3 or (e is not None and dec(r['entropy'])>e) or (s is not None and stable<s):continue
    old=chosen[name].get(r['match_id'])
    if old is None or dec(r['q_lb'])>dec(old['q_lb']) or (r['q_lb']==old['q_lb'] and '310'.index(r['candidate_code'])<'310'.index(old['candidate_code'])):chosen[name][r['match_id']]=r
 out={}
 for n,d in chosen.items():
  by=defaultdict(list)
  for mid,r in d.items():by[mem[mid]['pool_id']].append((mem[mid],r))
  for x in by.values():x.sort(key=lambda z:(-dec(z[1]['q_lb']),int(z[0]['match_idx']),int(z[0]['match_id'])))
  out[n]=by
 return mem,out

def build_gate_a():
 prov=validate_gate_a(); pools=csvread(M101/'issue_pool_census.csv',POOL_FIELDS); mem,byvar=candidates(); fronts=[];assign=[]
 if len(pools)!=2659 or len({r['issue'] for r in pools})!=344:raise RuntimeError('denominator drift')
 for variant in VARIANTS:
  for pool in pools:
   cand=byvar.get(variant,{}).get(pool['pool_id'],[]); codes=Counter(r['candidate_code'] for _,r in cand); conc=max(codes.values(),default=0)/len(cand) if cand else 0
   usable=cand if conc<=.8 else []
   for rank,(m,r) in enumerate(usable,1):assign.append({'variant_id':variant,'issue':m['issue'],'fold':m['fold'],'year':m['year'],'pool_id':m['pool_id'],'match_id':m['match_id'],'match_idx':m['match_idx'],'candidate_code':r['candidate_code'],'p_cal':r['p_cal'],'q_hat':r['q_hat'],'q_lb':r['q_lb'],'entropy':r['entropy'],'sp_stability_ratio':format(dec(r['q_lb'])/dec(r['q_hat']),'.12f'),'rank':rank})
   for arm in ARMS:
    n=0 if arm=='NO_BET_CONTROL' else (4 if arm.endswith('N4') else 7 if arm.endswith('N7') else (7 if len(usable)>=7 else 4 if len(usable)>=4 else 0))
    selected=usable[:n] if n and len(usable)>=n else []
    full=arm.startswith('FULL_COVER');k=(3**n if full and n else 1 if n else 0); stake=Decimal(2*k)
    reason='NO_BET_CONTROL' if arm=='NO_BET_CONTROL' else ('DATA_UNAVAILABLE' if variant=='FUNDAMENTAL_DECISION_CHAIN_UNAVAILABLE' else 'NO_CANDIDATE_UNDER_RULE' if not cand else 'CONCENTRATION_CAP' if not usable else 'INSUFFICIENT_MATCHES_FOR_N')
    disp='AVAILABLE' if selected else 'NO_BET'
    fronts.append({**pool,'variant_id':variant,'arm':arm,'candidate_match_count':len(usable),'candidate_outcome_count':len(usable),'candidate_code_concentration':format(conc,'.12f'),'selected_n':n if selected else 0,'selected_match_ids':';'.join(m['match_id'] for m,_ in selected),'selected_codes':';'.join(r['candidate_code'] for _,r in selected),'formula_k':k,'stake_yuan':money(stake if selected else Decimal(0)),'disposition':disp,'reason':'AVAILABLE_FROZEN' if selected else reason})
 return prov,pools,fronts,assign

def gate_a(output):
 if output.exists():raise SystemExit('immutable output exists')
 stage=Path(tempfile.mkdtemp(prefix='bj119_a_',dir=output.parent))
 try:
  prov,pools,fronts,assign=build_gate_a();write(stage/'portfolio_frontier.csv',FRONT_FIELDS,fronts);write(stage/'candidate_assignments.csv',ASSIGN_FIELDS,assign)
  summaries=[]
  for v in VARIANTS:
   for a in ARMS:
    rs=[r for r in fronts if r['variant_id']==v and r['arm']==a];av=[r for r in rs if r['disposition']=='AVAILABLE'];summaries.append({'variant_id':v,'arm':a,'pools':len(rs),'available':len(av),'no_bet':len(rs)-len(av),'candidate_matches':sum(int(r['candidate_match_count']) for r in rs),'tickets':sum(int(r['formula_k']) for r in av),'stake_yuan':money(sum((dec(r['stake_yuan']) for r in av),Decimal(0)))})
  write(stage/'candidate_density_summary.csv',('variant_id','arm','pools','available','no_bet','candidate_matches','tickets','stake_yuan'),summaries)
  distribution=[]
  for v in VARIANTS:
   for year in sorted({r['year'] for r in pools}):
    for code in ('3','1','0'):
     count=sum(1 for r in assign if r['variant_id']==v and r['year']==year and r['candidate_code']==code)
     distribution.append({'variant_id':v,'year':year,'league_stratum':'UNAVAILABLE_SOURCE','candidate_code':code,'assignments':count})
  write(stage/'candidate_distribution.csv',('variant_id','year','league_stratum','candidate_code','assignments'),distribution)
  reasons=[]
  for v in VARIANTS:
   for arm in ARMS:
    for reason in sorted({r['reason'] for r in fronts if r['variant_id']==v and r['arm']==arm}):
     reasons.append({'variant_id':v,'arm':arm,'reason':reason,'pools':sum(1 for r in fronts if r['variant_id']==v and r['arm']==arm and r['reason']==reason)})
  write(stage/'reason_census.csv',('variant_id','arm','reason','pools'),reasons)
  concentration=[]
  for v in VARIANTS:
   rs=[r for r in fronts if r['variant_id']==v and r['arm']=='SINGLE_N4']
   concentration.append({'variant_id':v,'pools':len(rs),'candidate_pools':sum(int(r['candidate_match_count'])>0 for r in rs),'concentration_capped_pools':sum(r['reason']=='CONCENTRATION_CAP' for r in rs),'league_source':'UNAVAILABLE_SOURCE','league_missingness':'100.000000000000'})
  write(stage/'missingness_concentration.csv',('variant_id','pools','candidate_pools','concentration_capped_pools','league_source','league_missingness'),concentration)
  card={'issue':119,'stage':'GATE_A_OUTCOME_UNEXPOSED_SENSITIVITY_FREEZE','contract':'BJ-HIST-CANDIDATE-SENSITIVITY-001','provenance':prov,'baseline_controls':{'bj106_terminal':'NO_PROMOTION / nominated_strata=[]','bj107':'preserved externally; #119 does not modify it','bj108':'preserved externally; #119 does not modify it'},'variants':{k:('strict accepted #106 promoted-strata control' if v is None and k=='STRICT_106_PROMOTED' else 'auditable feature unavailable control' if v is None else {'q_lb_min':str(v[0]),'p_cal_min':str(v[1]),'entropy_max':None if v[2] is None else str(v[2]),'q_lb_over_q_hat_min':None if v[3] is None else str(v[3]),'stratum_support_min':500,'persistence_years_min':3,'pool_code_concentration_max':.8}) for k,v in VARIANTS.items()},'arms':ARMS,'selection':'one highest q_lb eligible code per match; pool candidates rank q_lb descending then match_idx/match_id; no outcome fields opened','gate_b':'AUTHORIZED only for exactly this immutable frontier; no variants added/removed after outcome access','scope':'paper-only historical research; no purchase, production or promotion.'}
  (stage/'gate_a_card.json').write_text(json.dumps(card,indent=2,sort_keys=True)+'\n');shutil.copyfile(__file__,stage/'runner.py');(stage/'README.md').write_text('# #119 Gate A\n\nFrozen sensitivity grid; run `python runner.py gate-a --output <empty>` from a compatible checkout.\n')
  m={p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file()};(stage/'SHA256SUMS.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');os.replace(stage,output);print(json.dumps({'manifest':sha(output/'SHA256SUMS.json'),'frontiers':len(fronts),'assignments':len(assign)}))
 finally:
  if stage.exists():shutil.rmtree(stage,ignore_errors=True)

def load_outcomes():
 manifest(OUTCOMES,MAN['out'],('canonical_outcome_join.csv',));d={}
 with (OUTCOMES/'canonical_outcome_join.csv').open(newline='') as f:
  for r in csv.DictReader(f):
   if r['settlement_quality']=='trusted' and r['has_trusted_settlement']=='1':d[r['match_id']]=r
 return d
def settle(output,ga):
 if output.exists():raise SystemExit('immutable output exists')
 expected=EXPECTED_GATE_A_MANIFEST or sha(ga/'SHA256SUMS.json')
 mg=manifest(ga,expected,('portfolio_frontier.csv','candidate_assignments.csv','gate_a_card.json','candidate_distribution.csv','reason_census.csv','missingness_concentration.csv'))
 fr=csvread(ga/'portfolio_frontier.csv',FRONT_FIELDS);ass=csvread(ga/'candidate_assignments.csv',ASSIGN_FIELDS);by={}
 for r in ass:by.setdefault((r['variant_id'],r['pool_id'],r['match_id']),r)
 out=load_outcomes();rows=[];bucket=defaultdict(Decimal)
 for r in fr:
  if r['disposition']!='AVAILABLE':rows.append({**r,'settlement_status':'NO_BET_GATE_A','coverage_hit':'NO','final_sp_product':'0.000000','gross_yuan':'0.000000','tax_yuan':'0.000000','after_tax_gross_yuan':'0.000000','net_yuan':'0.000000'});continue
  mids=r['selected_match_ids'].split(';'); selected=[by[(r['variant_id'],r['pool_id'],m)] for m in mids]
  if any(m not in out for m in mids):rows.append({**r,'settlement_status':'UNAVAILABLE_CANONICAL_OUTCOME','coverage_hit':'NO','final_sp_product':'0.000000','gross_yuan':'0.000000','tax_yuan':'0.000000','after_tax_gross_yuan':'0.000000','net_yuan':'0.000000'});continue
  hit=all(out[x['match_id']]['result_code']==x['candidate_code'] for x in selected) or r['arm'].startswith('FULL_COVER');prod=Decimal(1)
  for x in selected:prod*=dec(out[x['match_id']]['winning_sp'])
  gross=Decimal(2)*FACTOR*prod if hit else Decimal(0);bucket[(r['variant_id'],r['arm'],r['issue'])]+=gross
  rows.append({**r,'settlement_status':'SETTLED','coverage_hit':'YES' if hit else 'NO','final_sp_product':money(prod),'gross_yuan':money(gross),'tax_yuan':'','after_tax_gross_yuan':'','net_yuan':''})
 for r in rows:
  gross=dec(r['gross_yuan']);tax=gross*TAX if bucket[(r['variant_id'],r['arm'],r['issue'])]>=TAX_CLIFF else Decimal(0);after=gross-tax;r['tax_yuan']=money(tax);r['after_tax_gross_yuan']=money(after);r['net_yuan']=money(after-dec(r['stake_yuan']))
 stage=Path(tempfile.mkdtemp(prefix='bj119_b_',dir=output.parent))
 try:
  write(stage/'portfolio_settlement.csv',SET_FIELDS,rows);summary=[]
  for k in sorted({vkey(r) for r in rows}):
   rs=[r for r in rows if vkey(r)==k];bet=[r for r in rs if r['settlement_status']=='SETTLED'];stake=sum((dec(r['stake_yuan']) for r in bet),Decimal(0));net=sum((dec(r['net_yuan']) for r in bet),Decimal(0));gross=sum((dec(r['gross_yuan']) for r in bet),Decimal(0));tax=sum((dec(r['tax_yuan']) for r in bet),Decimal(0));hits=sum(r['coverage_hit']=='YES' for r in bet);issue=defaultdict(Decimal)
   for r in bet:issue[r['issue']]+=dec(r['net_yuan'])
   best=max(issue,key=issue.get,default='');ex=net-issue.get(best,Decimal(0));gate_a_no_bet=sum(r['settlement_status']=='NO_BET_GATE_A' for r in rs);outcome_unavailable=sum(r['settlement_status']=='UNAVAILABLE_CANONICAL_OUTCOME' for r in rs);non_settled=gate_a_no_bet+outcome_unavailable
   if len(bet)+non_settled!=len(rs):raise RuntimeError('settlement denominator partition drift')
   summary.append({'variant_id':k[0],'arm':k[1],'frontiers':len(rs),'eligible_periods':len(bet),'gate_a_no_bet':gate_a_no_bet,'outcome_unavailable':outcome_unavailable,'non_settled':non_settled,'tickets':sum(int(r['formula_k']) for r in bet),'stake_yuan':money(stake),'hits':hits,'hit_rate':format(hits/len(bet),'.12f') if bet else '','gross_yuan':money(gross),'tax_yuan':money(tax),'net_yuan':money(net),'roi':format(net/stake,'.12f') if stake else '','best_issue':best,'ex_best_issue_roi':format(ex/(stake-sum(dec(r['stake_yuan']) for r in bet if r['issue']==best)),'.12f') if best and stake>sum(dec(r['stake_yuan']) for r in bet if r['issue']==best) else ''})
  # Every frozen arm receives the same chronological and leave-one-year-out
  # views. These are reports only: no threshold/arm selection happens here.
  robust=[]
  def agg(scope,val,rs,k):
   bet=[r for r in rs if r['settlement_status']=='SETTLED'];stake=sum((dec(r['stake_yuan']) for r in bet),Decimal(0));gross=sum((dec(r['gross_yuan']) for r in bet),Decimal(0));tax=sum((dec(r['tax_yuan']) for r in bet),Decimal(0));net=sum((dec(r['net_yuan']) for r in bet),Decimal(0));hits=sum(r['coverage_hit']=='YES' for r in bet)
   issue=defaultdict(Decimal)
   for r in bet:issue[r['issue']]+=dec(r['net_yuan'])
   best_issue=max(issue,key=issue.get,default='');best_issue_stake=sum((dec(r['stake_yuan']) for r in bet if r['issue']==best_issue),Decimal(0));best_payout=max(bet,key=lambda r:dec(r['gross_yuan']),default=None);best_payout_stake=dec(best_payout['stake_yuan']) if best_payout else Decimal(0);best_payout_net=dec(best_payout['net_yuan']) if best_payout else Decimal(0)
   cum=peak=dd=Decimal(0);streak=maxstreak=0
   for r in sorted(bet,key=chronology_key):
    cum+=dec(r['net_yuan']);peak=max(peak,cum);dd=max(dd,peak-cum);streak=0 if r['coverage_hit']=='YES' else streak+1;maxstreak=max(maxstreak,streak)
   gate_a_no_bet=sum(r['settlement_status']=='NO_BET_GATE_A' for r in rs);outcome_unavailable=sum(r['settlement_status']=='UNAVAILABLE_CANONICAL_OUTCOME' for r in rs);non_settled=gate_a_no_bet+outcome_unavailable
   if len(bet)+non_settled!=len(rs):raise RuntimeError('robustness denominator partition drift')
   return {'scope':scope,'scope_value':val,'variant_id':k[0],'arm':k[1],'frontiers':len(rs),'eligible_periods':len(bet),'gate_a_no_bet':gate_a_no_bet,'outcome_unavailable':outcome_unavailable,'non_settled':non_settled,'tickets':sum(int(r['formula_k']) for r in bet),'stake_yuan':money(stake),'hits':hits,'hit_rate':format(hits/len(bet),'.12f') if bet else '','gross_yuan':money(gross),'tax_yuan':money(tax),'net_yuan':money(net),'roi':format(net/stake,'.12f') if stake else '','max_drawdown_yuan':money(dd),'longest_losing_streak':maxstreak,'best_issue':best_issue,'ex_best_issue_roi':format((net-issue.get(best_issue,Decimal(0)))/(stake-best_issue_stake),'.12f') if best_issue and stake>best_issue_stake else '','best_payout_pool':best_payout['pool_id'] if best_payout else '','ex_best_payout_roi':format((net-best_payout_net)/(stake-best_payout_stake),'.12f') if best_payout and stake>best_payout_stake else '','top_issue_positive_net_share':format(max((max(Decimal(0),x) for x in issue.values()),default=Decimal(0))/sum((max(Decimal(0),x) for x in issue.values()),Decimal(0)),'.12f') if any(x>0 for x in issue.values()) else ''}
  years=sorted({r['year'] for r in rows});folds=sorted({r['fold'] for r in rows})
  for k in sorted({vkey(r) for r in rows}):
   rs=[r for r in rows if vkey(r)==k];robust.append(agg('ALL','ALL',rs,k))
   for y in years:robust.append(agg('YEAR',y,[r for r in rs if r['year']==y],k));robust.append(agg('LOYO',y,[r for r in rs if r['year']!=y],k))
   for f in folds:robust.append(agg('FOLD',f,[r for r in rs if r['fold']==f],k))
  write(stage/'robustness_summary.csv',tuple(robust[0]),robust)
  all_scope={(r['variant_id'],r['arm']):r for r in robust if r['scope']=='ALL'}
  for r in summary:
   a=all_scope[(r['variant_id'],r['arm'])]
   r.update({
    'max_drawdown_yuan':a['max_drawdown_yuan'],
    'longest_losing_streak':a['longest_losing_streak'],
    'best_payout_pool':a['best_payout_pool'],
    'ex_best_payout_roi':a['ex_best_payout_roi'],
    'top_issue_positive_net_share':a['top_issue_positive_net_share'],
   })
  write(stage/'variant_roi_comparison.csv',tuple(summary[0]),summary)
  (stage/'decision.json').write_text(json.dumps({'decision':'FROZEN_RESULTS_PENDING_EV_IF_POSITIVE','rule':'No variant is promotable solely from this table; positive/robust rows require strict independent EV before promotion.'},indent=2,sort_keys=True)+'\n');card={'issue':119,'stage':'GATE_B_CANONICAL_FROZEN_VARIANT_SETTLEMENT','gate_a_manifest':sha(ga/'SHA256SUMS.json'),'outcome_manifest':MAN['out'],'settlement':'canonical final SP; factor .65 once; tax aggregated per variant/arm/issue','robustness_chronology':'year, first_kickoff_ts, segment_index, pool_id','denominator_partition':'eligible_periods + gate_a_no_bet + outcome_unavailable = frontiers','scope':'paper-only; no promotion without independent EV'};(stage/'settlement_card.json').write_text(json.dumps(card,indent=2,sort_keys=True)+'\n');shutil.copyfile(__file__,stage/'runner.py');m={p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file()};(stage/'SHA256SUMS.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');os.replace(stage,output);print(json.dumps({'manifest':sha(output/'SHA256SUMS.json'),'rows':len(rows),'summary':len(summary)}))
 finally:
  if stage.exists():shutil.rmtree(stage,ignore_errors=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('stage',choices=('gate-a','gate-b'));p.add_argument('--output',type=Path);p.add_argument('--gate-a',type=Path,default=GA);a=p.parse_args();out=(a.output or (GA if a.stage=='gate-a' else GB)).resolve();gate_a(out) if a.stage=='gate-a' else settle(out,a.gate_a.resolve())
if __name__=='__main__':main()
