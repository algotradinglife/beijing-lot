"""Observed settled SPF labels; pending/reference values are never settlements."""
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import json
import math

from . import parser, labels
from ..issue_schedule import fetch as fetch_module
from .parser import parse_page, source_url, expected_option, digest
from ..issue_schedule.fetch import fetch_issue_page


def fetch_issue_settlements(schedule, raw_dir, timeout=25, retries=2, pages=None):
    """Capture SPF page for one issue, retaining raw bytes before parsing.

    schedule rows bind issue_id, slot, fixture_key, provider_id_nowscore and
    handicap. Only an exact native ID/handicap match, explicit finished status,
    unique settled option and matching final score produces a settlement.
    label_available_at is observation time, never inferred kickoff/end time.
    Offline pages requires body bytes and its original observed_at timestamp.
    Returns settlements, diagnostics, and a durable receipt path.
    """
    if not isinstance(schedule, list) or not schedule:
        raise ValueError('schedule must contain at least one fixture')
    if not isinstance(raw_dir, str) or not raw_dir.strip():
        raise ValueError('raw_dir must be nonempty')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be positive and finite')
    if type(retries) is not int or retries < 0:
        raise ValueError('retries must be a nonnegative integer')
    issues = {r['issue_id'] for r in schedule}
    if len(issues) != 1:
        raise ValueError('schedule must contain exactly one issue')
    issue = next(iter(issues)); url = source_url(issue, 5)
    slots = [r['slot'] for r in schedule]; keys = [r['fixture_key'] for r in schedule]
    if len(set(slots)) != len(slots) or len(set(keys)) != len(keys):
        raise ValueError('duplicate schedule slot or fixture_key')
    for row in schedule:
        if type(row['slot']) is not int or row['slot'] <= 0 or row['fixture_key'] != f"{issue}:{row['slot']}":
            raise ValueError('invalid fixture key/slot')
        if not isinstance(row['provider_id_nowscore'], str) or not row['provider_id_nowscore'].isdigit():
            raise ValueError('missing native identity')
        if isinstance(row['handicap'], bool) or not isinstance(row['handicap'], (int, float)) or not math.isfinite(row['handicap']) or int(row['handicap']) != row['handicap']:
            raise ValueError('invalid handicap')
    if pages is None:
        response = fetch_issue_page(url, timeout=timeout, retries=retries)
        body, observed = response.body, response.observed_at
    else:
        if not isinstance(pages, dict) or set(pages) != {'body', 'observed_at'}:
            raise ValueError('pages requires body and observed_at')
        body, observed = pages['body'], pages['observed_at']
        if isinstance(body, bytearray):
            body = bytes(body)
        if not isinstance(body, bytes):
            raise ValueError('body must be bytes')
    timestamp = datetime.fromisoformat(observed.replace('Z', '+00:00'))
    if timestamp.tzinfo is None:
        raise ValueError('observed_at must contain timezone')
    observed = timestamp.astimezone(ZoneInfo('Asia/Shanghai')).isoformat()
    folder = Path(raw_dir) / issue / uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    raw_path = folder / 'nowscore.raw.html'; raw_path.write_bytes(body)
    schedule_path = folder / 'schedule.json'
    schedule_path.write_text(json.dumps(schedule, ensure_ascii=False, sort_keys=True, allow_nan=False), encoding='utf8')
    implementation = {str(p.relative_to(Path(__file__).parents[1])): digest(p.read_bytes())
        for p in (Path(__file__), Path(parser.__file__), Path(labels.__file__), Path(fetch_module.__file__))}
    receipt = {'schedule_path': str(schedule_path), 'schedule_sha256': digest(schedule_path.read_bytes()),
               'implementation_sha256': implementation, 'parameters': {'timeout': timeout, 'retries': retries},
               'issue_id': issue, 'source_url': url, 'observed_at': observed,
               'sha256': digest(body), 'raw_path': str(raw_path), 'evidence_class': 'observed_availability'}
    receipt_path = folder / 'receipt.json'
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf8')
    parsed = parse_page(body, issue, 5)
    by_slot = {r['slot']: r for r in parsed}
    if len(by_slot) != len(parsed):
        raise ValueError('duplicate source slots')
    settlements, diagnostics = [], []
    for fixture in schedule:
        row = by_slot.get(fixture['slot']); reason = None
        if row is None:
            reason = 'missing_source_fixture'
        elif row['native_match_id'] != fixture['provider_id_nowscore'] or row['handicap'] != fixture['handicap']:
            reason = 'identity_or_handicap_mismatch'
        elif row['status'] != '完场':
            reason = 'not_finished'
        elif row['can_sale'] != 'false' or row['parse_errors']:
            reason = 'invalid_source_contract'
        else:
            filled = [o for o in row['options'] if o['sp'] is not None]
            if len(filled) != 1:
                reason = 'settled_sp_not_unique'
            elif expected_option(row) != filled[0]['option']:
                reason = 'score_outcome_mismatch'
        if reason:
            diagnostics.append({'issue_id': issue, 'fixture_id': fixture['fixture_key'], 'reason': reason})
            continue
        settlements.append({'issue_id': issue, 'fixture_id': fixture['fixture_key'],
            'outcome': {'胜':'W', '平':'D', '负':'L'}[filled[0]['option']],
            'settled_sp': float(filled[0]['sp']), 'label_available_at': observed,
            'status': 'settled', 'source_url': url})
    result = {'settlements': settlements, 'diagnostics': diagnostics, 'receipt_path': str(receipt_path)}
    (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    return result
