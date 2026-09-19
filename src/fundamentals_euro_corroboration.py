"""Offline low-price adjudication using saved Titan and Nowscore responses."""
import hashlib
from pathlib import Path

from src.fundamentals_census import read_response, decode_analysis_text
from src.fundamentals_titan_euro import parse_titan_euro


def corroborated_euro(titan_path, nowscore_path):
    """Return parsed prices and capture hashes; no writes or probability conversion.

    Require HTTP 200, matching decoded scripts and the exact native-ID source
    URLs. Positive prices <=1 remain unchanged under the user-approved rule.
    Conflicting sources, invalid prices and wrong identities raise ValueError.
    """
    paths = [Path(titan_path), Path(nowscore_path)]
    captures = [read_response(p) for p in paths]
    if any(m.get('status') != 200 for m, _ in captures):
        raise ValueError('Successful source responses required')
    decoded = [decode_analysis_text(b) for _, b in captures]
    if decoded[0][0] != decoded[1][0]:
        raise ValueError('Source scripts disagree')
    parsed = parse_titan_euro(decoded[0][0], corroborating_text=decoded[1][0])
    pid = parsed['provider_id']
    urls = [f'https://1x2d.titan007.com/{pid}.js',
            f'https://1x2.nowscore.com/{pid}.js']
    for (meta, _), url in zip(captures, urls):
        if meta.get('url') != url or meta.get('final_url') != url:
            raise ValueError('Source URL/native identity mismatch')
    return dict(parsed=parsed, evidence=[dict(path=str(p), url=m['url'],
                capture_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                encoding=d[1], received_at_utc=m['received_at_utc'])
                for p, (m, _), d in zip(paths, captures, decoded)],
                rule='MULTISOURCE_LOW_ODDS_ACCEPTED', independent_sources=False,
                historical_admission=False)

def replay_corroborated_euro(initial_path, comparison_path, scope_path, *, repository_root):
    """Read-only diagnostic replay with original per-slot cutoffs and hash receipts.

    Return fixture, quote, receipt tables. No probabilities or prospective
    availability claims. Missing inputs or changed originals raise.
    """
    import json
    from src.temporal_learning import Cutoff
    from src.temporal_learning.diagnostic_window import diagnostic_quote_window
    from src.temporal_learning.provenance import implementation_closure
    from src.temporal_learning.roster_clock import roster_clock_alignment
    root = Path(repository_root)
    initial = json.loads(Path(initial_path).read_text())
    comparison = json.loads(Path(comparison_path).read_text())
    scope = json.loads(Path(scope_path).read_text())
    peers = {r['provider_id']: r['path'] for r in comparison['nowscore_comparison']}
    cutoffs = {(r['issue'], r['slot']): r['decision_ts'] for r in scope['fixtures']}
    closure = implementation_closure(root, ('src.fundamentals_euro_corroboration',))['files']
    bindings = {str(p): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in (initial_path, comparison_path, scope_path)}
    fixtures, quotes, receipts = [], [], []
    for row in initial:
        if row['category'] not in ('INVALID_COMPANY_PRICE', 'UTF16_ALTERNATE_DATE'):
            continue
        path = root / row['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != row['capture_sha256']:
            raise ValueError('Original capture changed')
        result = corroborated_euro(path, root / peers[row['provider_id']])
        parsed = result['parsed']
        if parsed['provider_id'] != row['provider_id']:
            raise ValueError('Triage identity mismatch')
        hashes = {e['path']: e['capture_sha256'] for e in result['evidence']}
        for roster in row['rosters']:
            rp = root / roster['path']
            if hashlib.sha256(rp.read_bytes()).hexdigest() != roster['sha256']:
                raise ValueError('Original roster changed')
            fixture = roster['row']
            if fixture['native_match_id'] != parsed['provider_id']:
                raise ValueError('Roster identity mismatch')
            key = dict(issue=fixture['issue'], slot=fixture['slot'], provider_id=parsed['provider_id'])
            cutoff = Cutoff.decision_epoch(fixture['issue'], cutoffs[(fixture['issue'], fixture['slot'])])
            clock_fixture = dict(fixture, deadline_text=fixture["cutoff_text"], clock=fixture["kickoff_time"])
            alignment = roster_clock_alignment(clock_fixture, {'euro': parsed['kickoff_utc']},
                cutoff=cutoff, timezone='Asia/Shanghai', midnight_hours=12)
            window = diagnostic_quote_window(parsed['quotes'], cutoff=cutoff,
                source_hashes={**bindings, **hashes, str(rp): roster['sha256']}, implementation_hashes=closure)
            identity_ok = (str(fixture["home_id"]) == parsed["home_team_id"] and str(fixture["away_id"]) == parsed["away_team_id"])
            status = ('IDENTITY_MISMATCH' if not identity_ok else 'ORIGINAL_NOT_FINISHED' if fixture['status'] != '完场' else
                      alignment['status'] if alignment['status'] != 'ALIGNED' else
                      'QUOTES_PRIOR_DIAGNOSTIC' if window['rows'] else 'NO_PRIOR_QUOTES')
            fixtures.append(dict(**key, original_status=fixture['status'], status=status,
                companies=len(parsed['quotes']), prior_companies=len(window['rows']),
                low_companies=sum(bool(q.get('low_odds_multisource_accepted')) for q in parsed['quotes']),
                low_prior_companies=sum(bool(q.get('low_odds_multisource_accepted')) for q in window['rows']),
                cutoff_utc=cutoff.cutoff_ts.isoformat(), historical_admission=False))
            selected = {q['quote_id'] for q in window['rows']}
            quotes.extend(dict(**key, **q, prior_cutoff=q['quote_id'] in selected) for q in parsed['quotes'])
            receipts.append(dict(**key, evidence=result['evidence'], alignment=alignment,
                                 window=window['receipt'], status=status))
    return dict(fixtures=fixtures, quotes=quotes, receipts=receipts,
                source_hashes=bindings, implementation_hashes=closure, historical_admission=False)
