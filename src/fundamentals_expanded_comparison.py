"""Descriptive report assembly; no learning, selection, or settlement writes."""
import gzip
import hashlib
import json
from pathlib import Path
from src.temporal_learning.core import stable_json_hash


def read_verified_report_archive(path):
    """Read a saved two-file report, verifying bytes and result/freeze identity.

    Returns decoded results and frozen receipt. Missing/corrupt files raise;
    archive verification does not claim current model/source replay. Read-only.
    """
    archive = json.loads(gzip.decompress(Path(path).read_bytes()))
    if set(archive['files']) != {'results.json', 'plans-frozen.json'}:
        raise ValueError('Unexpected archive scope')
    for name, body in archive['files'].items():
        if hashlib.sha256(body.encode()).hexdigest() != archive['hashes'][name]:
            raise ValueError('Changed archive bytes')
    result, frozen = (json.loads(archive['files'][n]) for n in ('results.json', 'plans-frozen.json'))
    if result['freeze_seal'] != frozen['seal']:
        raise ValueError('Archive freeze mismatch')
    if stable_json_hash(frozen['receipt']) != frozen['seal']:
        raise ValueError('Archive receipt mismatch')
    return result, frozen


def merge_variant_reports(original_rows, conflict_rows):
    """Union issue/policy rows, checking all shared fields except cohort label.

    One observation is an issue/strategy pair. Identifiers stay strings; missing
    settlement values stay None. Repeated keys within either input, conflicting
    shared results, or different issue scopes fail. No I/O or implicit filtering.
    """
    indexed = []
    for rows in (original_rows, conflict_rows):
        current = {}
        for row in rows:
            key = row['issue'], row['policy']
            if not all(isinstance(x, str) and x for x in key) or key in current:
                raise ValueError('Invalid or duplicate issue/policy')
            current[key] = dict(row)
        if not current:
            raise ValueError('Empty report')
        indexed.append(current)
    left, right = indexed
    if {x[0] for x in left} != {x[0] for x in right}:
        raise ValueError('Different issue scopes')
    for key in left.keys() & right.keys():
        a, b = left[key], right[key]
        fields = (a.keys() | b.keys()) - {'partition'}
        if any(a.get(f) != b.get(f) for f in fields):
            raise ValueError('Conflicting shared result: ' + str(key))
    return [dict(row, partition='POST_EXPOSURE_RETROSPECTIVE')
            for _, row in sorted((left | right).items())]
