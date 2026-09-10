"""Validate explicit owner decisions; no inference, fetching or raw mutation."""


def fixture_decisions(fixtures, decisions):
    """Return slot-keyed approved diagnostics policy bound to native identities.

    Each row requires issue/slot/provider_id/reason and exactly one of an exact
    Titan kickoff UTC, ALL_VENUES history mode, positive minimum, or exclusion.
    Unknown/duplicate/mismatched rows fail. None means no approved exceptions.
    No decisions authorize historical learning or alter the explicit cutoff.
    """
    lookup = {f['slot']: f for f in fixtures}
    result = {}
    for d in decisions or []:
        required = {'issue', 'slot', 'provider_id', 'reason'}
        actions = {'titan_kickoff_utc', 'history_mode', 'minimum', 'exclude'}
        if not isinstance(d, dict) or not required <= d.keys() or set(d)-required-actions or len(set(d)&actions)!=1:
            raise ValueError('Invalid adjudication fields')
        f = lookup.get(d['slot'])
        if f is None or type(d['slot']) is not int or d['slot'] in result or any(d[k]!=f[k] for k in ('issue','provider_id')):
            raise ValueError('Adjudication identity mismatch or duplicate')
        if not isinstance(d['reason'],str) or not d['reason'].strip():
            raise ValueError('Adjudication reason required')
        if 'minimum' in d and (type(d['minimum']) is not int or d['minimum']<2):
            raise ValueError('Invalid adjudicated minimum')
        if 'history_mode' in d and d['history_mode']!='ALL_VENUES':
            raise ValueError('Invalid adjudicated history mode')
        if 'exclude' in d and d['exclude'] is not True:
            raise ValueError('Invalid exclusion')
        if 'titan_kickoff_utc' in d:
            from datetime import datetime
            dt = datetime.fromisoformat(d['titan_kickoff_utc'])
            if dt.utcoffset() is None:
                raise ValueError('Adjudicated kickoff requires timezone')
        result[d['slot']] = dict(d)
    return result
