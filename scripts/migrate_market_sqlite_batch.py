"""Import and replay one frozen 50-issue batch; never delete raw files."""
import argparse
from collections import Counter
from contextlib import closing
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.market_sqlite import open_market_database, import_market_batch, backup_market_batch, canonical_market_record, verify_market_batch_backup
from src.market_sqlite_batch import verified_market_json, market_batch_records, load_market_issue_audits
from src.market_sqlite_query import verify_market_fixture_views
from src.market_storage import _publish_json
from src.temporal_learning.provenance import implementation_closure

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',required=True)
    p.add_argument('--batch',required=True,help='Plain batch identity; existing manifest resumes exact inputs')
    args=p.parse_args()
    if not args.batch or Path(args.batch).name!=args.batch or args.batch in ('.','..'):
        raise ValueError('unsafe batch identity')
    project=Path(__file__).resolve().parents[1]
    root=Path(args.data_root).resolve(strict=True)
    contract=json.loads((project/'config/persistent_data_layout.json').read_text())
    if root!=Path(contract['data_root']).resolve(strict=True):
        raise ValueError('data root differs from directory contract')
    subprocess.run([sys.executable,str(project/'scripts/check_persistent_data_layout.py'),
                    '--contract',str(project/'config/persistent_data_layout.json')],check=True)
    audit=root/'audits/market-sqlite'/args.batch
    database=root/'markets/releases/market-history-v1.sqlite'
    with (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with closing(open_market_database(database)) as connection:
            audit.mkdir(parents=True,exist_ok=True)
            manifest_path=audit/'manifest.json'
            closure=implementation_closure(project,('src.market_sqlite','src.market_sqlite_batch','src.market_sqlite_query'))['files']
            if manifest_path.exists():
                manifest=json.loads(manifest_path.read_text())
                if manifest['implementation_hashes']!=closure:
                    raise ValueError('frozen migration implementation changed')
            else:
                registry=json.loads((root/'registry/markets-current.json').read_text())
                published=registry['current_release']
                merged=verified_market_json(root/published['path'],published['sha256'])
                publication=json.loads((root/published['receipt']).read_text())
                if publication['status']!='ACCEPTED_DIAGNOSTIC_BATCH_PUBLISHED' or publication['merged_sha256']!=published['sha256']:
                    raise ValueError('accepted publication required')
                imported={row[0] for row in connection.execute('SELECT issue FROM batch_issue')}
                sources=sorted((s for s in merged['issue_sources'] if s['issue'] not in imported),key=lambda s:s['issue'])[:50]
                if len(sources)!=50 or len({s['issue'] for s in sources})!=50:
                    raise ValueError('fewer than 50 unique published issues available')
                archive_receipts=[dict(path=str(p.relative_to(root)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                                  for p in sorted([*(root/'markets/manifests').glob('*-archive.json'),
                                                  *(root/'fundamentals/manifests').glob('*-archive.json'),
                                                  *(root/name for name in registry['derived_archive_catalogs'])])]
                manifest=dict(batch_id=args.batch,issue_sources=sources,publication=published,archive_receipts=archive_receipts,
                              implementation_hashes=closure,historical_admission=False)
                _publish_json(manifest_path,manifest)
            for binding in manifest['archive_receipts']:
                verified_market_json(root/binding['path'],binding['sha256'])
            archive_receipts=[b['path'] for b in manifest['archive_receipts']]
            issues=[s['issue'] for s in manifest['issue_sources']]
            digest=hashlib.sha256(canonical_market_record(manifest).encode()).hexdigest()
            receipt=dict(input_sha256=digest,manifest=str(manifest_path),implementation_hashes=closure)
            print('IMPORTING '+issues[0]+'-'+issues[-1],flush=True)
            count=import_market_batch(connection,batch_id=args.batch,issues=issues,
                       records=market_batch_records(root,manifest['issue_sources'],archive_receipts=archive_receipts),receipt=receipt)
            print(f'IMPORTED {count}; replaying original source records',flush=True)
            replay=import_market_batch(connection,batch_id=args.batch,issues=issues,
                       records=market_batch_records(root,manifest['issue_sources'],archive_receipts=archive_receipts),receipt=receipt)
            if count!=replay or connection.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise ValueError('database validation failed')
            view_records=verify_market_fixture_views(database,batch_id=args.batch,
                issue_audits=load_market_issue_audits(root,manifest['issue_sources']))
            _publish_json(audit/'fixture-view-verification.json',dict(
                state='PUBLISHED_FIXTURE_VIEWS_EQUAL',batch_id=args.batch,
                manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                issues=view_records,implementation_hashes=closure,raw_files_deleted=0))
            backup=audit/'market-history-backup.sqlite'
            if backup.exists():
                backup_sha=verify_market_batch_backup(connection,backup,batch_id=args.batch,stage='import')
            else:
                backup_sha=backup_market_batch(connection,backup,batch_id=args.batch)
            counts=dict(connection.execute('SELECT kind,count(*) FROM market_record WHERE batch_id=? GROUP BY kind',(args.batch,)))
            _publish_json(audit/'import-receipt.json',dict(state='REPLAYED_BACKED_UP_PENDING_CUTOVER_REVIEW',
                batch_id=args.batch,issues=issues,counts=counts,manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                database=str(database),backup=str(backup),backup_sha256=backup_sha,
                raw_files_deleted=0,historical_admission=False))
            print(json.dumps(counts),flush=True)
