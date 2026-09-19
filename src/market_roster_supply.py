"""Supply only native fixture rosters for an explicit market plan; no analysis fetches."""
import fcntl
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from src.fundamentals_bulk_capture import atomic_json, historical_pages, attempt_receipt
from src.fundamentals_census import read_response
from src.fundamentals_history_capture import capture_history_batch
from src.fundamentals_market_history import issue_market_scope


def supply_rosters(plan_path, output, *, ledger_path, budget_id, request_budget,
                   min_interval_seconds=2, min_free_bytes=21474836480, fetch=None):
    """Run one resumable pass. Paths are explicit and must be storage-checked by caller.

    Preserve raw attempts, validate URL/status and parse before publishing status.
    Existing published statuses are never overwritten. At most three attempts per
    missing issue per pass; failed issues remain absent from the consumer status.
    Retry attempts use new immutable directories. HTTP 403/429 stops the pass.
    Return/write progress counts and failures; exceptions release the writer lock.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    plan_bytes = Path(plan_path).read_bytes()
    plan = json.loads(plan_bytes)
    cutoff = datetime.fromisoformat(plan['historical_before'])
    entries = [entry for batch in plan['batches'] for entry in batch]
    # Validate every identity before issuing a request or using it as a path.
    for entry in entries:
        issue = entry['issue']
        if not isinstance(issue, str) or not issue.isascii() or not issue.isdigit():
            raise ValueError('invalid issue identity')
        if entry['roster_url'] != f'https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=8&issueNum={issue}':
            raise ValueError('invalid roster URL')
    state = dict(plan_sha256=hashlib.sha256(plan_bytes).hexdigest(),
                 state='RUNNING', published=0, existing=0, failures={})
    destination = Path(plan['roster_root'])
    destination.mkdir(parents=True, exist_ok=True)
    with (destination/'supply.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for entry in entries:
            issue = entry['issue']
            target = Path(plan['roster_root'])/issue/'status.json'
            if target.exists():
                try:
                    prior = json.loads(target.read_text())
                    response_path = Path(prior['roster_path'])
                    meta, _ = read_response(response_path)
                    if meta['status'] != 200 or meta['url'] != entry['roster_url'] or meta['final_url'] != entry['roster_url']:
                        raise ValueError('existing roster transport mismatch')
                    if prior.get('roster_sha256') and hashlib.sha256(response_path.read_bytes()).hexdigest() != prior['roster_sha256']:
                        raise ValueError('existing roster hash mismatch')
                    scope = issue_market_scope(entry, destination, cutoff)
                    if not scope or scope['state'] != 'SCOPED' or not scope['fixtures']:
                        raise ValueError('existing roster rejected by current market plan')
                    state['existing'] += 1
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    state['failures'][issue] = 'EXISTING_ROSTER_UNUSABLE: ' + str(exc)
                continue
            state['active_issue'] = issue
            directory = output/issue
            attempts = sorted(directory.glob('attempt-*'))
            # Replay the last durable response before spending another request.
            candidates = [attempts[-1]] if attempts else []
            for attempt in range(4):
                replay = bool(candidates)
                if candidates:
                    raw_dir = candidates.pop()
                else:
                    if attempt == 3:
                        break
                    if shutil.disk_usage(output).free < min_free_bytes:
                        state['state'] = 'DISK_SPACE_LOW'
                        break
                    raw_dir = directory/f'attempt-{len(attempts)+1:06d}'
                    state.update(state='WAITING_SHARED_LEDGER', updated_at_utc=datetime.now(timezone.utc).isoformat())
                    atomic_json(output/'progress.json', state)
                    capture_history_batch([dict(source='nowscore', url=entry['roster_url'], filename='response.json')],
                        raw_dir, ledger_path=ledger_path, budget_id=budget_id,
                        request_budget=request_budget, min_interval_seconds=min_interval_seconds,
                        fetch=fetch, wait_for_lock=True)
                    state['state'] = 'RUNNING'
                    attempts.append(raw_dir)
                attempt_receipt(raw_dir, dict(source='nowscore', url=entry['roster_url'], filename='response.json'))
                try:
                    meta, raw = read_response(raw_dir/'response.json')
                    if meta['status'] in (403, 429) and replay:
                        continue
                    if meta['status'] in (403, 429):
                        state['state'] = 'RATE_LIMITED'
                        state['failures'][issue] = f"HTTP {meta['status']}"
                        break
                    if meta['status'] != 200 or meta['url'] != entry['roster_url']:
                        raise ValueError('roster transport mismatch')
                    rows, gaps, quarantined = historical_pages(raw, roster_url=entry['roster_url'], issue=issue,
                        cutoff=cutoff, allow_repeated_provider_ids=True, allow_same_team_identity=True,
                        quarantine_unavailable=True, include_quarantined=True)
                    if not rows:
                        raise ValueError('empty roster requires investigation')
                    receipt = dict(issue=issue, roster_path=str((raw_dir/'response.json').resolve()),
                        processing_complete=True, scope='MARKET_ROSTER_ONLY', fixture_count=len(rows),
                        slot_gaps=gaps, quarantined_slots=quarantined, historical_admission=False,
                        roster_sha256=hashlib.sha256((raw_dir/'response.json').read_bytes()).hexdigest())
                    atomic_json(target, receipt)
                    state['published'] += 1
                    state['failures'].pop(issue, None)
                    break
                except (ValueError, KeyError, TypeError, OSError) as exc:
                    state['failures'][issue] = str(exc)
            state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
            atomic_json(output/'progress.json', state)
            if state['state'] != 'RUNNING':
                return state
        state['updated_at_utc'] = datetime.now(timezone.utc).isoformat()
        state['state'] = 'NEEDS_RETRY' if state['failures'] else 'COMPLETE'
        atomic_json(output/'progress.json', state)
        return state
