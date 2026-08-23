from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.multin_top2_r0.contract import (
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_VALUES,
    PAYOUT_FACTOR,
    tickets_for_n,
    units_per_ticket,
)
from src.multin_top2_r0.pipeline import (
    _assert_semantic_equal,
    binary_design,
    construct_preoutcome,
    prepare_match_surface,
    settle,
)


def _cells(matches: int = 10) -> pd.DataFrame:
    rows = []
    probabilities = {"3": 0.55, "1": 0.25, "0": 0.20}
    lines = {"3": 0.45, "1": 0.30, "0": 0.25}
    for match_idx in range(1, matches + 1):
        for outcome in ("3", "1", "0"):
            rows.append(
                {
                    "issue": "23001", "issue_year": 2023,
                    "issue_anchor_ts": pd.Timestamp("2023-01-01", tz="UTC"),
                    "match_idx": match_idx, "outcome": outcome,
                    "q_eu": probabilities[outcome] - match_idx * (0.0001 if outcome == "3" else 0),
                    "q_line": lines[outcome],
                }
            )
        total = sum(row["q_eu"] for row in rows[-3:])
        for row in rows[-3:]:
            row["q_eu"] /= total
    return pd.DataFrame(rows)


def test_ticket_counts_budget_and_balance() -> None:
    for n in N_VALUES:
        design = binary_design(n)
        assert design.shape == (tickets_for_n(n), n)
        assert len(np.unique(design, axis=0)) == tickets_for_n(n)
        assert tickets_for_n(n) * units_per_ticket(n) == FUNDED_UNITS
        assert tickets_for_n(n) * units_per_ticket(n) * 2 == ISSUE_STAKE_CNY
        if n >= 7:
            assert np.all(design.sum(axis=0) == 64)


def test_n_below_seven_is_full_cartesian() -> None:
    for n in range(3, 7):
        observed = {tuple(row) for row in binary_design(n)}
        expected = {tuple((value >> bit) & 1 for bit in range(n)) for value in range(2**n)}
        assert observed == expected


def test_constructs_all_n_without_fake_tickets() -> None:
    matches = prepare_match_surface(_cells())
    bundles, tickets, coverage = construct_preoutcome(matches)
    assert set(bundles["n"]) == set(N_VALUES)
    for row in bundles.itertuples():
        group = tickets[(tickets["issue"].eq(row.issue)) & tickets["n"].eq(row.n)]
        assert len(group) == min(128, 2**row.n)
        assert group["ticket_key"].nunique() == len(group)
        assert group["units"].sum() == 512
    assert set(coverage["status"]) == {"FROZEN"}


def test_ticket_level_once_payout_and_fixed_stake() -> None:
    matches = prepare_match_surface(_cells(3))
    frozen, tickets, _ = construct_preoutcome(matches)
    frozen = frozen[frozen["n"].eq(3)].reset_index(drop=True)
    tickets = tickets[tickets["n"].eq(3)].reset_index(drop=True)
    settlement = pd.DataFrame(
        {
            "issue": ["23001"] * 3, "match_idx": [1, 2, 3],
            "result_code": ["3", "3", "3"], "winning_sp": [2.0, 2.0, 2.0],
            "settlement_available": [True, True, True],
        }
    )
    bundles, _, _ = settle(frozen, tickets, settlement)
    expected = (64 * 2) * PAYOUT_FACTOR * 8
    assert bundles.loc[0, "gross_cny"] == pytest.approx(expected)
    assert bundles.loc[0, "stake_cny"] == ISSUE_STAKE_CNY
    assert bundles.loc[0, "pnl_cny"] == pytest.approx(expected - ISSUE_STAKE_CNY)


def test_oa_can_miss_even_when_all_results_are_supported() -> None:
    matches = prepare_match_surface(_cells(8))
    frozen, tickets, _ = construct_preoutcome(matches)
    frozen = frozen[frozen["n"].eq(8)].reset_index(drop=True)
    tickets = tickets[tickets["n"].eq(8)].reset_index(drop=True)
    support = json.loads(frozen.loc[0, "support_json"])
    represented = {ticket.ticket_key for ticket in tickets.itertuples()}
    all_binary = []
    keys = sorted(support, key=int)
    for choices in np.ndindex(*(2,) * 8):
        all_binary.append("|".join(f"{key}={support[key][choice]}" for key, choice in zip(keys, choices, strict=True)))
    absent = next(key for key in all_binary if key not in represented)
    results = dict(part.split("=") for part in absent.split("|"))
    settlement = pd.DataFrame(
        {
            "issue": ["23001"] * 8,
            "match_idx": [int(key) for key in keys],
            "result_code": [results[key] for key in keys],
            "winning_sp": [2.0] * 8, "settlement_available": [True] * 8,
        }
    )
    bundles, attribution, _ = settle(frozen, tickets, settlement)
    assert attribution["included"].all()
    assert not bundles.loc[0, "hit"]
    assert bundles.loc[0, "gross_cny"] == 0


def test_prepare_match_surface_rejects_wrong_schema() -> None:
    with pytest.raises(KeyError):
        prepare_match_surface(pd.DataFrame({"issue": ["x"]}))


def test_adversarial_pnl_tamper_is_not_semantically_equal() -> None:
    expected = pd.DataFrame({"issue": ["23001"], "n": [7], "pnl_cny": [10.0]})
    tampered = expected.copy()
    tampered.loc[0, "pnl_cny"] += 0.01
    with pytest.raises(AssertionError):
        _assert_semantic_equal(tampered, expected, ["issue", "n"])


def test_adversarial_ticket_group_deletion_is_not_semantically_equal() -> None:
    expected = pd.DataFrame(
        {"issue": ["23001", "23001"], "n": [3, 3], "ticket_index": [0, 1]}
    )
    with pytest.raises(AssertionError):
        _assert_semantic_equal(expected.iloc[:1], expected, ["issue", "n", "ticket_index"])
