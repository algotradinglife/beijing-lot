"""Read frozen #425 inputs for post-settlement diagnosis, never for selection."""
import gzip
import hashlib
import json
from pathlib import Path


def load_rank_issue(study, issue):
    """Return compact JSON for one issue, verifying freeze/evaluation byte bindings.

    Paths explicit; no network or writes. Missing, altered or ambiguous inputs
    fail. Retains frozen rank order, ordered fixture identities, actual audit rows
    and cutoffs. Actual labels are intentionally diagnostic-only.
    """
    root = Path(study)
    freeze_raw = (root / 'plans-frozen.json').read_bytes()
    audit_raw = (root / 'audit-snapshot.json').read_bytes()
    receipt = json.loads((root / 'evaluation-receipt.json').read_text())
    for name, raw in [('freeze', freeze_raw), ('audit', audit_raw)]:
        if hashlib.sha256(raw).hexdigest() != receipt[f'{name}_sha256']:
            raise ValueError(f'{name} binding mismatch')
    frozen = json.loads(freeze_raw)
    if issue not in frozen['receipt']['issues']:
        raise ValueError('Unknown issue')
    objects = []
    for key in ['raw_hashes', 'source_hashes']:
        matches = [(p, h) for p, h in frozen['receipt'][key].items()
                   if Path(p).name == f'{issue}.json.gz']
        if len(matches) != 1:
            raise ValueError('Ambiguous issue input')
        path, expected = matches[0]
        raw = Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Source hash mismatch')
        objects.append(json.loads(gzip.decompress(raw)))
    raw, bundle = objects
    if (raw['issue'] != issue or bundle['issue'] != issue or
            raw['cutoffs'] != bundle['cutoffs'] or
            raw['historical_admission'] is not False):
        raise ValueError('Issue/cutoff mismatch')
    return json.dumps(dict(issue=issue, cutoffs=bundle['cutoffs'],
        curves=raw['curves'], fixtures=bundle['expanded_pool']['fixtures'],
        sleeves=[{k: s[k] for k in ['id', 'fixture_indices', 'origin']}
                 for s in bundle['sleeves']],
        audit=[r for r in json.loads(audit_raw)['rows'] if str(r['issue']) == issue],
        freeze_seal=frozen['seal'], evidence_class='POST_SETTLEMENT_DIAGNOSTIC'),
        allow_nan=False)
