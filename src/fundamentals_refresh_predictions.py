"""Compact authenticated prediction exchange for the historical refresh report."""
import hashlib,json
from pathlib import Path
import pandas as pd
from src.temporal_learning.core import stable_json_hash
from src.fundamentals_draw_versions import read_draw_version


def refresh_input_hash(study,entry,*,repository_root):
    """Reconstruct the authoritative router's nominated numeric input projection.

    Reads only saved feature snapshots and version-bound metadata. No fitting,
    imputation or label access; returns the exact JSON hash sent to the worker.
    """
    root=Path(repository_root);f=pd.DataFrame(json.loads((Path(study)/'test-features.json').read_text()))
    if entry['backend']=='RAW_TREE':
        paths=[(root/entry['models'][issue]).with_suffix('.json') for issue in f.issue_code.unique()]
    else:paths=[root/entry['model_dir']/'draw-expert/model.json']
    features=[]
    for path in dict.fromkeys(paths):
        for expert in json.loads(path.read_text())['receipt'].values():features.extend(expert['features'])
    columns=list(dict.fromkeys(['issue_code','slot','provider_id','handicap','predictor_clock_ts']+
        (['baseline_draw'] if entry['backend']=='CALIBRATED' else [])+features))
    return stable_json_hash(json.loads(f[columns].to_json(orient='records',double_precision=15)))


def validate_refresh_candidate(entry,expert,study,frozen):
    """Require version routing to name this study's exact frozen expert files."""
    study=Path(study)
    if expert=='draw':
        if entry['backend']!='CALIBRATED' or Path(entry['model_dir']).resolve()!=(study/'draw').resolve():raise ValueError('Wrong frozen candidate')
    else:
        expected=(study/'high/high-expert/model.pkl').resolve()
        if entry['backend']!='RAW_TREE' or not entry['models'] or any(Path(p).resolve()!=expected for p in entry['models'].values()):raise ValueError('Wrong frozen candidate')
    files=frozen_candidate_files(study,expert,frozen)
    actual={str(Path(k).resolve()):v for k,v in entry['files'].items()}
    if any(actual.get(k)!=v for k,v in files.items()):raise ValueError('Frozen candidate file binding differs')


def save_refresh_prediction(result,path,*,version,catalog_path,study,repository_root):
    """Write verified router output once, retaining compact model/source bindings.

    Full router receipts repeat large CV ledgers for every issue. Their hashes
    are retained instead; the version catalog binds the actual model files.
    No learning. Rejects changed rows, receipts, versions or existing output.
    """
    receipt=result.attrs['prediction_receipt']
    if (stable_json_hash(receipt)!=result.attrs['prediction_seal'] or
        stable_json_hash(result.to_json(orient='records'))!=receipt['prediction_sha256'] or
        receipt['version']!=version or not result.expert_version.eq(version).all()):
        raise ValueError('Prediction receipt/rows/version mismatch')
    catalog=read_draw_version(catalog_path,version,repository_root=repository_root)
    if catalog['catalog_seal']!=receipt['catalog_seal']:raise ValueError('Catalog binding mismatch')
    if refresh_input_hash(study,catalog['entry'],repository_root=repository_root)!=receipt['input_sha256']:raise ValueError('Router input hash mismatch')
    compact={k:v for k,v in receipt.items() if k!='model_receipts'}
    compact['model_receipt_hashes']={k:stable_json_hash(v) for k,v in receipt['model_receipts'].items()}
    compact['original_router_seal']=result.attrs['prediction_seal']
    compact['catalog_path']=str(catalog_path)
    compact['catalog_sha256']=hashlib.sha256(Path(catalog_path).read_bytes()).hexdigest()
    compact['snapshot_hashes']={name:hashlib.sha256((Path(study)/name).read_bytes()).hexdigest() for name in ['contract.json','test-features.json','models-frozen.json']}
    rows=json.loads(result.to_json(orient='records',double_precision=15))
    compact['rows_sha256']=stable_json_hash(rows)
    with Path(path).open('x') as h:json.dump(dict(rows=rows,receipt=compact,seal=stable_json_hash(compact)),h)


def verify_refresh_predictions(study,*,repository_root):
    """Validate all four nominated outputs before R computes comparison metrics.

    Checks seals, numeric rows, exact versions, frozen model catalogs, input
    snapshot hashes, fixture identities and per-fixture cutoffs. Returns counts;
    any missing/mutated file fails. Does not read labels, fit or write.
    """
    study=Path(study);contract=json.loads((study/'contract.json').read_text())
    features=json.loads((study/'test-features.json').read_text())
    keys=['issue_code','slot','provider_id'];identities=[[r[k] for k in keys] for r in features]
    from src.temporal_learning import Cutoff
    cuts=[Cutoff.decision_epoch(r['issue_code'],contract['cutoffs'][r['issue_code']][str(r['slot'])]).cutoff_ts.isoformat() for r in features]
    frozen=json.loads((study/'models-frozen.json').read_text())
    for name,h in frozen['files'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Frozen model changed')
    counts={}
    for name,version in [('new_draw','2.0.0'),('new_high','2.0.0'),('old_draw','1.1.0'),('old_high','0.1.0')]:
        x=json.loads((study/'evaluation'/f'{name}.json').read_text());r=x['receipt']
        if (stable_json_hash(r)!=x['seal'] or stable_json_hash(x['rows'])!=r['rows_sha256'] or r['version']!=version or
            any(row['expert_version']!=version for row in x['rows'])):raise ValueError('Prediction seal/version mismatch')
        if [[row[k] for k in keys] for row in x['rows']]!=identities or r['cutoffs']!=cuts:raise ValueError('Prediction identities/cutoffs changed')
        for file,h in r['snapshot_hashes'].items():
            if hashlib.sha256((study/file).read_bytes()).hexdigest()!=h:raise ValueError('Prediction input changed')
        if set(r['snapshot_hashes'])!={'contract.json','test-features.json','models-frozen.json'}:raise ValueError('Missing input binding')
        catalog=read_draw_version(r['catalog_path'],version,repository_root=repository_root)
        if (catalog['catalog_seal']!=r['catalog_seal'] or hashlib.sha256(Path(r['catalog_path']).read_bytes()).hexdigest()!=r['catalog_sha256']):raise ValueError('Prediction model catalog changed')
        if refresh_input_hash(study,catalog['entry'],repository_root=repository_root)!=r['input_sha256']:raise ValueError('Router input hash mismatch')
        if name.startswith('new_'):validate_refresh_candidate(catalog['entry'],name.split('_')[1],study,frozen)
        counts[name]=len(x['rows'])
    binding=json.loads((study/'report-inputs.json').read_text())
    if stable_json_hash(binding['receipt'])!=binding['seal'] or set(binding['receipt']['files'])!=set(REPORT_INPUTS):
        raise ValueError('Report input snapshot seal mismatch')
    for name,digest in binding['receipt']['files'].items():
        if hashlib.sha256((study/name).read_bytes()).hexdigest()!=digest:raise ValueError('Report input snapshot changed: '+name)
    return counts


REPORT_INPUTS = ('test-labels.json', 'training-data.json', 'contract.json', 'test-features.json',
                 'evaluation/new_draw.json', 'evaluation/new_high.json',
                 'evaluation/old_draw.json', 'evaluation/old_high.json')


def freeze_refresh_report_inputs(study):
    """Seal exact settlement, exclusion and prediction bytes after evaluation.

    Reads saved inputs only; no fitting or label availability inference. Writes
    report-inputs.json once. An identical repeat is harmless; changed inputs
    require a separate evaluation directory and never rewrite the old receipt.
    """
    study=Path(study)
    receipt=dict(files={name:hashlib.sha256((study/name).read_bytes()).hexdigest() for name in REPORT_INPUTS})
    payload=dict(receipt=receipt,seal=stable_json_hash(receipt));path=study/'report-inputs.json'
    if path.exists():
        if json.loads(path.read_text())!=payload:raise ValueError('Report input snapshot changed')
    else:
        with path.open('x') as handle:json.dump(payload,handle,indent=2)
    return path


def bind_legacy_catalog_roots(catalog, legacy_root):
    """Pin archived data/runtime paths to an explicit audit snapshot root.

    Returns a deep-copied sealed catalog. Preserves version/file hashes and the
    relative worker pin, whose identical implementation is checked by the router.
    No fallback, fitting, file access or mutation of the original catalog.
    """
    import copy
    root=Path(legacy_root).resolve();result=copy.deepcopy(catalog)
    if stable_json_hash(result['receipt'])!=result['seal']:raise ValueError('Legacy catalog seal changed')
    for entry in result['receipt']['versions'].values():
        for name in ['runtime_root','model_dir']:
            if name in entry:entry[name]=str(root/entry[name])
        if 'models' in entry:entry['models']={k:str(root/v) for k,v in entry['models'].items()}
        entry['files']={k if k=='scripts/predict_draw_version_worker.py' else str(root/k):v for k,v in entry['files'].items()}
    result['seal']=stable_json_hash(result['receipt'])
    return result


def verify_refresh_input_snapshots(study, *, prior, experiment, clean_study):
    """Independently reconstruct features and label admission from named sources.

    Runs in the explicitly selected source snapshot working directory when its
    receipts contain relative locators. Returns verified source hashes; raises
    on drift, inconsistent features, targets, labels or exclusion inventories.
    No fitting, model loading or writes.
    """
    from src.fundamentals_expert_refresh import read_refresh_features,attach_refresh_labels
    from src.temporal_learning import Cutoff
    study=Path(study);contract=json.loads((study/'contract.json').read_text())
    payload=json.loads((study/'input-receipt.json').read_text())
    if stable_json_hash(payload['receipt'])!=payload['seal']:raise ValueError('Input receipt changed')
    rebuilt=read_refresh_features(prior,experiment,clean_study,train_count=len(contract['train_issues']),
        test_count=len(contract['test_issues']),initial_issues=contract['initial_issues'])
    if rebuilt['contract']!=contract or rebuilt['source_hashes']!=payload['receipt']['source_hashes']:
        raise ValueError('Source/contract replay differs')
    for part in ['train','test']:
        if json.loads(rebuilt[part].to_json(orient='records',double_precision=15))!=json.loads((study/f'{part}-features.json').read_text()):
            raise ValueError('Feature replay differs')
    labels=pd.DataFrame(json.loads((study/'train-labels.json').read_text())['labels'])
    rows,excluded=attach_refresh_labels(rebuilt['train'],labels,cutoff=Cutoff.decision_epoch(contract['cutoff_issue'],contract['cutoff_ts']),label_delay_hours=contract['label_delay_hours'])
    pd.testing.assert_frame_equal(rows,pd.DataFrame(json.loads((study/'training-data.json').read_text())),check_dtype=False)
    if excluded.to_dict('records')!=json.loads((study/'training-exclusions.json').read_text()):raise ValueError('Exclusion replay differs')
    return rebuilt['source_hashes']


def frozen_candidate_files(study, expert, frozen):
    """Select a nonempty expert file set using normalized filesystem identities.

    Relative paths are resolved from the explicit command working directory;
    absolute and equivalent dot-segment paths identify the same frozen files.
    Returns absolute locators with unchanged hashes. No reads or writes.
    """
    if expert not in ['draw','high']:raise ValueError('Unknown expert')
    base=(Path(study)/expert).resolve()
    files={str(Path(name).resolve()):digest for name,digest in frozen['files'].items() if Path(name).resolve().is_relative_to(base)}
    if not files:raise ValueError('Missing frozen candidate files')
    return files
