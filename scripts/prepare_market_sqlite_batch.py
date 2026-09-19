"""Run resumable batch preparation; never activate a release or retire raw data."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_pipeline import prepare_market_batch

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--batch-id',required=True)
    parser.add_argument('--quarto',required=True)
    args=parser.parse_args()
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project=Path(__file__).resolve().parents[1]
    authoritative=Path(check_layout(project/'config/persistent_data_layout.json')['data_root']).resolve(strict=True)
    if root!=authoritative:raise ValueError('data root differs from repository contract')
    with (root/'runtime/state/market-sqlite-preparation.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stages=prepare_market_batch(project,python=sys.executable,data_root=root,
                                    batch_id=args.batch_id,quarto=args.quarto)
    print(json.dumps(dict(state='PREPARATION_COMPLETE_PENDING_REVIEW',stages=stages,
                          raw_deletion_authorized=False)))
