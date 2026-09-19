"""Explicit cooldown policy for the market capture supervisor; no import I/O."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import fcntl
import os
from pathlib import Path
import shutil
import time
import math

from src.fundamentals_bulk_capture import atomic_json
from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_history_capture import capture_history_batch
from src.fundamentals_market_history import index_market_captures, market_document, run_market_history
from src.fundamentals_titan_euro import parse_titan_euro
from src.fundamentals_titan_total import parse_titan_total_html
from src.persistent_data_layout import check_layout
from src.temporal_learning.provenance import implementation_closure


def recovery_deadline(attempt, now, *, retry_after=None, retry_after_date=None):
    """Return earliest UTC epoch seconds for one recovery probe.

    ``attempt`` is a zero-based consecutive recovery counter. ``now`` is UTC
    epoch seconds. Retry hints accept HTTP seconds/date or Jina's ISO date.
    Missing hints use 60, 300, 900 then 1800 seconds. Invalid hints fail closed.
    Upstream delays are never capped. Pure function; raises ValueError.
    """
    if type(attempt) is not int or attempt < 0:
        raise ValueError('invalid recovery attempt')
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('invalid current time')
    deadline = now + (60, 300, 900, 1800)[min(attempt, 3)]
    for hint in (retry_after, retry_after_date):
        if hint is None:
            continue
        if isinstance(hint, bool):
            raise ValueError('invalid retry hint')
        try:
            seconds = float(hint)
        except (TypeError, ValueError):
            try:
                value = datetime.fromisoformat(str(hint).replace('Z', '+00:00'))
            except ValueError:
                try:
                    value = parsedate_to_datetime(str(hint))
                except (TypeError, ValueError) as exc:
                    raise ValueError('invalid retry date') from exc
            if value.tzinfo is None:
                raise ValueError('retry date requires timezone')
            deadline = max(deadline, value.astimezone(timezone.utc).timestamp())
        else:
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError('invalid retry seconds')
            deadline = max(deadline, now + seconds)
    return deadline


def response_deadline(path, attempt, now):
    """Read a hashed raw receipt; honor HTTP and Jina retry hints, in seconds UTC."""
    meta, body = read_response(Path(path))
    hints = {}
    if meta.get('status') == 429:
        try:
            value = json.loads(body)
        except (ValueError, UnicodeError):
            value = None
        if isinstance(value, dict):
            hints = value
    return max(recovery_deadline(attempt, now, retry_after=meta.get('retry_after')),
               recovery_deadline(attempt, now, retry_after=hints.get('retryAfter'),
                                 retry_after_date=hints.get('retryAfterDate')))


def valid_market_probe(path, key):
    """Require HTTP 200, expected native match ID and nonempty parsed quotes.

    Transport/hash errors raise; invalid/empty market pages return False.
    This is a health check, not historical data acceptance or independent evidence.
    """
    meta, body = read_response(Path(path))
    if meta['status'] != 200 or meta['url'] != market_document(key)['url']:
        return False
    try:
        parsed = (parse_titan_euro(decode_analysis_text(body)[0]) if key.startswith('euro:')
                  else parse_titan_total_html(body.decode('utf-8')))
    except (ValueError, UnicodeError, IndexError, KeyError):
        return False
    return parsed['provider_id'] == key.split(':')[1] and bool(
        parsed.get('quotes') if key.startswith('euro:') else parsed.get('overview'))


def circuit_evidence(output):
    """Verify the latest consecutive blocking triple in the committed journal.

    In-flight success may follow a trip. Only a triple of 429 responses is
    automatically recoverable. Each affected endpoint needs a probe. 403 stays manual.
    Returns key/response references and a content-bound circuit identity.
    """
    output = Path(output).resolve()
    progress = json.loads((output/'progress.json').read_text())
    identities = progress.get('circuit_events', [])
    if len(identities) < 3 or len(set(identities)) != len(identities):
        raise ValueError('no verified circuit trigger')
    responses = []
    for identity in identities:
        name, digest = identity.rsplit(':', 1)
        path = Path(name).resolve()
        if not path.is_relative_to(output/'responses'):
            raise ValueError('circuit evidence outside response directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('circuit manifest changed')
        items = index_market_captures([path])
        if len(items) != 1:
            raise ValueError('invalid circuit manifest')
        key, value = next(iter(items.items()))
        responses.append(dict(key=key, identity=identity, **value['selected']))
    if any(x['status'] != 429 for x in responses[:3]) or any(x['status'] == 403 for x in responses):
        raise ValueError('circuit requires manual investigation')
    keys = list({x['key'].split(':')[0]: x['key'] for x in responses if x['status'] == 429}.values())
    return dict(key=keys[0], keys=keys, responses=responses,
                identity=hashlib.sha256(json.dumps(responses, sort_keys=True).encode()).hexdigest())



def recover_market_step(output, *, now, ledger_path, budget_id, request_budget,
                        min_free_bytes, min_interval_seconds, fetch=None, wall_clock=None,
                        sleeper=time.sleep, disk_free=None):
    """Advance one durable recovery step under the worker lock; at most one GET.

    Returns COOLDOWN with ``next_probe_at`` epoch seconds, RESUMED, or
    MANUAL_REQUIRED. Caller must own supervisor.lock. Writes immutable probe
    directories and pre-recovery snapshots, plus atomic recovery/progress state.
    Probe reservations share the original ledger/cap/interval. Crash after an
    attempted probe never repeats that probe directory or resets its budget.
    Local integrity/configuration failures raise without clearing the circuit.
    """
    output = Path(output).resolve()
    with (output/'worker.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        progress_path = output/'progress.json'
        progress = json.loads(progress_path.read_text())
        policy = json.loads((output/'policy.json').read_text())
        expected = dict(ledger_path=str(Path(ledger_path).resolve()), budget_id=budget_id,
                        request_budget=request_budget, min_interval_seconds=min_interval_seconds,
                        min_free_bytes=min_free_bytes)
        if any(policy[k] != v for k, v in expected.items()):
            raise ValueError('recovery request policy changed')
        state_path = output/'recovery.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if (progress.get('recovery_identity') == state.get('identity') and state.get('state') == 'READY'
                and not progress.get('circuit_tripped')):
            state.update(state='RESUMED', updated_at=now)
            atomic_json(state_path, state)
            atomic_json(output/'recovery'/state['identity']/'receipt.json', state)
            return state
        if progress.get('state') != 'CIRCUIT_OPEN' or not progress.get('circuit_tripped'):
            raise ValueError('only a reconciled circuit can be recovered')
        evidence = circuit_evidence(output)
        if state.get('identity') != evidence['identity']:
            attempt = state.get('attempt', -1) + 1
            state = dict(schema='market_recovery_v1', identity=evidence['identity'],
                         key=evidence['key'], evidence=evidence, attempt=attempt,
                         pending_keys=evidence['keys'], successful_probes=[],
                         state='COOLDOWN', supervisor_pid=os.getpid(), updated_at=now,
                         next_probe_at=max(response_deadline(x['path'], attempt, now)
                                           if x['status'] is not None else recovery_deadline(attempt, now)
                                           for x in evidence['responses']), reason='HTTP_429_RATE_LIMIT')
            atomic_json(state_path, state)
        state['supervisor_pid'] = os.getpid()
        if state['state'] == 'MANUAL_REQUIRED':
            return state
        episode = output/'recovery'/state['identity']
        if state['state'] == 'COOLDOWN':
            if now < state['next_probe_at']:
                atomic_json(state_path, state)
                return state
            if (disk_free(output) if disk_free else shutil.disk_usage(output).free) < min_free_bytes:
                raise ValueError('recovery disk space low')
            state.update(state='PROBING', probe_dir=str(episode/f"probe-{state['attempt']:06d}-{state['key'].replace(':','-')}"), updated_at=now)
            atomic_json(state_path, state)
            # PROBING is durable before consuming a request; a crash is not a retry grant.
            try:
                capture_history_batch([market_document(state['key'])], state['probe_dir'],
                    ledger_path=ledger_path, budget_id=budget_id, request_budget=request_budget,
                    min_interval_seconds=min_interval_seconds, fetch=fetch,
                    wall_clock=wall_clock, sleeper=sleeper)
                if wall_clock is not None:
                    now = wall_clock()
            except Exception as exc:
                state.update(state='MANUAL_REQUIRED', reason=f'PROBE_LOCAL_ERROR: {type(exc).__name__}: {exc}')
                atomic_json(state_path, state)
                raise
        if state['state'] == 'PROBING':
            manifest = Path(state['probe_dir'])/'capture-manifest.json'
            selected = index_market_captures([manifest])[state['key']]['selected'] if manifest.exists() else None
            if selected and selected['status'] == 200 and valid_market_probe(selected['path'], state['key']):
                state['successful_probes'].append(dict(key=state['key'], **selected))
                state['pending_keys'].remove(state['key'])
                if state['pending_keys']:
                    state.update(state='COOLDOWN', key=state['pending_keys'][0], next_probe_at=now, updated_at=now)
                    atomic_json(state_path, state)
                    return state
                state.update(state='READY', probe=selected, updated_at=now)
                atomic_json(state_path, state)
            else:
                state['attempt'] += 1
                state.update(pending_keys=evidence['keys'], successful_probes=[], key=evidence['keys'][0])
                state.update(state='COOLDOWN', updated_at=now,
                             reason='PROBE_FAILED_OR_INTERRUPTED',
                             next_probe_at=response_deadline(selected['path'], state['attempt'], now)
                             if selected and selected['status'] is not None else recovery_deadline(state['attempt'], now))
                if selected and selected['status'] not in (None, 200, 429, 500, 502, 503, 504):
                    state.update(state='MANUAL_REQUIRED', reason='PROBE_NONTRANSIENT_HTTP')
                atomic_json(state_path, state)
                return state
        if state['state'] != 'READY':
            raise ValueError('invalid recovery state')
        # Reverify probe on restart; only a content-valid receipt authorizes clear.
        from src.fundamentals_market_history import verify_market_receipt
        if sorted(x['key'] for x in state['successful_probes']) != sorted(evidence['keys']):
            raise ValueError('missing endpoint health probe')
        for selected in state['successful_probes']:
            verify_market_receipt(selected['path'], selected['key'], selected['sha256'])
            if not valid_market_probe(selected['path'], selected['key']):
                raise ValueError('recovery probe no longer valid')
        before = episode/'progress-before.json'
        if not before.exists():
            atomic_json(before, progress)
        elif json.loads(before.read_text()) != progress:
            raise ValueError('progress changed during recovery')
        state['progress_before_sha256'] = hashlib.sha256(before.read_bytes()).hexdigest()
        atomic_json(state_path, state)
        progress.update(state='RECOVERY_AUTHORIZED', circuit_tripped=False, blocked_streak=0,
                        blocked_events=[], circuit_events=[],
                        recovery_identity=state['identity'])
        atomic_json(progress_path, progress)
        state.update(state='RESUMED', updated_at=now)
        atomic_json(state_path, state)
        atomic_json(episode/'receipt.json', state)
        return state


def run_supervised_market_history(plan, index, output, *, contract, ledger_path,
                                  budget_id, request_budget, min_free_bytes,
                                  min_interval_seconds, workers, fetch=None,
                                  wall_clock=time.time, sleeper=time.sleep, disk_free=None):
    """Run capture and recovery in one process with exclusive supervisor ownership.

    Checks mounted storage before writes and each probe. Sleeps at most 30s per
    loop; cooldown persists across restart. Local failures propagate to the
    service and never clear a circuit. No retries of terminal disk/budget states.
    All request options are explicit and shared between collector and probe.
    """
    root = Path(check_layout(contract)['data_root']).resolve()
    if any(not Path(p).resolve().is_relative_to(root) for p in (plan, index, output, ledger_path)):
        raise ValueError('supervisor paths outside persistent root')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    options = dict(ledger_path=ledger_path, budget_id=budget_id, request_budget=request_budget,
                   min_free_bytes=min_free_bytes, min_interval_seconds=min_interval_seconds,
                   fetch=fetch, wall_clock=wall_clock, sleeper=sleeper, disk_free=disk_free)
    with (output/'supervisor.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        policy = dict(schema='market_supervisor_policy_v1',
                      plan_sha256=hashlib.sha256(Path(plan).read_bytes()).hexdigest(),
                      index_sha256=hashlib.sha256(Path(index).read_bytes()).hexdigest(),
                      contract_sha256=hashlib.sha256(Path(contract).read_bytes()).hexdigest(),
                      request_policy={k:options[k] for k in ('budget_id','request_budget','min_free_bytes','min_interval_seconds')},
                      ledger_path=str(Path(ledger_path).resolve()), workers=workers,
                      implementation_hashes=implementation_closure(Path(__file__).resolve().parents[1],
                          ('src.market_capture_recovery',))['files'])
        policy_path = output/'supervisor-policy.json'
        if policy_path.exists() and json.loads(policy_path.read_text()) != policy:
            raise ValueError('immutable supervisor policy changed')
        if not policy_path.exists():
            atomic_json(policy_path, policy)
        atomic_json(output/'supervisor.json', dict(pid=os.getpid(), started_at=wall_clock()))
        while True:
            progress_path = output/'progress.json'
            recovery_path = output/'recovery.json'
            if progress_path.exists() and recovery_path.exists():
                prior = json.loads(recovery_path.read_text())
                progress = json.loads(progress_path.read_text())
                if (prior.get('state') in ('READY', 'RESUMED') and not progress.get('circuit_tripped')
                        and prior.get('identity') == progress.get('recovery_identity')):
                    prior.update(state='RESUMED')
                    atomic_json(recovery_path, prior)
                    atomic_json(output/'recovery'/prior['identity']/'receipt.json', prior)
            result = run_market_history(plan, index, output, workers=workers, **options)
            if result['state'] != 'CIRCUIT_OPEN':
                return result
            while True:
                check_layout(contract)
                result = recover_market_step(output, now=wall_clock(), **options)
                if result['state'] == 'RESUMED':
                    break
                if result['state'] == 'MANUAL_REQUIRED':
                    return result
                sleeper(max(0, min(30, result['next_probe_at'] - wall_clock())))
