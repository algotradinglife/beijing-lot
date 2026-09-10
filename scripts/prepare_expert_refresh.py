"""Freeze explicit CV/test feature partitions without opening new target labels."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expert_refresh import read_refresh_features,repair_refresh_training_clocks
from src.temporal_learning.core import stable_json_hash
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for name in ['prior','experiment','clean-study','output']:p.add_argument('--'+name,required=name=='output')
 p.add_argument('--repair-study');p.add_argument('--clock-audit');p.add_argument('--source-root')
 a=p.parse_args();out=Path(a.output)
 if a.repair_study:
  if not a.clock_audit or not a.source_root:p.error('Clock audit and source root required')
  print(repair_refresh_training_clocks(a.repair_study,a.clock_audit,out,source_root=a.source_root));sys.exit(0)
 if not all([a.prior,a.experiment,a.clean_study]):p.error('Prior, experiment and clean study required')
 if (out/'contract.json').exists():raise FileExistsError('Immutable study already exists')
 data=read_refresh_features(a.prior,a.experiment,a.clean_study,train_count=72,test_count=24,initial_issues=32)
 out.mkdir(parents=True,exist_ok=True)
 (out/'contract.json').write_text(json.dumps(data['contract'],indent=2))
 for part in ['train','test']:
  (out/f'{part}-features.json').write_text(data[part].to_json(orient='records',double_precision=15))
 receipt=dict(source_hashes=data['source_hashes'],readiness=data['readiness'],contract=data['contract'],
     preparation=dict(prior=a.prior,experiment=a.experiment,clean_study=a.clean_study,source_root=str(Path.cwd().resolve())))
 (out/'input-receipt.json').write_text(json.dumps(dict(receipt=receipt,seal=stable_json_hash(receipt)),indent=2))
 print('FEATURES',len(data['train']),len(data['test']),flush=True)
