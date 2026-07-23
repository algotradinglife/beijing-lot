from __future__ import annotations

from pathlib import Path

from src.decision_api import app as appmod


def test_paper_candidate_api_exposes_status_only(tmp_path: Path) -> None:
    client = appmod.create_app(sqlite_db=tmp_path / "empty.sqlite").test_client()

    response = client.get("/api/strategy-candidates")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["api_scope"] == "strategy_status_metadata_only"
    assert payload["candidates"] == [{
        "strategy_id": "shadow_n4_probability_weighted_512_v1",
        "status": "continue_paper_non_selectable",
        "execution_enabled": False,
        "frontend_selectable": False,
        "scope": "whole_issue",
        "n_value": 4,
        "budget_yuan": 512,
        "budget_units": 256,
        "unit_price_yuan": 2,
        "base_decision_chain": "shadow_v3.3.3",
        "ordering": "probability_weighted",
        "candidate_attempts": 3000,
        "seed_policy": "research_sensitivity_seeds_20260707_20260716_only",
        "evidence": {
            "settled_issues": ["26072", "26073", "26074"],
            "combined_weighted_roi": 0.278206,
            "combined_full_loss_rate": 0.0,
        },
        "activation_requirements": [
            "freeze one operational randomization policy or deterministic seed",
            "complete new-issue forward validation with the frozen candidate",
            "complete formal release review before any release manifest change",
        ],
    }]
    assert "tickets" not in payload
    assert "ticket_plan" not in payload["candidates"][0]


def test_paper_candidate_is_not_exposed_by_release_or_strategy_lab(tmp_path: Path) -> None:
    client = appmod.create_app(sqlite_db=tmp_path / "empty.sqlite").test_client()

    release = client.get("/api/strategy-release").get_json()
    lab = client.get("/api/strategies/lab").get_json()

    assert all(
        item.get("variant_id") != "shadow_n4_probability_weighted_512_v1"
        for item in release["decision_variants"]
    )
    assert all(
        item.get("strategy_id") != "shadow_n4_probability_weighted_512_v1"
        for item in lab["strategies"]
    )
