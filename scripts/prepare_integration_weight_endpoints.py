"""Freeze exact1.1.0 probability endpoints; no fitting or outcome-based selection."""
import argparse,hashlib,json,sys,warnings
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_calibrated_draw import load_calibrated_draw,predict_calibrated_draw
from src.temporal_learning import Cutoff
from src.temporal_learning.replay import HistoricalReplayWarning
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output)
 if out.exists():raise FileExistsError('Immutable endpoint output exists')
 root=Path.cwd();base=root/'data/derived/fundamentals_417'
 artifact=load_calibrated_draw(base/'calibrated-draw-1.1.0',expected_version='1.1.0',repository_root=root)
 training=base/'cv-thirtytwo-test-sixteen-v1/training.json';old_path=base/'cv-thirtytwo-test-sixteen-v1/predictions.json';rates_path=base/'signal-rates-v1/predictions.json'
 train=json.loads(training.read_text())['data'];old=json.loads(old_path.read_text());rates=json.loads(rates_path.read_text())
 frames=[]
 for row in train:
  if not row.get('predictor_clock_ts'):continue
  frames.append((row['issue_code'],row['data_available_ts'],row))
 clocks={(r['issue'],r['slot'],r['provider_id']):r['predictor_clock_ts'] for r in rates['receipt']['clocks']}
 for row in old['features']:
  key=(row['issue'],row['slot'],row['provider_id']);r=dict(row,issue_code=key[0],predictor_clock_ts=clocks[key]);frames.append((key[0],old['selected']['cutoffs'][key[0]][str(key[1])],r))
 records=[];receipts=[]
 features=list(artifact['expert']['features']['draw'])
 columns=list(dict.fromkeys(['issue_code','slot','provider_id','handicap','baseline_draw','predictor_clock_ts']+features))
 with warnings.catch_warnings():
  warnings.simplefilter('ignore',HistoricalReplayWarning)
  for issue in sorted({r[0] for r in frames}):
   bytime={}
   for i,t,r in frames:
    if i==issue:bytime.setdefault(t,[]).append(r)
   for t,rows in bytime.items():
    frame=pd.DataFrame(rows)[columns];cutoff=Cutoff.decision_epoch(issue,t)
    zero=predict_calibrated_draw(artifact,frame,cutoff,draw_weight=0)
    one=predict_calibrated_draw(artifact,frame,cutoff,draw_weight=1)
    for z,o in zip(zero.to_dict('records'),one.to_dict('records')):
     records.append(dict(issue=issue,slot=z['slot'],provider_id=z['provider_id'],cutoff_ts=t,baseline_draw=z['draw_target_probability'],expert_draw=o['draw_target_probability'],draw_signal=o['draw_signal'],calibration_status=o['calibration_status'],evaluation_scope=o['evaluation_scope']))
    receipts.extend([zero.attrs['prediction_receipt'],one.attrs['prediction_receipt']])
   print('ENDPOINTS',issue,flush=True)
 out.write_text(json.dumps(dict(version='1.1.0',rows=records,model_receipt=artifact['receipt'],prediction_receipts=receipts,input_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [training,old_path,rates_path]},implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
