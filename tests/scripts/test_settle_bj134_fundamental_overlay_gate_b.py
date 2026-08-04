from __future__ import annotations

import array
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj134_fundamental_overlay_gate_b.py"
SPEC = importlib.util.spec_from_file_location("bj134_gate_b", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_frozen_contract_and_source_hashes_are_exact() -> None:
    assert RUNNER.ARMS == (
        "B0_BEST_FULL",
        "L1_LEAGUE_CORE",
        "T1_TEAM_CORE",
        "M1_MARKET_DYNAMICS",
        "F1_CORE_ALL",
        "D1_DECISION_CHAIN_CORE",
        "F_MINUS_L",
        "F_MINUS_T",
        "F_MINUS_M",
    )
    assert RUNNER.FULL_TICKETS == 2187
    assert RUNNER.FULL_STAKE == 4374.0
    assert (
        RUNNER.sha256_file(RUNNER.GATE_A / "SHA256SUMS.json")
        == RUNNER.EXPECTED_GATE_A_MANIFEST
    )
    assert (
        RUNNER.sha256_file(RUNNER.OUTCOME_DIR / "SHA256SUMS.json")
        == RUNNER.EXPECTED_OUTCOME_MANIFEST
    )
    selections = RUNNER.read_csv(RUNNER.GATE_A / "selection_freeze.csv")
    assert sum(
        row["policy_status"] == "SELECTED_PREOUTCOME" for row in selections
    ) == 1701


def test_full_ticket_tax_is_per_ticket_at_boundary() -> None:
    # Seven factors with product chosen around the CNY10,000 ticket threshold.
    factor = (10_000.0 / (RUNNER.STAKE_PER_TICKET * RUNNER.PAYOUT_FACTOR)) ** (1 / 7)
    below = RUNNER.full_ticket_settlement([factor * (1 - 1e-8)] + [factor] * 6, True)
    boundary = RUNNER.full_ticket_settlement([factor * (1 + 1e-8)] + [factor] * 6, True)
    missing = RUNNER.full_ticket_settlement([], False)
    assert float(below["gross_pre_tax_yuan"]) < 10_000.0
    assert below["tax_yuan"] == 0.0
    assert float(boundary["gross_pre_tax_yuan"]) >= 10_000.0
    assert float(boundary["tax_yuan"]) == pytest.approx(2_000.0)
    assert missing == {
        "gross_pre_tax_yuan": 0.0,
        "tax_yuan": 0.0,
        "hit_ticket_count": 0,
    }


def test_missing_selected_match_fails_closed_for_that_arm_issue() -> None:
    selection = {
        "issue": "1",
        "year": "2020",
        "fold": "OOS_2020",
        "issue_instance": "1@OOS_2020",
        "arm": "B0_BEST_FULL",
        "arm_role": "PRIMARY",
        "choice_opportunity": "1",
        "selected_portfolio_id": "p",
        "selected_identity_fingerprint": "f",
        "selected_score": "3.0",
    }
    candidate = {
        "selected_match_ids": "1|2|3|4|5|6|7",
        "identity_fingerprint": "f",
        "market_gm_e_sp": "3.0",
        "league_gm_e_sp": "3.0",
        "team_gm_e_sp": "3.0",
        "market_dynamics_gm_e_sp": "3.0",
        "combined_gm_e_sp": "3.0",
        "decision_f1_gm_e_sp": "3.0",
        "combined_minus_league_gm_e_sp": "3.0",
        "combined_minus_team_gm_e_sp": "3.0",
        "combined_minus_market_gm_e_sp": "3.0",
    }
    outcomes = {str(i): {"winning_sp": "3.0"} for i in range(1, 7)}
    rows = RUNNER.settle_rows(
        [selection],
        {("1@OOS_2020", "p"): candidate},
        outcomes,
        {"1@OOS_2020": "2020-01-01 00:00:00"},
    )
    assert rows[0]["policy_status"] == "UNAVAILABLE_CANONICAL_OUTCOME"
    assert rows[0]["executed_ticket_count"] == 0
    assert rows[0]["stake_yuan"] == "0.000000"
    assert rows[0]["pre_tax_net_yuan"] == "0.000000"


def test_bootstrap_is_paired_and_deterministic(tmp_path: Path) -> None:
    first, first_meta = RUNNER.build_draw_matrix(tmp_path / "a.gz", 3, 0)
    second, second_meta = RUNNER.build_draw_matrix(tmp_path / "b.gz", 3, 0)
    assert isinstance(first, array.array)
    assert first == second
    assert first_meta["sha256"] == second_meta["sha256"]
    candidate = [
        {
            "pre_tax_net_yuan": str(x),
            "tax_adjusted_net_yuan": str(x),
            "stake_yuan": "10",
        }
        for x in (1, 2, 3)
    ]
    baseline = [
        {"pre_tax_net_yuan": "0", "tax_adjusted_net_yuan": "0", "stake_yuan": "10"}
        for _ in range(3)
    ]
    result = RUNNER.bootstrap_pair(candidate, baseline, first)
    assert result["lift_ci_low"] > 0
    assert result["positive_lift_fraction"] == 1.0


def test_risk_metrics_include_required_path_contract() -> None:
    rows = []
    for index, net in enumerate((-10.0, 20.0, -15.0)):
        stake = 100.0
        rows.append(
            {
                "policy_status": "SETTLED",
                "pre_tax_net_yuan": str(net),
                "tax_adjusted_net_yuan": str(net),
                "stake_yuan": str(stake),
                "gross_pre_tax_yuan": str(stake + net),
                "year": str(2020 + index),
                "first_kickoff_ts": f"{2020 + index}-01-01 00:00:00",
                "hit_ticket_count": int(net > 0),
                "issue_instance": str(index),
            }
        )
    metric = RUNNER.risk_row(rows, "PRE_TAX", "ALL_189", "TEST")
    assert metric["annualized_sharpe"]
    assert metric["annualized_sortino"]
    assert metric["calmar"]
    assert float(metric["max_drawdown_yuan"]) == 15.0
    assert metric["longest_miss_streak"] == 1
    assert metric["payout_issue_hhi"]


def test_gate_a_has_zero_handicap_contradiction_ranking_power() -> None:
    candidates = RUNNER.read_gzip(RUNNER.GATE_A / "candidate_universe_scores.csv.gz")
    assert len(candidates) == 424
    assert (
        sum(int(row["decision_handicap_contradiction_legs"]) for row in candidates) == 0
    )


def test_committed_package_is_complete_if_present() -> None:
    package = RUNNER.DEFAULT_OUTPUT
    if not package.exists():
        return
    manifest = __import__("json").loads((package / "SHA256SUMS.json").read_text())
    actual = sorted(
        path.name
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    assert sorted(manifest) == actual
    for name, digest in manifest.items():
        assert RUNNER.sha256_file(package / name) == digest
