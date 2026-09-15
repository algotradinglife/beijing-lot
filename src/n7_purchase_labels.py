"""Post-freeze identity binding; parsing and official SP querying stay upstream."""


def bind_purchase_roster_labels(issue, fixtures, inventory, outcomes, cohort):
    """Bind parsed roster results to frozen fixture identities, preserving order.

    All row collections are lists keyed by integer slot; inventory includes
    provider_id/home/away and outcomes include actual_home/actual_away/result_state.
    Missing results remain missing for later settlement eligibility checks.
    No I/O, learning, label-availability inference, score correction or SP mapping.
    Caller must enforce the pre-label freeze/replay gate before obtaining outcomes.
    Duplicate slots, missing identities or mismatched provider IDs raise ValueError.
    """
    if not isinstance(issue, str) or not issue or not isinstance(cohort, str) or not cohort:
        raise ValueError('Explicit native issue and cohort required')
    indexed = []
    for rows in (fixtures, inventory, outcomes):
        if not isinstance(rows, list):
            raise ValueError('Explicit row lists required')
        lookup = {}
        for row in rows:
            slot = row.get('slot')
            if type(slot) is not int or slot < 1 or slot in lookup:
                raise ValueError('Unique positive integer slots required')
            lookup[slot] = row
        indexed.append(lookup)
    frozen, native, observed = indexed
    if not set(frozen) <= set(native) or not set(frozen) <= set(observed):
        raise ValueError('Missing roster fixture identity or result row')
    result = []
    for slot, fixture in frozen.items():
        row, outcome = native[slot], observed[slot]
        provider = fixture.get('provider_id')
        if (fixture.get('issue') != issue or provider is None or row.get('provider_id') is None
                or str(row.get('provider_id')) != str(provider)):
            raise ValueError('Outcome native identity mismatch')
        result.append(dict(issue=issue, slot=slot, provider_id=provider,
            handicap=fixture['handicap'], home=row['home'], away=row['away'],
            actual_home=outcome['actual_home'], actual_away=outcome['actual_away'],
            result_state=outcome['result_state'], cohort=cohort))
    return result
