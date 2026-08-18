#!/usr/bin/env python3
"""Streaming descriptive diagnostics for immutable #90 Gate-B v4 predictions."""
from __future__ import annotations
import csv, hashlib, json, math, os, shutil, sys, tempfile
from collections import defaultdict
from pathlib import Path

def root():
 for p in (Path(__file__).resolve().parent,*Path(__file__).resolve().parents):
  if (p/'AGENTS.md').is_file() and (p/'scripts').is_dir():return p
 raise RuntimeError('root')
R=root(); I=R/'results/bj90_gate_b_price_vectors_v4r1'; O=R/'results/bj90_gate_b_diagnostics_v4r2'; C=('3','1','0')
def sh(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,rows):
 with p.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=sorted({k for r in rows for k in r}));w.writeheader();w.writerows(rows)
def main():
 if O.exists():raise SystemExit('immutable output exists')
 s=Path(tempfile.mkdtemp(prefix='bj90-diag-',dir=O.parent))
 try:
  m=json.loads((I/'SHA256SUMS.json').read_text());a={p.name:sh(p) for p in I.iterdir() if p.is_file() and p.name!='SHA256SUMS.json'}
  if m!=a:raise RuntimeError('input manifest')
  groups=defaultdict(lambda:[0,0.,0.]); cov=defaultdict(lambda:[0,0]); tail=defaultdict(lambda:[0,0.,0.]); yearly_issue=defaultdict(lambda:[0,0.,0.,0.,0.])
  with (I/'oos_predictions.csv').open(newline='',encoding='utf8') as f:
   for r in csv.DictReader(f):
    y=int(r['year']);z=yearly_issue[(y,r['issue'])];z[0]+=1;z[1]+=float(r['deployed_logmae']);z[2]+=float(r['m0_logmae']);z[3]+=float(r['deployed_rankdisp']);z[4]+=float(r['m0_rankdisp'])
    ad=(math.log(max(.01,float(r['asian_max1'])))-math.log(max(.01,float(r['asian_min1'])))+math.log(max(.01,float(r['asian_max3'])))-math.log(max(.01,float(r['asian_min3']))))/2
    ad='LOW_LE_005' if ad<=.05 else ('MID_LE_015' if ad<=.15 else 'HIGH_GT_015')
    for c in C:
     actual=float(r['y'+c]); band='LT2' if actual<2 else ('2_3' if actual<3 else ('3_5' if actual<5 else ('5_10' if actual<10 else 'GE10')))
     for method,key in (('M0','m0_'+c),('M1','m1_'+c),('M2','m2_'+c),('DEPLOYED',('m0_' if r['deployed_method'].startswith('M0') else 'm1_')+c)):
      pred=float(r[key]);err=abs(math.log(pred)-math.log(actual))
      for dim,val in (('sp_band',band),('league',r['league'] or '__MISSING__'),('bj_line',r['handicap_line_norm']),('asian_dispersion',ad)):
       g=groups[(method,c,dim,val)];g[0]+=1;g[1]+=err;g[2]+=pred-actual
     z=cov[(y,c)];z[0]+=1;z[1]+=actual>=float(r['m2_'+c])
     if actual>=5:
      z=tail[(y,c)];z[0]+=1;z[1]+=abs(math.log(float(r['m0_'+c]))-math.log(actual));z[2]+=abs(math.log(float(r['m1_'+c]))-math.log(actual))
  yearly=defaultdict(lambda:[0,0.,0.,0.,0.])
  for (year,_issue),v in yearly_issue.items():
   z=yearly[year];z[0]+=1;z[1]+=v[1]/v[0];z[2]+=v[2]/v[0];z[3]+=v[3]/v[0];z[4]+=v[4]/v[0]
  slices=[{'method':k[0],'code':k[1],'dimension':k[2],'slice':k[3],'n':v[0],'logmae':v[1]/v[0],'mean_prediction_minus_target':v[2]/v[0]} for k,v in sorted(groups.items())]
  yrs=[{'year':k,'policy_logmae':v[1]/v[0],'m0_logmae':v[2]/v[0],'policy_rankdisp':v[3]/v[0],'m0_rankdisp':v[4]/v[0],'policy_no_worse_logmae':v[1]<=v[2]} for k,v in sorted(yearly.items())]
  write(s/'diagnostic_slices.csv',slices);write(s/'m2_coverage.csv',[{'year':k[0],'code':k[1],'n':v[0],'m2_conservative_coverage':v[1]/v[0]} for k,v in sorted(cov.items())]);write(s/'high_sp_tail.csv',[{'year':k[0],'code':k[1],'target_sp_ge_5_n':v[0],'m0_logmae':v[1]/v[0],'m1_logmae':v[2]/v[0]} for k,v in sorted(tail.items())]);write(s/'metrics_by_year.csv',yrs);shutil.copyfile(__file__,s/'diagnostic_runner.py');meta={'input_manifest_sha256':sh(I/'SHA256SUMS.json'),'input_bundle':'bj90_gate_b_price_vectors_v4r1','metric_semantics':'equal-issue, matching evaluator metrics_by_year.csv','scope':'streaming diagnostics only; no SQLite/model/selector access'};(s/'diagnostic_card.json').write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n");mm={p.name:sh(p) for p in s.iterdir() if p.is_file()};(s/'SHA256SUMS.json').write_text(json.dumps(mm,indent=2,sort_keys=True)+"\n");os.replace(s,O);print(json.dumps({'output':str(O),'manifest':sh(O/'SHA256SUMS.json')}))
 except Exception:
  shutil.rmtree(s,ignore_errors=True);raise
if __name__=='__main__':main()
