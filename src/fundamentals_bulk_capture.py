"""Sequential resumable capture of an explicit native historical inventory.

No import I/O. Raw attempts are immutable; status is a replaceable progress view.
HTTP 200 denotes captured bytes, never accepted identity or historical facts.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
from functools import partial
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from src.fundamentals_capture import TRANSIENT_STATUSES
from src.fundamentals_census import read_response
from src.fundamentals_history_capture import capture_history_batch
from src.fundamentals_issue_pages import issue_analysis_pages


def native_page_fetch(url, *, timeout, stream, referer):
    """Fetch with the client headers verified by the prior 130511 capture.

    Explicit native roster Referer supplies navigation context; no cookies or
    authentication are injected. Requests preserves TLS verification; redirects
    remain disabled and response ownership passes to capture_documents.
    """
    return requests.get(url, timeout=timeout, stream=stream, allow_redirects=False,
        headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36',
                 'Referer': referer})


def atomic_json(path, value):
    """Replace a UTF-8 JSON progress file atomically; caller holds worker lock."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def load_inventory(path):
    """Validate fixed native TypeID=8 scope and timezone-aware historical bound."""
    content = Path(path).read_bytes()
    inventory = json.loads(content)
    if inventory.get('schema') != 'bj411_historical_inventory_v1':
        raise ValueError('invalid inventory schema')
    cutoff = datetime.fromisoformat(inventory['historical_before'].replace('Z', '+00:00'))
    if cutoff.utcoffset() is None or cutoff > datetime.now(timezone.utc):
        raise ValueError('historical_before must be an elapsed timezone-aware instant')
    issues = inventory.get('issues')
    if not isinstance(issues, list) or not issues:
        raise ValueError('nonempty issues required')
    seen = set()
    for row in issues:
        issue = row.get('issue')
        url = urlparse(row.get('roster_url', ''))
        query = parse_qs(url.query)
        if (not isinstance(issue, str) or not re.fullmatch(r'\d+', issue) or issue in seen
                or url.scheme != 'https' or url.netloc != 'cp.nowscore.com'
                or url.path != '/buy/DanChang.aspx' or url.fragment
                or query.get('issueNum') != [issue] or query.get('TypeID') != ['8']):
            raise ValueError('invalid or duplicate native issue URL')
        seen.add(issue)
    return inventory, cutoff, hashlib.sha256(content).hexdigest()


def historical_pages(raw, *, roster_url, issue, cutoff):
    """Extract all slots and reject a roster if any diagnostic kickoff is not past.

    Deadline plus next displayed clock is a conservative collection scope check,
    not proof of historical information availability. Slot gaps are reported.
    """
    pages = issue_analysis_pages(raw, roster_url=roster_url, issue=issue)
    for row in pages:
        match = re.fullmatch(r'截止时间[：:]\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', row['deadline_text'] or '')
        if match is None:
            raise ValueError('missing explicit deadline')
        deadline = datetime.strptime(match[1], '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('Asia/Shanghai'))
        clock = datetime.strptime(row['clock'], '%H:%M')
        kickoff = deadline.replace(hour=clock.hour, minute=clock.minute)
        if kickoff < deadline:
            kickoff += timedelta(days=1)
        if kickoff >= cutoff or deadline >= cutoff:
            raise ValueError('roster contains nonhistorical fixture')
    slots = {row['slot'] for row in pages}
    return pages, sorted(set(range(1, max(slots) + 1)) - slots)


def attempt_receipt(directory, document):
    """Verify immutable batch manifest/file hashes and expected response identity.

    Returns a validated HTTP receipt or recorded transport failure. Missing raw
    output after a reserved attempt is explicitly INTERRUPTED, never success.
    """
    directory = Path(directory)
    if not directory.exists():
        return {'state': 'INTERRUPTED', 'status': None}
    manifest = json.loads((directory / 'capture-manifest.json').read_text())
    if manifest.get('schema') != 'bj408_capture_batch_v1' or len(manifest['documents']) != 1:
        raise ValueError('invalid attempt manifest')
    row = manifest['documents'][0]
    if any(row[key] != document[key] for key in ('source', 'url', 'filename')):
        raise ValueError('attempt document identity mismatch')
    for name, digest in manifest['file_hashes'].items():
        if Path(name).name != name or hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise ValueError('attempt file hash mismatch')
    if document['filename'] not in manifest['file_hashes']:
        raise ValueError('missing response hash binding')
    path = directory / document['filename']
    receipt = json.loads(path.read_text())
    if receipt['url'] != document['url']:
        raise ValueError('receipt URL mismatch')
    if 'error' in receipt:
        start, end = [datetime.fromisoformat(receipt[key]) for key in ('started_at_utc', 'received_at_utc')]
        if start.utcoffset() is None or end.utcoffset() is None or end < start or not receipt['error']:
            raise ValueError('invalid transport receipt')
        return {'state': 'TRANSPORT_FAILURE', 'status': None, 'receipt_path': str(path.resolve()), 'error': receipt['error']}
    meta, _ = read_response(path)
    if meta['final_url'] != document['url']:
        raise ValueError('unexpected final URL')
    return {'state': 'CAPTURED' if meta['status'] == 200 else 'HTTP_FAILURE',
            'status': meta['status'], 'receipt_path': str(path.resolve())}


def save_progress(status_path, state, issue, item):
    """Checkpoint one active issue and a compact root index, avoiding raw fan-out.

    The root points to progress; offline consumers use published status.json.
    Circuit state travels with the issue checkpoint for crash recovery.
    """
    progress = Path(status_path).parent / issue / 'progress.json'
    atomic_json(progress, {'item': item, 'blocked_streak': state['blocked_streak']})
    state['issues'][issue] = {'progress_path': str(progress),
        'capture_complete': item['capture_complete'],
        'processing_complete': item.get('processing_complete', False)}
    atomic_json(status_path, state)


def run_historical_inventory(manifest_path, output_dir, *, ledger_path, budget_id,
                             request_budget, min_free_bytes=20 * 1024**3, fetch=None, wall_clock=None, sleeper=None):
    """Capture fixed issues sequentially; resume durable attempts without repeats.

    One worker lock spans the loop, plus existing shared ledger request locking.
    Each page has at most three attempts, only transport/transient failures retry.
    Three consecutive 403/429 responses trip a durable circuit breaker. Budget
    exhaustion is a normal stop. All arguments are explicit; no facts are edited.
    """
    if type(min_free_bytes) is not int or min_free_bytes < 0:
        raise ValueError('min_free_bytes must be a nonnegative integer')
    inventory, cutoff, digest = load_inventory(manifest_path)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'worker.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        status_path = output / 'status.json'
        state = json.loads(status_path.read_text()) if status_path.exists() else {
            'schema': 'bj411_bulk_capture_status_v1', 'inventory_sha256': digest,
            'budget_id': budget_id, 'request_budget': request_budget,
            'ledger_path': str(Path(ledger_path).resolve()), 'issues': {},
            'blocked_streak': 0, 'state': 'RUNNING'}
        for key, value in [('inventory_sha256', digest), ('budget_id', budget_id),
                           ('request_budget', request_budget), ('ledger_path', str(Path(ledger_path).resolve()))]:
            if state[key] != value:
                raise ValueError('immutable run policy mismatch: ' + key)
        # Restore the previously active checkpoint before replay can replace its
        # identity. A crash between checkpoint and root writes must not reopen
        # a circuit merely because an earlier completed issue is visited first.
        previous_active = state.get('active_issue')
        if previous_active is not None:
            if previous_active not in {entry['issue'] for entry in inventory['issues']}:
                raise ValueError('active issue outside inventory')
            previous_path = output / previous_active / 'progress.json'
            if previous_path.exists():
                previous_progress = json.loads(previous_path.read_text())
                if previous_progress['item']['issue'] != previous_active:
                    raise ValueError('active checkpoint identity mismatch')
                state['blocked_streak'] = previous_progress['blocked_streak']
        if state['state'] == 'CIRCUIT_OPEN' or state['blocked_streak'] >= 3:
            state['state'] = 'CIRCUIT_OPEN'
            atomic_json(status_path, state)
            return state
        state['state'] = 'RUNNING'
        atomic_json(status_path, state)
        for entry in inventory['issues']:
            issue = entry['issue']
            issue_dir = output / issue
            progress_path = issue_dir / 'progress.json'
            if progress_path.exists():
                progress = json.loads(progress_path.read_text())
                item = progress['item']
            else:
                item = {'issue': issue, 'page_states': {}, 'capture_complete': False}
            state['active_issue'] = issue
            documents = [('roster', {'source': 'nowscore', 'url': entry['roster_url'], 'filename': 'response.json'})]
            index = 0
            while index < len(documents):
                key, document = documents[index]
                page = item['page_states'].setdefault(key, {'url': document['url'], 'source': document['source'], 'provider_id': document.get('provider_id'), 'attempts': []})
                # Reconcile an attempt whose bytes committed just before interruption.
                if page['attempts']:
                    for previous in page['attempts'][:-1]:
                        attempt_receipt(previous['directory'], document)
                    last = page['attempts'][-1]
                    result = attempt_receipt(last['directory'], document)
                    if last.get('state') == 'RESERVED':
                        last.update(result)
                        state['blocked_streak'] = state['blocked_streak'] + 1 if result['status'] in (403, 429) else 0
                while not page['attempts'] or (len(page['attempts']) < 3 and
                        (page['attempts'][-1].get('status') in TRANSIENT_STATUSES or
                         page['attempts'][-1]['state'] in ('TRANSPORT_FAILURE', 'INTERRUPTED'))):
                    if shutil.disk_usage(output).free < min_free_bytes:
                        state['state'] = 'DISK_SPACE_LOW'
                        break
                    if state['blocked_streak'] >= 3:
                        state['state'] = 'CIRCUIT_OPEN'
                        break
                    attempt_dir = issue_dir / key / f'attempt-{len(page["attempts"]) + 1:02d}'
                    attempt = {'directory': str(attempt_dir), 'state': 'RESERVED', 'status': None}
                    page['attempts'].append(attempt)
                    save_progress(status_path, state, issue, item)
                    try:
                        capture_history_batch([document], attempt_dir, ledger_path=ledger_path,
                            budget_id=budget_id, request_budget=request_budget, min_interval_seconds=5,
                            fetch=fetch if fetch is not None else partial(native_page_fetch, referer=entry['roster_url']),
                            wall_clock=wall_clock, sleeper=sleeper)
                    except ValueError as exc:
                        if 'request budget exhausted' not in str(exc):
                            raise
                        page['attempts'].pop()  # No request reservation occurred.
                        state['state'] = 'BUDGET_EXHAUSTED'
                        break
                    attempt.update(attempt_receipt(attempt_dir, document))
                    state['blocked_streak'] = state['blocked_streak'] + 1 if attempt['status'] in (403, 429) else 0
                    if state['blocked_streak'] >= 3:
                        state['state'] = 'CIRCUIT_OPEN'
                    save_progress(status_path, state, issue, item)
                    if state['state'] != 'RUNNING':
                        break
                last = page['attempts'][-1] if page['attempts'] else {}
                page['state'] = last.get('state', 'NOT_REQUESTED')
                page['receipt_path'] = last.get('receipt_path')
                page['http_status'] = last.get('status')
                page['error'] = last.get('error')
                if state['state'] != 'RUNNING':
                    break
                if key == 'roster':
                    if page['state'] != 'CAPTURED':
                        item['roster_error'] = 'ROSTER_CAPTURE_FAILED'
                        break
                    item['roster_path'] = last['receipt_path']
                    _, raw = read_response(Path(item['roster_path']))
                    try:
                        pages, gaps = historical_pages(raw, roster_url=entry['roster_url'], issue=issue, cutoff=cutoff)
                    except (ValueError, TypeError) as exc:
                        item['roster_error'] = str(exc)
                        break
                    item.update(fixture_count=len(pages), slot_gaps=gaps, expected_pages=2 * len(pages), inventory=pages)
                    for row in pages:
                        for source, url_key in [('nowscore', 'nowscore_url'), ('titan', 'titan_candidate_url')]:
                            documents.append((f'{row["slot"]:03d}-{source}', {'source': source, 'url': row[url_key], 'filename': 'response.json', 'provider_id': row['provider_id']}))
                elif (page['state'] == 'CAPTURED' and document['source'] == 'nowscore'
                      and not key.endswith('-asset')):
                    _, html = read_response(Path(page['receipt_path']))
                    nodes = BeautifulSoup(html, 'html.parser').select('script[src*="/analysisJs/data"]')
                    if nodes:
                        asset_path = f"/analysisJs/data{document['provider_id']}.js"
                        if len(nodes) != 1 or nodes[0]['src'] != asset_path:
                            page['asset_error'] = 'unexpected auxiliary data identity'
                        else:
                            asset_key = key + '-asset'
                            item.setdefault('required_assets', {})[document['url']] = asset_key
                            documents.insert(index + 1, (asset_key, {
                                'source': 'nowscore', 'url': 'https://live.nowscore.com' + asset_path,
                                'filename': 'response.json', 'provider_id': document['provider_id']}))
                index += 1
            item['processing_complete'] = state['state'] == 'RUNNING'
            item['response_paths'] = [page['attempts'][-1]['receipt_path'] for key, page in item['page_states'].items()
                                      if key != 'roster' and not key.endswith('-asset') and page.get('state') == 'CAPTURED']
            item['asset_response_paths'] = {url: item['page_states'][key]['receipt_path']
                for url, key in item.get('required_assets', {}).items()
                if item['page_states'].get(key, {}).get('state') == 'CAPTURED'}
            item['capture_complete'] = (not item.get('roster_error') and
                len(item['response_paths']) == item.get('expected_pages', -1) and
                len(item['asset_response_paths']) == len(item.get('required_assets', {})) and
                not any(page.get('asset_error') for page in item['page_states'].values()))
            atomic_json(issue_dir / 'selected-assets.json', item['asset_response_paths'])
            atomic_json(issue_dir / 'selected-responses.json', item['response_paths'])
            atomic_json(issue_dir / 'status.json', item)
            save_progress(status_path, state, issue, item)
            if state['state'] != 'RUNNING':
                return state
        state['state'] = 'FINISHED'
        atomic_json(status_path, state)
        return state
