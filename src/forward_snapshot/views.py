"""Causal derived views for Issue #248 prospective observations."""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

import pandas as pd

from .store import SnapshotStore, _canonical_utc, _iso, _utc


VIEW_COLUMNS = [
    "issue_code", "match_idx", "fixture_key", "native_handicap_line", "sale_status",
    "outcome_code", "sp", "source_changed_at_utc", "trusted_received_at_utc",
    "decision_at_utc", "view_kind", "minutes_to_kickoff", "capture_key",
]


def _eligible_vectors(store: SnapshotStore, *, issue: str, match_idx: int,
                      decision_at_utc: str, kickoff_at_utc: str) -> list[dict]:
    """Return complete vectors whose source *and receive* clocks are causal."""
    decision_at_utc = _canonical_utc(decision_at_utc)
    kickoff_at_utc = _canonical_utc(kickoff_at_utc)
    rows = store.conn.execute("""
        SELECT r.capture_key,r.fixture_key,r.native_handicap_line,r.sale_status,
               r.trusted_received_at_utc,v.source_changed_at_utc,v.outcome_code,v.sp
        FROM capture_receipt r JOIN sp_change_vector v USING(capture_key)
        WHERE r.issue_code=? AND r.match_idx=?
          AND r.acquisition_result='OK'
          AND r.source_id='nowscore_bj_sp_change_typeid5'
          AND r.trusted_received_at_utc <= ?
          AND v.source_changed_at_utc <= ?
          AND r.trusted_received_at_utc < r.kickoff_at_utc
          AND v.source_changed_at_utc < r.kickoff_at_utc
        ORDER BY v.source_changed_at_utc DESC,r.trusted_received_at_utc DESC,r.capture_key DESC
    """, (issue, match_idx, decision_at_utc, decision_at_utc)).fetchall()
    grouped: dict[tuple[str, str], list[tuple]] = {}
    for row in rows:
        grouped.setdefault((row[0], row[5]), []).append(row)
    complete = [(key, values) for key, values in grouped.items()
                if {value[6] for value in values} == {"3", "1", "0"} and len(values) == 3]
    if not complete:
        return []
    # Deterministic nearest prior state: source time first, receipt and key break ties.
    _, selected = max(complete, key=lambda item: (item[0][1], item[1][0][4], item[0][0]))
    return [{
        "fixture_key": row[1], "native_handicap_line": row[2], "sale_status": row[3],
        "trusted_received_at_utc": row[4], "source_changed_at_utc": row[5],
        "outcome_code": row[6], "sp": row[7], "capture_key": row[0],
    } for row in sorted(selected, key=lambda row: ("3", "1", "0").index(row[6]))]


def _fixtures(store: SnapshotStore) -> list[tuple]:
    return store.conn.execute("""
        SELECT issue_code,match_idx,kickoff_at_utc FROM capture_receipt
        GROUP BY issue_code,match_idx,kickoff_at_utc ORDER BY issue_code,match_idx
    """).fetchall()


def materialize_relative_horizon_view(store: SnapshotStore, *, horizons_minutes: Iterable[int] = (600, 60)) -> pd.DataFrame:
    output: list[dict] = []
    for issue, match_idx, kickoff in _fixtures(store):
        for minutes in horizons_minutes:
            decision = _iso(_utc(kickoff) - timedelta(minutes=int(minutes)))
            for vector in _eligible_vectors(store, issue=issue, match_idx=match_idx,
                                            decision_at_utc=decision, kickoff_at_utc=kickoff):
                output.append({"issue_code": issue, "match_idx": match_idx, **vector,
                               "decision_at_utc": decision, "view_kind": f"relative_{minutes}m",
                               "minutes_to_kickoff": int(minutes)})
    return pd.DataFrame(output, columns=VIEW_COLUMNS)


def _schedule_only_epoch(store: SnapshotStore, issue: str) -> str | None:
    rows = store.conn.execute("""
        SELECT kickoff_at_utc FROM capture_receipt WHERE issue_code=? AND sale_status='OPEN'
        GROUP BY match_idx,kickoff_at_utc
    """, (issue,)).fetchall()
    if not rows:
        return None
    # Fallback is deliberately schedule/sale only: earliest still-sale-open kickoff - 120m.
    return _iso(min(_utc(row[0]) for row in rows) - timedelta(minutes=120))


def materialize_common_epoch_view(store: SnapshotStore, *, decision_epochs: dict[str, str] | None = None) -> pd.DataFrame:
    output: list[dict] = []
    passed = decision_epochs or {}
    issues = [row[0] for row in store.conn.execute("SELECT DISTINCT issue_code FROM capture_receipt ORDER BY issue_code")]
    for issue in issues:
        epoch = passed.get(issue) or _schedule_only_epoch(store, issue)
        if not epoch:
            continue
        epoch = _canonical_utc(epoch)
        for current_issue, match_idx, kickoff in (row for row in _fixtures(store) if row[0] == issue):
            # A shared issue epoch cannot ever be at/after an individual kickoff.
            if _utc(epoch) >= _utc(kickoff):
                continue
            for vector in _eligible_vectors(store, issue=current_issue, match_idx=match_idx,
                                            decision_at_utc=epoch, kickoff_at_utc=kickoff):
                output.append({"issue_code": issue, "match_idx": match_idx, **vector,
                               "decision_at_utc": epoch, "view_kind": "common_epoch",
                               "minutes_to_kickoff": int((_utc(kickoff) - _utc(epoch)).total_seconds() // 60)})
    return pd.DataFrame(output, columns=VIEW_COLUMNS)
