"""Read verified market projections; never read outcome labels or fit models."""
import hashlib
import json
from pathlib import Path


def read_total_draw_inputs(manifest_path, manifest_sha256):
    """Explicit hash manifest -> label-free JSON rows and source identities.

    One row per issue/slot/provider_id. Lambda units: expected goals. No writes.
    Missing fields, duplicate keys, invalid positive rates or changed bytes fail.
    """
    raw = Path(manifest_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest_sha256:
        raise ValueError('Manifest hash mismatch')
    manifest = json.loads(raw)
    rows, seen = [], set()
    for item in manifest['sources']:
        raw = Path(item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Projection hash mismatch')
        data = json.loads(raw)
        for f in data['fixtures']:
            key = (f['issue'], f['slot'], f['provider_id'])
            if key in seen or not isinstance(key[0], str) or not isinstance(key[2], str):
                raise ValueError('Duplicate or invalid identity')
            seen.add(key)
            total = f['lambda_home'] + f['lambda_away']
            if not 0 < f['lambda_home'] < 100 or not 0 < f['lambda_away'] < 100:
                raise ValueError('Invalid expected goals')
            rows.append(dict(issue=f['issue'], slot=f['slot'], provider_id=f['provider_id'],
                handicap=f['handicap'], q_W=f['q_W'], q_D=f['q_D'], q_L=f['q_L'],
                lambda_total=total, fixture_decision_ts=f['cutoff_utc'],
                last_fixture_cutoff=max(data['cutoffs'][f['issue']].values())))
    if not rows:
        raise ValueError('Empty projection')
    return json.dumps(dict(rows=rows, sources=manifest['sources']), allow_nan=False)
