"""Deterministic Hong-Kong natural-day segment contract (BJ-SEG-DAY-001)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo


HKT = ZoneInfo("Asia/Hong_Kong")
POLICY_ID = "BJ-SEG-DAY-001/natural_day_v1"
MIN_MATCHES = 20
MAX_MERGE_SPAN = timedelta(hours=36)
FREEZE_LEAD = timedelta(minutes=25)


@dataclass(frozen=True)
class SegmentMembership:
    segment_idx: int
    match_indices: tuple[int, ...]
    first_kickoff: datetime
    last_kickoff: datetime
    freeze_at: datetime
    hkt_dates: tuple[str, ...]


@dataclass(frozen=True)
class SegmentBuildResult:
    issue: str
    segments: tuple[SegmentMembership, ...]
    skipped: tuple[dict[str, Any], ...]
    denominator_match_indices: tuple[int, ...]


def _as_hkt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=HKT)
    return value.astimezone(HKT)


def build_natural_day_segments(issue: str, matches: Iterable[Any]) -> SegmentBuildResult:
    """Build the only operational membership boundary used by all consumers.

    ``matches`` need only expose ``match_idx`` and ``kickoff``.  This deliberately
    never returns an entire-issue fallback segment: uncovered day groups are
    represented in ``skipped`` with their complete denominator.
    """
    ordered = sorted(matches, key=lambda item: (_as_hkt(item.kickoff), int(item.match_idx)))
    denominator = tuple(int(item.match_idx) for item in ordered)
    if len(ordered) < MIN_MATCHES:
        return SegmentBuildResult(str(issue), (), ({
            "reason": "skipped_insufficient_issue_matches", "match_indices": list(denominator),
            "match_count": len(denominator), "minimum_matches": MIN_MATCHES,
        },), denominator)

    days: list[list[Any]] = []
    for item in ordered:
        if not days or _as_hkt(days[-1][0].kickoff).date() != _as_hkt(item.kickoff).date():
            days.append([])
        days[-1].append(item)

    accepted: list[list[Any]] = []
    skipped: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(days):
        group = list(days[cursor])
        # A qualified natural day stands alone unless it is consumed by the
        # preceding undersized day, which is the policy's forward-merge rule.
        if len(group) >= MIN_MATCHES:
            accepted.append(group)
            cursor += 1
            continue
        while len(group) < MIN_MATCHES and cursor + 1 < len(days):
            candidate = group + days[cursor + 1]
            span = _as_hkt(candidate[-1].kickoff) - _as_hkt(candidate[0].kickoff)
            if span > MAX_MERGE_SPAN:
                break
            group = candidate
            cursor += 1
        if len(group) >= MIN_MATCHES:
            accepted.append(group)
        elif accepted:
            # The final small day group is merged backwards when allowed.
            candidate = accepted[-1] + group
            span = _as_hkt(candidate[-1].kickoff) - _as_hkt(candidate[0].kickoff)
            if span <= MAX_MERGE_SPAN:
                accepted[-1] = candidate
            else:
                skipped.append({"reason": "skipped_insufficient_segment_matches", "match_indices": [int(x.match_idx) for x in group], "match_count": len(group), "merge_span_hours": round(span.total_seconds() / 3600, 6), "maximum_merge_span_hours": 36})
        else:
            first, last = _as_hkt(group[0].kickoff), _as_hkt(group[-1].kickoff)
            skipped.append({"reason": "skipped_insufficient_segment_matches", "match_indices": [int(x.match_idx) for x in group], "match_count": len(group), "merge_span_hours": round((last - first).total_seconds() / 3600, 6), "maximum_merge_span_hours": 36})
        cursor += 1

    segments = tuple(
        SegmentMembership(
            segment_idx=index,
            match_indices=tuple(int(item.match_idx) for item in group),
            first_kickoff=_as_hkt(group[0].kickoff), last_kickoff=_as_hkt(group[-1].kickoff),
            freeze_at=_as_hkt(group[0].kickoff) - FREEZE_LEAD,
            hkt_dates=tuple(dict.fromkeys(_as_hkt(item.kickoff).date().isoformat() for item in group)),
        )
        for index, group in enumerate(accepted, 1)
    )
    covered = [idx for segment in segments for idx in segment.match_indices]
    skipped_indices = [idx for row in skipped for idx in row["match_indices"]]
    if len(covered) != len(set(covered)) or sorted(covered + skipped_indices) != sorted(denominator):
        raise ValueError("natural-day segment contract failed closed: incomplete or overlapping membership")
    return SegmentBuildResult(str(issue), segments, tuple(skipped), denominator)
