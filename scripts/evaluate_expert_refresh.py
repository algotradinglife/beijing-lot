"""Replay exact frozen releases on the nominated holdout; no fitting or tuning."""
import argparse, copy, hashlib, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure
from src.fundamentals_draw_versions import predict_draw_version
from src.fundamentals_refresh_predictions import save_refresh_prediction,freeze_refresh_report_inputs

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);p.add_argument('--python',required=True);p.add_argument('--only',nargs='+',choices=['new_draw','new_high','old_draw','old_high']);a=p.parse_args()
 study=Path(a.study);root=Path.cwd();contract=json.loads((study/'contract.json').read_text())
 frozen=json.loads((study/'models-frozen.json').read_text())
 for name,h in frozen['files'].items():
  if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Frozen model changed: '+name)
 out=study/'evaluation';out.mkdir(exist_ok=True)
 old=json.loads(Path('config/expert_versions/draw.json').read_text())
 old=copy.deepcopy(old);entry=old['receipt']['versions']['0.1.0']
 entry['models']={i:'data/derived/fundamentals_417/cv-thirtytwo-test-sixteen-v1/models/100305/frozen-experts.pkl' for i in contract['test_issues']}
 old['seal']=stable_json_hash(old['receipt'])
 path=out/'old-catalog.json'
 if path.exists() and json.loads(path.read_text())!=old:raise ValueError('Existing old catalog differs')
 if not path.exists():path.write_text(json.dumps(old))
 files=implementation_closure(root,['src.fundamentals_calibrated_draw','src.fundamentals_retrained_experts'])['files']
 files.update({x:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in ['scripts/predict_draw_version_worker.py','src/fundamentals_draw_versions.py']})
 for expert in ['draw','high']:
  model_files={k:v for k,v in frozen['files'].items() if str(study/expert)+'/' in k}
  entry=dict(version='2.0.0',runtime_root='.',files={**files,**model_files},description='72 issue trained model; retrospective holdout only')
  if expert=='draw':entry.update(backend='CALIBRATED',model_dir=str(study/'draw'),implementation_version='1.1.0',supports_draw_weight=True,probability_semantics='FINAL_HANDICAP_DRAW_MASS')
  else:entry.update(backend='RAW_TREE',models={i:str(study/'high/high-expert/model.pkl') for i in contract['train_issues']+contract['test_issues']},probability_semantics='RAW_EXPERT_PROBABILITY')
  receipt=dict(schema=1,versions={'2.0.0':entry});path=study/f'{expert}-catalog.json'
  expected=dict(receipt=receipt,seal=stable_json_hash(receipt))
  if path.exists() and json.loads(path.read_text())!=expected:raise ValueError('Existing catalog differs from frozen candidate')
  if not path.exists():path.write_text(json.dumps(expected,indent=2))
 f=pd.DataFrame(json.loads((study/'test-features.json').read_text()))
 cuts=[Cutoff.decision_epoch(r.issue_code,contract['cutoffs'][r.issue_code][str(r.slot)]) for r in f.itertuples()]
 for name,version,catalog in [('new_draw','2.0.0',study/'draw-catalog.json'),('new_high','2.0.0',study/'high-catalog.json'),('old_draw','1.1.0',out/'old-catalog.json'),('old_high','0.1.0',out/'old-catalog.json')]:
  if a.only and name not in a.only:continue
  path=out/f'{name}.json'
  if path.exists():raise FileExistsError(path)
  result=predict_draw_version(version,f,cutoffs=cuts,catalog_path=catalog,repository_root=root,python=a.python,timeout_seconds=3600)
  save_refresh_prediction(result,path,version=version,catalog_path=catalog,study=study,repository_root=root)
  print('PREDICTED',name,len(result),flush=True)

 if all((out/(n+".json")).exists() for n in ["new_draw","new_high","old_draw","old_high"]):freeze_refresh_report_inputs(study)
