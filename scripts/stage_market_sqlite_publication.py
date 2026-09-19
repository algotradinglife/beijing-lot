"""Stage and read back a 50-issue SQLite publication without changing registry."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_publication import prepare_market_sqlite_publication
from src.n7_published_markets import read_n7_published_markets
from src.market_storage import _publish_json
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--batch-id',required=True)
    args=parser.parse_args()
    if Path(args.batch_id).name!=args.batch_id or args.batch_id in ('.','..'):
        raise ValueError('unsafe batch id')
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project=Path(__file__).resolve().parents[1]
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        registry=root/'registry/markets-current.json'
        original=registry.read_bytes();release=json.loads(original)['current_release']
        result=prepare_market_sqlite_publication(root,merged_path=release['path'],
            merged_sha256=release['sha256'],database='markets/releases/market-history-v1.sqlite',batch_id=args.batch_id)
        output=root/'audits/market-sqlite'/args.batch_id/'publication-staged.json'
        if output.exists() and json.loads(output.read_text())!=result:
            raise ValueError('staged publication already exists with different content')
        _publish_json(output,result)
        digest=hashlib.sha256(output.read_bytes()).hexdigest()
        issues=[s['issue'] for s in result['issue_sources'] if s.get('batch_id')==args.batch_id]
        verified=read_n7_published_markets(data_root=root,merged_path=str(output.relative_to(root)),
            expected_sha256=digest,issues=issues)
        if registry.read_bytes()!=original:raise ValueError('registry changed during staging')
        code=implementation_closure(project,('src.market_sqlite_publication',))['files']
        code[str(Path(__file__).relative_to(project))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        receipt=dict(state='PUBLICATION_STAGED_READBACK_VERIFIED_NOT_ACTIVATED',batch_id=args.batch_id,
            issues=issues,fixture_market_rows=len(verified['rows']),publication=str(output),sha256=digest,
            original_registry_sha256=hashlib.sha256(original).hexdigest(),implementation_hashes=code,
            raw_files_deleted=0)
        _publish_json(output.parent/'publication-staging-receipt.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False))
