"""Independently rebuild nominated inputs and label admission; never refit."""
import argparse,json,hashlib,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expert_refresh import read_refresh_features,attach_refresh_labels
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();study=Path(a.study)
 c=json.loads((study/'contract.json').read_text());r=json.loads((study/'input-receipt.json').read_text())
 if stable_json_hash(r['receipt'])!=r['seal']:raise ValueError('Input receipt changed')
 x=read_refresh_features('data/derived/fundamentals_417/cv-thirtytwo-test-sixteen-v1',
   'data/derived/fundamentals_417/signal-rates-v1','data/derived/fundamentals_417/new48-expanded-validation-v1',
   train_count=72,test_count=24,initial_issues=32)
 if x['contract']!=c or x['source_hashes']!=r['receipt']['source_hashes']:raise ValueError('Source/contract replay differs')
 for part in ['train','test']:
  if json.loads(x[part].to_json(orient='records',double_precision=15))!=json.loads((study/f'{part}-features.json').read_text()):raise ValueError('Feature replay differs')
 train=pd.DataFrame(json.loads((study/'train-features.json').read_text()))
 labels=pd.DataFrame(json.loads((study/'train-labels.json').read_text())['labels'])
 data,exclusions=attach_refresh_labels(train,labels,cutoff=Cutoff.decision_epoch(c['cutoff_issue'],c['cutoff_ts']),label_delay_hours=c['label_delay_hours'])
 pd.testing.assert_frame_equal(data,pd.DataFrame(json.loads((study/'training-data.json').read_text())),check_dtype=False)
 if exclusions.to_dict('records')!=json.loads((study/'training-exclusions.json').read_text()):raise ValueError('Exclusion replay differs')
 files={str(study/f):hashlib.sha256((study/f).read_bytes()).hexdigest() for f in ['input-receipt.json','training-data.json','train-features.json','test-features.json','models-frozen.json']}
 (study/'input-replay.json').write_text(json.dumps(dict(status='PASS',train_rows=len(data),files=files,implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
 print('INPUT_REPLAY_PASS',len(data))
