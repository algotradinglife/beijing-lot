"""Bind an existing diagnostic draw model to explicit new issue cutoffs; no fit.

CLI: project-python scripts/bind_n7_expanded_foundation.py CONFIG.json
All history, model, projection and code roots are explicit hash-bound inputs.
Chronology, weights, receipts and prediction are supplied by shared modules.
"""
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd
from src.n7_frozen_foundation import read_frozen_draw_history, bind_frozen_draw_foundation
from src.probability_foundation_draw import predict_draw_foundation
from src.temporal_learning import Cutoff

cfg=json.loads(Path(sys.argv[1]).read_text());out=Path(cfg['output'])
if out.exists():raise ValueError('Output already exists')
for path,identity in cfg['source_hashes'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=identity:raise ValueError('Source changed: '+path)
projection=json.loads(Path(cfg['projection']).read_text())
for name,identity in projection['implementation_hashes'].items():
    if hashlib.sha256((Path(cfg['repository_root'])/name).read_bytes()).hexdigest()!=identity:
        raise ValueError('Projection implementation changed')
frame=pd.DataFrame(projection['fixtures']).rename(columns={'cutoff_utc':'fixture_decision_ts'})
first=frame.sort_values('fixture_decision_ts').iloc[0]
history=read_frozen_draw_history(factors_path=cfg['factors'],factors_sha256=cfg['source_hashes'][cfg['factors']],
    audit_path=cfg['history_audit'],audit_sha256=cfg['source_hashes'][cfg['history_audit']],
    cutoff=Cutoff.decision_epoch(first.issue,first.fixture_decision_ts),label_delay_hours=6)
out.mkdir(parents=True);(out/'models').mkdir();models={};predictions=[]
for issue in projection['issue_order']:
    x=frame[frame.issue==issue][['issue','slot','provider_id','handicap','fixture_decision_ts','q_W','q_D','q_L']]
    if x.empty:continue
    cutoff=Cutoff.decision_epoch(issue,min(x.fixture_decision_ts))
    model=bind_frozen_draw_foundation(history,cutoff,model_path=cfg['reference_model'],
        model_sha256=cfg['source_hashes'][cfg['reference_model']],
        reference_repository_root=cfg['reference_repository_root'],repository_root=cfg['repository_root'],
        source_hashes=cfg['source_hashes'])
    prediction=predict_draw_foundation(model,x,cutoff,repository_root=cfg['repository_root'])
    path=out/'models'/f'{issue}.json';path.write_text(json.dumps(model,allow_nan=False))
    models[issue]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    predictions.extend(json.loads(prediction.to_json(orient='records',double_precision=15)))
    if len(models)%25==0:print('Frozen model bindings',len(models),flush=True)
for path,identity in cfg['source_hashes'].items():
    if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=identity:raise ValueError('Source changed during bind')
(out/'predictions.json').write_text(json.dumps(dict(rows=predictions,models=models,
    issue_order=projection['issue_order'],publication_coverage=projection['publication_coverage'],
    source_hashes=cfg['source_hashes'],projection_implementation=projection['implementation_hashes'],
    historical_admission=False),allow_nan=False))
print('Bound',len(models),'unchanged models;',len(predictions),'predictions',flush=True)
