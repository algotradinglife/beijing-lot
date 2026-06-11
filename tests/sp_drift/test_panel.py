import pandas as pd

from src.sp_drift.panel import build_snapshot_panel, minutes_to_kickoff


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


def test_snapshot_panel_unpivots_three_selections(live_db):
    panel = build_snapshot_panel(live_db)
    # 3 pre-kickoff snapshots for A x 3 selections = 9, plus 2 for B x 3 = 6 → 15
    assert len(panel) == 15
    assert set(panel["selection"].unique()) == {"3", "1", "0"}


def test_snapshot_panel_drops_post_kickoff(live_db):
    panel = build_snapshot_panel(live_db)
    assert (panel["mtk"] > 0).all()
    # the 13:00Z row of match A is post-kickoff → gone
    assert not ((panel["match_id"] == "A") & (panel["snapshot_ts"] == "2026-06-09T13:00:00Z")).any()


def test_snapshot_panel_attaches_labels(live_db):
    panel = build_snapshot_panel(live_db)
    a = panel[panel["match_id"] == "A"].iloc[0]
    assert a["league_bucket"] == "Top5EU"   # 英超
    assert a["hcp_class"] == "h1"            # |-1.0|
    assert a["comp_type"] == "league"


from src.sp_drift.panel import attach_final_and_settlement


def test_final_sp_is_last_pre_kickoff_snapshot(live_db):
    panel = build_snapshot_panel(live_db)
    dec = attach_final_and_settlement(panel, live_db)
    # one row per (match, selection)
    a0 = dec[(dec["match_id"] == "A") & (dec["selection"] == "0")].iloc[0]
    assert a0["final_sp"] == 3.0      # closing snapshot (MTK 10), not the dropped post-kickoff one
    assert a0["is_winner"]            # away won
    assert a0["winning_sp"] == 3.0


def test_final_sp_matches_winning_sp_for_winners(live_db):
    """Anchor: closing pre-kickoff SP should equal settlement winning_sp for winners."""
    panel = build_snapshot_panel(live_db)
    dec = attach_final_and_settlement(panel, live_db)
    win = dec[dec["is_winner"]]
    rel = (win["final_sp"] - win["winning_sp"]).abs() / win["winning_sp"]
    assert (rel < 0.05).all()
