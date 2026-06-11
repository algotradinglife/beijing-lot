from src.sp_drift.panel import minutes_to_kickoff


def test_mtk_treats_kickoff_as_beijing_and_snapshot_as_utc():
    # snapshot 11:35Z = 19:35 Beijing == kickoff → MTK 0
    assert minutes_to_kickoff("2026-06-09T11:35:00Z", "2026-06-09T19:35:00") == 0.0


def test_mtk_positive_before_kickoff():
    # one hour earlier in UTC → 60 min before kickoff
    assert minutes_to_kickoff("2026-06-09T10:35:00Z", "2026-06-09T19:35:00") == 60.0


def test_mtk_negative_after_kickoff():
    assert minutes_to_kickoff("2026-06-09T12:35:00Z", "2026-06-09T19:35:00") == -60.0


def test_mtk_handles_naive_snapshot_as_utc():
    # no Z suffix → treated as UTC
    assert minutes_to_kickoff("2026-06-09T10:35:00", "2026-06-09T19:35:00") == 60.0
