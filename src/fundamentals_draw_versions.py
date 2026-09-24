"""Explicit historical draw-version routing with isolated frozen runtimes."""
from src.fundamentals_signal_rates import validate_draw_weight
import hashlib
import json
import subprocess
import warnings
from beidan_backend.temporal_learning.replay import HistoricalReplayWarning
from pathlib import Path
import pandas as pd
from beidan_backend.temporal_learning import Cutoff
from beidan_backend.temporal_learning.core import stable_json_hash
from beidan_backend.temporal_learning.predictor_clock import require_prior_predictor_clock


def read_draw_version(catalog_path, version, *, repository_root):
    """Resolve an exact numbered release and verify its files; read-only.

    Historical numbering is retrospective. The catalog names the probability
    semantics, frozen runtime and model identity; no latest/default substitution.
    Missing versions, mutated catalog seals or frozen files fail closed.
    """
    root=Path(repository_root).resolve(); path=Path(catalog_path)
    if not path.is_absolute():
        path=root/path
    catalog=json.loads(path.read_text())
    if stable_json_hash(catalog['receipt'])!=catalog['seal']:
        raise ValueError('Version catalog changed')
    if not isinstance(version,str) or version not in catalog['receipt']['versions']:
        raise ValueError('Unknown exact draw version')
    entry=catalog['receipt']['versions'][version]
    if entry['version']!=version or entry['backend'] not in ['RAW_TREE','CALIBRATED']:
        raise ValueError('Invalid version routing')
    for name,expected in entry['files'].items():
        file=Path(name) if Path(name).is_absolute() else root/name
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            raise ValueError('Version file changed: '+name)
    return dict(entry=entry,catalog_seal=catalog['seal'],version=version)


def predict_draw_version(version, frame, *, cutoffs, catalog_path, repository_root,
                         python, timeout_seconds=300, draw_weight=None):
    """Predict a batch using one explicit Cutoff per row in a separate process.

    frame has unique issue_code/slot/provider_id, predictor_clock_ts and model
    predictors (plus baseline_draw/handicap for calibrated releases). cutoffs is
    an equally sized sequence of shared Cutoff objects, in frame order.
    Returns a DataFrame with expert_version and receipt attrs. RAW_TREE returns
    draw_probability for existing raw fusion; CALIBRATED returns already-blended
    draw_target_probability for signal_rate_score_choices. Never intermix them.
    draw_weight optionally overrides the calibrated draw blend in [0,1] for
    releases explicitly supporting it; None preserves their frozen default.
    Explicit interpreter/runtime isolation avoids replacing current imports.
    No learning, target-label reads, model overwrites or persistent writes.
    """
    root=Path(repository_root).resolve()
    release=read_draw_version(catalog_path,version,repository_root=root)
    keys=['issue_code','slot','provider_id']
    if frame.empty or frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError('Nonempty unique target identities required')
    if len(cutoffs)!=len(frame) or timeout_seconds<=0:
        raise ValueError('Explicit per-fixture cutoffs and positive timeout required')
    decisions=[]
    for (_,row),cutoff in zip(frame.iterrows(),cutoffs):
        if not isinstance(cutoff,Cutoff) or row.issue_code!=cutoff.target_issue:
            raise ValueError('Target cutoff identity mismatch')
        require_prior_predictor_clock(row.predictor_clock_ts,cutoff)
        decisions.append(cutoff.cutoff_ts.isoformat())
    entry=release['entry']
    if draw_weight is not None and not entry.get('supports_draw_weight',False):
        raise ValueError('Selected version does not support draw_weight; use 1.1.0')
    if draw_weight is not None:
        draw_weight=validate_draw_weight(draw_weight)
    if entry['backend']=='RAW_TREE':
        if not set(frame.issue_code).issubset(entry['models']):
            raise ValueError('No frozen model registered for target issue')
        metadata=[(root/entry['models'][issue]).with_suffix('.json') for issue in frame.issue_code.unique()]
    else:
        metadata=[root/entry['model_dir']/'draw-expert/model.json']
    features=[]
    for path in metadata:
        for expert in json.loads(path.read_text())['receipt'].values():
            features.extend(expert['features'])
    columns=list(dict.fromkeys(keys+['handicap','predictor_clock_ts']+
        (['baseline_draw'] if entry['backend']=='CALIBRATED' else [])+features))
    nominated=frame[columns]
    runtime=Path(entry['runtime_root'])
    if not runtime.is_absolute():
        runtime=root/runtime
    runner=root/'scripts/predict_draw_version_worker.py'
    if str(runner.relative_to(root)) not in entry['files']:
        raise ValueError('Worker implementation must be bound')
    request=dict(entry=entry,root=str(root),records=json.loads(nominated.to_json(orient='records',double_precision=15)),
                 decisions=decisions,version=version,draw_weight=draw_weight)
    process=subprocess.run([str(Path(python).absolute()),'-I','-B',str(runner)],cwd=runtime,
        input=json.dumps(request),text=True,capture_output=True,timeout=timeout_seconds,check=False)
    if process.returncode:
        raise ValueError('Version prediction failed: '+process.stderr[-2000:])
    payload=json.loads(process.stdout)
    if payload['runtime_root']!=str(runtime.resolve()):
        raise ValueError('Executed runtime differs from release')
    result=pd.DataFrame(payload['rows'])
    if result[keys].to_dict('records')!=frame[keys].to_dict('records'):
        raise ValueError('Version output identity mismatch')
    result['expert_version']=version
    if 'evaluation_scope' in result and result.evaluation_scope.ne('OUT_OF_SAMPLE').any():
        warnings.warn('训练内／回顾诊断回放：模型可能使用了当时尚不可得的训练信息，结果不代表样本外预测能力。',
                      HistoricalReplayWarning, stacklevel=2)
    receipt=dict(version=version,catalog_seal=release['catalog_seal'],
        probability_semantics=entry['probability_semantics'],cutoffs=decisions,
        draw_weight_override=draw_weight,
        input_sha256=stable_json_hash(request['records']),model_receipts=payload['model_receipts'],
        runtime_root=payload['runtime_root'],imported_sources=payload['imported_sources'],
        prediction_sha256=stable_json_hash(result.to_json(orient='records')),deployable=False)
    result.attrs={'prediction_receipt':receipt,'prediction_seal':stable_json_hash(receipt)}
    return result
