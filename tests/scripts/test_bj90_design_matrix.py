"""Regression coverage for #90's explicit one-hot design contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj90_gate_b", ROOT / "scripts" / "evaluate_bj90_asof_sp_gate_b.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(match_id: str, league: str, offset: float) -> dict[str, str]:
    data = {
        "match_id": match_id,
        "league": league,
        "kickoff_ts": "2024-01-01 12:00:00",
        "handicap_line_norm": "0",
    }
    for market in ("euro", "asian", "ou"):
        data[f"{market}_n"] = "3"
        for position in ("1", "2", "3"):
            data[f"{market}_v{position}"] = str(2.0 + offset + int(position) / 10)
            data[f"{market}_i_v{position}"] = str(2.1 + offset + int(position) / 10)
            data[f"{market}_min{position}"] = str(1.9 + offset + int(position) / 10)
            data[f"{market}_max{position}"] = str(2.2 + offset + int(position) / 10)
    return data


def test_known_and_unseen_league_one_hot_blocks_are_deterministic() -> None:
    train = [row("1", "Alpha", 0.0), row("2", "Beta", 0.2)]
    test = [row("3", "Alpha", 0.1), row("4", "Gamma", 0.3)]
    design_train, design_test = MODULE.design(train, test)
    league_start = 1 + MODULE.NUMERIC_DIM

    np.testing.assert_array_equal(design_train[0, league_start:], np.array([1.0, 0.0]))
    np.testing.assert_array_equal(design_train[1, league_start:], np.array([0.0, 1.0]))
    np.testing.assert_array_equal(design_test[0, league_start:], np.array([1.0, 0.0]))
    np.testing.assert_array_equal(design_test[1, league_start:], np.array([0.0, 0.0]))
