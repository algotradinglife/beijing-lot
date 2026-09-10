"""Independent calibrated-draw v1 interface over frozen, reviewed artifacts.

No fitting, fetching or writes on import or prediction. The loader reads trusted
local pickle files only after checking their hashes and transitive provenance.
"""
import hashlib
import json
import pickle
import warnings
from src.temporal_learning.replay import prediction_scope, HistoricalReplayWarning
from datetime import datetime, timezone
from pathlib import Path

from src.fundamentals_retrained_experts import predict_experts
from src.fundamentals_signal_rates import predict_signal_rates, validate_draw_weight
from src.temporal_learning import Cutoff
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure, verify_implementation_closure


CALIBRATED_DRAW_VERSION = '1.1.0'
RELEASE_FILE = 'calibrated-draw-release.json'


def _load_calibrated_draw(directory, *, repository_root, provenance_root=None):
    """Load frozen draw tree, historical rates and CV-selected projection policy.

    directory contains draw-expert/model.{json,pkl}, signal-rates.{json,pkl}
    and rate-cv.json from the calibration pipeline. All source/code bindings
    must still match. Returns an in-memory v1 artifact; does not read target
    predictions or settlement. Missing/mutated files fail closed. No writes.
    """
    root=Path(repository_root).resolve(); path=Path(directory)
    if not path.is_absolute():
        path=root/path
    provenance_root=Path(provenance_root).resolve() if provenance_root is not None else root
    cv_path=path/'rate-cv.json'; cv=json.loads(cv_path.read_text())
    rates_meta=json.loads((path/'signal-rates.json').read_text())
    if (stable_json_hash(cv['receipt'])!=cv['seal'] or
        cv['selected']!=cv['receipt']['selected'] or cv['selected']!=rates_meta['selected'] or
        stable_json_hash(cv['oof'])!=cv['receipt']['oof_sha256']):
        raise ValueError('Frozen calibration selection changed')
    artifacts={}; bindings={}
    verify_implementation_closure(provenance_root,cv['receipt']['implementation'])
    for source,expected in cv['receipt']['source_hashes'].items():
        file=Path(source) if Path(source).is_absolute() else root/source
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen CV source changed: '+source)
        bindings[source]=expected
    for name,stem in [('expert','draw-expert/model'),('rates','signal-rates')]:
        meta_path=path/(stem+'.json'); binary_path=path/(stem+'.pkl')
        meta=json.loads(meta_path.read_text()); raw=binary_path.read_bytes()
        if stable_json_hash(meta['receipt'])!=meta['seal'] or hashlib.sha256(raw).hexdigest()!=meta['model_sha256']:
            raise ValueError('Frozen model/receipt changed')
        receipts=[meta['receipt']] if name=='rates' else list(meta['receipt'].values())
        for receipt in receipts:
            verify_implementation_closure(provenance_root,receipt['implementation'])
            for source,expected in receipt['source_hashes'].items():
                file=Path(source) if Path(source).is_absolute() else root/source
                if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:
                    raise ValueError('Frozen source changed: '+source)
        artifact=pickle.loads(raw)
        if artifact['seal']!=meta['seal'] or stable_json_hash(artifact['receipt'])!=meta['seal']:
            raise ValueError('Deserialized receipt mismatch')
        artifacts[name]=artifact
        bindings[str(meta_path)]=hashlib.sha256(meta_path.read_bytes()).hexdigest()
        bindings[str(binary_path)]=hashlib.sha256(raw).hexdigest()
    if set(artifacts['expert']['features'])!={'draw'}:
        raise ValueError('Independent draw-only artifact required')
    if artifacts['expert']['cutoff']!=artifacts['rates']['cutoff']:
        raise ValueError('Expert/rate freeze cutoff mismatch')
    bindings[str(cv_path)]=hashlib.sha256(cv_path.read_bytes()).hexdigest()
    receipt=dict(api='CALIBRATED_DRAW_V1',provenance_root=str(provenance_root),expert_seal=artifacts['expert']['seal'],
        rate_seal=artifacts['rates']['seal'],policy=cv['selected'],source_hashes=bindings,
        selection_implementation=cv['receipt']['implementation'],
        implementation=implementation_closure(root,['src.fundamentals_calibrated_draw']),
        probability_semantics='FINAL_HANDICAP_DRAW_MASS',deployable=False)
    return dict(**artifacts,receipt=receipt,seal=stable_json_hash(receipt))


def freeze_calibrated_draw_release(directory, *, version, repository_root, provenance_root=None):
    """Publish a version receipt once after validating the frozen inputs.

    Explicit write: creates calibrated-draw-release.json with exclusive creation,
    never overwrites. Only this runtime's exact semantic version is supported.
    provenance_root optionally names the preserved training implementation; its
    full closures are verified separately from the current prediction runtime.
    Binds five model/CV files plus the API's transitive implementation. Returns
    the receipt path. Does not fit models or change their files.
    """
    if version != CALIBRATED_DRAW_VERSION:
        raise ValueError('Unsupported calibrated draw version')
    root=Path(repository_root).resolve(); path=Path(directory)
    if not path.is_absolute():
        path=root/path
    if (path/RELEASE_FILE).exists():
        raise FileExistsError('Release already frozen; use a new release directory')
    artifact=_load_calibrated_draw(path,repository_root=root,provenance_root=provenance_root)
    files=['draw-expert/model.json','draw-expert/model.pkl','signal-rates.json','signal-rates.pkl','rate-cv.json']
    receipt=dict(version=version,provenance_root=artifact['receipt']['provenance_root'],api=artifact['receipt']['api'],artifact_seal=artifact['seal'],
        files={name:hashlib.sha256((path/name).read_bytes()).hexdigest() for name in files},
        implementation=artifact['receipt']['implementation'],
        generated_at=datetime.now(timezone.utc).isoformat())
    payload=dict(receipt=receipt,seal=stable_json_hash(receipt))
    with (path/RELEASE_FILE).open('x') as handle:
        json.dump(payload,handle,indent=2)
    return path/RELEASE_FILE


def load_calibrated_draw(directory, *, expected_version, repository_root):
    """Load only an exact requested, frozen release; no default/latest fallback.

    Version, model/CV bytes and transitive runtime must match the release before
    deserialization. Also validates all underlying historical source receipts.
    No writes. Missing release or omitted version is an error.
    """
    if expected_version != CALIBRATED_DRAW_VERSION:
        raise ValueError('Unsupported calibrated draw version')
    root=Path(repository_root).resolve(); path=Path(directory)
    if not path.is_absolute():
        path=root/path
    release=json.loads((path/RELEASE_FILE).read_text()); receipt=release['receipt']
    if stable_json_hash(receipt)!=release['seal'] or receipt['version']!=expected_version:
        raise ValueError('Frozen release version/seal mismatch')
    verify_implementation_closure(root,receipt['implementation'])
    for name,expected in receipt['files'].items():
        if hashlib.sha256((path/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Released model/receipt changed: '+name)
    artifact=_load_calibrated_draw(path,repository_root=root,provenance_root=receipt['provenance_root'])
    if artifact['seal']!=receipt['artifact_seal']:
        raise ValueError('Released artifact binding changed')
    artifact['receipt']=dict(artifact['receipt'],version=expected_version,release_seal=release['seal'])
    artifact['seal']=stable_json_hash(artifact['receipt'])
    return artifact


def predict_calibrated_draw(artifact, frame, cutoff, *, draw_weight=None):
    """Predict one target cutoff without learning, labels or I/O.

    frame: unique issue_code/slot/provider_id, integer handicap, baseline_draw
    in [0,1], strictly prior predictor_clock_ts and nominated tree predictors.
    Returns those keys, original three-state draw_signal (or missing-feature
    status), raw_draw_probability, reference/boosted rates, calibration_status,
    and draw_target_probability in [0,1]. The latter is an ALREADY blended mass;
    it intentionally is not named draw_probability, preventing silent use by
    the legacy fusion interface. Use signal_rate_score_choices for projection.
    draw_weight optionally overrides only the draw/baseline blend in [0,1].
    None uses the frozen CV policy. No refitting or weight selection is done;
    the effective weight and frozen policy are bound separately in the receipt.
    Missing features/bands retain baseline with an explicit status. Training or
    earlier targets return automatically with a warning and evaluation_scope.
    Modified artifacts, invalid identities and predictor clocks still fail.
    """
    receipt=artifact['receipt']
    policy=dict(receipt['policy'])
    if draw_weight is not None:
        policy['blend_weight']=validate_draw_weight(draw_weight)
    if (receipt.get('version')!=CALIBRATED_DRAW_VERSION or not receipt.get('release_seal') or
        stable_json_hash(receipt)!=artifact['seal'] or
        artifact['expert']['seal']!=receipt['expert_seal'] or
        artifact['rates']['seal']!=receipt['rate_seal']):
        raise ValueError('Calibrated expert binding changed')
    if not isinstance(cutoff,Cutoff):
        raise ValueError('Explicit target cutoff required')
    scope=prediction_scope(cutoff, set(artifact['expert']['training_issues']) |
        set(artifact['rates']['receipt']['training_issues']), artifact['expert']['cutoff'])
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', HistoricalReplayWarning)
        raw=predict_experts(artifact['expert'],frame,cutoff)
    columns=['issue_code','slot','provider_id','handicap','baseline_draw','predictor_clock_ts']
    inputs=frame[columns].copy()
    inputs['draw_signal']=raw.draw_signal.to_numpy()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', HistoricalReplayWarning)
        result=predict_signal_rates(artifact['rates'],inputs,cutoff,**policy)
    result['draw_weight']=float(policy['blend_weight'])
    result['evaluation_scope']=scope
    result['model_cutoff_ts']=artifact['expert']['cutoff'].cutoff_ts.isoformat()
    result=result.rename(columns={'draw_probability':'draw_target_probability'})
    result['raw_draw_probability']=raw.draw_probability.to_numpy()
    result['expert_version']=receipt['version']
    input_columns=list(dict.fromkeys(columns+artifact['expert']['features']['draw']))
    binding=dict(evaluation_scope=scope,model_cutoff_ts=artifact['expert']['cutoff'].cutoff_ts.isoformat(),
        api=receipt['api'],version=receipt['version'],release_seal=receipt['release_seal'],
        model_seal=artifact['seal'],cutoff_identity=cutoff.identity,
        cutoff_ts=cutoff.cutoff_ts.isoformat(),probability_semantics=receipt['probability_semantics'],
        input_sha256=stable_json_hash(frame[input_columns].to_json(orient='records')),
        policy=policy,frozen_policy=receipt['policy'],
        policy_source='FROZEN_CV_DEFAULT' if draw_weight is None else 'CALLER_WEIGHT',
        prediction_sha256=stable_json_hash(result.to_json(orient='records')),
        deployable=False)
    result.attrs={'prediction_receipt':binding,'prediction_seal':stable_json_hash(binding)}
    return result
