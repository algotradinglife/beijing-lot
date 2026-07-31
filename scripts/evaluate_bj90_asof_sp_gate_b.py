#!/usr/bin/env python3
"""Fixed chronological M0/M1/M2 price-vector evaluation for #90 Gate B."""
from __future__ import annotations
import csv, hashlib, json, math, os, shutil, sys, tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

def root():
 for p in (Path(__file__).resolve().parent,*Path(__file__).resolve().parents):
  if (p/'AGENTS.md').is_file() and (p/'scripts').is_dir(): return p
 raise RuntimeError('root')
R=root(); F=R/'results/bj90_gate_a_preoutcome_v3'; L=R/'results/bj90_gate_b_target_ledger_v1'; O=R/'results/bj90_gate_b_price_vectors_v3'; CODES=('3','1','0'); LAM=10.
def sh(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(p):
 with p.open(newline='',encoding='utf8') as f:return list(csv.DictReader(f))
def write(p,rs):
 with p.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=sorted({k for r in rs for k in r}));w.writeheader();w.writerows(rs)
def logc(x):
 try:return math.log(max(.01,float(x)))
 except:return math.log(.01)
def mins(ts):
 return int(ts[11:13])*60+int(ts[14:16])
def nums(r):
 z=[]
 for m in ('euro','asian','ou'):
  for j in ('1','2','3'):
   if m in ('asian','ou') and j=='2': z += [float(r[f'{m}_v2']),float(r[f'{m}_i_v2']),float(r[f'{m}_v2'])-float(r[f'{m}_i_v2']),float(r[f'{m}_max2'])-float(r[f'{m}_min2'])]
   else:z += [logc(r[f'{m}_v{j}']),logc(r[f'{m}_i_v{j}']),logc(r[f'{m}_v{j}'])-logc(r[f'{m}_i_v{j}']),logc(r[f'{m}_max{j}'])-logc(r[f'{m}_min{j}'])]
 z += [math.log1p(max(0,float(r[f'{m}_n']))) for m in ('euro','asian','ou')]
 z += [float(r['handicap_line_norm'])]
 t=2*math.pi*mins(r['kickoff_ts'])/1440; return z+[math.sin(t),math.cos(t)]
def design(train,test):
 mu=np.mean([nums(r) for r in train],axis=0); sd=np.std([nums(r) for r in train],axis=0);sd[sd==0]=1
 leagues=sorted({r['league'] if r['league'] else '__MISSING__' for r in train}); ix={x:i for i,x in enumerate(leagues)}
 def x(rows):
  a=np.empty((len(rows),1+42+len(leagues)));a[:,0]=1
  for i,r in enumerate(rows):
   a[i,1:43]=(np.array(nums(r))-mu)/sd; k=r['league'] if r['league'] else '__MISSING__'
   if k in ix:a[i,43+ix[k]]=1
  return a
 return x(train),x(test)
def ranks(v):return np.argsort(np.argsort(-np.array(v),kind='stable'),kind='stable')
def rowstats(r,p,prefix):
 y=np.array([r['y3'],r['y1'],r['y0']],float);q=np.array(p);return {prefix+'logmae':float(np.mean(np.abs(np.log(q)-np.log(y)))),prefix+'rankdisp':float(np.mean(np.abs(ranks(q)-ranks(y))))}
def eq(rows,key):
 d=defaultdict(list)
 for r in rows:d[r['issue']].append(float(r[key]))
 return sum(sum(v)/len(v) for v in d.values())/len(d)
def main():
 if O.exists():raise SystemExit('immutable output exists')
 s=Path(tempfile.mkdtemp(prefix='bj90-eval-',dir=O.parent))
 try:
  for b in (F,L):
   m=json.loads((b/'SHA256SUMS.json').read_text());a={p.name:sh(p) for p in b.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
   if m!=a:raise RuntimeError('input manifest')
  rows=read(F/'frozen_preoutcome_rows.csv'); targets={r['match_id']:r for r in read(L/'official_sp_target_ledger.csv')}
  for r in rows:
   t=targets[r['match_id']];r.update(y3=float(t['sp_3']),y1=float(t['sp_1']),y0=float(t['sp_0']))
  out=[]; decisions=[]; prior=[]; residual=[[],[],[]]
  for year in range(2019,2026):
   train=[r for r in rows if int(r['year'])<year]; test=[r for r in rows if int(r['year'])==year]
   X,Z=design(train,test);Y=np.log(np.array([[r['y3'],r['y1'],r['y0']] for r in train]));pen=np.eye(X.shape[1])*LAM;pen[0,0]=0;B=np.linalg.solve(X.T@X+pen,X.T@Y);m1=np.exp(np.clip(Z@B,-10,10));m0=np.array([[max(.01,float(r['euro_v1'])),max(.01,float(r['euro_v2'])),max(.01,float(r['euro_v3']))] for r in test]);shift=np.array([sorted(x)[int(math.floor(.2*(len(x)-1)))] if x else 0 for x in residual]);m2=m1*np.exp(shift)
   if year==2019: chosen='M0_EURO_10H'
   else:
    a=[(eq(prior,'m0_logmae'),eq(prior,'m0_rankdisp'),'M0_EURO_10H'),(eq(prior,'m1_logmae'),eq(prior,'m1_rankdisp'),'M1_RIDGE_LOG_SP')];chosen=min(a,key=lambda x:(x[0],x[1],0 if x[2].startswith('M0') else 1))[2]
   decisions.append({'year':year,'method':chosen,'prior_oos_years':'' if year==2019 else f'2019-{year-1}'})
   for i,r in enumerate(test):
    z={**r,'m0_3':m0[i,0],'m0_1':m0[i,1],'m0_0':m0[i,2],'m1_3':m1[i,0],'m1_1':m1[i,1],'m1_0':m1[i,2],'m2_3':m2[i,0],'m2_1':m2[i,1],'m2_0':m2[i,2],'deployed_method':chosen};z.update(rowstats(z,m0[i],'m0_'));z.update(rowstats(z,m1[i],'m1_'));z.update(rowstats(z,m2[i],'m2_'));p=m0[i] if chosen.startswith('M0') else m1[i];z.update(rowstats(z,p,'deployed_'));out.append(z);prior.append(z);[residual[j].append(math.log([z['y3'],z['y1'],z['y0']][j])-math.log(m1[i,j])) for j in range(3)]
  # NEXT_PERIOD uses all seven already-scored folds, exactly like the yearly selector.
  allm=[(eq(out,'m0_logmae'),eq(out,'m0_rankdisp'),'M0_EURO_10H'),(eq(out,'m1_logmae'),eq(out,'m1_rankdisp'),'M1_RIDGE_LOG_SP')];next_method=min(allm,key=lambda x:(x[0],x[1],0 if x[2].startswith('M0') else 1))[2];decisions.append({'year':'NEXT_PERIOD','method':next_method,'prior_oos_years':'2019-2025'})
  primary=[r for r in out if r['deployed_method'].startswith('M1')]
  yearly=[]
  for year in range(2019,2026):
   rr=[r for r in out if int(r['year'])==year];yearly.append({'year':year,'policy_logmae':eq(rr,'deployed_logmae'),'m0_logmae':eq(rr,'m0_logmae'),'policy_rankdisp':eq(rr,'deployed_rankdisp'),'m0_rankdisp':eq(rr,'m0_rankdisp'),'m1_logmae':eq(rr,'m1_logmae'),'m1_rankdisp':eq(rr,'m1_rankdisp'),'policy_no_worse_logmae':eq(rr,'deployed_logmae')<=eq(rr,'m0_logmae')})
  tail=[]; cover=[]; code=[]
  for year in range(2019,2026):
   rr=[r for r in out if int(r['year'])==year]
   for j,c in enumerate(CODES):
    ykey='y'+c; m0='m0_'+c; m1='m1_'+c; m2='m2_'+c
    tailrows=[r for r in rr if float(r[ykey])>=5]
    tail.append({'year':year,'code':c,'target_sp_ge_5_n':len(tailrows),'m0_logmae':sum(abs(math.log(float(r[m0]))-math.log(float(r[ykey]))) for r in tailrows)/len(tailrows) if tailrows else '','m1_logmae':sum(abs(math.log(float(r[m1]))-math.log(float(r[ykey]))) for r in tailrows)/len(tailrows) if tailrows else ''})
    cover.append({'year':year,'code':c,'n':len(rr),'m2_conservative_coverage':sum(float(r[ykey])>=float(r[m2]) for r in rr)/len(rr)})
    for method,key in (('M0',m0),('M1',m1),('M2',m2)):
     code.append({'year':year,'method':method,'code':c,'logmae':sum(abs(math.log(float(r[key]))-math.log(float(r[ykey]))) for r in rr)/len(rr)})
  high=[r for r in tail if r['target_sp_ge_5_n']]
  high_m0=sum(float(r['m0_logmae'])*int(r['target_sp_ge_5_n']) for r in high)/sum(int(r['target_sp_ge_5_n']) for r in high);high_m1=sum(float(r['m1_logmae'])*int(r['target_sp_ge_5_n']) for r in high)/sum(int(r['target_sp_ge_5_n']) for r in high)
  # Fixed descriptive slices; these never feed a selector, q, or promotion condition.
  groups=defaultdict(lambda:[0,0.,0.])
  def band(x): return 'LT2' if x<2 else ('2_3' if x<3 else ('3_5' if x<5 else ('5_10' if x<10 else 'GE10')))
  def adisp(r):
   x=(logc(r['asian_max1'])-logc(r['asian_min1'])+logc(r['asian_max3'])-logc(r['asian_min3']))/2
   return 'LOW_LE_005' if x<=.05 else ('MID_LE_015' if x<=.15 else 'HIGH_GT_015')
  for r in out:
   for code in CODES:
    y=float(r['y'+code])
    for method,key in (('M0','m0_'+code),('M1','m1_'+code),('M2','m2_'+code),('DEPLOYED',('m0_' if r['deployed_method'].startswith('M0') else 'm1_')+code)):
     err=abs(math.log(float(r[key]))-math.log(y))
     for dim,val in (('sp_band',band(y)),('league',r['league'] or '__MISSING__'),('bj_line',str(r['handicap_line_norm'])),('asian_dispersion',adisp(r))):
      g=groups[(method,code,dim,val)];g[0]+=1;g[1]+=err;g[2]+=float(r[key])-y
  slices=[{'method':k[0],'code':k[1],'dimension':k[2],'slice':k[3],'n':v[0],'logmae':v[1]/v[0],'mean_prediction_minus_target':v[2]/v[0]} for k,v in sorted(groups.items())]
  summary={'policy_n':len(out),'deployed_m1_n':len(primary),'next_period_method':next_method,'policy_logmae':eq(out,'deployed_logmae'),'m0_logmae_same':eq(out,'m0_logmae'),'policy_rankdisp':eq(out,'deployed_rankdisp'),'m0_rankdisp_same':eq(out,'m0_rankdisp'),'years_logmae_no_worse_than_m0':sum(r['policy_no_worse_logmae'] for r in yearly),'high_sp_ge5_m0_logmae':high_m0,'high_sp_ge5_m1_logmae':high_m1}
  promote=next_method.startswith('M1') and summary['policy_logmae']<summary['m0_logmae_same'] and summary['policy_rankdisp']<summary['m0_rankdisp_same'] and summary['years_logmae_no_worse_than_m0']>=4 and high_m1<=high_m0;summary['decision']='PROMOTABLE_CANDIDATE' if promote else 'NO_PROMOTION'
  write(s/'oos_predictions.csv',out);write(s/'selector_decisions.csv',decisions);write(s/'summary.csv',[summary]);write(s/'metrics_by_year.csv',yearly);write(s/'high_sp_tail.csv',tail);write(s/'m2_coverage.csv',cover);write(s/'code_logmae.csv',code);write(s/'diagnostic_slices.csv',slices);shutil.copyfile(__file__,s/'evaluation_runner.py');card={'issue':90,'stage':'GATE_B_FIXED_CHRONOLOGICAL_PRICE_EVALUATION','created_at_utc':datetime.now(timezone.utc).isoformat(),'gate_a_manifest':sh(F/'SHA256SUMS.json'),'ledger_manifest':sh(L/'SHA256SUMS.json'),'inputs':'Gate-A v3 preoutcome rows plus immutable official-SP target ledger only','promotion_rule':'locked PI five-condition M1+M2 rule; diagnostics are descriptive only'};(s/'evaluation_card.json').write_text(json.dumps(card,indent=2)+"\n");m={p.name:sh(p) for p in s.iterdir() if p.is_file()};(s/'SHA256SUMS.json').write_text(json.dumps(m,indent=2,sort_keys=True)+"\n");os.replace(s,O);print(json.dumps(summary));
 except Exception:
  shutil.rmtree(s,ignore_errors=True);raise
if __name__=='__main__':main()
