import pandas as pd

from src.sp_drift.forward import FORWARD_START, HAIRCUT_MAP, build_arms, forward_panel


def test_forward_panel_keeps_only_kickoffs_after_start():
    panel = pd.DataFrame({
        "match_id": ["A", "B"],
        "kickoff_ts": ["2026-06-10T19:00:00", "2026-06-20T19:00:00"],
        "sp": [4.0, 4.0],
    })
    out = forward_panel(panel, "2026-06-13")
    assert list(out["match_id"]) == ["B"]


def test_build_arms_three_arms_with_expected_policies():
    arms = build_arms(baseline_mtk=1080.0, haircut_map=HAIRCUT_MAP)
    names = [n for n, _ in arms]
    assert names == ["C0", "C1", "C2"]
    by = dict(arms)
    assert by["C0"].mtk_target == 1080.0 and by["C0"].haircut is None
    assert by["C1"].mtk_target == 180.0 and by["C1"].haircut is None
    assert by["C2"].mtk_target == 180.0 and by["C2"].haircut == HAIRCUT_MAP


def test_haircut_map_is_frozen_gate1_values():
    assert HAIRCUT_MAP["5-8"] == -0.36 and HAIRCUT_MAP["<3.5"] == 0.33
