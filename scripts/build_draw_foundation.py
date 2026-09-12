"""Freeze versioned diagnostic draw foundations; open target audit only afterwards."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from src.probability_foundation_draw import fit_draw_foundation,predict_draw_foundation
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_labels import diagnostic_label_clock

p=argparse.ArgumentParser()
p.add_argument('--output',required=True)
p.add_argument('--variant',required=True,choices=['strength','balance'])
a=p.parse_args()
version=f'market-{a.variant}-draw-1.0.0-diagnostic'
market_edges=[0,.1,.15,.2,.25,.3,.35,1] if a.variant=='balance' else [0,.2,.24,.28,1]
secondary_edges=[0,.1,.2,.3,.4,.5,.6,1] if a.variant=='balance' else [0,.15,.2,.25,.3,1]
root=Path(__file__).resolve().parents[1]
base=root/'data/derived/fundamentals_417'
out=Path(a.output)
out.mkdir(parents=True,exist_ok=False)
(out/'models').mkdir()
old_path=base/'new48-pure-baseline-v1/factors.json'
new_path=base/'updated100-strategies-v1/factors.json'
audit_path=base/'new48-expanded-validation-v1/settlement-audit.json'
sources={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
         for path in [old_path,new_path,audit_path,Path(__file__),root/'r/probability_foundation_draw.R',
                      root/'r/fundamentals_signal_rate_projection.R',root/'r/fundamentals_score_shape.R']}
old=json.loads(old_path.read_text());new=json.loads(new_path.read_text())
history=pd.DataFrame(old['rows'])
audit=pd.DataFrame(json.loads(audit_path.read_text())['rows'])
history=history.merge(audit[['issue','slot','provider_id','actual_direction']],
    on=['issue','slot','provider_id'],validate='one_to_one',how='left').rename(columns={'actual_direction':'actual'})
history['fixture_decision_ts']=[old['cutoffs'][str(r.issue)][str(r.slot)] for r in history.itertuples()]
clock_limit=Cutoff.last_issue('CLOCK_CONSTRUCTION_ONLY',pd.to_datetime(history.fixture_decision_ts,utc=True).max()+pd.Timedelta(days=1))
history['label_available_ts']=[diagnostic_label_clock(t,cutoff=clock_limit,delay_hours=6) for t in history.fixture_decision_ts]
history['issue_code']=history.issue.astype(str)
history['issue_year']=pd.to_datetime(history.fixture_decision_ts,utc=True).dt.year
rows=[];models={}
for issue in new['issues']:
    target=pd.DataFrame([r for r in new['rows'] if str(r['issue'])==str(issue)])
    target['fixture_decision_ts']=[new['cutoffs'][str(issue)][str(r.slot)] for r in target.itertuples()]
    cutoff=Cutoff.decision_epoch(str(issue),min(pd.to_datetime(list(new['cutoffs'][str(issue)].values()),utc=True)))
    artifact=fit_draw_foundation(history,cutoff,repository_root=root,source_hashes=sources,
        market_edges=market_edges,secondary_edges=secondary_edges,
        prior_strength=100,epsilon=1e-6,version=version)
    path=out/'models'/f'{issue}.json'
    with path.open('x') as handle:json.dump(artifact,handle,ensure_ascii=False)
    models[str(issue)]={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    # Mandatory independent deterministic fit replay before prediction.
    assert artifact==fit_draw_foundation(history,cutoff,repository_root=root,source_hashes=sources,
        market_edges=market_edges,secondary_edges=secondary_edges,
        prior_strength=100,epsilon=1e-6,version=artifact['version'])
    predicted=predict_draw_foundation(artifact,target,cutoff,repository_root=root)
    predicted['cutoff_ts']=cutoff.cutoff_ts.isoformat()
    rows.extend(predicted.to_dict('records'))
predictions=pd.DataFrame(rows)
predictions.to_csv(out/'predictions.csv',index=False)
manifest={'version':artifact['version'],'historical_admission':False,'source_hashes':sources,
    'models':models,'predictions_sha256':hashlib.sha256((out/'predictions.csv').read_bytes()).hexdigest(),
    'parameters':artifact['parameters'],'scope':'FIXED_ORIGINAL48_TRAINING_NEW100_POST_EXPOSURE_DIAGNOSTIC',
    'label_evidence':'FIXTURE_PLUS_6H_HISTORICAL_PROXY','independent_fit_replays':len(models)}
with (out/'frozen.json').open('x') as handle:json.dump(manifest,handle,ensure_ascii=False,indent=2)
# Labels are used solely for final retrospective evaluation after all artifacts freeze.
target_audit=base/'updated100-strategies-v1/settlement-audit.json'
labels=pd.DataFrame(json.loads(target_audit.read_text())['rows'])
evaluated=predictions.merge(labels[['issue','slot','provider_id','actual_direction']],
    on=['issue','slot','provider_id'],how='left',validate='one_to_one')
assert evaluated.actual_direction.isin(['W','D','L']).all()
evaluated.to_csv(out/'evaluation.csv',index=False)
(out/'evaluation-receipt.json').write_text(json.dumps({
    'freeze_sha256':hashlib.sha256((out/'frozen.json').read_bytes()).hexdigest(),
    'label_source_sha256':hashlib.sha256(target_audit.read_bytes()).hexdigest(),
    'evaluation_sha256':hashlib.sha256((out/'evaluation.csv').read_bytes()).hexdigest()},indent=2))
print(json.dumps({'issues':len(models),'fixtures':len(predictions),'version':artifact['version']}))
