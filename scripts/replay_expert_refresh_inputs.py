"""Reconstruct original source features and label admission before clock repair."""
import argparse,json,hashlib,sys,subprocess,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.fundamentals_expert_refresh import repair_refresh_training_clocks
from src.fundamentals_refresh_predictions import verify_refresh_input_snapshots

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--study',required=True)
 for name in ['prior','experiment','clean-study','source-root']:p.add_argument('--'+name)
 p.add_argument('--source-process',action='store_true');a=p.parse_args();study=Path(a.study).resolve()
 info=json.loads((study/'clock-repair.json').read_text()) if (study/'clock-repair.json').exists() else None
 original=Path(info['study']) if info else study
 receipt=json.loads((original/'input-receipt.json').read_text())['receipt']
 locations=receipt.get('preparation',{})
 selected={name:getattr(a,name) or locations.get(name) for name in ['prior','experiment','clean_study','source_root']}
 if not all(selected.values()):p.error('Explicit original preparation locations required for an archived study')
 if not a.source_process:
  command=[sys.executable,str(Path(__file__).resolve()),'--study',str(study),'--source-process']
  for key,value in selected.items():command.extend(['--'+key.replace('_','-'),str(value)])
  subprocess.run(command,cwd=selected['source_root'],check=True);sys.exit(0)
 if Path.cwd().resolve()!=Path(selected['source_root']).resolve():raise ValueError('Wrong source snapshot directory')
 verify_refresh_input_snapshots(original,**{k:v for k,v in selected.items() if k!='source_root'})
 names=['contract.json','fit-policy.json','train-labels.json','test-features.json','training-exclusions.json','train-features.json','training-data.json','input-receipt.json']
 if info:
  with tempfile.TemporaryDirectory(dir=study.parent) as temporary:
   rebuilt=repair_refresh_training_clocks(original,info['audit_path'],Path(temporary)/'replay',source_root=info['source_root'])
   for name in names:
    if (rebuilt/name).read_bytes()!=(study/name).read_bytes():raise ValueError('Clock repair replay differs: '+name)
 files={str(study/name):hashlib.sha256((study/name).read_bytes()).hexdigest() for name in names}
 (study/'input-replay.json').write_text(json.dumps(dict(status='PASS',files=files,preparation=selected,implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),indent=2))
 print('FULL_SOURCE_AND_LABEL_REPLAY_PASS')
