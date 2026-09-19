"""Offline historical Titan European odds; no fetching, fitting or label access."""
from datetime import datetime, timezone
from pathlib import Path
import math
import re
import hashlib
import json
import json5
from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_issue_report import issue_capture_report
from src.fundamentals_pilot import pilot_tables
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc
from src.temporal_learning.diagnostic_window import diagnostic_quote_window
from src.temporal_learning.provenance import implementation_closure


def titan_js_timestamp(value):
    """Parse literal JS UTC date components; never eval source expressions.

    Titan showDate constructs Date.UTC from these components. Month is written
    MM-1 or a literal zero-based month for the JS constructor. Invalid/missing clocks raise.
    """
    match = re.fullmatch(r"(\d{4}),(\d{1,2})(-1)?,(\d{1,2}),(\d{1,2}),(\d{1,2}),(\d{1,2})", value)
    if not match:
        raise ValueError("Invalid Titan date literal")
    year, month, subtract, day, hour, minute, second = match.groups()
    month = int(month) if subtract else int(month) + 1
    return datetime(int(year), month, int(day), int(hour), int(minute),
                    int(second), tzinfo=timezone.utc).isoformat()


def parse_titan_euro(text, *, corroborating_text=None):
    """Return native identity and last nonexchange quotes from 24-field JS.

    Positive low quotes (<=1) require identical corroborating source text.
    Raw values are preserved; this is not a probability conversion.
    Empty last triples stay missing; partial/nonfinite triples
    and duplicate companies fail. Opening prices lack clocks and are never
    substituted. Counters disclose omissions. No prices selected by outcomes.
    """
    values = {}
    for name in ('ScheduleID', 'hometeamID', 'guestteamID', 'MatchTime'):
        matches = re.findall(r'(?:^|[;\n])\s*(?:var\s+)?'+name+r'\s*=\s*([^;]+);', text)
        if len(matches) != 1:
            raise ValueError('Missing/duplicate Titan identity: '+name)
        values[name] = json5.loads(matches[0])
    for name in ('ScheduleID', 'hometeamID', 'guestteamID'):
        if type(values[name]) is not int or values[name] <= 0:
            raise ValueError('Invalid native identity')
    blocks = re.findall(r'\bgame\s*=\s*Array\((.*?)\)\s*;', text, re.S)
    if len(blocks) != 1:
        raise ValueError('Missing/duplicate Titan odds array')
    try:
        records = json.loads('['+blocks[0]+']')
    except json.JSONDecodeError:
        records = json5.loads('['+blocks[0]+']')
    quotes = []; seen = set(); missing = 0; exchanges = 0
    for record in records:
        parts = record.split('|')
        if len(parts) != 24 or not parts[0].isdigit() or parts[0] in seen:
            raise ValueError('Invalid/duplicate Titan company record')
        seen.add(parts[0])
        if parts[23] not in ('0', '1'):
            raise ValueError('Unknown exchange flag')
        if parts[23] == '1':
            exchanges += 1
            continue
        if parts[10:13] == ['', '', '']:
            missing += 1
            continue
        odds = list(map(float, parts[10:13]))
        if any(not math.isfinite(x) or x <= 0 for x in odds):
            raise ValueError('Invalid last decimal odds')
        if min(odds) <= 1 and corroborating_text != text:
            raise ValueError("Low odds require matching source evidence")
        quotes.append(dict(quote_id=parts[0], company=parts[2],
            odds_W=odds[0], odds_D=odds[1], odds_L=odds[2],
            quoted_at=titan_js_timestamp(parts[20])))
        if min(odds) <= 1:
            quotes[-1]["low_odds_multisource_accepted"] = True
    return dict(provider_id=str(values['ScheduleID']),home_team_id=str(values['hometeamID']),
        away_team_id=str(values['guestteamID']),kickoff_utc=titan_js_timestamp(values['MatchTime']),
        quotes=quotes,missing_last=missing,exchanges=exchanges,company_count=len(seen))


def titan_euro_inputs(inventories, capture_paths, *, repository_root, cache_dir):
    """Bind saved odds to Titan-primary identities and explicit original cutoffs.

    One row per captured issue/slot, including failures. Mean decimal odds over
    nonexchange last quotes strictly before cutoff, each company's own clock.
    This is an asynchronous snapshot with unproven historical availability.
    Reuses source integration and shared chronology; read-only except parse cache.
    Returns rows, per-company quotes, receipts and transitive implementation hashes.
    """
    closure = implementation_closure(Path(repository_root), ('src.fundamentals_titan_euro',))['files']
    captures = {}
    for path in capture_paths:
        meta, raw = read_response(Path(path))
        if meta.get('status') != 200:
            raise ValueError('Successful capture required')
        text, _ = decode_analysis_text(raw)
        parsed = parse_titan_euro(text)
        pid = parsed['provider_id']
        if pid in captures:
            raise ValueError('Duplicate native capture')
        expected_url = 'https://1x2d.titan007.com/'+pid+'.js'
        if meta.get('url') != expected_url or meta.get('final_url') != expected_url:
            raise ValueError('Capture URL/native identity mismatch')
        captures[pid] = (parsed, meta, path)
    rows = []; receipts = []; companies = []; matched = set()
    for inv in inventories:
        report = issue_capture_report(inv['roster_path'],inv['response_paths'],issue=inv['issue'],
            expected_fixture_count=inv['fixture_count'],expected_slots=[int(s) for s in inv['cutoffs']],cache_dir=cache_dir)
        pilot = pilot_tables(report,cutoffs=inv['cutoffs'],adjudications=inv.get('adjudications'))
        for f in pilot['integrated_fixtures']:
            if f['provider_id'] not in captures:
                continue
            pid=f['provider_id']; matched.add(pid); p,meta,path=captures[pid]
            row=dict(issue=inv['issue'],slot=f['slot'],provider_id=pid,status='IDENTITY_MISMATCH',
                odds_W=None,odds_D=None,odds_L=None,companies=0,missing_last=p['missing_last'],
                exchanges=p['exchanges'],raw_sha256=meta['sha256'],capture_path=str(path),
                capture_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                received_at_utc=meta['received_at_utc'],url=meta['url'],final_url=meta['final_url'],
                cutoff_utc=inv['cutoffs'][str(f['slot'])],historical_admission=False)
            rows.append(row)
            # Identity fields come from the already validated source fixture.
            source=next((s for s in pilot['source_fixtures'] if s['slot']==f['slot'] and s['source']=='titan'),None)
            if source is None or not f['kickoff_utc']:
                continue
            if (str(source.get('home_id'))!=p['home_team_id'] or
                str(source.get('away_id'))!=p['away_team_id'] or
                utc(f['kickoff_utc'])!=utc(p['kickoff_utc'])):
                continue
            selected=diagnostic_quote_window(p['quotes'],cutoff=Cutoff.decision_epoch(inv['issue'],row['cutoff_utc']),
                source_hashes={str(path):row['capture_sha256'],**report['input_file_hashes']},implementation_hashes=closure)
            receipts.append(dict(issue=inv['issue'],slot=f['slot'],receipt=selected['receipt'],receipt_json=selected['receipt_json']))
            row['companies']=len(selected['rows']); row['excluded_late']=selected['receipt']['excluded_same_or_later']
            row['status']='OK_DIAGNOSTIC' if selected['rows'] else 'NO_PRIOR_LAST_QUOTES'
            if selected['rows']:
                for key in ('odds_W','odds_D','odds_L'):
                    row[key]=sum(q[key] for q in selected['rows'])/len(selected['rows'])
                row['oldest_quote']=min(q['quoted_at'] for q in selected['rows'])
                row['latest_quote']=max(q['quoted_at'] for q in selected['rows'])
                companies.extend(dict(issue=inv['issue'],slot=f['slot'],**q) for q in selected['rows'])
    if matched != set(captures):
        raise ValueError('Unmatched capture IDs')
    result=dict(rows=rows,companies=companies,receipts=receipts,implementation_hashes=closure,historical_admission=False)
    canonical=json.dumps(result,ensure_ascii=True,separators=(',',':'),allow_nan=False)
    return dict(result,canonical_json=canonical,seal=hashlib.sha256(canonical.encode()).hexdigest())
