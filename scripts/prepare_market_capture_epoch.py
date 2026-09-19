"""Prepare explicit immutable parallel-capture inputs from a stopped epoch."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market_capture_epoch import prepare_market_epoch
from src.persistent_data_layout import check_layout
from src.market_sqlite_query import query_market_records

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'plan', 'index', 'old-output', 'manifest-dir', 'output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--storage-acceptance', help='Accepted SQLite batch receipt under persistent root')
    parser.add_argument('--storage-acceptance-sha256', help='Expected receipt SHA256')
    args = parser.parse_args()
    root = Path(check_layout(args.contract)['data_root']).resolve()
    paths = [args.plan, args.index, args.old_output, args.manifest_dir, args.output]
    if any(not Path(path).resolve().is_relative_to(root) for path in paths):
        raise ValueError('epoch data paths must be under the persistent root')
    cutover=None
    if bool(args.storage_acceptance)!=bool(args.storage_acceptance_sha256):
        parser.error('storage acceptance path and SHA256 must be supplied together')
    if args.storage_acceptance:
        acceptance_path=Path(args.storage_acceptance).resolve(strict=True)
        acceptance_path.relative_to(root)
        raw=acceptance_path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=args.storage_acceptance_sha256:
            raise ValueError('storage acceptance hash mismatch')
        accepted=json.loads(raw)
        if accepted.get('state')!='SQLITE_BATCH_ACCEPTED' or len(set(accepted['issues']))!=50:
            raise ValueError('accepted fifty-issue storage batch required')
        database=Path(accepted['database']).resolve(strict=True)
        database.relative_to(root)
        captures=[]
        for issue in accepted['issues']:
            rows=query_market_records(database,issue=issue,kind='capture')
            if any(r['batch_id']!=accepted['batch_id'] for r in rows):
                raise ValueError('storage capture batch mismatch')
            captures.extend(rows)
        cutover=dict(captures=captures,database=database,
                     acceptance=dict(path=str(acceptance_path),sha256=args.storage_acceptance_sha256))
    print(json.dumps(prepare_market_epoch(*paths,storage_cutover=cutover), ensure_ascii=False))
