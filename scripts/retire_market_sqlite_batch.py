"""Verify a frozen final retirement bundle; --execute retires its exact files."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.persistent_data_layout import check_layout
from src.market_sqlite_batch import verified_market_json
from src.market_retirement_final import verify_final_retirement
from src.market_sqlite_retirement import execute_market_raw_retirement
from src.market_storage import _publish_json


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'bundle', 'bundle-sha256', 'review', 'review-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    root = Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    project = Path(__file__).resolve().parents[1]
    bundle_path = (root / args.bundle).resolve(strict=True)
    review_path = (root / args.review).resolve(strict=True)
    bundle_path.relative_to(root)
    review_path.relative_to(root)
    bundle = verified_market_json(bundle_path, args.bundle_sha256)
    review = verified_market_json(review_path, args.review_sha256)
    command_name = str(Path(__file__).resolve().relative_to(project))
    if review.get('command_hashes') != {command_name: hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}:
        raise ValueError('current retirement command review required')
    plan_path = (root / bundle['plan']['path']).resolve(strict=True)
    plan_path.relative_to(root)
    plan = verified_market_json(plan_path, bundle['plan']['sha256'])
    batch = plan['batch_id']
    if not batch or Path(batch).name != batch or batch in ('.', '..'):
        raise ValueError('unsafe retirement batch')
    audit = root / 'audits/market-sqlite' / batch
    audit.resolve(strict=True).relative_to(root / 'audits/market-sqlite')
    with ExitStack() as stack:
        cleaning = stack.enter_context((Path.home() / '.local/state/beijing-lot-market-cleaning/run.lock').open('a+b'))
        fcntl.flock(cleaning, fcntl.LOCK_EX | fcntl.LOCK_NB)
        registry = json.loads((root / 'registry/markets-current.json').read_text())
        for name in sorted(set([registry['capture_root'], *registry.get('prior_capture_roots', [])])):
            output = (root / name).resolve(strict=True)
            output.relative_to(root / 'markets/raw')
            worker = stack.enter_context((output / 'worker.lock').open('a+b'))
            fcntl.flock(worker, fcntl.LOCK_EX | fcntl.LOCK_NB)

        def verify(plan_to_check):
            """Run the reviewed gates while cleaning and collector locks remain held."""
            return verify_final_retirement(root, project, plan_to_check, bundle=bundle, review=review)

        if args.execute:
            result = execute_market_raw_retirement(root, plan, journal_path=audit / 'raw-retirement-journal.json',
                                                   verify_acceptance=verify)
        else:
            migration = stack.enter_context((root / 'runtime/state/market-sqlite-migration.lock').open('a+b'))
            fcntl.flock(migration, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = verify(plan)
        check_layout(args.contract)
        _publish_json(audit / ('raw-retirement-result.json' if args.execute else 'final-retirement-preflight.json'), result)
        print(json.dumps(result))
