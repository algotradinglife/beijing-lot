from __future__ import annotations

from pathlib import Path

from issue296.panel import (
    build_expert_panel,
    build_expert_registry,
    load_issue_features,
)


ROOT = Path(__file__).resolve().parents[2]


def test_registry_keeps_summary_only_candidate_out_of_training() -> None:
    registry = build_expert_registry()
    n7 = registry.set_index("expert_id").loc["N7_K16_WR"]
    assert n7["training_status"] == "SUMMARY_ONLY_INELIGIBLE"
    assert n7["estimand"] == "NO_TRUSTED_ISSUE_PATH"


def test_panel_distinguishes_no_bet_from_missing_support() -> None:
    features = load_issue_features(ROOT)
    panel, nuisance = build_expert_panel(ROOT)
    assert features["issue_year"].max() == 2023
    assert panel["issue_year"].max() == 2023
    assert panel.groupby(["issue", "expert_id"]).size().eq(1).all()
    assert panel.query("available and stake_unit_cny == 0").shape[0] > 0
    unavailable = panel.query("not available").groupby("expert_id").size()
    assert unavailable["FULL_CONTROL"] == 42
    assert unavailable["SMOOTH_M512"] == 42
    assert unavailable["Q_TAIL_M192"] == 42
    assert unavailable["Q_WOR_M64"] == 42
    assert unavailable["DIVERGENCE_Z100_K1"] == 42
    assert "RARE_LOGIT_TOP64" not in unavailable
    assert nuisance["seed"].nunique() == 3
