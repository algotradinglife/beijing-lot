"""Fixed observed-history market collection, sequential groups of 100 issues.

Collection state is not data acceptance. Every fixture occurrence survives ID
deduplication. Missing upstream rosters pause, failed rosters remain explicit.
All paths and limits are caller supplied; importing has no side effects.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.fundamentals_bulk_capture import atomic_json, historical_pages, load_inventory
from src.fundamentals_census import read_response
from src.fundamentals_capture import TRANSIENT_STATUSES
from src.fundamentals_history_capture import capture_history_batch
from src.temporal_learning.provenance import implementation_closure


def market_key(url):
    """Return (market, native ID) only for the two fixed capture endpoints."""
    for market, pattern in (
        ('euro', r'https://1x2d\.titan007\.com/(\d+)\.js'),
        ('total', r'https://r\.jina\.ai/https://vip\.titan007\.com/OverDown_n\.aspx\?id=(\d+)&l=0')):
        match = re.fullmatch(pattern, url)
        if match:
            return market + ':' + match[1]
    return None


def market_document(key):
    """Map a validated market/native-ID key to one immutable transport document."""
    if not re.fullmatch(r'(euro|total):\d+', key):
        raise ValueError('invalid market key')
    market, pid = key.split(':')
    url = (f'https://1x2d.titan007.com/{pid}.js' if market == 'euro' else
           f'https://r.jina.ai/https://vip.titan007.com/OverDown_n.aspx?id={pid}&l=0')
    return {'source': 'independent', 'url': url, 'filename': pid + '.json'}


def verify_market_receipt(path, expected_key, expected_sha256):
    """Verify transport hash and URL; HTTP_OK never asserts valid market content."""
    path = Path(path)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError('market receipt hash mismatch')
    receipt = json.loads(content)
    if market_key(receipt.get('url', '')) != expected_key:
        raise ValueError('market receipt identity mismatch')
    if 'error' not in receipt:
        read_response(path)
    elif not receipt['error']:
        raise ValueError('empty transport error')
    return receipt


def index_market_captures(manifest_paths):
    """Verify saved market responses and select latest successful transport per ID.

    Older attempts remain in ``attempts``. No parsed identity acceptance is
    inferred and non-market documents are ignored. Missing/bad bytes are fatal.
    """
    result = {}
    for manifest_path in sorted(map(Path, manifest_paths)):
        manifest = json.loads(manifest_path.read_text())
        for document in manifest.get('documents', []):
            key = market_key(document.get('url', ''))
            if key is None:
                continue
            name = document['filename']
            if Path(name).name != name:
                raise ValueError('unsafe capture path')
            sha = manifest['file_hashes'][name]
            path = (manifest_path.parent / name).resolve()
            receipt = verify_market_receipt(path, key, sha)
            item = {'path': str(path), 'sha256': sha,
                    'state': document['state'], 'status': receipt.get('status'),
                    'received_at_utc': receipt['received_at_utc']}
            current = result.setdefault(key, {'attempts': []})
            current['attempts'].append(item)
            chosen = current.get('selected')
            if chosen is None or (item['status'] == 200, item['received_at_utc']) > (chosen['status'] == 200, chosen['received_at_utc']):
                current['selected'] = item
    return result


def issue_market_scope(entry, roster_root, cutoff):
    """Read the upstream roster receipt and preserve its exact slot inventory.

    None means upstream has not published a roster outcome. Invalid/failed
    upstream rosters return a terminal explicit error, never an empty success.
    """
    directory = Path(roster_root) / entry['issue']
    status = directory / 'status.json'
    if not status.exists():
        return None
    item = json.loads(status.read_text())
    path = item.get('roster_path')
    if not path:
        if item.get('processing_complete'):
            return {'issue': entry['issue'], 'state': 'ROSTER_UNAVAILABLE', 'error': item.get('roster_error'), 'fixtures': []}
        return None
    try:
        meta, raw = read_response(Path(path))
        if meta['url'] != entry['roster_url'] or meta['status'] != 200:
            raise ValueError('roster transport mismatch')
        fixtures, gaps, quarantined = historical_pages(
            raw, roster_url=entry['roster_url'], issue=entry['issue'], cutoff=cutoff,
            allow_repeated_provider_ids=True, allow_same_team_identity=True,
            quarantine_unavailable=True, include_quarantined=True)
    except (ValueError, TypeError) as exc:
        return {'issue': entry['issue'], 'state': 'ROSTER_INVALID', 'error': str(exc), 'fixtures': [], 'roster_path': path}
    return {'issue': entry['issue'], 'state': 'SCOPED', 'fixtures': fixtures, 'slot_gaps': gaps,
            'quarantined_slots': quarantined,
            'roster_path': path, 'roster_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def verify_reused_scope(scope, cache):
    """Verify every frozen roster and market response before reusing an issue."""
    if not isinstance(scope, dict) or scope.get('state') != 'SCOPED':
        raise ValueError('invalid reused market scope')
    roster_path = Path(scope.get('roster_path', ''))
    if not roster_path.is_file() or hashlib.sha256(roster_path.read_bytes()).hexdigest() != scope.get('roster_sha256'):
        raise ValueError('reused roster changed')
    fixtures = scope.get('fixtures')
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError('reused scope has no fixtures')
    rows = []
    for fixture in fixtures:
        provider_id = fixture.get('provider_id')
        if not isinstance(provider_id, str) or not re.fullmatch(r'\d+', provider_id):
            raise ValueError('invalid reused fixture identity')
        for market in ('euro', 'total'):
            key = market + ':' + provider_id
            selected = cache.get(key, {}).get('selected')
            if not selected:
                raise ValueError('reused market response missing: ' + key)
            verify_market_receipt(selected['path'], key, selected['sha256'])
            rows.append({'issue': scope['issue'], 'slot': fixture['slot'],
                         'provider_id': provider_id, 'market': market, **selected})
    return rows


def _capture_manifest_identity(path):
    """Return a stable identity for one immutable capture manifest."""
    path = Path(path).resolve()
    return f'{path}:{hashlib.sha256(path.read_bytes()).hexdigest()}'


def _capture_manifests(output):
    """Enumerate completed response manifests in chronological order."""
    paths = list((Path(output) / 'responses').glob('*/attempt-*/capture-manifest.json'))
    def received_at(path):
        indexed = index_market_captures([path])
        return next(iter(indexed.values()))['selected']['received_at_utc']
    return sorted(paths, key=received_at)


def _reconcile_uncheckpointed_attempts(state, output):
    """Account exactly once for manifests committed before a progress checkpoint."""
    manifests = _capture_manifests(output)
    accounted = state.get('accounted_manifests')
    if accounted is None:
        # Runs created before this receipt ledger already counted their files.
        state['accounted_manifests'] = [_capture_manifest_identity(path) for path in manifests]
        return
    accounted = set(accounted)
    for path in manifests:
        identity = _capture_manifest_identity(path)
        if identity in accounted:
            continue
        indexed = index_market_captures([path])
        chosen = next(iter(indexed.values()))['selected']
        state['new_responses'] = state.get('new_responses', 0) + 1
        state['blocked_streak'] = (state.get('blocked_streak', 0) + 1
                                   if chosen['status'] in (403, 429) else 0)
        accounted.add(identity)
    state['accounted_manifests'] = sorted(accounted)


def plan_market_history(manifest_path, roster_root, existing_index):
    """Freeze observed issue order; defer already attempted pairs without refetch.

    Groups contain at most 100 not-yet-covered issues, with a separate preserved
    reused list. Missing future upstream rosters stay in the remaining groups.
    """
    inventory, cutoff, sha = load_inventory(manifest_path)
    pending, reused = [], []
    for entry in inventory['issues']:
        # Upstream inventory is only a cheap candidate filter. Actual reuse is
        # admitted below by reparsing its raw roster; pending issues are parsed
        # just before collection instead of spending hours parsing twice.
        status_path = Path(roster_root) / entry['issue'] / 'status.json'
        upstream = json.loads(status_path.read_text()) if status_path.exists() else {}
        candidate_keys = {market + ':' + f['provider_id'] for f in upstream.get('inventory', [])
                          for market in ('euro', 'total')}
        scope = (issue_market_scope(entry, roster_root, cutoff)
                 if not candidate_keys or candidate_keys <= existing_index.keys() else None)
        keys = {market + ':' + f['provider_id'] for f in scope['fixtures'] for market in ('euro', 'total')} if scope else set()
        if keys and keys <= existing_index.keys():
            reused.append(scope)
        else:
            pending.append(entry)
    return {'schema': 'bj411_market_history_plan_v1', 'inventory_path': str(Path(manifest_path).resolve()),
            'inventory_sha256': sha, 'historical_before': inventory['historical_before'],
            'completeness': inventory['completeness'], 'observed_issues': len(inventory['issues']),
            'roster_root': str(Path(roster_root).resolve()), 'reused_issues': reused,
            'batches': [pending[i:i + 100] for i in range(0, len(pending), 100)]}


def run_market_history(plan_path, index_path, output_dir, *, ledger_path, budget_id,
                       request_budget, min_free_bytes, min_interval_seconds=5.0, fetch=None, sleeper=time.sleep,
                       disk_free=None, wall_clock=None):
    """Run fixed issue batches with shared ledger, two bounded attempts and resume.

    Status/attempt checkpoints are atomic; raw output is immutable. Return on
    disk/budget/circuit pause; wait for live upstream or shared-lock availability.
    No subprocess or daemon is created by this function. Caller owns lifecycle.
    """
    if type(min_interval_seconds) not in (int, float) or not math.isfinite(min_interval_seconds) or min_interval_seconds < 1:
        raise ValueError("invalid minimum interval")
    if type(min_free_bytes) is not int or min_free_bytes < 0:
        raise ValueError('invalid disk floor')
    plan_bytes, index_bytes = Path(plan_path).read_bytes(), Path(index_path).read_bytes()
    plan, cache = json.loads(plan_bytes), json.loads(index_bytes)
    inventory, cutoff, digest = load_inventory(plan['inventory_path'])
    if digest != plan['inventory_sha256']:
        raise ValueError('inventory changed')
    entries = [entry for batch in plan['batches'] for entry in batch]
    issue_ids = [entry['issue'] for entry in entries] + [entry['issue'] for entry in plan['reused_issues']]
    if len(issue_ids) != len(set(issue_ids)) or set(issue_ids) != {entry['issue'] for entry in inventory['issues']}:
        raise ValueError('plan does not partition inventory')
    if any(not 0 < len(batch) <= 100 for batch in plan['batches']):
        raise ValueError('invalid issue batch size')
    native = {entry['issue']: entry for entry in inventory['issues']}
    if any(entry != native[entry['issue']] for entry in entries):
        raise ValueError('plan issue URL changed')
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    policy = {'plan_sha256': hashlib.sha256(plan_bytes).hexdigest(), 'index_sha256': hashlib.sha256(index_bytes).hexdigest(),
              'ledger_path': str(Path(ledger_path).resolve()), 'budget_id': budget_id,
              'request_budget': request_budget, 'min_free_bytes': min_free_bytes,
              'min_interval_seconds': min_interval_seconds,
              'implementation_hashes': implementation_closure(Path(__file__).resolve().parents[1],
                  ('src.fundamentals_market_history', 'src.fundamentals_history_capture'))['files']}
    with (output / 'worker.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        policy_path = output / 'policy.json'
        if policy_path.exists() and json.loads(policy_path.read_text()) != policy:
            raise ValueError('immutable run policy changed')
        if not policy_path.exists():
            atomic_json(policy_path, policy)
        progress_path = output / 'progress.json'
        state = json.loads(progress_path.read_text()) if progress_path.exists() else {
            'schema': 'bj411_market_history_progress_v1', 'completed_batches': [], 'completed_issues': 0,
            'new_responses': 0, 'blocked_streak': 0, 'accounted_manifests': []}
        _reconcile_uncheckpointed_attempts(state, output)
        state.update(state='RUNNING', pid=os.getpid(), updated_at_utc=datetime.now(timezone.utc).isoformat())
        atomic_json(progress_path, state)
        if state['blocked_streak'] >= 3:
            state['state'] = 'CIRCUIT_OPEN'
            atomic_json(progress_path, state)
            return state
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'identity', 'X-Return-Format': 'html'})
        try:
            reused_dir = output / 'reused-issues'
            for reused_scope in plan['reused_issues']:
                rows = verify_reused_scope(reused_scope, cache)
                receipt = {'issue': reused_scope['issue'], 'state': 'CAPTURE_ATTEMPTED', 'rows': rows,
                           'scope_sha256': reused_scope['roster_sha256'],
                           'acceptance': 'NOT_REVIEWED', 'provenance': 'REUSED_VERIFIED'}
                atomic_json(reused_dir / (reused_scope['issue'] + '-receipt.json'), receipt)
            for batch_no, entries in enumerate(plan['batches'], 1):
                batch_dir = output / f'batch-{batch_no:04d}'
                batch_dir.mkdir(exist_ok=True)
                state['active_batch'] = batch_no
                results = []
                for entry in entries:
                    issue = entry['issue']
                    state.update(active_issue=issue, state='RUNNING')
                    scope_path = batch_dir / (issue + '-scope.json')
                    scope = json.loads(scope_path.read_text()) if scope_path.exists() else issue_market_scope(entry, plan['roster_root'], cutoff)
                    if scope_path.exists() and scope.get('roster_sha256') and hashlib.sha256(Path(scope['roster_path']).read_bytes()).hexdigest() != scope['roster_sha256']:
                        raise ValueError('frozen roster changed')
                    while scope is None:
                        state.update(state='WAITING_UPSTREAM_ROSTER', updated_at_utc=datetime.now(timezone.utc).isoformat())
                        atomic_json(progress_path, state)
                        sleeper(60)
                        scope = issue_market_scope(entry, plan['roster_root'], cutoff)
                    if not scope_path.exists():
                        atomic_json(scope_path, scope)
                    rows = []
                    for fixture in scope['fixtures']:
                        for market in ('euro', 'total'):
                            key = market + ':' + fixture['provider_id']
                            state.update(state='RUNNING', active_key=key)
                            document = market_document(key)
                            key_dir = output / 'responses' / key.replace(':', '-')
                            for attempt in range(1, 3):
                                if key in cache:
                                    break
                                directory = key_dir / f'attempt-{attempt:02d}'
                                manifest = directory / 'capture-manifest.json'
                                newly_captured = False
                                reservation = key_dir / f'attempt-{attempt:02d}.json'
                                if reservation.exists() and not manifest.exists():
                                    interrupted = {'path': str(reservation), 'sha256': hashlib.sha256(reservation.read_bytes()).hexdigest(),
                                                   'state': 'INTERRUPTED', 'status': None, 'received_at_utc': json.loads(reservation.read_text())['received_at_utc']}
                                    if attempt == 2:
                                        cache[key] = {'attempts': [interrupted], 'selected': interrupted}
                                    continue
                                if not manifest.exists():
                                    if (disk_free(output) if disk_free else shutil.disk_usage(output).free) < min_free_bytes:
                                        state['state'] = 'DISK_SPACE_LOW'
                                        atomic_json(progress_path, state)
                                        return state
                                    while True:
                                        try:
                                            # Preserve an interrupted attempt without granting a hidden retry.
                                            atomic_json(reservation, {'url': document['url'], 'error': 'INTERRUPTED_OR_RESERVED',
                                                'received_at_utc': datetime.now(timezone.utc).isoformat()})
                                            capture_history_batch([document], directory, ledger_path=ledger_path,
                                                budget_id=budget_id, request_budget=request_budget, min_interval_seconds=min_interval_seconds,
                                                wall_clock=wall_clock, sleeper=sleeper,
                                                fetch=fetch if fetch is not None else lambda url, **kw: session.get(url, allow_redirects=False, **kw))
                                            state['new_responses'] += 1
                                            newly_captured = True
                                            state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
                                            break
                                        except BlockingIOError:
                                            reservation.unlink()  # The shared lock rejected before budget/network I/O.
                                            state['state'] = 'WAITING_SHARED_LEDGER'
                                            atomic_json(progress_path, state)
                                            sleeper(5)
                                        except ValueError as exc:
                                            if 'budget exhausted' not in str(exc):
                                                raise
                                            reservation.unlink()  # No reservation was available in the ledger.
                                            state['state'] = 'BUDGET_EXHAUSTED'
                                            atomic_json(progress_path, state)
                                            return state
                                indexed = index_market_captures([manifest])[key]
                                chosen = indexed['selected']
                                if newly_captured:
                                    state['blocked_streak'] = state['blocked_streak'] + 1 if chosen['status'] in (403, 429) else 0
                                    state.setdefault('accounted_manifests', []).append(_capture_manifest_identity(manifest))
                                atomic_json(progress_path, state)
                                if state['blocked_streak'] >= 3:
                                    state['state'] = 'CIRCUIT_OPEN'
                                    atomic_json(progress_path, state)
                                    return state
                                if (chosen['status'] not in TRANSIENT_STATUSES and chosen['state'] != 'TRANSPORT_FAILURE') or attempt == 2:
                                    cache[key] = indexed
                            selected = cache[key]['selected']
                            verify_market_receipt(selected['path'], key, selected['sha256'])
                            rows.append({'issue': issue, 'slot': fixture['slot'], 'provider_id': fixture['provider_id'], 'market': market, **selected})
                    receipt = {'issue': issue, 'state': 'CAPTURE_ATTEMPTED' if rows else scope['state'], 'rows': rows,
                               'scope_sha256': hashlib.sha256(scope_path.read_bytes()).hexdigest(), 'acceptance': 'NOT_REVIEWED'}
                    receipt_path = batch_dir / (issue + '-receipt.json')
                    atomic_json(receipt_path, receipt)
                    results.append({'issue': issue, 'state': receipt['state'], 'responses': len(rows),
                                    'receipt_path': str(receipt_path), 'receipt_sha256': hashlib.sha256(receipt_path.read_bytes()).hexdigest()})
                    state.update(completed_issues=sum(len(x) for x in plan['batches'][:batch_no - 1]) + len(results), updated_at_utc=datetime.now(timezone.utc).isoformat())
                    atomic_json(progress_path, state)
                batch_receipt = {'issues': results, 'policy': policy, 'acceptance': 'NOT_REVIEWED'}
                batch_receipt_path = batch_dir / 'receipt.json'
                if batch_receipt_path.exists():
                    previous = json.loads(batch_receipt_path.read_text())
                    previous.pop('generated_at_utc')
                    if previous != batch_receipt:
                        raise ValueError('published batch receipt changed')
                else:
                    atomic_json(batch_receipt_path, {**batch_receipt,
                        'generated_at_utc': datetime.now(timezone.utc).isoformat()})
                if batch_no not in state['completed_batches']:
                    state['completed_batches'].append(batch_no)
                atomic_json(progress_path, state)
            state.update(state='OBSERVED_INVENTORY_ATTEMPTED', updated_at_utc=datetime.now(timezone.utc).isoformat())
            atomic_json(progress_path, state)
            return state
        except Exception as exc:
            state.update(state='FAILED', error=f'{type(exc).__name__}: {exc}',
                         updated_at_utc=datetime.now(timezone.utc).isoformat())
            atomic_json(progress_path, state)
            raise
        finally:
            session.close()
