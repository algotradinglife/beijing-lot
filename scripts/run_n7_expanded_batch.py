"""Thin sequential per-batch adapter/projection/frozen-model/candidate entry.

CLI: project-python scripts/run_n7_expanded_batch.py CONFIG.json BATCH_INDEX
The parent dispatches bounded separate batches. This entry never reads target
settlement. All business operations call existing project implementations.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

cfg=json.loads(Path(sys.argv[1]).read_text());batch_index=int(sys.argv[2])
root=Path(cfg['repository_root']);study=Path(cfg['study'])
receipt=json.loads((study/'inputs/input-receipt.json').read_text())
batch=receipt['batches'][batch_index];inputs=Path(batch['path'])
out=study/f'batch-{batch_index:03d}'
if out.exists():raise ValueError('Batch output exists; inspect receipt instead of overwriting')
out.mkdir()
params=json.loads((root/'config/n7_next100_435.json').read_text())
params['scope']=dict(anchor='110513',first=batch['issues'][0],last=batch['issues'][-1],issue_count=len(batch['issues']))
config=out/'config.json';config.write_text(json.dumps(params,indent=2))
scope=out/'scope.json';scope.write_text(json.dumps(dict(issues=batch['issues'])))
prepared=out/'projection-inputs.json';projection=out/'projected.json'
subprocess.run([cfg['rscript'],str(root/'scripts/project_n7_published_markets.R'),
    str(inputs/'published-markets.json.gz'),batch['market_sha256'],
    str(inputs/'handicaps.json'),batch['handicap_sha256'],str(prepared),str(root)],cwd=root,check=True)
subprocess.run([cfg['rscript'],str(root/'scripts/run_n7_market_projection.R'),str(prepared),
    hashlib.sha256(prepared.read_bytes()).hexdigest(),str(config),hashlib.sha256(config.read_bytes()).hexdigest(),
    str(projection),str(root)],cwd=root,check=True)
old=Path(cfg['reference_study']);model=old/'reference-model-101120.json'
factors=old/'reference-history/new48-pure-baseline-v1/factors.json'
audit=old/'reference-history/new48-expanded-validation-v1/settlement-audit.json'
source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [projection,prepared,config,model,factors,audit]}
source_hashes.update(json.loads(projection.read_text())['source_hashes'])
binding=dict(output=str(out/'probabilities'),repository_root=str(root),reference_repository_root=str(old/'reference-implementation'),
    projection=str(projection),reference_model=str(model),factors=str(factors),history_audit=str(audit),source_hashes=source_hashes)
binding_path=out/'binding-config.json';binding_path.write_text(json.dumps(binding,indent=2))
subprocess.run([cfg['python'],str(root/'scripts/bind_n7_expanded_foundation.py'),str(binding_path)],cwd=root,check=True)
pred=out/'probabilities/predictions.json'
subprocess.run([cfg['python'],str(root/'scripts/build_n7_next100_candidates.py'),
    '--predictions',str(pred),'--predictions-sha256',hashlib.sha256(pred.read_bytes()).hexdigest(),
    '--config',str(config),'--config-sha256',hashlib.sha256(config.read_bytes()).hexdigest(),
    '--repository-root',str(root),'--output',str(out/'candidates'),
    '--reference-model',str(model),'--scope-manifest',str(scope),
    '--scope-sha256',hashlib.sha256(scope.read_bytes()).hexdigest(),'--workers',str(cfg['candidate_workers'])],cwd=root,check=True)
names=['projection-inputs.json','projected.json','config.json','scope.json','binding-config.json',
       'probabilities/predictions.json','candidates/candidate-manifest.json']
(out/'batch-receipt.json').write_text(json.dumps(dict(status='PREDICTION_CANDIDATES_ONLY',issues=batch['issues'],
    source_receipt_sha256=hashlib.sha256((study/'inputs/input-receipt.json').read_bytes()).hexdigest(),
    files={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in names},
    implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),historical_admission=False),indent=2))
print('Completed prediction batch',batch_index,flush=True)
