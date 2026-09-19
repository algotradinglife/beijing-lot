"""Stage collector registry pointers; never deploy services or replace registry."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market_epoch_registry import prepare_market_epoch_registry, verify_market_epoch_output
from src.market_sqlite_batch import verified_market_json
from src.market_storage import _publish_json
from src.persistent_data_layout import check_layout

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'manifest-dir', 'output', 'epoch-sha256'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    root = Path(check_layout(args.contract)['data_root']).resolve(strict=True)
    manifests = Path(args.manifest_dir).resolve(strict=True)
    target = Path(args.output).resolve(strict=True)
    manifests.relative_to(root / 'markets/manifests')
    target.relative_to(root / 'markets/raw')
    registry_path = root / 'registry/markets-current.json'
    original = registry_path.read_bytes()
    registry = json.loads(original)
    epoch = verified_market_json(manifests / 'epoch-receipt.json', args.epoch_sha256)
    old = root / registry['capture_root']
    policy = verified_market_json(old / 'policy.json', epoch['prior_policy_sha256'])
    for filename, key in (('plan.json', 'plan_sha256'), ('existing-captures.json', 'index_sha256')):
        verified_market_json(manifests / filename, epoch[key])
    proposed = prepare_market_epoch_registry(registry, data_root=root, manifest_dir=manifests,
                                             output=target, epoch=epoch, prior_policy=policy)
    output_evidence = verify_market_epoch_output(root, target, epoch)
    if registry_path.read_bytes() != original:
        raise ValueError('registry changed during staging')
    staged = dict(state='EPOCH_REGISTRY_STAGED_NOT_DEPLOYED',
                  original_registry_sha256=hashlib.sha256(original).hexdigest(),
                  epoch_sha256=args.epoch_sha256, registry=proposed, output_evidence=output_evidence)
    destination = manifests / 'registry-staged.json'
    with (manifests / 'registry-staging.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if registry_path.read_bytes() != original:
            raise ValueError('registry changed before staging publication')
        if destination.exists() and json.loads(destination.read_text()) != staged:
            raise ValueError('different staged registry already exists')
        _publish_json(destination, staged)
    print(json.dumps(dict(state=staged['state'], path=str(destination))))
