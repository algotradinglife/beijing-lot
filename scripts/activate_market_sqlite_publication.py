"""Activate a verified SQLite publication under cleaning and migration locks."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_batch import verified_market_json
from src.market_sqlite_publication import market_sqlite_release_reference,verify_market_publication_activation
from src.n7_published_markets import read_n7_published_markets
from src.market_storage import _publish_json

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('contract','acceptance','acceptance-sha256','cleaning-lock'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    root=Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    acceptance_path=(root/args.acceptance).resolve(strict=True);acceptance_path.relative_to(root)
    accepted=verified_market_json(acceptance_path,args.acceptance_sha256)
    staging_ref=accepted['evidence']['publication']
    staging_path=(root/staging_ref['path']).resolve(strict=True);staging_path.relative_to(root)
    staged=verified_market_json(staging_path,staging_ref['sha256'])
    staged_publication=Path(staged['publication']).resolve(strict=True);staged_publication.relative_to(root)
    batch=accepted['batch_id']
    if Path(batch).name!=batch or batch in ('.','..'):raise ValueError('unsafe batch identity')
    publication=root/'markets/releases'/('market-sqlite-'+batch)/'merged.json'
    with Path(args.cleaning_lock).open('a+b') as cleaning, (root/'runtime/state/market-sqlite-migration.lock').open('a+b') as migration:
        fcntl.flock(cleaning,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fcntl.flock(migration,fcntl.LOCK_EX|fcntl.LOCK_NB)
        registry_path=root/'registry/markets-current.json';original=registry_path.read_bytes()
        registry=json.loads(original)
        receipt_path=publication.parent/'receipt.json'
        if registry['current_release']['path']==str(publication.relative_to(root)):
            verify_market_publication_activation(registry,json.loads(receipt_path.read_text()),staged_receipt=staged,
                acceptance_reference=dict(path=str(acceptance_path),sha256=args.acceptance_sha256),
                publication_path=str(publication.relative_to(root)),receipt_path=str(receipt_path.relative_to(root)))
            read_n7_published_markets(data_root=root,merged_path=str(publication.relative_to(root)),
                expected_sha256=staged['sha256'],issues=accepted['issues'])
            print(json.dumps(dict(state='PUBLICATION_SQLITE_ACTIVE',batch_id=batch,raw_files_deleted=0,resumed=True)))
            sys.exit(0)
        if hashlib.sha256(original).hexdigest()!=staged['original_registry_sha256']:
            raise ValueError('registry changed since staging; restage required')
        registry=json.loads(original)
        previous_path=(root/registry['current_release']['receipt']).resolve(strict=True);previous_path.relative_to(root)
        previous=json.loads(previous_path.read_text())
        read_n7_published_markets(data_root=root,merged_path=str(staged_publication.relative_to(root)),
            expected_sha256=staged['sha256'],issues=accepted['issues'])
        contents=verified_market_json(staged_publication,staged['sha256'])
        if publication.exists():
            verified_market_json(publication,staged['sha256'])
        else:
            _publish_json(publication,contents)
            verified_market_json(publication,staged['sha256'])
        result=market_sqlite_release_reference(registry,previous,staged_receipt=staged,acceptance=accepted,
            acceptance_reference=dict(path=str(acceptance_path),sha256=args.acceptance_sha256),
            publication_path=str(publication.relative_to(root)),receipt_path=str(receipt_path.relative_to(root)))
        if receipt_path.exists() and json.loads(receipt_path.read_text())!=result['receipt']:
            raise ValueError('activation receipt differs')
        _publish_json(receipt_path,result['receipt'])
        if registry_path.read_bytes()!=original:raise ValueError('registry changed before activation')
        _publish_json(registry_path,result['registry'])
        if json.loads(registry_path.read_text())!=result['registry']:raise ValueError('registry readback mismatch')
        print(json.dumps(dict(state='PUBLICATION_SQLITE_ACTIVE',batch_id=batch,raw_files_deleted=0)))
