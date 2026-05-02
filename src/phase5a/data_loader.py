"""Read open matches + latest SP snapshots from the Live Collector DB.

The Live Collector writes:
  - matches (one row per (issue, match_idx))
  - snapshots (append-only time series; latest row carries current SP)
  - settlements (after kaijiang)

For Phase 5a the planner only needs:
  - the latest SP_3 / SP_1 / SP_0 per match
  - kickoff in [now, now+window_days] (default 7)
  - status = 'open' (Live Collector's analogue of "未结算")
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class LiveSnapshot:
    """One match × latest 3-SP snapshot."""

    match_id: str
    issue: str
    match_idx: int
    league: Optional[str]
    kickoff_ts: str
    home: Optional[str]
    away: Optional[str]
    handicap_line: Optional[float]
    sp_3: Optional[float]
    sp_1: Optional[float]
    sp_0: Optional[float]
    snapshot_ts: Optional[str]


_LATEST_SQL = """
SELECT m.match_id, m.issue, m.match_idx, m.league, m.kickoff_ts,
       m.home, m.away, m.handicap_line,
       s.sp_3, s.sp_1, s.sp_0, s.snapshot_ts
FROM matches m
LEFT JOIN (
    SELECT s1.*
    FROM snapshots s1
    JOIN (
        SELECT match_id, MAX(snapshot_ts) AS mts
        FROM snapshots
        GROUP BY match_id
    ) s2 ON s1.match_id = s2.match_id AND s1.snapshot_ts = s2.mts
) s ON s.match_id = m.match_id
WHERE m.status = ?
  AND m.kickoff_ts >= ?
  AND m.kickoff_ts <  ?
ORDER BY m.kickoff_ts ASC, m.match_idx ASC
"""


def load_open_matches(
    db_path: str | Path,
    *,
    window_days: int = 7,
    now: Optional[datetime] = None,
    status: str = "open",
) -> List[LiveSnapshot]:
    """Return open matches kicking off within ``window_days``.

    The Live Collector schema uses ``status='open'`` for unsettled matches
    (the user-facing label is 未结算). The kickoff window is half-open:
    ``[now, now + window_days)``. Returns an empty list if the DB is empty
    or no matches qualify; callers must handle this gracefully.
    """
    p = Path(db_path)
    if not p.exists():
        return []
    now = now or datetime.now(timezone.utc)
    end = now + timedelta(days=window_days)
    # Live Collector kickoff_ts is a naive ISO string in local Beijing-ish
    # zone (e.g. "2026-05-01T01:00:00"). We compare lexicographically using
    # naive ISO from `now`/`end` — this is a stable string compare for the
    # same timezone convention. Use UTC-naive ISO; matches are within hours,
    # so window edge fuzziness ≤ 8h is acceptable for a 7-day plan.
    lo = now.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")
    hi = end.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")

    conn = sqlite3.connect(str(p))
    try:
        rows = conn.execute(_LATEST_SQL, (status, lo, hi)).fetchall()
    finally:
        conn.close()

    out: List[LiveSnapshot] = []
    for r in rows:
        out.append(
            LiveSnapshot(
                match_id=r[0], issue=r[1], match_idx=int(r[2]),
                league=r[3], kickoff_ts=r[4], home=r[5], away=r[6],
                handicap_line=(float(r[7]) if r[7] is not None else None),
                sp_3=(float(r[8]) if r[8] is not None else None),
                sp_1=(float(r[9]) if r[9] is not None else None),
                sp_0=(float(r[10]) if r[10] is not None else None),
                snapshot_ts=r[11],
            )
        )
    return out


def load_settlements(db_path: str | Path) -> dict[str, dict]:
    """Return {match_id: {result_code, winning_sp, fthg, ftag}} for all settlements."""
    p = Path(db_path)
    if not p.exists():
        return {}
    conn = sqlite3.connect(str(p))
    try:
        rows = conn.execute(
            "SELECT match_id, result_code, winning_sp, fthg, ftag FROM settlements"
        ).fetchall()
    finally:
        conn.close()
    return {
        r[0]: dict(result_code=str(r[1]) if r[1] is not None else None,
                   winning_sp=(float(r[2]) if r[2] is not None else None),
                   fthg=r[3], ftag=r[4])
        for r in rows
    }
