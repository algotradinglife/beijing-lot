"""Read existing settlement observations as descriptive competition evidence.

This does not establish pre-match availability or team league membership.
No writes, network requests, fitting or import-time side effects.
"""
import hashlib
import json
import sqlite3
from pathlib import Path


def read_competition_labels(database, fixtures):
    """Return rows plus a digest of admitted observation evidence.

    fixtures: list of issue/string, slot/positive integer, provider_id/string.
    Exact three-part identity is required. Missing labels remain None; conflicting
    nonempty labels fail. All matching SPF observation provenance is retained.
    The digest binds returned source evidence, not a mutable whole database.
    """
    keys = []
    for f in fixtures:
        key = (f['issue'], f['slot'], f['provider_id'])
        if (not isinstance(key[0], str) or not key[0]
                or type(key[1]) is not int or key[1] < 1
                or not isinstance(key[2], str) or not key[2]):
            raise ValueError('Invalid fixture identity')
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate fixture identity')
    wanted = set(keys)
    evidence = {k: [] for k in keys}
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        for issue, slot, native, payload in connection.execute(
                'SELECT issue,slot,native_match_id,payload_json FROM observation WHERE play=?', ('spf',)):
            key = (issue, slot, native)
            if key not in wanted:
                continue
            data = json.loads(payload)
            league = data.get('league')
            if league is not None and not isinstance(league, str):
                raise ValueError('Invalid competition label')
            evidence[key].append({'competition': league or None,
                                  'payload_sha256': hashlib.sha256(payload.encode()).hexdigest(),
                                  'source_sha256': data.get('source_sha256'),
                                  'source_url': data.get('source_url')})
    finally:
        connection.close()
    rows = []
    for key in keys:
        observations = sorted(evidence[key], key=lambda x: x['payload_sha256'])
        labels = {x['competition'] for x in observations if x['competition'] is not None}
        if len(labels) > 1:
            raise ValueError(f'Conflicting competition labels: {key}')
        rows.append(dict(issue=key[0], slot=key[1], provider_id=key[2],
                         competition=next(iter(labels), None), evidence=observations))
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    return {'rows': rows, 'evidence_sha256': hashlib.sha256(encoded).hexdigest(),
            'availability': 'RETROSPECTIVE_DESCRIPTIVE_ONLY'}
