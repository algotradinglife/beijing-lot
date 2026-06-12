import pandas as pd

from src.sp_drift.replay import decision_snapshots


def _panel():
    # match A, two selections present at the decision snapshot (MTK 60)
    return pd.DataFrame({
        "match_id": ["A", "A", "A"],
        "selection": ["3", "1", "0"],
        "sp": [2.5, 3.4, 4.0],
        "mtk": [60.0, 60.0, 60.0],
        "issue": ["26099", "26099", "26099"],
        "match_idx": [1, 1, 1],
        "league": ["英超", "英超", "英超"],
        "kickoff_ts": ["2026-06-09T19:35:00"] * 3,
        "handicap_line": [-1.0, -1.0, -1.0],
    })


def test_decision_snapshots_pivots_to_livesnapshot(tmp_path):
    snaps = decision_snapshots(_panel(), mtk_target=30)
    assert len(snaps) == 1
    s = snaps[0]
    assert s.match_id == "A"
    assert s.sp_3 == 2.5 and s.sp_1 == 3.4 and s.sp_0 == 4.0
    assert s.league == "英超" and s.handicap_line == -1.0
    assert s.issue == "26099"
