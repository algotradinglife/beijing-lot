"""Explicit diagnostic scope exclusions; no source corrections or inference."""


def exclude_n7_research_fixtures(rows, exclusions, roster_hashes):
    """Return retained rows and a bound exclusion ledger without changing inputs.

    Each exclusion requires string issue, positive integer slot, nonempty reason,
    and roster_sha256 matching the caller's verified roster hashes. Every declared
    fixture must exist. All its market rows are excluded together. Empty policies
    retain all rows. Missing/duplicate declarations or stale hashes raise.
    This is an explicit retrospective eligibility operation, not a learned gate.
    No I/O, labels, probability changes, or source-data writes occur.
    """
    keys = {(row['issue'], row['slot']) for row in rows}
    declared = set()
    ledger = []
    for item in exclusions:
        issue, slot = item['issue'], item['slot']
        if (not isinstance(issue, str) or not issue or type(slot) is not int
                or slot < 1 or not isinstance(item.get('reason'), str)
                or not item['reason'].strip()):
            raise ValueError('Explicit fixture identity and exclusion reason required')
        key = (issue, slot)
        if key in declared or key not in keys:
            raise ValueError('Duplicate or absent excluded fixture')
        if (not item.get('roster_sha256')
                or roster_hashes.get(issue) != item['roster_sha256']):
            raise ValueError('Excluded fixture roster binding mismatch')
        declared.add(key)
        ledger.append({**item, 'excluded_market_rows': sum(
            (row['issue'], row['slot']) == key for row in rows)})
    return ([row for row in rows if (row['issue'], row['slot']) not in declared], ledger)
