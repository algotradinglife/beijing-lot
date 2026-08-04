from __future__ import annotations

import array
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj179_hierarchical_league_gate_b.py"
SPEC = importlib.util.spec_from_file_location("bj179_gate_b", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


def test_frozen_contract_and_source_hashes_are_exact() -> None:
    assert RUNNER.ARMS == (
        "B0_BEST_FULL",
        "Q1_QUICK_LEAGUE",
        "H1_DEEP_ALL",
        "H_CFG_BALANCED_CONSERVATIVE",
        "H_CFG_BALANCED_RESPONSIVE",
        "H_CFG_PRICING_HEAVY",
        "H_CFG_REGIME_HEAVY",
        "H_CFG_PRICING_CONSERVATIVE",
        "H_MINUS_RAW_HDA",
        "H_MINUS_BJ_REGIME",
        "H_MINUS_EURO",
        "H_MINUS_ASIAN",
        "H_MINUS_BEIJING_SP",
        "H_MINUS_LIQUIDITY",
    )
    assert RUNNER.FULL_TICKETS == 2187
    assert RUNNER.FULL_STAKE == 4374.0
    assert (
        RUNNER.sha256_file(RUNNER.GATE_A / "SHA256SUMS.json")
        == RUNNER.EXPECTED_GATE_A_MANIFEST
    )
    assert (
        RUNNER.sha256_file(RUNNER.GATE_A / "CONTENT_IDENTITY.json")
        == RUNNER.EXPECTED_GATE_A_CONTENT
    )
    assert (
        RUNNER.sha256_file(RUNNER.OUTCOME_DIR / "SHA256SUMS.json")
        == RUNNER.EXPECTED_OUTCOME_MANIFEST
    )
    active, candidates, probabilities, chronology, binding = RUNNER.load_inputs()
    assert len(active) == 2646
    assert len(candidates) == 424
    assert len(probabilities) == 1558
    assert len(chronology) == 189
    assert binding["probability_frontier"]["parameter_frontier_rows"] == 12
    score_columns = set(next(iter(candidates.values())))
    assert set(RUNNER.ARM_SCORE_FIELDS.values()) <= score_columns
    assert RUNNER.ARM_SCORE_FIELDS["Q1_QUICK_LEAGUE"] == "quick_league_gm_e_sp"


def test_full_ticket_tax_is_per_ticket_at_boundary() -> None:
    factor = (10_000.0 / (RUNNER.STAKE_PER_TICKET * RUNNER.PAYOUT_FACTOR)) ** (1 / 7)
    below = RUNNER.full_ticket_settlement([factor * (1 - 1e-8)] + [factor] * 6, True)
    boundary = RUNNER.full_ticket_settlement(
        [factor * (1 + 1e-8)] + [factor] * 6, True
    )
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
        **{field: "3.0" for field in set(RUNNER.ARM_SCORE_FIELDS.values())},
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


def frozen_probability_row(match_id: str, year: str, unknown: str) -> dict[str, str]:
    row = {
        "match_id": match_id,
        "issue": "1",
        "year": year,
        "kickoff_ts": f"{year}-01-01 00:00:00",
        "league": "L",
        "unknown_league_fallback": unknown,
        "target_euro_source_complete": "1",
        "target_asian_source_complete": "1",
        "target_beijing_pred_sp_source_complete": "1",
    }
    for vector in set(RUNNER.ARM_VECTOR_FIELDS.values()):
        row[f"{vector}_p3"] = "0.6"
        row[f"{vector}_p1"] = "0.3"
        row[f"{vector}_p0"] = "0.1"
    return row


def test_probability_frontier_is_complete_and_probability_first() -> None:
    frozen = [
        frozen_probability_row("m1", "2020", "0"),
        frozen_probability_row("m2", "2021", "1"),
    ]
    outcomes = {"m1": {"result_code": "3"}}
    rows = RUNNER.probability_rows(frozen, outcomes)
    assert len(rows) == 2 * len(RUNNER.ARMS)
    assert sum(row["outcome_status"] == "SETTLED" for row in rows) == len(RUNNER.ARMS)
    b0 = next(row for row in rows if row["arm"] == "B0_BEST_FULL")
    assert float(b0["log_loss"]) == pytest.approx(-__import__("math").log(0.6))
    assert float(b0["brier"]) == pytest.approx(0.26)
    reliability = RUNNER.reliability_rows(rows)
    assert len(reliability) == len(RUNNER.ARMS) * 3 * 10
    frontier = RUNNER.probability_frontier(rows, reliability)
    assert len(frontier) == len(RUNNER.ARMS) * 5
    overall = [row for row in frontier if row["view"] == "ALL"]
    assert len(overall) == len(RUNNER.ARMS)
    assert all(row["settled_match_count"] == 1 for row in overall)
    assert all(row["missing_outcome_count"] == 1 for row in overall)


def test_parameter_frontier_preserves_all_frozen_arms() -> None:
    probability_summary = [
        {
            "arm": arm,
            "view": "ALL",
            "value": "ALL",
            "settled_match_count": 100,
            "multiclass_log_loss": "1.0",
            "multiclass_brier": "0.5",
            "multiclass_ece": "0.1",
        }
        for arm in RUNNER.ARMS
    ]
    frontier = RUNNER.complete_parameter_frontier(probability_summary)
    assert len(frontier) == len(RUNNER.ARMS)
    assert {row["arm"] for row in frontier} == set(RUNNER.ARMS)
    assert all(row["selection_authority"] == "NONE_FROZEN_FRONTIER_ONLY" for row in frontier)


def test_b0_and_q1_selection_bridges_match_accepted_134_controls() -> None:
    current = RUNNER.read_csv(RUNNER.GATE_A / "selection_freeze.csv")
    accepted = RUNNER.read_csv(
        ROOT / "results" / "bj134_gate_a_preoutcome_v3" / "selection_freeze.csv"
    )
    for current_arm, accepted_arm in (
        ("B0_BEST_FULL", "B0_BEST_FULL"),
        ("Q1_QUICK_LEAGUE", "L1_LEAGUE_CORE"),
    ):
        current_identity = {
            (row["issue_instance"], row["policy_status"]): (
                row["selected_portfolio_id"],
                row["selected_identity_fingerprint"],
            )
            for row in current
            if row["arm"] == current_arm
        }
        accepted_identity = {
            (row["issue_instance"], row["policy_status"]): (
                row["selected_portfolio_id"],
                row["selected_identity_fingerprint"],
            )
            for row in accepted
            if row["arm"] == accepted_arm
        }
        assert current_identity == accepted_identity


def test_bootstrap_is_paired_and_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(RUNNER, "BOOTSTRAP_REPLICATES", 200)
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
    assert metric["ex_largest_issue_roi"]
    assert metric["ex_largest_year_roi"]


def test_report_separates_probability_and_economic_findings() -> None:
    probability = [
        {
            "view": "ALL",
            "value": "ALL",
            "arm": "B0_BEST_FULL",
            "settled_match_count": 1,
            "unknown_league_count": 0,
            "multiclass_log_loss": "1",
            "multiclass_brier": "0.5",
            "multiclass_ece": "0.1",
        }
    ]
    economic = [
        {
            "segment": "ALL_189",
            "arm": "B0_BEST_FULL",
            "settled_native_issue_count": 1,
            "no_tax_roi": "-0.1",
            "paired_roi_lift": "0",
            "paired_q1_roi_lift": "0.01",
            "tax_adjusted_roi": "-0.1",
            "profitable_issue_count": 0,
            "choice_identity_changed_count": 0,
        }
    ]
    text = RUNNER.report(probability, economic, [], [])
    assert "Probability-first frozen frontier" in text
    assert "Matched FULL-N7 economics" in text
    assert "LIQUIDITY_DRIFT" in text
    assert "strict independent EV" in text


def test_chart_builder_covers_all_fourteen_arms(tmp_path: Path) -> None:
    summary = [
        {
            "segment": "ALL_189",
            "arm": arm,
            "choice_identity_changed_count": 0,
            "paired_roi_lift": "0",
            "paired_q1_roi_lift": "0",
        }
        for arm in RUNNER.ARMS
    ]
    probability = [
        {
            "view": "ALL",
            "value": "ALL",
            "arm": arm,
            "multiclass_log_loss": "1",
            "multiclass_brier": "0.5",
            "multiclass_ece": "0.1",
        }
        for arm in RUNNER.ARMS
    ]
    series = [
        {
            "segment": "ALL_189",
            "arm": arm,
            "cumulative_pre_tax_profit_yuan": "0",
            "pre_tax_drawdown_yuan": "0",
        }
        for arm in RUNNER.ARMS
    ]
    RUNNER.write_charts(tmp_path, summary, probability, series)
    assert (tmp_path / "probability_frontier.svg").exists()
    assert (tmp_path / "economic_lift_frontier.svg").exists()
    assert len(RUNNER.read_csv(tmp_path / "chart_source_primary_comparison.csv")) == 14


def test_committed_package_is_complete_if_present() -> None:
    package = RUNNER.DEFAULT_OUTPUT
    if not package.exists():
        return
    manifest = json.loads((package / "SHA256SUMS.json").read_text())
    actual = sorted(
        path.name
        for path in package.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    assert sorted(manifest) == actual
    for name, digest in manifest.items():
        assert RUNNER.sha256_file(package / name) == digest
