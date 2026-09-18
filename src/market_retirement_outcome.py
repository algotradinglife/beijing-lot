"""Read-only post-retirement verification; never authorizes or performs deletion."""
import hashlib
import json
from pathlib import Path

from src.market_sqlite_query import query_market_batch_source_inventories


def verify_market_retirement_outcome(data_root, *, plan, result, journal,
                                     database, batch_id, expected_inventories):
    """Verify exact removal membership and replay frozen SQLite source inventories.

    Inputs are previously hash-verified batch documents, not regenerated proofs.
    Caller holds the migration lock and binds these documents in its receipt.
    Raises on incomplete logs, remaining files (including dangling symlinks),
    unsafe paths, or changed/missing database source records. Returns counts and
    the plan digest. Does not establish earlier review, backup or cutover gates,
    measure reclaimed disk space, or write any files.
    """
    root = Path(data_root).resolve(strict=True)
    if plan.get('batch_id') != batch_id:
        raise ValueError('retirement batch mismatch')
    digest = hashlib.sha256(json.dumps(
        plan, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    names = [item['path'] for item in plan['candidates']]
    if len(set(names)) != len(names):
        raise ValueError('duplicate retirement candidate')
    if (result.get('state') != 'RAW_RETIREMENT_COMPLETE' or
            result.get('plan_sha256') != digest or journal.get('plan_sha256') != digest or
            type(result.get('removed_files')) is not int or result['removed_files'] != len(names) or
            journal.get('entries') != dict.fromkeys(names, 'REMOVED')):
        raise ValueError('incomplete retirement result or journal')
    for name in names:
        relative = Path(name)
        path = root / relative
        if (str(relative) != name or relative.is_absolute() or '..' in relative.parts or
                path.absolute() != path.resolve() or
                not path.is_relative_to(root / 'markets/raw') or path.suffix != '.json'):
            raise ValueError('unsafe retirement path')
        if path.exists() or path.is_symlink():
            raise ValueError('retired file still present: ' + name)
    actual = query_market_batch_source_inventories(database, batch_id=batch_id)
    if not expected_inventories or actual != expected_inventories:
        raise ValueError('post-retirement source inventory mismatch')
    return dict(state='RETIREMENT_FILES_AND_SQLITE_VERIFIED', batch_id=batch_id,
                plan_sha256=digest, removed_files=len(names), sources=len(actual))
