"""Create new immutable capture inputs while preserving the prior raw epoch."""
import fcntl
import hashlib
import json
from pathlib import Path

from src.fundamentals_bulk_capture import atomic_json
from src.fundamentals_capture import TRANSIENT_STATUSES
from src.fundamentals_market_history import index_market_captures, plan_market_history, _reconcile_uncheckpointed_attempts


def prepare_market_epoch(plan_path, index_path, old_output, manifest_dir, new_output, *, storage_cutover=None):
    """Freeze a new epoch from a stopped worker; never move/delete old responses.

    Hash-check old policy inputs and raw responses. Reuse terminal outcomes;
    carry interrupted first attempts as reservation evidence so only attempt two
    remains available. Preserve original budget identity/cap/clock. Outputs are
    new explicit directories, rejected if already present. Raises on live lock,
    changed input bytes or invalid source receipts; no HTTP or SQLite writes.
    Optional storage_cutover supplies database, acceptance and verified captures
    for an accepted batch. Bindings are validated before publishing new inputs.
    """
    old, target, manifests = map(Path, (old_output, new_output, manifest_dir))
    if target.exists() or manifests.exists():
        raise FileExistsError('new epoch directories must not exist')
    with (old/'worker.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        progress = json.loads((old/'progress.json').read_text())
        _reconcile_uncheckpointed_attempts(progress, old)
        if progress.get('circuit_tripped') or progress.get('state') == 'CIRCUIT_OPEN' or progress.get('blocked_streak', 0) >= 3:
            raise ValueError('prior circuit remains open')
        policy_bytes = (old/'policy.json').read_bytes()
        policy = json.loads(policy_bytes)
        for path, name in [(plan_path, 'plan'), (index_path, 'index')]:
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != policy[name+'_sha256']:
                raise ValueError('prior input hash changed')
        prior = json.loads(Path(plan_path).read_text())
        index = json.loads(Path(index_path).read_text())
        captured = index_market_captures(list((old/'responses').glob('*/attempt-*/capture-manifest.json')))
        carry = []
        for directory in sorted((old/'responses').glob('*')):
            if not directory.is_dir():
                continue
            key = directory.name.replace('-', ':', 1)
            selected = captured.get(key, {}).get('selected')
            second = directory/'attempt-02.json'
            second_manifest = directory/'attempt-02/capture-manifest.json'
            if second.exists() and not second_manifest.exists():
                receipt = json.loads(second.read_text())
                captured[key] = dict(attempts=[], selected=dict(path=str(second.resolve()),
                    sha256=hashlib.sha256(second.read_bytes()).hexdigest(), state='INTERRUPTED',
                    status=None, received_at_utc=receipt['received_at_utc']))
            elif selected is not None and (second_manifest.exists() or
                    (selected['status'] not in TRANSIENT_STATUSES and selected['state'] != 'TRANSPORT_FAILURE')):
                pass
            else:
                captured.pop(key, None)
                first = directory/'attempt-01.json'
                if first.exists():
                    carry.append((directory.name, json.loads(first.read_text()), str(first.resolve())))
        overlap = set(index) & set(captured)
        if overlap:
            raise ValueError('prior indexed keys unexpectedly recaptured')
        index.update(captured)
        storage_changed=0
        if storage_cutover is not None:
            from src.market_sqlite_capture import bind_market_capture_index
            from src.market_sqlite_retirement import market_reference_paths
            bound=bind_market_capture_index(index,**storage_cutover)
            market_reference_paths([bound['index']],[])
            index=bound['index'];storage_changed=bound['changed_references']
        plan = plan_market_history(prior['inventory_path'], prior['roster_root'], index)
        plan['inherited_blocked_streak'] = progress.get('blocked_streak', 0)
        plan['inherited_request_policy'] = {name: policy[name] for name in
            ('ledger_path', 'budget_id', 'request_budget', 'min_interval_seconds')}
        target.mkdir(parents=True)
        manifests.mkdir(parents=True)
        carried_files = {}
        for name, receipt, source in carry:
            carried_path = target/'responses'/name/'attempt-01.json'
            atomic_json(carried_path,
                {**receipt, 'prior_reservation_path': source})
            carried_files[str(carried_path.relative_to(target))] = hashlib.sha256(carried_path.read_bytes()).hexdigest()
        atomic_json(manifests/'plan.json', plan)
        atomic_json(manifests/'existing-captures.json', index)
        receipt = dict(schema='market_capture_epoch_v1', prior_output=str(old.resolve()),
            output=str(target.resolve()), carried_files=carried_files,
            prior_policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
            prior_progress_sha256=hashlib.sha256((old/'progress.json').read_bytes()).hexdigest(),
            budget_id=policy['budget_id'], request_budget=policy['request_budget'],
            ledger_path=policy['ledger_path'], min_interval_seconds=policy['min_interval_seconds'],
            reused_issues=len(plan['reused_issues']), pending_issues=sum(map(len, plan['batches'])),
            carried_first_attempts=len(carry), indexed_keys=len(index),
            sqlite_bound_references=storage_changed,
            plan_sha256=hashlib.sha256((manifests/'plan.json').read_bytes()).hexdigest(),
            index_sha256=hashlib.sha256((manifests/'existing-captures.json').read_bytes()).hexdigest())
        atomic_json(manifests/'epoch-receipt.json', receipt)
        return receipt
