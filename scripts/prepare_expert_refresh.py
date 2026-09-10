"""Freeze explicit CV/test feature partitions without opening new target labels."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expert_refresh import read_refresh_features
from src.temporal_learning.core import stable_json_hash
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ['prior','experiment','clean-study','output']:p.add_argument('--'+name,required=True)
 a=p.parse_args();out=Path(a.output)
 if (out/'contract.json').exists():raise FileExistsError('Immutable study already exists')
 data=read_refresh_features(a.prior,a.experiment,a.clean_study,train_count=72,test_count=24,initial_issues=32)
 out.mkdir(parents=True,exist_ok=True)
 (out/'contract.json').write_text(json.dumps(data['contract'],indent=2))
 for part in ['train','test']:
  (out/f'{part}-features.json').write_text(data[part].to_json(orient='records',double_precision=15))
 receipt=dict(source_hashes=data['source_hashes'],readiness=data['readiness'],contract=data['contract'])
 (out/'input-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 print('FEATURES',len(data['train']),len(data['test']),flush=True)
