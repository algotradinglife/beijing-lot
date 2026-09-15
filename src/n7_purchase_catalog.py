"""Pure catalog composition for a manually frozen diagnostic issue universe."""
import re
from src.n7_study_scope import n7_study_scope


def merge_purchase_catalogs(catalogs, scopes, requested_issues):
    """Merge explicitly scoped catalogs, retaining missing-data reasons.

    Each input catalog is parsed metadata whose byte/source verification belongs
    to the caller. Scopes are native string issue lists fixed before settlement;
    a subset can select the original reference cohort from a larger archive.
    Returns ordered issue bindings and an exact full-scope partition. No I/O,
    label access, fitting, selection, or mutation. Invalid identities, conflicting
    ownership, malformed hashes, and unexplained missing issues raise ValueError.
    """
    if not isinstance(catalogs, list) or not catalogs or len(catalogs) != len(scopes):
        raise ValueError('Paired nonempty catalogs and scopes required')
    entries, missing, claimed = {}, {}, []
    for catalog, scope in zip(catalogs, scopes):
        n7_study_scope(scope, scope, {})
        rows = catalog['issues']
        if not isinstance(rows, list):
            raise ValueError('Catalog issue rows must be a list')
        by_issue = {}
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('issue'), str)
                    or not row['issue'] or row['issue'] in by_issue):
                raise ValueError('Unique native catalog issue identity required')
            by_issue[row['issue']] = row
        unavailable = catalog.get('unavailable', {})
        modeled = [issue for issue in scope if issue in by_issue]
        absent = {issue: unavailable[issue] for issue in scope if issue in unavailable}
        n7_study_scope(scope, modeled, absent)
        for issue in scope:
            if issue in claimed:
                raise ValueError('Issue is owned by more than one catalog scope')
            claimed.append(issue)
        for issue in modeled:
            row = by_issue[issue]
            if (not isinstance(row.get('path'), str) or not row['path']
                    or not isinstance(row.get('sha256'), str)
                    or re.fullmatch('[0-9a-f]{64}', row['sha256']) is None):
                raise ValueError('Explicit bundle path and SHA-256 required')
            entries[issue] = dict(row)
        missing.update(absent)
    partition = n7_study_scope(requested_issues, list(entries), missing)
    if set(claimed) != set(requested_issues):
        raise ValueError('Catalog ownership differs from requested scope')
    return dict(issues=[entries[i] for i in partition['modeled_issues']],
                requested_issues=list(requested_issues), unavailable=missing,
                unavailable_issues=partition['unavailable_issues'], historical_admission=False)
