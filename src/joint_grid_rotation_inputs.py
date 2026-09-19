"""Small verified post-freeze membership projection for settlement diagnostics."""
import json
from src.strategy_diagnostic_inputs import read_verified_bundle_json


def read_rotation_members_json(path, sha256):
    """Read/hash the same bytes; retain issue, fixtures and sleeve membership only.

    No fetching, writes, probability selection or label access. Full raw bundle
    identity is supplied by the frozen allocation receipt, not guessed by age.
    """
    b=json.loads(read_verified_bundle_json(path,sha256))
    return json.dumps(dict(issue=b['issue'],fixtures=b['expanded_pool']['fixtures'],
        sleeves=[dict(id=g['id'],fixture_indices=g['fixture_indices']) for g in b['sleeves']]))
