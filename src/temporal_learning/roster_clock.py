"""Resolve source-published roster clocks for retrospective fixture matching."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .core import utc,stable_json_hash


def roster_clock_alignment(fixture, source_times, *, cutoff, timezone, midnight_hours):
    """Use roster HH:MM on first occurrence at/after its dated sale deadline.

    date_group is a display grouping, not a full calendar timestamp. Return
    canonical UTC and source day-discrepancy ledger; same-date hour differences
    pass, adjacent midnight crossings pass only within explicit midnight_hours.
    No quote timestamps/cutoffs are changed. Missing clocks fail. Diagnostic only.
    """
    if not 0<midnight_hours<=12:raise ValueError('Invalid midnight boundary')
    zone=ZoneInfo(timezone)
    if cutoff.target_issue!=fixture['issue']:raise ValueError('Roster cutoff issue mismatch')
    deadline=datetime.strptime(fixture['deadline_text'].split('：',1)[-1].strip(),'%Y-%m-%d %H:%M').replace(tzinfo=zone)
    if cutoff.cutoff_ts>utc(deadline):raise ValueError('Cutoff after roster deadline')
    canonical=datetime.combine(deadline.date(),datetime.strptime(fixture['clock'],'%H:%M').time(),tzinfo=zone)
    if canonical<deadline:canonical+=timedelta(days=1)
    ledger=[]
    for source,value in source_times.items():
        if value is None:raise ValueError('Missing source time')
        time=utc(value).to_pydatetime().astimezone(zone);hours=(time-canonical).total_seconds()/3600
        different=time.date()!=canonical.date()
        ledger.append(dict(source=source,original_time=value,delta_hours=hours,day_conflict=different and abs(hours)>=midnight_hours))
    return dict(canonical_kickoff_utc=utc(canonical).isoformat(),policy='ROSTER_DATE_ALIGNMENT',
        status='DAY_MISMATCH' if any(r['day_conflict'] for r in ledger) else 'ALIGNED',source_times=ledger,
        timezone=timezone,midnight_hours=midnight_hours,cutoff_identity=cutoff.identity,
        roster_sha256=stable_json_hash(fixture),historical_admission=False)
