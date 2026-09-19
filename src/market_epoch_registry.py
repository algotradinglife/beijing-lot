"""Prepare registry changes for a verified collector epoch without writing files."""
from copy import deepcopy
from pathlib import Path


def prepare_market_epoch_registry(registry, *, data_root, manifest_dir, output,
                                  epoch, prior_policy):
    """Return updated pointers, preserving publication, ledger and request policy.

    Caller verifies input hashes, stopped service and worker locks before atomic
    publication. Paths must be explicit persistent paths. No IO, writes, service
    startup or deletion occurs here. Invalid scope/policy raises ValueError.
    """
    root = Path(data_root)
    manifests, target = Path(manifest_dir), Path(output)
    if not root.is_absolute() or '..' in root.parts:
        raise ValueError('absolute data root required')
    for path, domain in ((manifests, 'markets/manifests'), (target, 'markets/raw')):
        if '..' in path.parts or path == root / domain or not path.is_relative_to(root / domain):
            raise ValueError('epoch path outside persistent domain')
    prior = root / registry['capture_root']
    if (Path(epoch['prior_output']) != prior or target.is_relative_to(prior)
            or prior.is_relative_to(target)):
        raise ValueError('epoch prior output mismatch')
    for key in ('budget_id', 'request_budget', 'min_interval_seconds', 'ledger_path'):
        if epoch[key] != prior_policy[key]:
            raise ValueError('request policy changed: ' + key)
    if Path(epoch['ledger_path']) != root / registry['ledger']:
        raise ValueError('registered ledger mismatch')
    if epoch.get('sqlite_bound_references', 0) <= 0:
        raise ValueError('SQLite bindings required')
    result = deepcopy(registry)
    prior_roots = result.setdefault('prior_capture_roots', [])
    if registry['capture_root'] not in prior_roots:
        prior_roots.append(registry['capture_root'])
    result.update(capture_root=str(target.relative_to(root)),
                  plan=str((manifests / 'plan.json').relative_to(root)),
                  index=str((manifests / 'existing-captures.json').relative_to(root)))
    return result


def verify_market_epoch_output(data_root, output, epoch):
    """Verify a fresh output's exact carried reservations against their sources.

    Returns a hash-bound output inventory. Reads files only. Rejects extra files,
    symlinks, modified reservations, wrong counts and changed prior progress.
    This is required before staging; activation must revalidate this inventory.
    """
    import hashlib
    import json
    root = Path(data_root).resolve(strict=True)
    target = Path(output).resolve(strict=True)
    prior = Path(epoch['prior_output']).resolve(strict=True)
    raw = root / 'markets/raw'
    if epoch.get('output') != str(target) or not isinstance(epoch.get('carried_files'), dict):
        raise ValueError('epoch output inventory binding missing')
    if (target == raw or prior == raw or not target.is_relative_to(raw)
            or not prior.is_relative_to(raw) or target.is_relative_to(prior)
            or prior.is_relative_to(target)):
        raise ValueError('invalid epoch output scope')
    progress = (prior / 'progress.json').read_bytes()
    if hashlib.sha256(progress).hexdigest() != epoch['prior_progress_sha256']:
        raise ValueError('prior progress changed')
    inventory = {}
    for path in target.rglob('*'):
        if path.is_symlink():
            raise ValueError('output symlink')
        if path.is_dir():
            continue
        relative = path.relative_to(target)
        if len(relative.parts) != 3 or relative.parts[0] != 'responses' or relative.name != 'attempt-01.json':
            raise ValueError('unexpected epoch output file')
        content = path.read_bytes()
        receipt = json.loads(content)
        source = prior / relative
        if source.is_symlink() or source.resolve() != source:
            raise ValueError('reservation source symlink')
        original = source.read_bytes()
        expected = dict(json.loads(original), prior_reservation_path=str(source))
        if receipt != expected:
            raise ValueError('carried reservation mismatch')
        inventory[str(relative)] = dict(sha256=hashlib.sha256(content).hexdigest(),
                                       source=str(source), source_sha256=hashlib.sha256(original).hexdigest())
    if len(inventory) != epoch['carried_first_attempts']:
        raise ValueError('carried reservation count mismatch')
    if {name: value['sha256'] for name, value in inventory.items()} != epoch['carried_files']:
        raise ValueError('carried reservation identities mismatch')
    return dict(output=str(target), prior_output=str(prior), files=inventory,
                prior_progress_sha256=epoch['prior_progress_sha256'])
