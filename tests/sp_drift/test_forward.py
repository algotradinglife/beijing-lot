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


from src.sp_drift.forward import LEDGER_COLS, append_ledger


def _row(run_date, arm, roi):
    return {"run_date": run_date, "arm": arm, "forward_start": "2026-06-13",
            "n_combos": 10, "n_hits": 1, "total_stake": 100.0, "total_pnl": roi * 100.0,
            "roi": roi, "max_dd": 0.1, "final_bankroll": 100000.0 + roi * 100.0}


def test_append_ledger_creates_then_appends(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    out = append_ledger([_row("2026-06-27", "C0", 0.2)], led)
    assert list(out.columns) == LEDGER_COLS
    assert set(out["run_date"]) == {"2026-06-20", "2026-06-27"}


def test_append_ledger_is_idempotent_per_run_date(tmp_path):
    led = tmp_path / "ledger.csv"
    append_ledger([_row("2026-06-20", "C0", 0.1)], led)
    # re-run same run_date with a corrected value → replaces, not duplicates
    out = append_ledger([_row("2026-06-20", "C0", 0.5)], led)
    sub = out[(out["run_date"] == "2026-06-20") & (out["arm"] == "C0")]
    assert len(sub) == 1 and abs(float(sub.iloc[0]["roi"]) - 0.5) < 1e-9
