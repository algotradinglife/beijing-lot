"""Read explicitly assigned frozen odds across full-history source formats.

No quote selection, fitting, network, writes, or labels in the returned frame.
Archives use the authoritative byte-verified archive reader. Missing identities
or different fixture decision epochs fail rather than substitute newer quotes.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
from src.data_archive import read_archive_members
from src.zero_handicap_inputs import verified_zero_json
from src.strategy_diagnostic_inputs import read_verified_bundle_json
from src.temporal_learning import Cutoff
from src.temporal_learning.core import utc


def read_zero_purchase_history(manifest_path, manifest_sha256, zero_only=True):
    """Return JSON with zero-line odds and source hashes for explicit issue scope.

    sources: kind=fixtures / market / euro, issues, and either file+sha256 or
    archive+archive_sha256+member. bundles pins one candidate JSON per issue.
    Rows are unique issue/slot/provider_id, handicap=0, odds_W/D/L plus frozen
    p/q controls. Every needed quote must have the same decision epoch as bundle.
    zero_only=False admits every signed handicap and adds cutoff_utc and nullable
    lambda_home/away (mapped goal means, NOT original over/under quote lines).
    Missing means remain null; malformed supplied means fail. No labels returned.
    """
    m = verified_zero_json(manifest_path, manifest_sha256)
    hashes = {str(manifest_path): manifest_sha256}
    assigned, packets, rows = {}, {}, []
    archives = {}
    for source in m['sources']:
        for issue in source['issues']:
            if issue in assigned:
                raise ValueError('Repeated issue source assignment')
            assigned[issue] = source
        if 'archive' in source:
            key = (source['archive'], source['archive_sha256'])
            archives.setdefault(key, []).append(source['member'])
    for (path, sha), members in archives.items():
        packets.update({(path, k): v for k, v in read_archive_members(
            path, list(dict.fromkeys(members)), expected_sha256=sha).items()})
        hashes[path] = sha
    quotes = {}
    for source in m['sources']:
        if 'archive' in source:
            raw = packets[(source['archive'], source['member'])]
            if source['member'].endswith('.gz'):
                raw = gzip.decompress(raw)
            obj = json.loads(raw)
        else:
            obj = verified_zero_json(source['path'], source['sha256'])
            hashes[source['path']] = source['sha256']
        kind = source['kind']
        if kind == 'fixtures':
            values = obj['fixtures']
        elif kind == 'market':
            values = obj['market']['rows']
        elif kind == 'euro':
            values = obj['rows']
        else:
            raise ValueError('Unknown quote container')
        for row in values:
            if row['issue'] not in source['issues']:
                continue
            key = (row['issue'], row['slot'], row['provider_id'])
            if key in quotes:
                raise ValueError('Duplicate quote identity')
            quotes[key] = row
    issues = [b['issue'] for b in m['bundles']]
    if len(set(issues)) != len(issues) or set(issues) != set(assigned):
        raise ValueError('Quote/bundle issue scope differs')
    for entry in m['bundles']:
        bundle = json.loads(read_verified_bundle_json(entry['path'], entry['sha256']))
        hashes[entry['path']] = entry['sha256']
        if bundle['issue'] != entry['issue']:
            raise ValueError('Bundle issue differs')
        for fixture in bundle['expanded_pool']['fixtures']:
            if zero_only and fixture['handicap'] != 0:
                continue
            key = (fixture['issue'], fixture['slot'], fixture['provider_id'])
            if key not in quotes:
                raise ValueError(f'Missing zero-line odds: {key}')
            q = quotes[key]
            if Cutoff.decision_epoch(key[0], q['cutoff_utc']) != Cutoff.decision_epoch(
                    key[0], bundle['cutoffs'][str(key[1])]):
                raise ValueError(f'Quote epoch mismatch: {key}')
            if 'handicap' in q and q['handicap'] != fixture['handicap']:
                raise ValueError('Quote handicap differs')
            odds = {f'odds_{d}': q[f'odds_{d}'] for d in 'WDL'}
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 1
                   for v in odds.values()):
                raise ValueError(f'Invalid odds: {key}')
            for d in 'WDL':
                if f'q_{d}' in q and abs(q[f'q_{d}'] - fixture[f'q_{d}']) > 1e-10:
                    raise ValueError(f'Frozen quote projection differs: {key}')
            row = dict(fixture, **odds)
            if not zero_only:
                row['cutoff_utc'] = utc(q['cutoff_utc']).isoformat()
                for field in ('lambda_home', 'lambda_away'):
                    value = q.get(field)
                    if value is not None and (not isinstance(value, (int, float))
                            or not math.isfinite(value) or value <= 0):
                        raise ValueError('Invalid mapped goal mean')
                    row[field] = value
            rows.append(row)
    return json.dumps(dict(rows=rows, issues=issues, source_hashes=hashes,
                           historical_learning='NONE'), allow_nan=False)
