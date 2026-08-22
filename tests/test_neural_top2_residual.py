from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from neural_top2_residual.contract import FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS, FUNDED_UNITS, PAYOUT_FACTOR
from neural_top2_residual.data import assert_feature_boundary
from neural_top2_residual.policy import largest_remainder_units

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/neural_top2_residual"


def test_largest_remainder_is_deterministic_and_funded() -> None:
    weights = np.linspace(0.1, 2.0, 128)
    keys = [f"ticket-{index:03d}" for index in range(128)]
    first = largest_remainder_units(weights, keys)
    second = largest_remainder_units(weights, keys)
    assert np.array_equal(first, second)
    assert first.sum() == FUNDED_UNITS
    assert first.min() >= 1


def test_equal_weights_reproduce_four_units() -> None:
    units = largest_remainder_units(np.ones(128), [f"t-{index:03d}" for index in range(128)])
    assert set(units) == {4}


def test_feature_contract_is_outcome_unexposed() -> None:
    frame = pd.DataFrame({name: [1.0] for name in FEATURE_COLUMNS})
    assert_feature_boundary(frame)
    assert not any(
        any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS)
        for name in FEATURE_COLUMNS
    )


def test_payout_factor_is_once_per_ticket() -> None:
    sp = np.array([1.5, 2.0, 1.8, 2.1, 1.6, 2.4, 1.7])
    units = 7
    gross = 2.0 * units * PAYOUT_FACTOR * np.prod(sp)
    assert np.isclose(gross, 2.0 * units * 0.65 * np.prod(sp))
    assert not np.isclose(gross, 2.0 * units * np.prod(0.65 * sp))


def test_generated_package_contract() -> None:
    if not (OUTPUT / "decision.json").exists():
        return
    decision = json.loads((OUTPUT / "decision.json").read_text())
    policies = pd.read_parquet(OUTPUT / "issue_policies.parquet")
    parity = pd.read_csv(OUTPUT / "accepted_baseline_parity.csv")
    assert policies["issue_year"].max() == 2024
    assert parity[["fixture_parity", "support_parity", "gross_parity"]].all().all()
    assert decision["promotion"] == decision["unlock_210"]


def test_model_choice_is_not_made_on_2024() -> None:
    if not (OUTPUT / "model_receipt.json").exists():
        return
    receipt = json.loads((OUTPUT / "model_receipt.json").read_text())
    assert receipt["selection_year"] == 2023
    assert receipt["terminal_year"] == 2024
    assert receipt["terminal_rows_seen_during_selection"] == 0


def test_anchor_component_arms_are_semantically_separate() -> None:
    if not (OUTPUT / "issue_policies.parquet").exists():
        return
    policies = pd.read_parquet(OUTPUT / "issue_policies.parquet")
    local = policies[policies["model"].eq("ANCHOR_SHRINK_A000")]
    pivot = local.pivot_table(
        index=["issue", "issue_year"],
        columns="arm",
        values=["selected_fixture_keys", "support", "ticket_hhi"],
        aggfunc="first",
    )
    assert pivot["selected_fixture_keys"]["S0O0"].eq(
        pivot["selected_fixture_keys"]["S0O1_SUPPORT"]
    ).all()
    assert pivot["support"]["S0O0"].eq(pivot["support"]["S0O1_ALLOC"]).all()
    assert pivot["support"]["S0O1"].eq(pivot["support"]["S0O1_SUPPORT"]).all()
    assert np.isclose(pivot["ticket_hhi"]["S0O1_SUPPORT"], 1 / 128).all()
