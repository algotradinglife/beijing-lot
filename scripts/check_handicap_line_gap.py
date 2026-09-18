"""Independent read-only discrete-line and descriptive settlement replay."""
import sys,json,hashlib,gzip
from pathlib import Path
import numpy as np
import pandas as pd
p=Path(sys.argv[1]);r=json.loads(p.read_text());c=r['config'];out=p.parent
for n,h in r['files'].items():assert hashlib.sha256((out/n).read_bytes()).hexdigest()==h
for n,h in r['code'].items():assert hashlib.sha256((Path(c['repository_root'])/n).read_bytes()).hexdigest()==h
assert hashlib.sha256(Path(c['input']).read_bytes()).hexdigest()==c['input_sha256']
raw=gzip.decompress(Path(c['input']).read_bytes());assert hashlib.sha256(raw).hexdigest()==c['input_uncompressed_sha256']
a=json.loads(raw);f=pd.read_csv(out/'features-before-labels.csv',dtype={'issue':str,'provider_id':str}).set_index(['issue','slot','provider_id'])
assert len(f)==len(a['rows']) and not f.index.duplicated().any()
for x in a['rows']:
 z=f.loc[(x['issue'],x['slot'],x['provider_id'])];d=x['distribution'];nets=np.array([q['net'] for q in d]);mass=np.array([q['probability'] for q in d]);lines=np.arange(-nets.max()-1,-nets.min()+2)
 imbalance=np.array([abs(mass[nets+h>0].sum()-mass[nets+h<0].sum()) for h in lines]);best=lines[imbalance<=imbalance.min()+c['tolerance']];h=sorted(best,key=lambda n:(abs(n),n))[0]
 assert h==z.optimal_line and len(best)==z.ties and x['handicap']-h==z.delta
 signal='AMBIGUOUS' if len(best)>1 else 'W' if x['handicap']>h else 'L' if x['handicap']<h else 'NONE'
 assert signal==z.signal
x=pd.read_csv(out/'fixtures.csv',dtype={'issue':str,'provider_id':str});s=pd.read_csv(out/'selected.csv')
cp=Path(c['context_receipt']);assert hashlib.sha256(cp.read_bytes()).hexdigest()==c['context_receipt_sha256']
cr=json.loads(cp.read_text());cx=cp.parent/'regime-fixtures.csv';assert hashlib.sha256(cx.read_bytes()).hexdigest()==cr['files']['regime-fixtures.csv']
context=pd.read_csv(cx,dtype={'issue':str,'provider_id':str}).set_index(['issue','slot','provider_id'])
xx=x.set_index(['issue','slot','provider_id']);assert not xx.index.duplicated().any()
expected=context.index.intersection(f.index);assert set(expected)==set(xx.index)
for col in ['handicap','optimal_line','delta','ties','q_W','q_D','q_L']:
 assert np.allclose(xx[col],f.loc[xx.index,col])
assert (xx.signal==f.loc[xx.index,'signal']).all()
for col in ['handicap','spf_sp']:assert np.allclose(xx[col],context.loc[xx.index,col])
assert (xx.actual_direction==context.loc[xx.index,'actual_direction']).all()
assert (xx.raw_top1==xx[['q_W','q_D','q_L']].idxmax(axis=1).str[-1]).all()
missing=context.index.difference(xx.index);declared={z['issue'] for z in a['exclusions']}
assert set(missing.get_level_values('issue'))==declared
for row in s.itertuples():
 z=x[x.signal==row.signal];gross=c['unit_cny']*c['payout_factor']*z.spf_sp*(z.signal==z.actual_direction)
 assert len(z)==row.fixtures and abs(gross.sum()-row.gross_cny)<1e-7
 assert abs((z.signal==z.actual_direction).mean()-row.hit)<1e-12
 assert abs((z.signal==z.actual_direction).sum()/(z.actual_direction!='D').sum()-row.non_draw_hit)<1e-12
 assert abs(z['q_'+row.signal].mean()-row.predicted)<1e-12
 assert abs((z.signal==z.raw_top1).mean()-row.same_as_top1)<1e-12
for name,h in r['source_hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h
print(f'PASS: {len(f)} saved-grid projections; {len(x)} paired candidate records; optimum/ties/sign and equal-stake settlement independently replayed')
