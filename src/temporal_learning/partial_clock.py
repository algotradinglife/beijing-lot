"""Bounded resolution of source month/day clocks for diagnostic quotes only."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .core import utc
from .diagnostic_window import diagnostic_quote_window


def diagnostic_monthday_quotes(rows, *, anchor_utc, timezone, maximum_days,
                              cutoff, source_hashes, implementation_hashes):
    """Resolve a unique nearby year, filter strictly prior, keep latest/company.

    Rows require quote_id, company, quoted_local (M-D HH:MM), and market values.
    Anchor is independently checked fixture kickoff, not collection time. The
    explicit timezone is source display policy, not evidence of availability.
    Ambiguous/out-of-bound clocks and conflicting same-minute prices fail.
    Returns selected rows plus the shared window receipt and selection ledger.
    Pure; no fitting, cache or I/O. All outputs remain HISTORICAL_PROXY.
    """
    if type(maximum_days) is not int or not 1 <= maximum_days < 180:
        raise ValueError('Invalid partial-clock horizon')
    anchor = utc(anchor_utc).to_pydatetime().astimezone(ZoneInfo(timezone))
    resolved = []
    for row in rows:
        candidates = []
        for year in (anchor.year-1, anchor.year, anchor.year+1):
            try:
                clock = datetime.strptime(f'{year}-{row["quoted_local"]}', '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(timezone))
            except ValueError:
                continue
            if abs((clock-anchor).total_seconds()) <= maximum_days*86400:
                candidates.append(clock)
        if len(candidates) != 1:
            raise ValueError('Missing/ambiguous/out-of-bound partial clock')
        resolved.append(dict(row, quoted_at=candidates[0].isoformat()))
    window = diagnostic_quote_window(resolved, cutoff=cutoff,
        source_hashes=source_hashes, implementation_hashes=implementation_hashes)
    latest = {}
    for row in sorted(window['rows'], key=lambda r: (utc(r['quoted_at']), r['quote_id'])):
        previous = latest.get(row['company'])
        if previous and previous['quoted_at'] == row['quoted_at']:
            if any(previous[k] != row[k] for k in ('line', 'over_hk', 'under_hk')):
                raise ValueError('Conflicting same-minute company quotes')
        latest[row['company']] = row
    return dict(rows=sorted(latest.values(), key=lambda r: r['company']),
        window=window, policy=dict(anchor_utc=anchor_utc, timezone=timezone,
        maximum_days=maximum_days, selection='LATEST_PRIOR_PER_COMPANY',
        selected_ids=[r['quote_id'] for r in sorted(latest.values(),key=lambda r:r['company'])]))
