"""Revalidate stored content before raw retirement; no deletion or service writes."""
from contextlib import closing
from pathlib import Path
import sqlite3

from src.market_sqlite import verify_market_batch_backup
from src.market_sqlite_acceptance import prepare_market_storage_acceptance
from src.market_sqlite_batch import verified_market_json
from src.market_sqlite_query import query_market_records
from src.market_sqlite_retirement import verify_retirement_capture_bindings
from src.market_retirement_relocations import bind_relocated_capture_aliases


def verify_retirement_content(data_root, plan, *, acceptance_reference):
    """Recheck immutable content evidence, live records and independent backup.

    acceptance_reference is a path/SHA256 pair. Caller holds the migration lock
    and separately validates current consumers, reference exclusion and final
    review. Historical content review binds the accepted implementation; final
    retirement review must bind the current deletion implementation separately.
    Returns evidence only, never deletion permission. Missing, changed or foreign
    inputs raise; database connections are read-only and always closed.
    """
    root = Path(data_root).resolve(strict=True)
    path = (root / acceptance_reference['path']).resolve(strict=True)
    path.relative_to(root)
    accepted = verified_market_json(path, acceptance_reference['sha256'])
    if accepted.get('state') != 'SQLITE_BATCH_ACCEPTED' or accepted.get('batch_id') != plan.get('batch_id'):
        raise ValueError('accepted retirement batch required')
    rebuilt = prepare_market_storage_acceptance(
        root, evidence=accepted['evidence'], implementation_hashes=accepted['implementation_hashes'])
    if rebuilt != accepted:
        raise ValueError('content acceptance changed')
    reference = accepted['evidence']['inventory']
    inventory_path = (root / reference['path']).resolve(strict=True)
    inventory_path.relative_to(root)
    inventory = verified_market_json(inventory_path, reference['sha256'])
    database = Path(accepted['database']).resolve(strict=True)
    backup = Path(inventory['backup']).resolve(strict=True)
    database.relative_to(root)
    backup.relative_to(root)
    if database.samefile(backup):
        raise ValueError('independent backup required')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        backup_hash = verify_market_batch_backup(connection, backup, batch_id=accepted['batch_id'])
    if backup_hash != inventory['backup_sha256']:
        raise ValueError('backup hash changed')
    captures = []
    for issue in accepted['issues']:
        captures.extend(query_market_records(database, issue=issue, kind='capture'))
    if 'relocation' in plan:
        ref = plan['relocation']
        mapping_path = (root / ref['path']).resolve(strict=True)
        mapping_path.relative_to(root)
        mappings = verified_market_json(mapping_path, ref['sha256'])
        captures = bind_relocated_capture_aliases(
            captures, mappings, original_root=ref['original_root'], data_root=root)
    binding = verify_retirement_capture_bindings(root, plan, captures, batch_id=accepted['batch_id'])
    return dict(state='RETIREMENT_CONTENT_REVALIDATED', batch_id=accepted['batch_id'],
                acceptance=acceptance_reference, backup_sha256=backup_hash,
                candidate_bindings=binding, raw_deletion_authorized=False)
