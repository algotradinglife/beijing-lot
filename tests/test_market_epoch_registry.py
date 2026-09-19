from copy import deepcopy
import pytest
from src.market_epoch_registry import prepare_market_epoch_registry


def test_epoch_registry_preserves_publication_and_inputs():
    registry = dict(capture_root='markets/raw/old', ledger='runtime/state/ledger.sqlite',
                    current_release={'path': 'markets/releases/current.json'})
    policy = dict(budget_id='original', request_budget=99, min_interval_seconds=2,
                  ledger_path='/data/runtime/state/ledger.sqlite')
    epoch = dict(policy, prior_output='/data/markets/raw/old', sqlite_bound_references=4)
    before = deepcopy(registry)
    args = dict(data_root='/data', manifest_dir='/data/markets/manifests/new',
                output='/data/markets/raw/new', epoch=epoch, prior_policy=policy)
    result = prepare_market_epoch_registry(registry, **args)
    assert registry == before
    assert result['current_release'] == registry['current_release']
    assert result['ledger'] == registry['ledger']
    assert result['prior_capture_roots'] == ['markets/raw/old']
    assert result['index'] == 'markets/manifests/new/existing-captures.json'
    for key in policy:
        changed = dict(epoch, **{key: 'changed'})
        with pytest.raises(ValueError, match='policy changed'):
            prepare_market_epoch_registry(registry, **dict(args, epoch=changed))
    for patch in [dict(output='/data/markets/raw/../other'),
                  dict(manifest_dir='/elsewhere'),
                  dict(epoch=dict(epoch, sqlite_bound_references=0)),
                  dict(epoch=dict(epoch, prior_output='/data/markets/raw/wrong'))]:
        with pytest.raises(ValueError):
            prepare_market_epoch_registry(registry, **dict(args, **patch))


def test_stage_entrypoint_is_repeatable_and_rejects_changed_inputs(tmp_path, monkeypatch):
    import hashlib
    import json
    import runpy
    import sys
    from pathlib import Path
    root = tmp_path
    old = root / 'markets/raw/old'
    target = root / 'markets/raw/new'
    manifests = root / 'markets/manifests/new'
    for directory in (old, target, manifests, root / 'registry'):
        directory.mkdir(parents=True, exist_ok=True)
    registry = dict(capture_root='markets/raw/old', ledger='runtime/state/ledger.sqlite')
    registry_path = root / 'registry/markets-current.json'
    registry_path.write_text(json.dumps(registry))
    original = registry_path.read_bytes()
    policy = dict(budget_id='original', request_budget=99, min_interval_seconds=2,
                  ledger_path=str(root / registry['ledger']))
    (old / 'policy.json').write_text(json.dumps(policy))
    (old / 'progress.json').write_text('{}')
    reservation = 'responses/euro-123/attempt-01.json'
    for directory in (old, target):
        (directory / reservation).parent.mkdir(parents=True)
    (old / reservation).write_text('{"status": 200}')
    (target / reservation).write_text(json.dumps(dict(status=200, prior_reservation_path=str(old / reservation))))
    for filename in ('plan.json', 'existing-captures.json'):
        (manifests / filename).write_text('{}')
    epoch = dict(policy, prior_output=str(old), sqlite_bound_references=2,
                 output=str(target), carried_files={reservation: hashlib.sha256((target / reservation).read_bytes()).hexdigest()},
                 carried_first_attempts=1, prior_progress_sha256=hashlib.sha256(b'{}').hexdigest(),
                 prior_policy_sha256=hashlib.sha256((old / 'policy.json').read_bytes()).hexdigest(),
                 plan_sha256=hashlib.sha256(b'{}').hexdigest(),
                 index_sha256=hashlib.sha256(b'{}').hexdigest())
    epoch_path = manifests / 'epoch-receipt.json'
    epoch_path.write_text(json.dumps(epoch))
    script = Path(__file__).resolve().parents[1] / 'scripts/stage_market_epoch_registry.py'
    monkeypatch.setattr('src.persistent_data_layout.check_layout', lambda _: {'data_root': str(root)})
    monkeypatch.setattr(sys, 'argv', [str(script), '--contract', 'test', '--manifest-dir', str(manifests),
                       '--output', str(target), '--epoch-sha256', hashlib.sha256(epoch_path.read_bytes()).hexdigest()])
    runpy.run_path(str(script), run_name='__main__')
    staged = (manifests / 'registry-staged.json').read_bytes()
    runpy.run_path(str(script), run_name='__main__')
    assert (manifests / 'registry-staged.json').read_bytes() == staged
    assert registry_path.read_bytes() == original
    from src.market_epoch_registry import verify_market_epoch_output
    import fcntl
    with (manifests / 'registry-staging.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            runpy.run_path(str(script), run_name='__main__')
    (target / reservation).write_text('{}')
    with pytest.raises(ValueError, match='reservation mismatch'):
        verify_market_epoch_output(root, target, epoch)
    (target / reservation).unlink()
    with pytest.raises(ValueError, match='count mismatch'):
        verify_market_epoch_output(root, target, epoch)
    other = 'responses/euro-456/attempt-01.json'
    for directory in (old, target):
        (directory / other).parent.mkdir(parents=True)
    (old / other).write_text('{"status": 200}')
    (target / other).write_text(json.dumps(dict(status=200, prior_reservation_path=str(old / other))))
    with pytest.raises(ValueError, match='identities mismatch'):
        verify_market_epoch_output(root, target, epoch)
    (manifests / 'plan.json').write_text('{"changed": true}')
    with pytest.raises(ValueError):
        runpy.run_path(str(script), run_name='__main__')
    assert registry_path.read_bytes() == original
    assert (manifests / 'registry-staged.json').read_bytes() == staged
