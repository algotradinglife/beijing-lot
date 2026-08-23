from __future__ import annotations

import json

import pandas as pd

from src.multin_fixed_rn.pipeline import (
    _armwise_ex_largest,
    development_curve_and_selection,
    freeze_bundles,
    prepare_support_matches,
    settle_bundles,
)
from src.multin_top2_r0.contract import N_VALUES
from src.multin_top2_r0.pipeline import (
    binary_design,
    construct_preoutcome,
    prepare_match_surface,
    settle,
)


def _cells(year: int = 2022, matches: int = 10) -> pd.DataFrame:
    rows = []
    for match_idx in range(1, matches + 1):
        # Probability Top2=31 while QEU Top2=30, with increasing pressure.
        for outcome, q_eu, q_line in (
            ("3", .55, .40), ("1", .25, .50), ("0", .20, .10),
        ):
            rows.append(
                {"issue": f"{str(year)[-2:]}001", "issue_year": year,
                 "issue_anchor_ts": pd.Timestamp(f"{year}-01-01", tz="UTC"),
                 "match_idx": match_idx, "outcome": outcome,
                 "q_eu": q_eu, "q_line": q_line}
            )
    return pd.DataFrame(rows)


def test_qeu_support_is_distinct_and_pressure_positive() -> None:
    matches = prepare_support_matches(_cells())
    assert matches["baseline_support"].eq("31").all()
    assert matches["qeu_support"].eq("03").all()
    assert matches["support_changed"].all()
    assert matches["support_pressure"].gt(0).all()


def test_freeze_contains_full_r_range_for_every_n() -> None:
    matches = prepare_support_matches(_cells())
    spec = {n: tuple(range(n + 1)) for n in N_VALUES}
    bundles, coverage = freeze_bundles(matches, spec, (2022,), "DEVELOPMENT")
    for n in N_VALUES:
        assert set(bundles[bundles["n"].eq(n)]["r"]) == set(range(n + 1))
    assert set(coverage["status"]) == {"FROZEN"}


def test_armwise_ex_largest_is_not_paired_delta_deletion() -> None:
    challenger = pd.DataFrame({"gross_cny": [100.0, 1000.0], "pnl_cny": [-10.0, 900.0]})
    control = pd.DataFrame({"gross_cny": [800.0, 10.0], "pnl_cny": [700.0, -90.0]})
    assert _armwise_ex_largest(challenger, control) == 80.0


def test_selection_freezes_n7_r3_and_uses_robust_rule() -> None:
    rows = []
    for n in N_VALUES:
        for issue, r0 in (("22001", -100.0), ("22002", -100.0), ("22003", 200.0)):
            for r in range(n + 1):
                # R1 improves every issue; higher R is weaker. N7 still must be R3.
                pnl = r0 + (50.0 if r == 1 else 0.0)
                rows.append(
                    {"issue": issue, "issue_year": 2022,
                     "issue_anchor_ts": pd.Timestamp("2022-01-01", tz="UTC"),
                     "n": n, "r": r, "settlement_status": "SETTLED",
                     "pnl_cny": pnl, "gross_cny": pnl + 1024.0, "stake_cny": 1024.0}
                )
    _, _, selected = development_curve_and_selection(pd.DataFrame(rows))
    assert selected[7] == 3
    assert all(selected[n] == 1 for n in N_VALUES if n != 7)


def test_n8_r0_preserves_numeric_match_column_order() -> None:
    cells = _cells(matches=10)
    phase_a_matches = prepare_match_surface(cells)
    phase_a_frozen, phase_a_tickets, _ = construct_preoutcome(phase_a_matches)
    phase_a_frozen = phase_a_frozen[phase_a_frozen["n"].eq(8)]
    phase_a_tickets = phase_a_tickets[phase_a_tickets["n"].eq(8)]
    support = json.loads(phase_a_frozen.iloc[0]["support_json"])
    ordered = [int(value) for value in phase_a_frozen.iloc[0]["selected_match_ids"].split("|")]
    choices = binary_design(8)[1]
    result = {match: support[str(match)][int(choice)] for match, choice in zip(ordered, choices, strict=True)}
    settlement = pd.DataFrame(
        {"issue": ["22001"] * 8, "match_idx": ordered,
         "result_code": [result[match] for match in ordered], "winning_sp": [2.0] * 8,
         "settlement_available": [True] * 8}
    )
    phase_a, _, _ = settle(phase_a_frozen, phase_a_tickets, settlement)
    support_matches = prepare_support_matches(cells)
    phase_b_frozen, _ = freeze_bundles(support_matches, {n: (0,) for n in N_VALUES}, (2022,), "EVALUATION")
    phase_b_frozen = phase_b_frozen[phase_b_frozen["n"].eq(8)]
    phase_b, _, _ = settle_bundles(phase_b_frozen, support_matches, settlement)
    assert phase_b.iloc[0]["gross_cny"] == phase_a.iloc[0]["gross_cny"]
