"""Portable current release: immutable model bytes and explicit deployment roots.

Legacy release readers remain exclusively for their exact-version archives.
This format never attempts legacy absolute-path resolution at load time.
"""
import hashlib
import json
import pickle
from pathlib import Path
from src.temporal_learning.core import stable_json_hash
from src.temporal_learning.provenance import implementation_closure,verify_implementation_closure
from src.fundamentals_calibrated_draw import predict_calibrated_draw
from src.fundamentals_retrained_experts import predict_experts

FILES=('draw/draw-expert/model.json','draw/draw-expert/model.pkl',
       'draw/signal-rates.json','draw/signal-rates.pkl','draw/rate-cv.json',
       'high/high-expert/model.json','high/high-expert/model.pkl')


def _portable_metadata(model_root):
    """Validate frozen JSON and binary hashes; return metadata before unpickling."""
    root=Path(model_root);metadata={};receipts=[]
    for name,stem in [('draw','draw/draw-expert/model'),('rates','draw/signal-rates'),('high','high/high-expert/model')]:
        meta=json.loads((root/(stem+'.json')).read_text())
        if stable_json_hash(meta['receipt'])!=meta['seal'] or hashlib.sha256((root/(stem+'.pkl')).read_bytes()).hexdigest()!=meta['model_sha256']:
            raise ValueError('Portable model/receipt changed')
        metadata[name]=meta
        receipts.extend([meta['receipt']] if name=='rates' else meta['receipt'].values())
    cv=json.loads((root/'draw/rate-cv.json').read_text())
    if (stable_json_hash(cv['receipt'])!=cv['seal'] or stable_json_hash(cv['oof'])!=cv['receipt']['oof_sha256'] or
        cv['selected']!=cv['receipt']['selected'] or cv['selected']!=metadata['rates']['selected']):
        raise ValueError('Portable calibration changed')
    if set(metadata['draw']['receipt'])!={'draw'} or set(metadata['high']['receipt'])!={'high'}:
        raise ValueError('Independent draw/high models required')
    receipts.append(cv['receipt'])
    sources={}
    for receipt in receipts:
        for name,digest in receipt['source_hashes'].items():
            if name in sources and sources[name]!=digest:raise ValueError('Conflicting portable source identity')
            sources[name]=digest
    return metadata,cv,receipts,sources


def _portable_path(root,relative):
    """Resolve a declared relative locator; reject absolute and escaping paths."""
    p=Path(relative)
    if str(p)=='.':return Path(root)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Invalid portable relative path')
    return Path(root)/p


def freeze_portable_experts(model_root, *, output_path, source_root, provenance_root,
                            repository_root, version):
    """Write a new source-bound portable envelope, never rewrite model files.

    source_root explicitly locates the original source IDs during publication.
    Absolute IDs must be beneath it; relative IDs are relative to it. The sealed
    envelope stores only relative locators, never physical runtime roots.
    Inputs: trusted local JSON/pickles; all hashes/code verified before publish.
    Returns manifest path. Existing output fails; no fitting or label changes.
    """
    if version!='2.0.0':raise ValueError('Exact model version 2.0.0 required')
    root=Path(model_root);source_root=Path(source_root).absolute()
    _,_,receipts,sources=_portable_metadata(root);bindings={}
    for source,expected in sources.items():
        p=Path(source)
        if p.is_absolute():
            try:p=p.relative_to(source_root)
            except ValueError:raise ValueError('Source outside explicit publication root: '+source)
        file=_portable_path(source_root,str(p))
        if hashlib.sha256(file.read_bytes()).hexdigest()!=expected:raise ValueError('Portable source changed: '+source)
        bindings[source]=dict(path=str(p),sha256=expected)
    for receipt in receipts:verify_implementation_closure(Path(provenance_root),receipt['implementation'])
    receipt=dict(format='PORTABLE_EXPERTS_V1',version=version,
        files={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in FILES},
        sources=bindings,implementation=implementation_closure(Path(repository_root),['src.fundamentals_portable_experts']))
    with Path(output_path).open('x') as handle:json.dump(dict(receipt=receipt,seal=stable_json_hash(receipt)),handle,indent=2)
    return Path(output_path)


def load_portable_experts(manifest_path, *, expected_version, model_root,
                          source_root, provenance_root, repository_root):
    """Load exact portable models with explicit roots, no original-path fallback.

    Every model, upstream source and implementation is checked before any
    deserialization. Physical roots do not enter the returned artifact identity.
    Raises for missing/mutated inputs, wrong version or unsupported format.
    """
    payload=json.loads(Path(manifest_path).read_text());r=payload['receipt']
    if (expected_version!='2.0.0' or r['version']!=expected_version or
        r['format']!='PORTABLE_EXPERTS_V1' or stable_json_hash(r)!=payload['seal'] or set(r['files'])!=set(FILES)):
        raise ValueError('Portable release version/seal mismatch')
    verify_implementation_closure(Path(repository_root),r['implementation'])
    for name,digest in r['files'].items():
        if hashlib.sha256(_portable_path(model_root,name).read_bytes()).hexdigest()!=digest:raise ValueError('Portable released file changed')
    metadata,cv,receipts,sources=_portable_metadata(model_root)
    if set(sources)!=set(r['sources']):raise ValueError('Portable source bindings incomplete')
    for source,expected in sources.items():
        binding=r['sources'][source]
        if binding['sha256']!=expected or hashlib.sha256(_portable_path(source_root,binding['path']).read_bytes()).hexdigest()!=expected:
            raise ValueError('Portable source changed: '+source)
    for receipt in receipts:verify_implementation_closure(Path(provenance_root),receipt['implementation'])
    artifacts={}
    for name,stem in [('draw','draw/draw-expert/model'),('rates','draw/signal-rates'),('high','high/high-expert/model')]:
        artifact=pickle.loads((Path(model_root)/(stem+'.pkl')).read_bytes())
        if artifact['seal']!=metadata[name]['seal'] or stable_json_hash(artifact['receipt'])!=artifact['seal']:
            raise ValueError('Portable deserialized receipt mismatch')
        artifacts[name]=artifact
    if artifacts['draw']['cutoff']!=artifacts['rates']['cutoff'] or artifacts['draw']['cutoff']!=artifacts['high']['cutoff']:
        raise ValueError('Portable expert cutoff mismatch')
    draw_receipt=dict(api='CALIBRATED_DRAW_V1',version='1.1.0',release_seal=payload['seal'],
        expert_seal=artifacts['draw']['seal'],rate_seal=artifacts['rates']['seal'],policy=cv['selected'],
        probability_semantics='FINAL_HANDICAP_DRAW_MASS',portable_files=r['files'])
    draw=dict(expert=artifacts['draw'],rates=artifacts['rates'],receipt=draw_receipt,seal=stable_json_hash(draw_receipt))
    binding=dict(version=expected_version,release_seal=payload['seal'],draw_seal=draw['seal'],high_seal=artifacts['high']['seal'])
    return dict(draw=draw,high=artifacts['high'],version=expected_version,release_seal=payload['seal'],binding=binding,seal=stable_json_hash(binding))


def predict_portable_expert(artifacts, expert, frame, *, cutoff, draw_weight=None):
    """Predict one expert/cutoff using the unchanged authoritative predictors.

    draw_weight is valid only for draw. Returns the existing prediction receipt
    plus the portable model version/release binding; no learning or I/O.
    """
    if (stable_json_hash(artifacts['binding'])!=artifacts['seal'] or artifacts['binding']!=dict(version=artifacts['version'],release_seal=artifacts['release_seal'],draw_seal=artifacts['draw']['seal'],high_seal=artifacts['high']['seal'])):raise ValueError('Portable model binding changed')
    if expert not in ['draw','high'] or artifacts['version']!='2.0.0':raise ValueError('Unknown portable expert/version')
    if expert=='high' and draw_weight is not None:raise ValueError('draw_weight applies only to draw')
    if expert=='draw':result=predict_calibrated_draw(artifacts['draw'],frame,cutoff,draw_weight=draw_weight)
    else:result=predict_experts(artifacts['high'],frame,cutoff)
    result['expert_version']=artifacts['version']
    original=result.attrs
    receipt=dict(portable_release_seal=artifacts['release_seal'],version=artifacts['version'],expert=expert,
        original=original,prediction_sha256=stable_json_hash(result.to_json(orient='records')))
    result.attrs=dict(prediction_receipt=receipt,prediction_seal=stable_json_hash(receipt))
    return result
