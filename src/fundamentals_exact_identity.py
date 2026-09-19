
"""Exact-fixture identity adjudications; no team-wide aliases or raw writes."""
import hashlib
import json
from pathlib import Path
from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_euro_corroboration import corroborated_euro
from src.fundamentals_titan_total import parse_titan_total_html
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_window import diagnostic_quote_window
from src.temporal_learning.partial_clock import diagnostic_monthday_quotes
from src.temporal_learning.roster_clock import roster_clock_alignment
from src.temporal_learning.provenance import implementation_closure


def exact_identity_match(fixture, parsed, decision, *, market, cutoff):
    """Validate one approved issue/slot, provider, market, IDs and cutoff.

    Return a receipt without modifying inputs. Wrong context raises ValueError;
    an approval never applies to other fixtures, sides or source snapshots.
    """
    actual = dict(issue=fixture['issue'], slot=fixture['slot'],
        provider_id=fixture['native_match_id'], market=market,
        roster_ids=[str(fixture['home_id']), str(fixture['away_id'])],
        source_ids=[parsed['home_team_id'], parsed['away_team_id']],
        cutoff_utc=cutoff.cutoff_ts.isoformat())
    if decision['approved'] is not True or any(actual[k] != decision[k] for k in actual):
        raise ValueError('Exact fixture adjudication mismatch')
    if parsed['provider_id'] != actual['provider_id'] or cutoff.target_issue != actual['issue']:
        raise ValueError('Native fixture/cutoff mismatch')
    return dict(**actual, adjudication_id=decision['adjudication_id'],
                rule='EXACT_FIXTURE_IDENTITY', original_ids_preserved=True)


def replay_exact_identity(config_path, *, repository_root):
    """Read hash-bound four-fixture configuration and replay original cutoffs.

    Return fixtures, selected quotes and evidence receipts. No writes, fitting,
    global ID replacement or prospective availability claims. Invalid data fails.
    """
    root = Path(repository_root)
    config_path = Path(config_path)
    decisions = json.loads(config_path.read_text())
    keys = [(d['issue'], d['slot'], d['market']) for d in decisions]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate adjudication')
    closure = implementation_closure(root, ('src.fundamentals_exact_identity',))['files']
    rows, receipts, quotes = [], [], []
    for d in decisions:
        if d['market'] not in ('euro', 'total'):
            raise ValueError('Unsupported market')
        required = [d['roster_path'], d['capture_path']]
        if d['market'] == 'euro':
            required.append(d['peer_path'])
        bound = {(root / name).resolve() for name in d['files']}
        if not d['files'] or any((root / name).resolve() not in bound for name in required):
            raise ValueError('Consumed evidence missing from hash manifest')
        hashes = {str(config_path): hashlib.sha256(config_path.read_bytes()).hexdigest()}
        for name, digest in d['files'].items():
            p = root / name
            if hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                raise ValueError('Adjudication evidence changed')
            hashes[str(p)] = digest
        from src.nowscore_settlement import parse_page
        _, raw = read_response(root / d['roster_path'])
        fixtures = [f for f in parse_page(raw, d['issue'], 8) if f['slot'] == d['slot']]
        if len(fixtures) != 1:
            raise ValueError('Unique roster fixture required')
        f = fixtures[0]
        if d['market'] == 'euro':
            p = corroborated_euro(root / d['capture_path'], root / d['peer_path'])['parsed']
            kickoff = p['kickoff_utc']
        else:
            meta, body = read_response(root / d['capture_path'])
            if meta['status'] != 200:
                raise ValueError('Successful market response required')
            p = parse_titan_total_html(body.decode('utf-8'))
            kickoff = p['kickoff_local'].replace(' ', 'T') + ':00+08:00'
        cutoff = Cutoff.decision_epoch(d['issue'], d['cutoff_utc'])
        identity = exact_identity_match(f, p, d, market=d['market'], cutoff=cutoff)
        alignment = roster_clock_alignment(dict(f, deadline_text=f['cutoff_text'], clock=f['kickoff_time']),
            {d['market']: kickoff}, cutoff=cutoff, timezone='Asia/Shanghai', midnight_hours=12)
        if f['status'] != '完场' or alignment['status'] != 'ALIGNED':
            raise ValueError('Identity approval does not override status/date')
        if d['market'] == 'euro':
            window = diagnostic_quote_window(p['quotes'], cutoff=cutoff,
                source_hashes=hashes, implementation_hashes=closure)
        else:
            window = diagnostic_monthday_quotes([q for q in p['changes'] if q['phase'] == 'PREMATCH'],
                anchor_utc=alignment['canonical_kickoff_utc'], timezone='Asia/Shanghai', maximum_days=31,
                cutoff=cutoff, source_hashes=hashes, implementation_hashes=closure)
        rows.append(dict(issue=d['issue'], slot=d['slot'], market=d['market'],
            provider_id=d['provider_id'], prior_companies=len(window['rows']),
            status='QUOTES_PRIOR_DIAGNOSTIC' if window['rows'] else 'NO_PRIOR_QUOTES',
            roster_ids='/'.join(d['roster_ids']), source_ids='/'.join(d['source_ids']),
            adjudication_id=d['adjudication_id'], cutoff_utc=d['cutoff_utc']))
        quotes.extend(dict(issue=d['issue'], slot=d['slot'], market=d['market'], **q) for q in window['rows'])
        receipts.append(dict(identity=identity, alignment=alignment, window=window,
                             source_hashes=hashes, implementation_hashes=closure))
    return dict(fixtures=rows, quotes=quotes, receipts=receipts, historical_admission=False)
