"""Observed Beijing Single Match reference SP, never European or settlement odds."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import math
from .settlement import parser, labels
from .issue_schedule import fetch, store


def parse_prematch_sp(body, schedule, observed_at):
    """Return (quotes, diagnostics); W/D/L refer to Beijing handicap outcomes.

    Schedule supplies issue_id, slot, fixture_key, native identity, handicap and
    timezone-aware kickoff_at. Observation is the earliest evidenced availability,
    not a guessed source update time. Only complete live pre-kickoff vectors pass.
    No SP cap/transformation or probability calculation is applied here.
    """
    at = datetime.fromisoformat(observed_at.replace('Z', '+00:00'))
    if at.tzinfo is None:
        raise ValueError('observed_at requires timezone')
    if not schedule:
        raise ValueError('schedule must not be empty')
    issues = {r['issue_id'] for r in schedule}
    if len(issues) != 1:
        raise ValueError('schedule must contain one issue')
    issue = next(iter(issues))
    url = parser.source_url(issue, 5)
    slots = [r['slot'] for r in schedule]
    if len(set(slots)) != len(slots):
        raise ValueError('duplicate schedule slots')
    for r in schedule:
        if type(r['slot']) is not int or r['slot'] <= 0 or r['fixture_key'] != f"{issue}:{r['slot']}":
            raise ValueError('invalid slot or fixture key')
        if not isinstance(r['provider_id_nowscore'], str) or not r['provider_id_nowscore'].isdigit():
            raise ValueError('invalid native identity')
        if isinstance(r['handicap'], bool) or not isinstance(r['handicap'], (int,float)) or not math.isfinite(r['handicap']) or r['handicap'] != int(r['handicap']):
            raise ValueError('invalid handicap')
        if datetime.fromisoformat(r['kickoff_at']).tzinfo is None:
            raise ValueError('kickoff_at requires timezone')
    rows = parser.parse_page(bytes(body), issue, 5)
    by_slot = {r['slot']:r for r in rows}
    if len(by_slot) != len(rows):
        raise ValueError('duplicate source slots')
    quotes, diagnostics = [], []
    for fixture in schedule:
        r = by_slot.get(fixture['slot'])
        reason = None
        if r is None:
            reason = 'missing_source_fixture'
        elif r['native_match_id'] != fixture['provider_id_nowscore'] or r['handicap'] != fixture['handicap']:
            reason = 'identity_or_handicap_mismatch'
        elif at >= datetime.fromisoformat(fixture['kickoff_at']):
            reason = 'already_kicked_off'
        elif r['status'] not in ('', '未', '未开', '未开赛') or r['can_sale'].lower() != 'true':
            reason = 'not_live_prematch'
        elif r['parse_errors'] or len(r['options']) != 3 or {o['option'] for o in r['options']} != {'胜','平','负'}:
            reason = 'invalid_source_contract'
        elif any(o['sp'] is None for o in r['options']):
            reason = 'incomplete_sp_vector'
        if reason:
            diagnostics.append(dict(issue_id=issue,fixture_id=fixture['fixture_key'],reason=reason))
            continue
        for option in r['options']:
            quotes.append(dict(fixture_id=fixture['fixture_key'],outcome={'胜':'W','平':'D','负':'L'}[option['option']],
                quote_at=at.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(),
                sp_raw=float(option['sp']),source_url=url))
    return quotes, diagnostics


def fetch_issue_prematch_sp(schedule, raw_dir, timeout=25, retries=2, pages=None):
    """Fetch once using the shared bounded client; persist bytes before parsing.

    Offline pages={body:bytes, observed_at:timezone-aware ISO} preserves original
    observation time. Each call gets its own immutable directory. Receipts include
    market identity, raw hashes, schedule, code hashes and parser failures.
    """
    if not isinstance(schedule,list) or not schedule:
        raise ValueError('schedule must not be empty')
    issue = schedule[0]['issue_id']; url = parser.source_url(issue,5)
    if not isinstance(raw_dir,str) or not raw_dir.strip():
        raise ValueError('raw_dir required')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('invalid timeout')
    if type(retries) is not int or retries < 0:
        raise ValueError('invalid retries')
    if pages is None:
        response = fetch.fetch_issue_page(url,timeout=timeout,retries=retries)
        body, observed_at = response.body, response.observed_at
    else:
        if not isinstance(pages,dict) or set(pages) != {'body','observed_at'} or not isinstance(pages['body'],(bytes,bytearray)):
            raise ValueError('pages requires raw body and observed_at')
        body, observed_at = bytes(pages['body']), pages['observed_at']
    at = datetime.fromisoformat(observed_at.replace('Z','+00:00'))
    if at.tzinfo is None:
        raise ValueError('observed_at requires timezone')
    folder = store.new_fetch_directory(raw_dir,issue,at.isoformat())
    bodies = {'nowscore_beidan_sp':body}
    paths = store.persist_issue_raw(directory=folder,issue_id=issue,bodies=bodies)
    meta = dict(issue_id=issue,source_url=url,observed_at=observed_at,
        market='beidan_handicap_sp_reference',quote_time_basis='observed_availability',
        encoding='utf-8-sig',schedule=schedule,raw_paths=paths,
        implementation_sha256={str(Path(p).name):parser.digest(Path(p).read_bytes()) for p in
            (__file__,parser.__file__,labels.__file__,fetch.__file__,store.__file__)})
    try:
        quotes, diagnostics = parse_prematch_sp(body,schedule,observed_at)
        meta['parse'] = {'status':'parsed'}
        meta['diagnostics'] = diagnostics
    except Exception as error:
        meta['parse'] = {'status':'failed','error':str(error)}
        store.persist_issue_meta(directory=folder,issue_id=issue,bodies=bodies,rows={},meta=meta)
        raise
    paths.update(store.persist_issue_meta(directory=folder,issue_id=issue,bodies=bodies,
        rows={'prematch_sp':quotes},meta=meta))
    return dict(prematch_sp=quotes,diagnostics=diagnostics,receipt_path=paths['source_meta'])
