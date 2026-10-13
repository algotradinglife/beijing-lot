"""Offline replay of historical capture bytes; market failures stay independent."""
from datetime import datetime
import hashlib
import re
from pathlib import Path

from .history import (euro_history_url, over_under_history_url,
                      parse_asian_handicap_history_json, parse_over_under_history_json)
from .service import parse_markets, titan_identity, validate_fixture


def replay_fixture_capture(record: dict, repository_root: str, expected_team_ids: dict) -> dict:
    """Verify a saved bounded collector receipt and reparse all three markets.

    No network, writes, cutoff selection or forecasting. Inputs are the original
    capture dict, explicit frozen native home/away IDs and explicit absolute root for relative raw paths. SHA256, URL,
    original observation timezone and unique market receipts are mandatory.
    Critical provenance errors raise; each source/parser failure is recorded
    independently. Decimal prices include stake; AH is signed home handicap.
    EXACT requires all native fixture/team IDs, names and kickoff. EXACT_IDS
    permits differing names only when all native IDs and kickoff match.
    Other statuses preserve quotes for diagnosis but do not authorize admission.
    Return JSON-native quotes, raw identities, row counts and explicit errors.
    """
    root = Path(repository_root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("Existing absolute repository root required")
    if set(expected_team_ids) != {'home_id','away_id'} or not all(isinstance(v,str) and v.isdigit() and int(v)>0 for v in expected_team_ids.values()):
        raise ValueError("Explicit frozen native team IDs required")
    fixture = record['fixture']; kickoff = validate_fixture(fixture)
    pid = fixture['provider_id_nowscore']
    urls = {'euro': euro_history_url(pid),
            'total': over_under_history_url(pid, 8, kickoff)}
    urls['asian'] = urls['total'].replace('oddskind=1', 'oddskind=0')
    captures = record['captures']
    if len({c['kind'] for c in captures}) != len(captures):
        raise ValueError("Duplicate capture market")
    result = dict(fixture=fixture, euro=[], totals=[], asian=[], diagnostics=[],
                  identity={}, identity_status='UNVERIFIED', captures=captures, expected_team_ids=expected_team_ids)
    bodies = {}
    for c in captures:
        kind = c['kind']
        if kind not in urls or c['url'] != urls[kind]:
            raise ValueError("Source URL/fixture binding mismatch")
        observed = datetime.fromisoformat(c['observed_at'])
        if observed.tzinfo is None:
            raise ValueError("Original observation must have timezone")
        if 'sha256' not in c:
            if not c.get('error'):
                raise ValueError("Missing hash or failure evidence")
            result['diagnostics'].append(dict(market=kind, status='REQUEST_FAILURE', reason=c['error']))
            continue
        path = Path(c['raw_path'])
        body = (path if path.is_absolute() else root / path).read_bytes()
        if hashlib.sha256(body).hexdigest() != c['sha256']:
            raise ValueError("Raw response SHA256 differs")
        bodies[kind] = body
    if 'euro' in bodies:
        try:
            identity = titan_identity(bodies['euro'])
            result['identity'] = {**identity, 'kickoff_at': identity['kickoff_at'].isoformat()}
            if str(identity['ScheduleID']) != pid:
                result['identity_status'] = 'NATIVE_ID_CONFLICT'
                raise ValueError("Euro native fixture ID differs")
            team_ids = {}
            for name in ('hometeamID','guestteamID'):
                found = re.findall(r'(?:^|(?<=[;\n]))\s*(?:var\s+)?'+name+r'\s*=\s*([0-9]+)\s*;', bodies['euro'].decode('utf-8-sig'))
                team_ids[name] = found[0] if len(found)==1 and int(found[0])>0 else None
            result['identity'].update(team_ids)
            matching_ids = team_ids == dict(hometeamID=expected_team_ids['home_id'],guestteamID=expected_team_ids['away_id'])
            if not all(team_ids.values()):
                result['identity_status'] = 'UNVERIFIED'
            elif not matching_ids:
                result['identity_status'] = 'TEAM_ID_CONFLICT'
            elif identity['kickoff_at'] != kickoff:
                result['identity_status'] = 'NAME_OR_CLOCK_CONFLICT'
            else:
                result['identity_status'] = ('EXACT' if identity['hometeam_cn']==fixture['home_nowscore'] and identity['guestteam_cn']==fixture['away_nowscore'] else 'EXACT_IDS')
            parsed = parse_markets(fixture, bodies['euro'], {})
            result['euro'] = parsed['euro']
            result['diagnostics'].extend(parsed['diagnostics'])
        except (ValueError, KeyError, UnicodeError) as exc:
            result['diagnostics'].append(dict(market='euro', status='PARSER_FAILURE', reason=str(exc)))
    for kind, name, parse in [('total', 'totals', parse_over_under_history_json),
                              ('asian', 'asian', parse_asian_handicap_history_json)]:
        if kind not in bodies:
            continue
        try:
            rows, counters = parse(bodies[kind], kickoff_hkt=kickoff)
            result['diagnostics'].append(dict(market=kind, status='PARSED', counters=counters))
            for row in rows:
                if not row.complete:
                    continue
                prices = (dict(line=row.line_value, over_decimal=1 + row.odds['over'],
                               under_decimal=1 + row.odds['under']) if kind == 'total' else
                          dict(handicap=row.line_value, home_decimal=1 + row.odds['home'],
                               away_decimal=1 + row.odds['away']))
                result[name].append(dict(fixture_id=fixture['fixture_id'], company_id='8',
                    quote_at=row.snapshot_ts_hkt, source_url=urls[kind],
                    raw_row_sha256=row.raw_row_sha256, **prices))
        except (ValueError, KeyError, UnicodeError) as exc:
            result['diagnostics'].append(dict(market=kind, status='PARSER_FAILURE', reason=str(exc)))
    result['parser_bindings'] = {
        str(p.relative_to(root)) if p.is_relative_to(root) else str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), Path(__file__).with_name('history.py'), Path(__file__).with_name('service.py'))}
    return result
