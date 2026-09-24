"""Explicit paired selection of the portable current historical experts."""
import hashlib,json
from pathlib import Path
import pandas as pd
from beidan_backend.temporal_learning import Cutoff
from beidan_backend.temporal_learning.core import stable_json_hash
from beidan_backend.temporal_learning.predictor_clock import require_prior_predictor_clock
from src.fundamentals_portable_experts import load_portable_experts,predict_portable_expert,_portable_path


def predict_active_experts(frame, *, cutoffs, selection_path, repository_root,
                           python, draw_weight=None, model_root=None, source_root=None, provenance_root=None):
    """Predict both pinned portable experts with explicit fixture cutoffs.

    Selection supplies relative model/source/provenance roots and a sealed
    portable manifest. All source/code checks precede prediction. Returns two
    separate DataFrames with per-fixture receipts; only draw accepts a weight.
    python identifies this process's project interpreter; it is verified rather
    than spawning another runtime. Legacy versions use their separate router.
    No fitting, scraping, settlement reads, persistent writes or path fallback.
    """
    import sys
    if Path(python).absolute()!=Path(sys.executable).absolute():
        raise ValueError('Use the explicit current project Python')
    root=Path(repository_root);path=Path(selection_path)
    if not path.is_absolute():path=root/path
    payload=json.loads(path.read_text());receipt=payload['receipt']
    if (stable_json_hash(receipt)!=payload['seal'] or set(receipt['experts'])!={'draw','high'} or
        any(e['version']!='2.0.0' for e in receipt['experts'].values()) or receipt['format']!='PORTABLE_EXPERT_SELECTION_V1'):
        raise ValueError('Invalid paired expert selection')
    keys=['issue_code','slot','provider_id']
    if frame.empty or frame[keys].isna().any().any() or frame.duplicated(keys).any() or len(cutoffs)!=len(frame):
        raise ValueError('Unique fixtures and one explicit cutoff per row required')
    for row,cutoff in zip(frame.itertuples(),cutoffs):
        if not isinstance(cutoff,Cutoff) or row.issue_code!=cutoff.target_issue:raise ValueError('Cutoff identity mismatch')
        require_prior_predictor_clock(row.predictor_clock_ts,cutoff)
    manifest=_portable_path(root,receipt['manifest_path'])
    if hashlib.sha256(manifest.read_bytes()).hexdigest()!=receipt['manifest_sha256']:raise ValueError('Selected expert manifest changed')
    supplied=dict(model_root=model_root,source_root=source_root,provenance_root=provenance_root)
    roots={k:Path(v) if v is not None else _portable_path(root,receipt[k]) for k,v in supplied.items()}
    artifacts=load_portable_experts(manifest,expected_version='2.0.0',repository_root=root,**roots)
    output={}
    for expert in ['draw','high']:
        rows=[];receipts=[]
        for i,cutoff in enumerate(cutoffs):
            result=predict_portable_expert(artifacts,expert,frame.iloc[[i]],cutoff=cutoff,
                **({'draw_weight':draw_weight} if expert=='draw' else {}))
            receipts.append(result.attrs);rows.append(result)
        output[expert]=pd.concat(rows,ignore_index=True)
        output[expert].attrs=dict(selection_seal=payload['seal'],release_seal=artifacts['release_seal'],fixtures=receipts)
    return output
