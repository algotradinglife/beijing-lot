"""Kickoff-bucketed execution: split a 北单 issue's matches into time buckets so
each batch can be planned/placed near its own kickoff (less SP drift) instead of
one global 7-day plan. Bucket labels feed issue+bucket plan ids.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from src.live_collector.db import SCHEMA as LIVE_SCHEMA
from src.webui.db import WebuiDB
from src.webui.strategies import apply_strategy
from src.webui.services import (
    assign_kickoff_buckets,
    generate_bucketed_plans,
    kickoff_bucket_label,
)


class _S:
    def __init__(self, kickoff_ts, issue="26065"):
        self.kickoff_ts = kickoff_ts
        self.issue = issue


def test_bucket_label_floors_to_block_6h():
    # 6h blocks start at 00/06/12/18. 19:30 -> the 18h block of that date.
    assert kickoff_bucket_label("2026-06-12T19:30:00", 6.0) == "0612-18h"
    assert kickoff_bucket_label("2026-06-12T05:59:00", 6.0) == "0612-00h"
    assert kickoff_bucket_label("2026-06-12T12:00:00", 6.0) == "0612-12h"


def test_bucket_label_different_days_distinct():
    a = kickoff_bucket_label("2026-06-12T20:00:00", 6.0)
    b = kickoff_bucket_label("2026-06-13T20:00:00", 6.0)
    assert a != b


def test_assign_groups_by_bucket():
    snaps = [
        _S("2026-06-12T19:30:00"), _S("2026-06-12T20:10:00"),
        _S("2026-06-12T13:00:00"), _S("2026-06-13T09:00:00"),
    ]
    buckets = assign_kickoff_buckets(snaps, 6.0)
    assert set(buckets) == {"0612-18h", "0612-12h", "0613-06h"}
    assert len(buckets["0612-18h"]) == 2


def test_assign_skips_blank_kickoff():
    snaps = [_S(None), _S(""), _S("2026-06-12T19:30:00")]
    buckets = assign_kickoff_buckets(snaps, 6.0)
    assert list(buckets) == ["0612-18h"]


def test_generate_bucketed_plans_tags_issue_and_bucket(tmp_path):
    # Two matches in distinct 6h kickoff buckets of the same issue must yield
    # two independent plans whose ids carry issue + bucket.
    now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    live = tmp_path / "live.db"
    conn = sqlite3.connect(live)
    conn.executescript(LIVE_SCHEMA)
    # kickoff_ts is naive Beijing; put them in 12h and 18h blocks, future.
    for mid, ko in [("26999_001", "2026-06-03T13:00:00"),
                    ("26999_002", "2026-06-03T19:00:00")]:
        conn.execute(
            "INSERT INTO matches(match_id,issue,match_idx,league,kickoff_ts,"
            "home,away,handicap_line,status) VALUES (?,?,?,?,?,?,?,?,?)",
            (mid, "26999", int(mid[-1]), "英超", ko, "H", "A", 1.0, "open"))
        conn.execute(
            "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0,source) "
            "VALUES (?,?,?,?,?,?)",
            (mid, "2026-06-01T00:00:00Z", 4.0, 3.4, 3.4, "test"))
    conn.commit()
    conn.close()

    db = WebuiDB(tmp_path / "webui.db")
    db.initialize(100000.0)
    apply_strategy(db, "S9")  # production mix path (where bucket id is tagged)

    plans = generate_bucketed_plans(
        db, live_db_path=str(live), plans_dir=str(tmp_path / "plans"),
        bucket_hours=6.0, now=now)

    ids = [p.get("plan_id") for p in plans if p.get("plan_id")]
    assert len(ids) == 2
    assert all(pid.startswith("26999-") for pid in ids)
    assert ids[0] != ids[1]
    assert any("0603-12h" in pid for pid in ids)
    assert any("0603-18h" in pid for pid in ids)
