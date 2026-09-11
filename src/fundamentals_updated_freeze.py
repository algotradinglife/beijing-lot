"""Immutable per-issue persistence for bounded parallel strategy replay."""
import gzip
import hashlib
import json
from pathlib import Path
from src.fundamentals_updated_scope import updated_strategy_plans


def freeze_updated_issue(frame, *, cutoffs, seeds, budget_cny, unit_cny, payout_factor, output_path):
    """Persist one immutable issue bundle for bounded parallel execution.

    Same inputs/validation as updated_strategy_plans; output_path must be new.
    Returns filename and SHA256; no settlement is read. Empty model-input frames
    write an explicit NO_READY_FACTORS record (caller records cash for all arms).
    """
    path=Path(output_path)
    bundle=updated_strategy_plans(frame,cutoffs=cutoffs,seeds=seeds,budget_cny=budget_cny,unit_cny=unit_cny,payout_factor=payout_factor) if len(frame) else dict(plans={},exclusions=dict(reason='NO_READY_FACTORS'))
    if not len(frame) and (cutoffs or (budget_cny,unit_cny,payout_factor)!=(1024,2,.65) or not seeds):raise ValueError('Invalid empty input contract')
    encoded=gzip.compress(json.dumps(bundle).encode(),compresslevel=1,mtime=0)
    with path.open('xb') as stream:stream.write(encoded)
    return dict(path=str(path),sha256=hashlib.sha256(encoded).hexdigest(),policies=len(bundle['plans']))
