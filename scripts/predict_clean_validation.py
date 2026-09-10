"""Apply exact frozen expert releases to label-free new-period R projections."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_draw_versions import predict_draw_version,read_draw_version

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--python',required=True);a=p.parse_args();root=Path.cwd();study=Path(a.study);out=study/'signals'
 if out.exists():raise FileExistsError('Immutable signal directory required')
 prepared=json.loads((study/'prepared.json').read_text());projected=json.loads((study/'projected/receipt.json').read_text())
 for path,h in {**projected['files'],**projected['implementation']}.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,path
 assert projected['prepared_sha256']==hashlib.sha256((study/'prepared.json').read_bytes()).hexdigest()
 catalog_path=root/'config/expert_versions/draw.json';catalog=json.loads(catalog_path.read_text())
 read_draw_version(catalog_path,'0.1.0',repository_root=root);read_draw_version(catalog_path,'1.1.0',repository_root=root)
 local=copy.deepcopy(catalog);model='data/derived/fundamentals_417/cv-thirtytwo-test-sixteen-v1/models/100305/frozen-experts.pkl'
 entry=local['receipt']['versions']['0.1.0']
 assert model in entry['models'].values()
 entry['models']={i:model for i in prepared['receipt']['contract']['issues']};entry['description']='Unchanged prior32 model, explicit later issue routing; no refit'
 local['seal']=stable_json_hash(local['receipt']);out.mkdir();local_path=out/'catalog.json';local_path.write_text(json.dumps(local))
 files={}
 for issue in prepared['receipt']['contract']['issues']:
  path=study/'projected'/f'{issue}.json';x=json.loads(path.read_text());f=pd.DataFrame(x['features'])
  rows=[];receipts={}
  if not f.empty:
   f['issue_code']=issue;cutoffs=[Cutoff.decision_epoch(issue,x['cutoffs'][issue][str(s)]) for s in f.slot]
   raw=predict_draw_version('0.1.0',f,cutoffs=cutoffs,catalog_path=local_path,repository_root=root,python=a.python,timeout_seconds=1800)
   draw=predict_draw_version('1.1.0',f,cutoffs=cutoffs,catalog_path=local_path,repository_root=root,python=a.python,timeout_seconds=1800,draw_weight=.5)
   keys=['issue_code','slot','provider_id']
   rows=json.loads(raw.merge(draw,on=keys,validate='one_to_one',suffixes=('_raw','_calibrated')).to_json(orient='records',double_precision=15))
   receipts=dict(raw=raw.attrs,draw=draw.attrs)
  path=out/f'{issue}.json';path.write_text(json.dumps(dict(rows=rows,receipts=receipts,projected_sha256=hashlib.sha256((study/'projected'/f'{issue}.json').read_bytes()).hexdigest()),default=str))
  files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();print('PREDICTED',issue,len(rows),flush=True)
 (out/'receipt.json').write_text(json.dumps(dict(files=files,catalog_sha256=hashlib.sha256(local_path.read_bytes()).hexdigest(),original_catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
