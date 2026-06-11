"""Phase 0 analysis substrate: build a tidy, MTK-indexed SP panel.

snapshot_ts is UTC (trailing 'Z'); kickoff_ts is Beijing time (UTC+8) with
no tz suffix. The collector keeps polling matches after kickoff (frozen SP),
so the panel keeps only pre-kickoff snapshots (MTK > 0).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def minutes_to_kickoff(snapshot_ts: str, kickoff_ts: str) -> float:
    """Minutes from a UTC snapshot to a Beijing-local kickoff. Positive = before."""
    snap = datetime.fromisoformat(snapshot_ts.replace("Z", "+00:00"))
    if snap.tzinfo is None:
        snap = snap.replace(tzinfo=timezone.utc)
    ko = datetime.fromisoformat(kickoff_ts)
    if ko.tzinfo is None:
        ko = ko.replace(tzinfo=BEIJING)
    return (ko - snap).total_seconds() / 60.0
