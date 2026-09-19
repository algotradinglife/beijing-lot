"""Post-freeze roster binding for an incremental strategy replay; no SP lookup."""
import hashlib
import json
from pathlib import Path
from .fundamentals_census import read_response
from .fundamentals_issue_pages import issue_analysis_pages
from .fundamentals_home_away import roster_observed_results
from .n7_purchase_labels import bind_purchase_roster_labels


def read_extension_labels(plan_path, plan_sha256, roster_path, roster_sha256):
    """Verify immutable plans and roster bytes before extracting target outcomes.

    Plan binds issue, all frozen fixture identities, six replayed policy plans,
    and native cutoff. Returns JSON rows for the authoritative R SQLite audit.
    Missing hashes, incomplete freeze, or changed source bytes raise ValueError.
    """
    raw = Path(plan_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != plan_sha256:
        raise ValueError('Frozen plan hash mismatch')
    plan = json.loads(raw)
    if (plan['status'] != 'FROZEN_REPLAYED' or plan['historical_admission'] is not False
            or set(plan['plans']) != {'BASE','ORIGINAL','PROB','EV','PROB_CAP','EV_CAP'}
            or plan['cutoff']['target_issue'] != plan['issue']
            or plan['roster_sha256'] != roster_sha256):
        raise ValueError('Incomplete pre-label freeze')
    path = Path(roster_path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != roster_sha256:
        raise ValueError('Roster hash mismatch')
    meta, html = read_response(path)
    slots = [f['slot'] for f in plan['fixtures']]
    inventory = issue_analysis_pages(html, roster_url=meta['url'], issue=plan['issue'], slots=slots)
    outcomes = roster_observed_results(path, issue=plan['issue'], slots=slots)
    rows = bind_purchase_roster_labels(plan['issue'], plan['fixtures'], inventory, outcomes, 'NEW50')
    if hashlib.sha256(path.read_bytes()).hexdigest() != roster_sha256:
        raise ValueError('Roster changed during parsing')
    return json.dumps(rows, ensure_ascii=False, allow_nan=False)
