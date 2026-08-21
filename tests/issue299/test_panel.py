from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from issue299.panel import (
    RESIDUAL_EXPERTS,
    build_action_panel,
    build_support_receipt,
    load_baseline,
)

ROOT = Path(__file__).resolve().parents[2]


def test_exact_baseline_projection_is_atomic_and_pre_2024() -> None:
    baseline = load_baseline(ROOT)
    assert len(baseline) == 270
    assert baseline["issue_year"].max() == 2023
    active = baseline["stake_yuan"].gt(0)
    assert baseline.loc[active, "stake_yuan"].eq(4374.0).all()
    assert baseline.loc[active, "executed_ticket_count"].eq(2187).all()


def test_common_support_is_explicit_not_imputed() -> None:
    receipt = build_support_receipt(ROOT)
    assert receipt["support_status"].value_counts().to_dict() == {
        "MATCHED_BASELINE_AND_FEATURES": 227,
        "EXCLUDED_NO_EXACT_BEST_FULL": 42,
    }


def test_action_economics_are_exact_residuals() -> None:
    issues, actions = build_action_panel(ROOT)
    baseline = actions[actions["action"].eq("BASELINE_ONLY")].set_index("issue")
    cash = actions[actions["action"].eq("BASELINE_SCALE_DOWN")].set_index("issue")
    assert len(issues) == 227
    assert np.allclose(
        baseline["pnl_cny"], issues.set_index("issue")["baseline_pnl_cny"]
    )
    assert cash[["stake_cny", "pnl_cny", "gross_cny"]].eq(0).all(axis=None)
    assert np.allclose(cash["residual_pnl_cny"], -baseline["pnl_cny"])


def test_residual_sources_are_realisable_whole_ticket_bundles() -> None:
    _, actions = build_action_panel(ROOT)
    assert set(RESIDUAL_EXPERTS) == {
        "SMOOTH_M512",
        "DIVERGENCE_Z100_K1",
        "RARE_LOGIT_TOP64",
    }
    assert "Q_WOR_M64" not in set(RESIDUAL_EXPERTS)
    available = actions[actions["available"]]
    assert np.allclose(available["hits"], np.rint(available["hits"]))


def test_residual_source_registry_is_complete() -> None:
    manifest = json.loads(
        (ROOT / "evidence/bj299_residual_sources_v1/source_manifest.json").read_text()
    )
    assert {source["expert_id"] for source in manifest["residual_sources"]} == set(
        RESIDUAL_EXPERTS
    )
