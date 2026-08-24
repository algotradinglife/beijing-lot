from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.low_n_third_outcome_protection.contract import FUNDED_UNITS
from src.low_n_third_outcome_protection.pipeline import (
    ContractError,
    _path_risk,
    _strict_bool,
    _ticket_units,
    construct_protection,
    diagnose_protection_rank,
    policy_state,
    settle_protection,
)


def _inputs() -> dict[str, pd.DataFrame]:
    anchor = pd.Timestamp("2019-01-01", tz="UTC")
    selections = pd.DataFrame(
        [
            {
                "issue": "19001",
                "issue_year": 2019,
                "issue_anchor_ts": anchor,
                "lane": "S0_N3",
                "n": 3,
                "match_idx": match_idx,
                "baseline_support": support,
                "omitted_outcome": omitted,
                "omitted_probability": probability,
                "strict_prior_coverage_score": coverage,
                "predicted_top2_miss": 1 - coverage,
                "protection_rank": rank,
            }
            for match_idx, support, omitted, probability, coverage, rank in (
                (1, "31", "0", 0.10, 0.70, 1),
                (2, "30", "1", 0.08, 0.80, 2),
                (3, "10", "3", 0.05, 0.90, 3),
            )
        ]
    )
    bundles = pd.DataFrame(
        [
            {
                "issue": "19001",
                "issue_year": 2019,
                "issue_anchor_ts": anchor,
                "lane": "S0_N3",
                "n": 3,
                "selected_match_ids": "1|2|3",
                "support_json": '{"1":"31","2":"30","3":"10"}',
                "ticket_count": 8,
                "planned_stake_cny": 1024.0,
            }
        ]
    )
    decisions = pd.DataFrame(
        [
            {
                "issue": "19001",
                "issue_year": 2019,
                "issue_anchor_ts": anchor,
                "lane": "S0_N3",
                "n": 3,
                "decision": "BET",
                "bet": True,
            }
        ]
    )
    upstream_tickets = []
    for ticket_index, outcomes in enumerate(
        (
            ("3", "3", "1"),
            ("3", "3", "0"),
            ("3", "0", "1"),
            ("3", "0", "0"),
            ("1", "3", "1"),
            ("1", "3", "0"),
            ("1", "0", "1"),
            ("1", "0", "0"),
        )
    ):
        ticket_key = "|".join(
            f"{match_idx}={outcome}"
            for match_idx, outcome in zip((1, 2, 3), outcomes, strict=True)
        )
        upstream_tickets.append(
            {
                "issue": "19001",
                "issue_year": 2019,
                "issue_anchor_ts": anchor,
                "lane": "S0_N3",
                "n": 3,
                "ticket_index": ticket_index,
                "ticket_key": ticket_key,
                "units": 64,
                "stake_cny": 128.0,
            }
        )
    return {
        "selections": selections,
        "bundles": bundles,
        "decisions": decisions,
        "tickets": pd.DataFrame(upstream_tickets),
    }


def test_ticket_count_budget_and_balance_for_all_low_n_depths() -> None:
    for n in (3, 4, 5):
        for p in range(n + 1):
            count = 2 ** (n - p) * 3**p
            units = _ticket_units("19001", f"S0_N{n}", n, p, count)
            assert len(units) == count
            assert units.sum() == FUNDED_UNITS
            assert units.max() - units.min() <= 1


def test_p0_exact_top2_and_equal_units() -> None:
    result = construct_protection(_inputs())
    bundle = result["bundles"].query("p == 0").iloc[0]
    assert json.loads(bundle.support_json) == {"1": "31", "2": "30", "3": "10"}
    tickets = result["tickets"].query("p == 0")
    assert len(tickets) == 8
    assert tickets.units.nunique() == 1
    assert tickets.units.iloc[0] == 64


def test_p1_adds_only_rank_one_omitted_outcome() -> None:
    result = construct_protection(_inputs())
    bundle = result["bundles"].query("p == 1").iloc[0]
    support = json.loads(bundle.support_json)
    assert support == {"1": "310", "2": "30", "3": "10"}
    assert bundle.ticket_count == 12


def test_p0_parity_rejects_a_mutated_upstream_ticket() -> None:
    inputs = _inputs()
    inputs["tickets"].loc[0, "units"] = 63
    with pytest.raises(ContractError, match="P0 ticket ledger"):
        construct_protection(inputs)


def test_ticket_level_once_settlement_salvages_protected_third() -> None:
    result = construct_protection(_inputs())
    bundles = result["bundles"].query("p == 1")
    tickets = result["tickets"].query("p == 1")
    settlement = pd.DataFrame(
        [
            {
                "issue": "19001",
                "match_idx": 1,
                "settlement_available": True,
                "result_code": "0",
                "winning_sp": 4.0,
            },
            {
                "issue": "19001",
                "match_idx": 2,
                "settlement_available": True,
                "result_code": "3",
                "winning_sp": 2.0,
            },
            {
                "issue": "19001",
                "match_idx": 3,
                "settlement_available": True,
                "result_code": "1",
                "winning_sp": 1.5,
            },
        ]
    )
    settled, _ = settle_protection(bundles, tickets, settlement)
    row = settled.iloc[0]
    assert bool(row.hit) is True
    assert bool(row.baseline_hit) is False
    expected = row.winning_ticket_units * 2.0 * 0.65 * 4.0 * 2.0 * 1.5
    assert row.gross_cny == pytest.approx(expected)


def test_no_bet_decision_has_zero_exposure_even_if_ticket_plan_exists() -> None:
    inputs = _inputs()
    inputs["decisions"].loc[0, ["decision", "bet"]] = ["NO_BET", False]
    result = construct_protection(inputs)
    settlement = pd.DataFrame(
        [
            {
                "issue": "19001",
                "match_idx": 1,
                "settlement_available": True,
                "result_code": "3",
                "winning_sp": 1.2,
            },
            {
                "issue": "19001",
                "match_idx": 2,
                "settlement_available": True,
                "result_code": "3",
                "winning_sp": 1.3,
            },
            {
                "issue": "19001",
                "match_idx": 3,
                "settlement_available": True,
                "result_code": "1",
                "winning_sp": 1.4,
            },
        ]
    )
    settled, _ = settle_protection(result["bundles"], result["tickets"], settlement)
    state = policy_state(result["decisions"], settled)
    assert state["settlement_status"].eq("NO_BET").all()
    assert state[["stake_cny", "gross_cny", "pnl_cny"]].eq(0).all().all()


def test_rank_diagnostic_uses_realized_baseline_misses_only() -> None:
    result = construct_protection(_inputs())
    settlement = pd.DataFrame(
        [
            {
                "issue": "19001",
                "match_idx": 1,
                "settlement_available": True,
                "result_code": "0",
                "winning_sp": 4.0,
            },
            {
                "issue": "19001",
                "match_idx": 2,
                "settlement_available": True,
                "result_code": "3",
                "winning_sp": 2.0,
            },
            {
                "issue": "19001",
                "match_idx": 3,
                "settlement_available": True,
                "result_code": "1",
                "winning_sp": 1.5,
            },
        ]
    )
    _, attribution = settle_protection(result["bundles"], result["tickets"], settlement)
    diagnostic = diagnose_protection_rank(result["selections"], attribution)
    pooled = diagnostic[diagnostic["period"].eq("ALL_2019_2021")].set_index(
        "protection_rank"
    )
    assert pooled.loc[1, "observed_top2_miss_rate"] == 1.0
    assert pooled.loc[2, "observed_top2_miss_rate"] == 0.0


def test_monotonic_gain_is_not_a_completed_recovery() -> None:
    result = _path_risk(np.array([100.0]))
    assert result["completed_recovery_issues"] == 0
    assert result["open_underwater_issues"] == 0
    assert result["recovery_censored"] is False


def test_real_underwater_episode_is_counted() -> None:
    recovered = _path_risk(np.array([-100.0, 150.0]))
    assert recovered["completed_recovery_issues"] == 2
    assert recovered["open_underwater_issues"] == 0
    open_path = _path_risk(np.array([-100.0, 50.0]))
    assert open_path["completed_recovery_issues"] == 0
    assert open_path["open_underwater_issues"] == 2


def test_strict_boolean_rejects_integer_flags() -> None:
    with pytest.raises(ContractError, match="strict boolean"):
        _strict_bool(pd.Series([0, 1]), "bad")
