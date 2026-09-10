"""Freeze both expert artifacts before permitting target-label collection."""
import argparse,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_calibrated_draw import load_calibrated_draw
from src.temporal_learning.core import stable_json_hash
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True);a=p.parse_args();study=Path(a.study)
 if (study/'test-labels.json').exists():raise ValueError('Freeze must precede test label collection')
 c=json.loads((study/'contract.json').read_text())
 load_calibrated_draw(study/'draw',expected_version=c['api_version'],repository_root=Path.cwd())
 high=json.loads((study/'high/high-expert/model.json').read_text())
 if stable_json_hash(high['receipt'])!=high['seal'] or hashlib.sha256((study/'high/high-expert/model.pkl').read_bytes()).hexdigest()!=high['model_sha256']:raise ValueError('High model changed')
 files={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for d in ['draw','high'] for x in (study/d).rglob('*') if x.is_file()}
 with (study/'models-frozen.json').open('x') as h:json.dump(dict(model_version=c['model_version'],api_version=c['api_version'],files=files,frozen_at=datetime.now(timezone.utc).isoformat(),test_labels_opened=False),h,indent=2)
