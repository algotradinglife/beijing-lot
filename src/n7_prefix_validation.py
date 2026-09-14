"""Descriptive #451 report completeness contract; no fitting or selection."""
def verify_summary_grid(rows, summary):
    """Require unique summary arm/seed keys equal to all result configurations.

    Pandas frames, no IO or mutation. Missing/null/duplicate keys and empty
    reports raise ValueError rather than silently accepting partial evidence.
    """
    keys=['arm','seed']
    if rows.empty or summary.empty or rows[keys].isna().any().any() or summary[keys].isna().any().any():
        raise ValueError('Missing report grid')
    if summary.duplicated(keys).any():
        raise ValueError('Duplicate summary configuration')
    actual=set(summary[keys].itertuples(index=False,name=None))
    expected=set(rows[keys].itertuples(index=False,name=None))
    if actual!=expected:
        raise ValueError('Incomplete summary configuration grid')
    return True
