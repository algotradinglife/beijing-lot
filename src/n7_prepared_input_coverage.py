"""Read-only coverage audit of hash-bound prepared N7 market/roster batches."""
import gzip
import hashlib
import json
from pathlib import Path


def prepared_input_coverage(receipt_path, expected_sha256):
    """Return per-issue counts, source hashes and scope; never reads settlement.

    Coverage means published quote availability plus roster identity/handicap,
    not probability eligibility or prospective admission. Paths are explicit in
    the receipt. Corrupt hashes, duplicate keys or changed issue sets raise.
    """
    path = Path(receipt_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Input receipt changed')
    receipt = json.loads(raw)
    if receipt['historical_admission'] is not False:
        raise ValueError('Diagnostic admission required')
    scope_raw = (path.parent / 'scope.json').read_bytes()
    if hashlib.sha256(scope_raw).hexdigest() != receipt['outputs']['scope.json']:
        raise ValueError('Scope changed')
    scope = json.loads(scope_raw)
    counts = {}; sources = {str(path): expected_sha256}
    for batch in receipt['batches']:
        base = Path(batch['path'])
        market_raw = (base / 'published-markets.json.gz').read_bytes()
        handicap_raw = (base / 'handicaps.json').read_bytes()
        if (hashlib.sha256(market_raw).hexdigest() != batch['market_sha256'] or
                hashlib.sha256(handicap_raw).hexdigest() != batch['handicap_sha256']):
            raise ValueError('Prepared batch changed')
        market = json.loads(gzip.decompress(market_raw)); handicap = json.loads(handicap_raw)
        if (market['issue_order'] != batch['issues'] or
                handicap['market_snapshot_sha256'] != batch['market_sha256'] or
                market['historical_admission'] is not False or handicap['historical_admission'] is not False):
            raise ValueError('Batch identity mismatch')
        fixtures = {}; rosters = {}
        for row in handicap['rows']:
            key = (row['issue'], row['slot'])
            if key in rosters or row['issue'] not in batch['issues']:
                raise ValueError('Duplicate/out-of-scope roster')
            rosters[key] = row
        seen = set()
        for row in market['rows']:
            key = (row['issue'], row['slot']); full = (*key, row['market'])
            if full in seen or row['issue'] not in batch['issues'] or row['market'] not in ('euro', 'total'):
                raise ValueError('Duplicate/out-of-scope market')
            seen.add(full); fixtures.setdefault(key, {})[row['market']] = row
        for issue in batch['issues']:
            if issue in counts:
                raise ValueError('Repeated issue')
            keys = [k for k in fixtures if k[0] == issue]
            euro = total = both = aligned = 0
            for key in keys:
                rows = fixtures[key]
                e = rows.get('euro', {}).get('status') == 'QUOTES_PRIOR_DIAGNOSTIC'
                t = rows.get('total', {}).get('status') == 'QUOTES_PRIOR_DIAGNOSTIC'
                euro += e; total += t; both += e and t
                roster = rosters.get(key)
                aligned += bool(e and t and roster and roster.get('home_handicap') is not None and
                                str(rows['euro']['provider_id']) == str(rows['total']['provider_id']) == str(roster['provider_id']))
            counts[issue] = dict(issue=issue,fixtures=len(keys),euro=euro,total=total,both_markets=both,roster_aligned=aligned)
        for name, identity in [('published-markets.json.gz', batch['market_sha256']), ('handicaps.json', batch['handicap_sha256'])]:
            sources[str(base / name)] = identity
    if set(counts) != set(scope['issues']) or len(counts) != receipt['issues']:
        raise ValueError('Incomplete prepared scope')
    return dict(rows=[counts[i] for i in sorted(counts)],scope=scope,source_hashes=sources,historical_admission=False)
