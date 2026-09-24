"""Join the nominated training labels before fitting; never opens test labels."""
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expert_refresh import attach_refresh_labels
from beidan_backend.temporal_learning import Cutoff
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();study=Path(a.study)
 for name in ['training-data.json','training-exclusions.json']:
  if (study/name).exists():raise FileExistsError('Training input already frozen')
 c=json.loads((study/'contract.json').read_text())
 features=pd.DataFrame(json.loads((study/'train-features.json').read_text()))
 labels=pd.DataFrame(json.loads((study/'train-labels.json').read_text())['labels'])
 rows,excluded=attach_refresh_labels(features,labels,cutoff=Cutoff.decision_epoch(c['cutoff_issue'],c['cutoff_ts']),label_delay_hours=c['label_delay_hours'])
 (study/'training-data.json').write_text(rows.to_json(orient='records',double_precision=15))
 (study/'training-exclusions.json').write_text(excluded.to_json(orient='records',double_precision=15))
 print('ADMITTED',len(rows),'EXCLUDED',len(excluded))
