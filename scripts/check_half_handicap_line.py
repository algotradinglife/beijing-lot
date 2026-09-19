"""Independent half/integer optimum, pairing and hit-rate replay; read-only."""
import json,gzip,hashlib,sys
from pathlib import Path
import numpy as np
import pandas as pd
p=Path(sys.argv[1]);r=json.loads(p.read_text());c=r['config'];out=p.parent
for n,h in r['files'].items():assert hashlib.sha256((out/n).read_bytes()).hexdigest()==h
for n,h in r['code'].items():assert hashlib.sha256((Path(c['repository_root'])/n).read_bytes()).hexdigest()==h
assert hashlib.sha256(Path(c['input']).read_bytes()).hexdigest()==c['input_sha256']
raw=gzip.decompress(Path(c['input']).read_bytes());assert hashlib.sha256(raw).hexdigest()==c['input_uncompressed_sha256'];a=json.loads(raw)
f=pd.read_csv(out/'fixtures.csv',dtype={'issue':str,'provider_id':str}).set_index(['issue','slot','provider_id','model']);assert not f.index.duplicated().any() and len(f)==3*len(a['rows'])
for x in a['rows']:
 nets=np.array([v['net'] for v in x['distribution']]);mass=np.array([v['probability'] for v in x['distribution']])
 for model,step,conditional in [('INTEGER',1,False),('HALF',.5,False),('HALF_CONDITIONAL',.5,True)]:
  z=f.loc[(x['issue'],x['slot'],x['provider_id'],model)]
  lines=np.arange(-nets.max()-1,-nets.min()+1+step/2,step);w=np.array([mass[nets+h>0].sum() for h in lines]);l=np.array([mass[nets+h<0].sum() for h in lines]);obj=abs(w-l)
  if conditional:obj=np.divide(obj,w+l,out=np.full_like(obj,np.inf),where=w+l>c['tolerance'])
  best=lines[np.isfinite(obj)&(obj<=obj.min()+c['tolerance'])];star=sorted(best,key=lambda h:(abs(h),h))[0]
  assert star==z.optimal_line and len(best)==z.ties and z.delta==x['handicap']-star
  signal='AMBIGUOUS' if len(best)>1 else 'W' if x['handicap']>star else 'L' if x['handicap']<star else 'NONE';assert signal==z.signal
cp=Path(c['previous_receipt']);assert hashlib.sha256(cp.read_bytes()).hexdigest()==c['previous_receipt_sha256'];pr=json.loads(cp.read_text());fp=cp.parent/'fixtures.csv';assert hashlib.sha256(fp.read_bytes()).hexdigest()==pr['files']['fixtures.csv'];old=pd.read_csv(fp,dtype={'issue':str,'provider_id':str}).set_index(['issue','slot','provider_id'])
for model in ['INTEGER','HALF','HALF_CONDITIONAL']:
 z=f.xs(model,level='model').sort_index();o=old.sort_index();assert z.index.equals(o.index)
 for col in ['actual_direction','old_signal']:assert (z[col]==o['signal' if col=='old_signal' else col]).all()
 if model=='INTEGER':assert (z.optimal_line==o.optimal_line).all() and (z.signal==o.signal).all()
for filename,only_new in [('summary.csv',False),('new-signals.csv',True)]:
 s=pd.read_csv(out/filename);x=f.reset_index()
 if only_new:x=x[(x.old_signal=='NONE')&x.signal.isin(['W','L'])]
 assert s.fixtures.sum()==len(x)
 for t in s.itertuples():
  z=x[(x.model==t.model)&(x.signal==t.signal)&(abs(x.delta)==t.degree)];assert len(z)==t.fixtures
  if t.signal in ['W','L']:
   assert abs((z.actual_direction==t.signal).mean()-t.hit_rate)<1e-12
   assert abs(z['q_'+t.signal].mean()-t.predicted)<1e-12
print(f'PASS: {len(a["rows"])} distributions x3 methods; independent direct-sum optima, integer reproduction, labels and aggregate hit rates')
