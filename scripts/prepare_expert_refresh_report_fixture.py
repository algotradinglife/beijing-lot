"""Generate a deterministic synthetic report fixture; never fit or scrape."""
import argparse,hashlib,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beidan_backend.temporal_learning.core import stable_json_hash
from src.fundamentals_refresh_predictions import save_refresh_prediction,refresh_input_hash,verify_refresh_predictions,freeze_refresh_report_inputs
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();s=Path(a.output);s.mkdir()
 (s/'evaluation').mkdir()
 for expert in ['draw','high']:
  d=s/expert/(expert+'-expert');d.mkdir(parents=True)
  (d/'model.json').write_text(json.dumps(dict(receipt={expert:dict(features=['baseline_draw'])})))
  (d/'model.pkl').write_bytes(b'SYNTHETIC_REPORT_ONLY_NO_INFERENCE')
  (s/expert/'tree-cv.json').write_text(json.dumps(dict(selected={'depth':1},metrics=[dict(candidate=0,n=4,brier=.2)])))
 (s/'draw/rate-cv.json').write_text(json.dumps(dict(selected={'blend_weight':.5,'abstain_boost':.02},metrics=[dict(candidate=0,n=4,brier=.2)])))
 files={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for e in ['draw','high'] for x in (s/e).rglob('*') if x.is_file()}
 (s/'models-frozen.json').write_text(json.dumps(dict(files=files)))
 f=pd.DataFrame([dict(issue_code='002',slot=i,provider_id=str(i),handicap=-2,baseline_draw=.25,baseline_cover=.4,predictor_clock_ts='2009-12-31T00:00:00Z') for i in range(1,5)])
 (s/'test-features.json').write_text(f.to_json(orient='records',double_precision=15))
 (s/'contract.json').write_text(json.dumps(dict(test_issues=['002'],synthetic=True,cutoffs={'002':{str(i):'2010-01-01T00:00:00Z' for i in range(1,5)}})))
 (s/'training-data.json').write_text(json.dumps([dict(provider_id='training')]))
 labels=f[['issue_code','slot','provider_id']].assign(actual_home=[2,3,1,2],actual_away=0,label_status='COMPLETED')
 (s/'test-labels.json').write_text(json.dumps(dict(labels=json.loads(labels.to_json(orient='records')))))
 for name,v in [('new_draw','2.0.0'),('new_high','2.0.0'),('old_draw','1.1.0'),('old_high','0.1.0')]:
  e=name.split('_')[1];entry=dict(version=v,files=files)
  if e=='draw':entry.update(backend='CALIBRATED',model_dir=str(s/'draw'))
  else:entry.update(backend='RAW_TREE',models={'002':str(s/'high/high-expert/model.pkl')})
  rc=dict(versions={v:entry});catalog=s/(name+'-catalog.json');catalog.write_text(json.dumps(dict(receipt=rc,seal=stable_json_hash(rc))))
  result=f[['issue_code','slot','provider_id']].copy();result['expert_version']=v
  result['draw_target_probability' if e=='draw' else 'high_probability']=[.3,.4,.2,.3]
  result[e+'_signal']=['ABSTAIN','POSITIVE','NEGATIVE','ABSTAIN']
  r=dict(version=v,input_sha256=refresh_input_hash(s,entry,repository_root=Path.cwd()),prediction_sha256=stable_json_hash(result.to_json(orient='records')),catalog_seal=stable_json_hash(rc),model_receipts={},cutoffs=['2010-01-01T00:00:00+00:00']*4)
  result.attrs=dict(prediction_receipt=r,prediction_seal=stable_json_hash(r))
  save_refresh_prediction(result,s/'evaluation'/f'{name}.json',version=v,catalog_path=catalog,study=s,repository_root=Path.cwd())
 freeze_refresh_report_inputs(s)
 print(verify_refresh_predictions(s,repository_root=Path.cwd()))
