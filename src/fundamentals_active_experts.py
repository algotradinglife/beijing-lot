"""Explicit, paired version selection for the two frozen historical experts."""
import hashlib,json
from pathlib import Path
from src.fundamentals_draw_versions import predict_draw_version,read_draw_version
from src.temporal_learning.core import stable_json_hash


def predict_active_experts(frame, *, cutoffs, selection_path, repository_root,
                           python, draw_weight=None, timeout_seconds=1800):
    """Predict both selected versions without fitting or changing probabilities.

    Requires an explicit sealed selection file, per-row Cutoffs and interpreter.
    Returns separate draw/high DataFrames with their existing provenance attrs.
    draw_weight overrides only the calibrated draw/baseline blend; None uses CV.
    Missing or changed catalogs, versions or expert names fail before prediction.
    No scraping, settlement reads, persistent writes or automatic version fallback.
    """
    root=Path(repository_root);path=Path(selection_path)
    if not path.is_absolute():path=root/path
    payload=json.loads(path.read_text());receipt=payload['receipt']
    if stable_json_hash(receipt)!=payload['seal'] or set(receipt['experts'])!={'draw','high'}:
        raise ValueError('Invalid paired expert selection')
    catalogs={}
    for expert,entry in receipt['experts'].items():
        catalog=root/entry['catalog_path']
        if hashlib.sha256(catalog.read_bytes()).hexdigest()!=entry['catalog_sha256']:
            raise ValueError('Selected expert catalog changed')
        release=read_draw_version(catalog,entry['version'],repository_root=root)
        expected='CALIBRATED' if expert=='draw' else 'RAW_TREE'
        if release['entry']['backend']!=expected:raise ValueError('Expert backend mismatch')
        catalogs[expert]=catalog
    return {expert:predict_draw_version(entry['version'],frame,cutoffs=cutoffs,
        catalog_path=catalogs[expert],repository_root=root,python=python,
        timeout_seconds=timeout_seconds,**({'draw_weight':draw_weight} if expert=='draw' else {}))
        for expert,entry in receipt['experts'].items()}
