from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj180_team_matchup_gate_b.py"


def load():
    spec = importlib.util.spec_from_file_location("bj180_gate_b_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_a_identity_and_frozen_surface_without_outcome_access():
    runner = load()
    manifest = runner.B.verify_package(
        runner.GATE_A,
        runner.EXPECTED_GATE_A_MANIFEST,
        runner.EXPECTED_GATE_A_CONTENT,
    )
    selections = runner.read_csv(runner.GATE_A / "selection_freeze.csv")
    assert len(manifest) == 19
    assert len(selections) == 348 * 14
    assert sum(row["policy_status"] == "SELECTED_PREOUTCOME" for row in selections) == 189 * 14
    assert tuple(dict.fromkeys(row["arm"] for row in selections)) == runner.ARMS


def test_probability_scoring_and_reliability_use_frozen_vectors():
    runner = load()
    frozen = {
        "match_id": "m1",
        "issue": "1",
        "year": "2024",
        "kickoff_ts": "2024-01-01 12:00:00",
        "league": "L",
        "min_history_n": "12",
        "new_team_fallback": "0",
        "h2h_prior_n": "2",
    }
    for vector in runner.ARM_VECTORS.values():
        frozen[f"{vector}_p3"] = "0.5"
        frozen[f"{vector}_p1"] = "0.3"
        frozen[f"{vector}_p0"] = "0.2"
    rows = runner.probability_rows([frozen], {"m1": {"result_code": "3"}})
    assert len(rows) == 14
    assert all(abs(float(row["log_loss"]) + __import__("math").log(0.5)) < 1e-12 for row in rows)
    reliability = runner.B.reliability_rows(rows)
    summary = runner.probability_frontier(rows, reliability)
    assert len(reliability) == 14 * 3 * 10
    assert len(summary) == 14 * 2
    assert all(row["settled_match_count"] == 1 for row in summary)


def test_full_ticket_tax_is_per_winning_ticket_and_missing_policy_fails_closed():
    runner = load()
    low = runner.B.full_ticket_settlement([2.0] * 7, True)
    high = runner.B.full_ticket_settlement([4.0] * 7, True)
    missing = runner.B.full_ticket_settlement([], False)
    assert low["tax_yuan"] == 0
    assert high["tax_yuan"] == high["gross_pre_tax_yuan"] * 0.20
    assert missing == {"gross_pre_tax_yuan": 0.0, "tax_yuan": 0.0, "hit_ticket_count": 0}


def test_settlement_requires_all_seven_outcomes_at_selector_issue_policy():
    runner = load()
    mids = [f"m{i}" for i in range(7)]
    selection = {
        "issue": "1", "year": "2024", "fold": "OOS_2024",
        "issue_instance": "1@OOS_2024", "arm": "B0_BEST_FULL",
        "arm_role": "BASELINE", "choice_opportunity": "0",
        "selected_portfolio_id": "p", "selected_identity_fingerprint": "fp",
        "selected_score": "3.1",
    }
    candidate = {
        "selected_match_ids": "|".join(mids), "identity_fingerprint": "fp",
        "market_gm_e_sp": "3.1",
    }
    outcomes = {mid: {"winning_sp": "2.0"} for mid in mids[:-1]}
    rows = runner.B.settle_rows(
        [selection], {("1@OOS_2024", "p"): candidate}, outcomes,
        {"1@OOS_2024": "2024-01-01 12:00:00"},
    )
    assert rows[0]["policy_status"] == "UNAVAILABLE_CANONICAL_OUTCOME"
    assert rows[0]["executed_ticket_count"] == 0
    assert float(rows[0]["stake_yuan"]) == 0
    assert rows[0]["missing_match_ids"] == "m6"
