"""Bounded resolution of source month/day clocks for diagnostic quotes only."""
from datetime import datetime
from zoneinfo import ZoneInfo

from .core import utc, stable_json_hash
from .diagnostic_window import diagnostic_quote_window


def diagnostic_monthday_quotes(rows, *, anchor_utc, timezone, maximum_days,
                              cutoff, source_hashes, implementation_hashes):
    """Resolve a unique nearby year, filter strictly prior, keep latest/company.

    Rows require quote_id, company, quoted_local (M-D HH:MM), and market values.
    Anchor is independently checked fixture kickoff, not collection time. The
    explicit timezone is source display policy, not evidence of availability.
    Malformed/ambiguous clocks fail; valid clocks outside the horizon are
    excluded with their raw rows retained in the policy ledger. Same-minute ties use the lowest
    numeric source row prefix in quote_id (source HTML is newest-first).
    This source-order assumption does not establish second-level chronology.
    Returns selected rows plus the shared window receipt and selection ledger.
    Pure; no fitting, cache or I/O. All outputs remain HISTORICAL_PROXY.
    """
    if type(maximum_days) is not int or not 1 <= maximum_days < 180:
        raise ValueError('Invalid partial-clock horizon')
    anchor = utc(anchor_utc).to_pydatetime().astimezone(ZoneInfo(timezone))
    ids = [r['quote_id'] for r in rows]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Unique quote IDs required')
    resolved = []
    excluded = []
    for row in rows:
        candidates = []
        valid_clocks = []
        for year in (anchor.year-1, anchor.year, anchor.year+1):
            try:
                clock = datetime.strptime(f'{year}-{row["quoted_local"]}', '%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo(timezone))
            except ValueError:
                continue
            valid_clocks.append(clock)
            if abs((clock-anchor).total_seconds()) <= maximum_days*86400:
                candidates.append(clock)
        if not valid_clocks:
            raise ValueError('Malformed partial clock')
        if not candidates:
            excluded.append(dict(row=row.copy(), reason='OUTSIDE_ANCHOR_HORIZON'))
            continue
        if len(candidates) != 1:
            raise ValueError('Ambiguous partial clock')
        resolved.append(dict(row, quoted_at=candidates[0].isoformat()))
    window = diagnostic_quote_window(resolved, cutoff=cutoff,
        source_hashes=source_hashes, implementation_hashes=implementation_hashes)
    latest = {}
    ties = []
    for row in window['rows']:
        prefix = row['quote_id'].split('/', 1)[0]
        if not prefix.isdigit():
            raise ValueError('Numeric source row prefix required for quote order')
    ordered = sorted(window['rows'], key=lambda r: (utc(r['quoted_at']), -int(r['quote_id'].split('/', 1)[0])))
    seen_positions = set()
    for row in ordered:
        position = (row['company'], int(row['quote_id'].split('/', 1)[0]))
        if position in seen_positions:
            raise ValueError('Duplicate company/source row position')
        seen_positions.add(position)
        previous = latest.get(row['company'])
        if previous and previous['quoted_at'] == row['quoted_at']:
            ties.append(dict(company=row['company'], quoted_at=row['quoted_at'],
                selected_id=row['quote_id'], superseded_id=previous['quote_id']))
        latest[row['company']] = row
    return dict(rows=sorted(latest.values(), key=lambda r: r['company']),
        window=window, policy=dict(anchor_utc=anchor_utc, timezone=timezone,
        maximum_days=maximum_days, input_sha256=stable_json_hash(rows),
        excluded_outside_horizon=excluded, excluded_outside_horizon_count=len(excluded), selection='LATEST_PRIOR_PER_COMPANY',
        same_minute_policy='SOURCE_ROW_ASC_NEWEST_FIRST_ASSUMPTION', tie_ledger=ties,
        selected_ids=[r['quote_id'] for r in sorted(latest.values(),key=lambda r:r['company'])]))
