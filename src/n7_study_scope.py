"""Validate declared study denominators without reading outcomes or choosing bets."""


def n7_study_scope(requested_issues, modeled_issues, unavailable):
    """Return ordered full, modeled and unavailable issue inventories.

    Inputs are unique native string IDs and an issue -> nonempty reason mapping.
    Modeled and unavailable issues must partition the requested scope exactly.
    Missing data is not a losing ticket or a no-bet strategy decision. This pure
    boundary validator neither fits nor selects, and has no I/O or side effects.
    Invalid or overlapping inventories raise ValueError rather than drop periods.
    """
    for values in (requested_issues, modeled_issues):
        if (not isinstance(values, list) or
                any(not isinstance(x, str) or not x for x in values) or
                len(set(values)) != len(values)):
            raise ValueError('Unique ordered native issue strings required')
    if not requested_issues or not isinstance(unavailable, dict):
        raise ValueError('Explicit full scope and unavailable reasons required')
    if any(not isinstance(v, str) or not v.strip() for v in unavailable.values()):
        raise ValueError('Every unavailable issue requires a reason')
    modeled = set(modeled_issues)
    missing = set(unavailable)
    if modeled & missing or modeled | missing != set(requested_issues):
        raise ValueError('Modeled and unavailable issues must partition full scope')
    return dict(requested_issues=list(requested_issues),
                modeled_issues=[i for i in requested_issues if i in modeled],
                unavailable_issues=[dict(issue=i, status='NOT_EVALUABLE', reason=unavailable[i])
                                    for i in requested_issues if i in missing])
