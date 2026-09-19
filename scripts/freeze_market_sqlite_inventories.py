"""Freeze batch source inventories only after exact independent backup comparison."""
import argparse
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite import open_market_database,verify_market_batch_backup
from src.market_sqlite_query import query_market_batch_source_inventories
from src.market_storage import _publish_json
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--batch-id',required=True)
    args=parser.parse_args()
    if Path(args.batch_id).name!=args.batch_id or args.batch_id in ('.','..'):raise ValueError('unsafe batch id')
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project=Path(__file__).resolve().parents[1]
    audit=root/'audits/market-sqlite'/args.batch_id
    retention_path=audit/'audit-retention-receipt.json'
    retention_bytes=retention_path.read_bytes();retention=json.loads(retention_bytes)
    if retention['batch_id']!=args.batch_id or retention['state']!='AUDIT_RETAINED_BACKED_UP_PENDING_CUTOVER':
        raise ValueError('verified audit backup required')
    backup=Path(retention['backup']).resolve(strict=True);backup.relative_to(root)
    database=root/'markets/releases/market-history-v1.sqlite'
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with closing(open_market_database(database)) as db:
            digest=verify_market_batch_backup(db,backup,batch_id=args.batch_id)
            if digest!=retention['backup_sha256']:raise ValueError('frozen backup hash mismatch')
        inventories=query_market_batch_source_inventories(database,batch_id=args.batch_id)
        if retention_path.read_bytes()!=retention_bytes:raise ValueError('audit receipt changed')
        code=implementation_closure(project,('src.market_sqlite_query','src.market_sqlite'))['files']
        code[str(Path(__file__).relative_to(project))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        proof=dict(state='SOURCE_INVENTORIES_BACKUP_VERIFIED_NOT_ACCEPTED',batch_id=args.batch_id,
            database=str(database),backup=str(backup),backup_sha256=digest,
            retention_receipt_sha256=hashlib.sha256(retention_bytes).hexdigest(),
            source_inventories=inventories,implementation_hashes=code)
        destination=audit/'source-inventories.json'
        if destination.exists() and json.loads(destination.read_text())!=proof:
            raise ValueError('frozen inventories already differ')
        _publish_json(destination,proof)
        print(json.dumps(dict(state=proof['state'],sources=len(inventories),path=str(destination))))
