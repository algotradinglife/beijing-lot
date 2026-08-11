from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ticket_policy.fixed_n7 import (
    N,
    OUTCOMES,
    TicketPolicyError,
    best_full_roster,
    legacy_full_metric,
    load_match_table,
    overlap_control_tickets,
    residual_tickets,
    temperature_probabilities,
    ticket_identity,
    top_mass_tickets,
    weighted_tickets,
)


def _matches(count: int = 14, *, year: int = 2023) -> pd.DataFrame:
    rows = []
    for match_idx in range(1, count + 1):
        row: dict[str, object] = {
            "issue": 1,
            "year": year,
            "split": "CV_2023" if year < 2025 else "LOCKED_TEST",
            "match_idx": match_idx,
            "realized_code": OUTCOMES[match_idx % 3] if year < 2025 else pd.NA,
            "expected_sp": 3.2 + match_idx / 100,
            "market_entropy": 1.0,
            "sp_cv": 0.2,
        }
        for code, probability, sp in zip(
            OUTCOMES, (0.2, 0.3, 0.5), (5.0, 3.4, 2.2), strict=True
        ):
            row[f"control_probability_{code}"] = probability
            row[f"predicted_final_sp_{code}"] = sp
            row[f"official_final_sp_label_{code}"] = sp if year < 2025 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _value_matrix() -> pd.DataFrame:
    rows = []
    for year, split in ((2023, "CV_2023"), (2026, "LOCKED_TEST")):
        for match_idx in range(1, 8):
            realized = OUTCOMES[match_idx % 3]
            for code, probability, sp in zip(
                OUTCOMES, (0.2, 0.3, 0.5), (5.0, 3.4, 2.2), strict=True
            ):
                rows.append(
                    {
                        "issue": year,
                        "year": year,
                        "split": split,
                        "match_idx": match_idx,
                        "outcome_code": code,
                        "control_probability": probability,
                        "control_probability_source": "MARKET_ONLY",
                        "control_probability_source_grade": "FROZEN_SAFE_BASELINE",
                        "control_probability_promoted": True,
                        "predicted_final_sp": sp,
                        "predicted_final_sp_source": "#204_FROZEN_PRE_EVENT_SP_HEAD",
                        "sp_seed_std": 0.01,
                        "control_expected_gross": probability * sp,
                        "control_expected_pre_tax_net": 0.65 * probability * sp - 1,
                        "control_displayed_scalar_utility": 0.65 * probability * sp - 1,
                        "experimental_probability": probability,
                        "experimental_probability_source_grade": "RETROSPECTIVE_PROXY_METHOD_CORRECTION",
                        "experimental_probability_promoted": False,
                        "experimental_model_market_residual": 0.0,
                        "realized_outcome": code == realized,
                        "official_final_sp_label": sp,
                    }
                )
    return pd.DataFrame(rows)


def test_ticket_identity_requires_exact_distinct_n7() -> None:
    identity = ticket_identity(range(1, 8), OUTCOMES[:1] * 7)
    assert len(identity.split("|")) == N
    with pytest.raises(TicketPolicyError, match="distinct"):
        ticket_identity([1, 1, 2, 3, 4, 5, 6], ["3"] * 7)


def test_temperature_rule_preserves_simplex_and_changes_concentration() -> None:
    source = np.asarray([[0.2, 0.3, 0.5]])
    cold = temperature_probabilities(source, 0.75)
    warm = temperature_probabilities(source, 1.25)
    assert np.isclose(cold.sum(), 1.0)
    assert np.isclose(warm.sum(), 1.0)
    assert cold.max() > source.max() > warm.max()


def test_weighted_wor_is_reproducible_and_constraint_valid() -> None:
    matches = _matches()
    first = weighted_tickets(
        matches,
        probability_prefix="control_probability",
        count=32,
        seed=7,
        distinct=True,
    )
    second = weighted_tickets(
        matches,
        probability_prefix="control_probability",
        count=32,
        seed=7,
        distinct=True,
    )
    assert [row["ticket_identity"] for row in first] == [
        row["ticket_identity"] for row in second
    ]
    assert len({row["ticket_identity"] for row in first}) == 32
    assert all(len(row["match_indices"].split(",")) == N for row in first)
    assert all(row["requested_stake_yuan"] == 2.0 for row in first)


def test_top_mass_and_residual_preserve_ticket_count_and_repeat_semantics() -> None:
    matches = _matches()
    top = top_mass_tickets(matches, probability_prefix="control_probability", count=64)
    residual = residual_tickets(matches, count=192, seed=8)
    assert len(top) == 64
    assert len({row["ticket_identity"] for row in top}) == 64
    assert len(residual) == 192
    assert len({row["ticket_identity"] for row in residual}) <= 32


def test_overlap_controls_are_matched_budget_and_constraint_valid() -> None:
    matches = _matches(20)
    capped = overlap_control_tickets(matches, count=32, seed=9, mode="CAP")
    penalized = overlap_control_tickets(matches, count=32, seed=9, mode="PENALTY")
    assert len(capped) == len(penalized) == 32
    assert all(len(row["match_indices"].split(",")) == N for row in capped + penalized)


def test_best_full_is_exact_2187_ticket_control() -> None:
    matches = _matches()
    roster = best_full_roster(matches)
    assert roster is not None
    assert len(roster) == N
    metric = legacy_full_metric(matches)
    assert metric["tickets"] == 3**N
    assert metric["stake_yuan"] == 2 * 3**N


def test_value_loader_fails_closed_and_nulls_2025_plus_labels(tmp_path: Path) -> None:
    matrix = _value_matrix()
    matrix_path = tmp_path / "matrix.parquet"
    schema_path = tmp_path / "schema.json"
    matrix.to_parquet(matrix_path, index=False)
    schema_path.write_text(
        json.dumps(
            {
                "safe_control_interface": {
                    "probability": "control_probability",
                    "probability_source": "MARKET_ONLY",
                    "source_grade": "FROZEN_SAFE_BASELINE",
                    "promoted": True,
                    "joint_scorer": "MARKET_INDEPENDENCE",
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_match_table(matrix_path, schema_path)
    locked = loaded.year.eq(2026)
    assert loaded.loc[locked, "realized_code"].isna().all()
    assert loaded.loc[
        locked, [f"official_final_sp_label_{code}" for code in OUTCOMES]
    ].isna().all().all()
    matrix.loc[0, "control_probability_source"] = "LOGISTIC_RESIDUAL"
    matrix.to_parquet(matrix_path, index=False)
    with pytest.raises(TicketPolicyError, match="control lane"):
        load_match_table(matrix_path, schema_path)
