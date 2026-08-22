from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from fixed_expert_moe.contract import (
    EVALUATION_SEEDS,
    EXPERT_NAMES,
    RANK_COUNTS,
    TOTAL_STAKE_CNY,
    TOTAL_TICKETS,
)
from fixed_expert_moe.data import assert_strict_chronology
from fixed_expert_moe.pipeline import _validate_cached_surface

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "results/fixed_expert_moe"


def test_rank_count_contract() -> None:
    assert len(RANK_COUNTS) == len(EXPERT_NAMES) == 8
    assert sum(RANK_COUNTS) == TOTAL_TICKETS
    assert tuple(sorted(RANK_COUNTS, reverse=True)) == RANK_COUNTS


def test_learning_panel_is_complete_and_causal() -> None:
    panel = pd.read_parquet(OUTPUT / "learning_panel.parquet")
    assert not panel.duplicated(["issue", "expert"]).any()
    assert panel.groupby("issue")["expert"].nunique().eq(8).all()
    assert panel["issue_year"].between(2020, 2024).all()
    assert_strict_chronology(panel)


def test_allocation_and_settlement_are_matched() -> None:
    allocation = pd.read_parquet(OUTPUT / "allocations.parquet")
    settlement = pd.read_parquet(OUTPUT / "settlement.parquet")
    assert allocation.groupby(["condition", "issue"])["ticket_count"].sum().eq(512).all()
    assert settlement["stake_cny"].eq(TOTAL_STAKE_CNY).all()
    assert settlement.groupby(["condition", "issue"])["seed"].nunique().eq(len(EVALUATION_SEEDS)).all()


def test_predictions_are_expanding_and_finite() -> None:
    prediction = pd.read_parquet(OUTPUT / "oof_predictions.parquet")
    assert set(prediction["prediction_year"]) == {2022, 2023, 2024}
    assert prediction.filter(like="predicted_").notna().all().all()
    assert prediction.groupby(["condition", "issue"])["expert"].nunique().eq(8).all()


def test_decision_does_not_unlock_without_promotion() -> None:
    decision = json.loads((OUTPUT / "decision.json").read_text())
    assert decision["payout_factor"] == 0.65
    assert decision["payout_application"] == "ONCE_PER_WINNING_COMPLETE_TICKET"
    assert not decision["unlock_210"] or decision["promotion"]


def test_cached_surface_contract() -> None:
    surface = pd.read_parquet(OUTPUT / "model_surface.parquet")
    _validate_cached_surface(surface, tuple(sorted(surface.seed.unique())), (512,))


def test_notebook_is_executed() -> None:
    notebook = json.loads(
        (ROOT / "notebooks/research/fixed-expert-moe/fixed_expert_moe.ipynb").read_text()
    )
    code = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert code and all(cell["execution_count"] is not None for cell in code)
