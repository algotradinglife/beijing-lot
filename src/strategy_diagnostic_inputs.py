"""Read-only adapter for hash-bound frozen candidate fixture probabilities."""
import gzip
import hashlib
import json
from pathlib import Path


def read_verified_bundle_json(path, expected_sha256):
    """Read and verify the exact compressed bytes parsed; no second file read."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Diagnostic bundle changed')
    return gzip.decompress(raw).decode('utf-8')


def read_diagnostic_epoch_fixtures(catalog_path, catalog_sha256):
    """Return label-free fixture JSON with explicit frozen fixture/issue clocks.

    Uses the authoritative identity reader and hash-verified same-byte bundle
    reader. Does not infer outcome or source availability from these clocks.
    """
    data = read_diagnostic_fixtures(catalog_path, catalog_sha256)
    raw = Path(catalog_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != catalog_sha256:
        raise ValueError('Diagnostic catalog changed')
    from .temporal_learning.core import utc
    clocks, last = {}, {}
    for item in json.loads(raw)['issues']:
        bundle = json.loads(read_verified_bundle_json(item['path'], item['sha256']))
        clocks[item['issue']] = bundle['cutoffs']
        last[item['issue']] = max(utc(x) for x in bundle['cutoffs'].values()).isoformat()
    for row in data['rows']:
        cuts = clocks[row['issue']]
        row['fixture_decision_ts'] = cuts[str(row['slot'])]
        # All clocks are validated/normalized by shared UTC handling.
        row['last_fixture_cutoff'] = last[row['issue']]
    return json.dumps(data, allow_nan=False)


def read_diagnostic_fixtures(catalog_path: str, catalog_sha256: str) -> dict:
    """Return {rows, source_hashes} from an explicit candidate catalog.

    One row per issue/slot/provider_id. Identifiers stay strings, slot stays int;
    probabilities and handicap retain source values for downstream R contracts.
    Only frozen fixture fields are returned, never candidate result columns.
    Missing/changed files, duplicate fixtures or invalid identity fail. No writes,
    network, fitting, clock inference or import-time side effects.
    """
    path = Path(catalog_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != catalog_sha256:
        raise ValueError('Diagnostic catalog changed')
    catalog = json.loads(raw)
    sources = {str(path): catalog_sha256}
    rows, seen, issues = [], set(), set()
    fields = ['issue', 'slot', 'provider_id', 'handicap',
              'p_W', 'p_D', 'p_L', 'q_W', 'q_D', 'q_L']
    if not catalog['issues']:
        raise ValueError('Empty diagnostic catalog')
    for item in catalog['issues']:
        source = Path(item['path'])
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Diagnostic bundle changed')
        bundle = json.loads(gzip.decompress(raw))
        issue = item['issue']
        if not isinstance(issue, str) or issue in issues or bundle['issue'] != issue:
            raise ValueError('Duplicate or inconsistent issue identity')
        issues.add(issue)
        fixtures = bundle['expanded_pool']['fixtures']
        if not fixtures:
            raise ValueError('Empty candidate fixtures')
        for fixture in fixtures:
            row = {key: fixture[key] for key in fields}
            key = row['issue'], row['slot'], row['provider_id']
            if (row['issue'] != issue or not isinstance(row['provider_id'], str)
                    or type(row['slot']) is not int or row['slot'] < 1 or key in seen):
                raise ValueError('Invalid or duplicate fixture identity')
            seen.add(key)
            rows.append(row)
        sources[str(source)] = item['sha256']
    return {'rows': rows, 'source_hashes': sources}
