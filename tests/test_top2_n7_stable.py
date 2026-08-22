from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from src.top2_n7_stable.contract import PAYOUT_FACTOR
from src.top2_n7_stable.pipeline import (
    _chronological,
    _fixture_table,
    _risk,
    _seed,
    construct_preoutcome,
    settle,
)


def surface(fixtures: int = 8) -> pd.DataFrame:
    rows = []
    for index in range(fixtures):
        for code, probability in zip(("3", "1", "0"), (.5, .3, .2), strict=True):
            rows.append({"canonical_fixture_key": f"bjslot:23001:{index:03d}", "issue_code": "23001",
                         "issue_year": 2023, "snapshot_kind": "10h", "match_idx": index,
                         "issue_anchor_ts": "2023-01-02T12:00:00+00:00",
                         "outcome_code": code, "q_eu_bjline": probability,
                         "native_handicap_line": 0.0, "eu_vs_line_divergence": 0.01,
                         "n_available_books": 10, "causal_grade": "TEST"})
    return pd.DataFrame(rows)


def test_top2_tie_order_is_310() -> None:
    frame = surface(1)
    frame["q_eu_bjline"] = 1 / 3
    assert _fixture_table(frame).iloc[0].support == ("3", "1")


def test_exact_128_unique_tickets_and_cny256() -> None:
    bundles, tickets = construct_preoutcome(surface())
    active = bundles[bundles.status_preoutcome == "ACTIVE"]
    assert set(active.ticket_count) == {128}
    assert set(active.planned_stake) == {256.0}
    assert tickets.groupby(["arm", "seed"]).size().eq(128).all()
    assert not tickets.duplicated(["arm", "seed", "ticket_key"]).any()


def test_price_arms_and_numeric_gates_fail_closed() -> None:
    bundles, _ = construct_preoutcome(surface())
    blocked = bundles[bundles.status_preoutcome != "ACTIVE"]
    assert blocked.status_preoutcome.eq("NO_BET_PRICE_DATA_INSUFFICIENT").all()
    assert not blocked.gate.eq("NONE").all()


def test_fewer_than_seven_fixtures_is_explicit_no_bet() -> None:
    bundles, tickets = construct_preoutcome(surface(6))
    assert tickets.empty
    probability = bundles[bundles.arm.isin(["P_TOP2_NO_GATE", "RANDOM_MATCH_P_TOP2"])]
    assert probability.status_preoutcome.eq("NO_BET_INSUFFICIENT_FIXTURES").all()
    price = bundles[bundles.arm.isin(["P_TOP2_VALUE_RANK", "Q_TOP2_VALUE_SUPPORT"])]
    assert price.status_preoutcome.eq("NO_BET_PRICE_DATA_INSUFFICIENT").all()


def test_random_seed_is_deterministic_and_issue_specific() -> None:
    assert _seed("23001", 0) == _seed("23001", 0)
    assert _seed("23001", 0) != _seed("23002", 0)


def test_factor_is_bundle_level() -> None:
    sps = [2.0] * 7
    correct = 2.0 * PAYOUT_FACTOR * np.prod(sps)
    wrong_per_leg = 2.0 * np.prod(np.array(sps) * PAYOUT_FACTOR)
    assert correct == 166.4
    assert not np.isclose(correct, wrong_per_leg)


def test_ticket_support_is_complete_cartesian_product() -> None:
    assert len(set(itertools.product((0, 1), repeat=7))) == 128


def primary_bundle_and_tickets() -> tuple[pd.DataFrame, pd.DataFrame]:
    bundles, tickets = construct_preoutcome(surface(7))
    bundles = bundles[(bundles.arm == "P_TOP2_NO_GATE") & (bundles.gate == "NONE")]
    tickets = tickets[tickets.arm == "P_TOP2_NO_GATE"]
    return bundles, tickets


def settlement_frame(fixtures: int = 7) -> pd.DataFrame:
    return pd.DataFrame({
        "issue_code": ["23001"] * fixtures,
        "canonical_fixture_key": [f"bjslot:23001:{index:03d}" for index in range(fixtures)],
        "result_code": ["3"] * fixtures,
        "winning_sp": [2.0] * fixtures,
        "has_trusted_settlement": [1] * fixtures,
    })


def test_settlement_reconciles_one_complete_winner_and_factor_once() -> None:
    bundles, tickets = settle(*primary_bundle_and_tickets(), settlement_frame())
    assert bundles.iloc[0].gross == 166.4
    assert bundles.iloc[0].hit
    assert tickets.ticket_hit.sum() == 1
    assert np.isclose(tickets.gross.sum(), bundles.gross.sum())


def test_missing_settlement_is_unobservable_not_scored_as_loss() -> None:
    bundles, tickets = settle(*primary_bundle_and_tickets(), settlement_frame(6))
    assert bundles.iloc[0].settlement_status == "UNOBSERVABLE_SETTLEMENT"
    assert np.isnan(bundles.iloc[0].pnl)
    assert tickets.gross.isna().all()


def test_recovery_diagnostics_distinguish_completed_and_open_drawdowns() -> None:
    recovered_then_open = pd.DataFrame({
        "pnl": [-100.0, 100.0, -50.0, -25.0],
        "gross": [0.0, 200.0, 0.0, 0.0],
        "capital_after": [99_900.0, 100_000.0, 99_950.0, 99_925.0],
    })
    diagnostics = _risk(recovered_then_open)
    assert diagnostics["completed_recovery_episode_count"] == 1
    assert diagnostics["max_completed_recovery_issues"] == 1
    assert diagnostics["open_underwater_issues"] == 2


def test_open_drawdown_is_not_reported_as_completed_recovery() -> None:
    open_only = pd.DataFrame({
        "pnl": [-100.0, -50.0],
        "gross": [0.0, 0.0],
        "capital_after": [99_900.0, 99_850.0],
    })
    diagnostics = _risk(open_only)
    assert diagnostics["completed_recovery_episode_count"] == 0
    assert diagnostics["max_completed_recovery_issues"] == 0
    assert diagnostics["open_underwater_issues"] == 2


def test_issue_path_uses_event_timestamp_not_issue_code() -> None:
    frame = pd.DataFrame({
        "issue_code": ["23001", "23002", "23003"],
        "issue_anchor_ts": [
            "2023-01-03T00:00:00+00:00",
            "2023-01-01T00:00:00+00:00",
            "2023-01-01T00:00:00+00:00",
        ],
    })
    assert _chronological(frame).issue_code.tolist() == ["23002", "23003", "23001"]
