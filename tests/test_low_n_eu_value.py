from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from src.low_n_eu_value.pipeline import (
    ContractError,
    _trusted_sqlite_sha,
    build_n_recipe,
    build_value_cells,
)


def _features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue": "22001",
                "issue_year": 2022,
                "issue_anchor_ts": pd.Timestamp("2022-01-01T12:00:00Z"),
                "match_idx": 1,
                "prediction_role": "FROZEN_THROUGH_2021_TRANSFER",
                "train_year_max": 2021,
                "baseline_support": "31",
                "retained_mass": 0.80,
                "prior_global_hit_rate": 0.79,
                "n_available_books": 2,
                "input_missing_count": 0,
                "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
                "q_raw_eu_3": 0.50,
                "q_raw_eu_1": 0.25,
                "q_raw_eu_0": 0.25,
                "q_candidate_3": 0.55,
                "q_candidate_1": 0.25,
                "q_candidate_0": 0.20,
            }
        ]
    )


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_code": "22001",
                "match_idx": 1,
                "source_match_id": "nowscore-1",
                "snapshot_kind": "10h",
                "bookmaker_id": "A",
                "v1": 2.0,
                "v2": 4.0,
                "v3": 4.0,
            },
            {
                "issue_code": "22001",
                "match_idx": 1,
                "source_match_id": "nowscore-1",
                "snapshot_kind": "10h",
                "bookmaker_id": "B",
                "v1": 2.0,
                "v2": 4.0,
                "v3": 4.0,
            },
            {
                "issue_code": "22001",
                "match_idx": 1,
                "source_match_id": "nowscore-1",
                "snapshot_kind": "10h",
                "bookmaker_id": "invalid",
                "v1": 2.0,
                "v2": 1.0,
                "v3": 4.0,
            },
        ]
    )


def test_value_cells_preserve_outcome_order_and_european_value_identities() -> None:
    cells, quality = build_value_cells(_features(), _quotes())

    assert cells["outcome_code"].tolist() == ["3", "1", "0"]
    home = cells.iloc[0]
    assert home["average_european_decimal_odds"] == pytest.approx(2.0)
    assert home["raw_implied_probability"] == pytest.approx(0.5)
    assert home["average_odds_overround"] == pytest.approx(1.0)
    assert home["average_odds_devig_probability"] == pytest.approx(0.5)
    assert home["source_consensus_devig_probability"] == pytest.approx(0.5)
    assert home["calibrated_probability_354"] == pytest.approx(0.55)
    assert home["p_times_odds_contribution"] == pytest.approx(1.1)
    assert home["top2_member"]
    assert home["top2_reliability"] == pytest.approx(0.79)
    assert home["top2_full_cartesian_contribution"] == pytest.approx(1.05)
    assert set(cells["source_timestamp_semantics"]) == {"RELATIVE_10H_LABEL_NO_EXACT_OBSERVATION_TIMESTAMP"}
    assert quality.iloc[0]["invalid_bookmaker_rows"] == 1


def test_value_cells_reject_source_consensus_that_does_not_match_frozen_354_surface() -> None:
    features = _features()
    features.loc[0, "q_raw_eu_3"] = 0.49

    with pytest.raises(ContractError, match="source consensus"):
        build_value_cells(features, _quotes())


def test_n_recipe_applies_065_once_without_selecting_fixtures() -> None:
    recipe = build_n_recipe()

    assert recipe["n"].tolist() == [3, 4, 5]
    assert recipe["full_cartesian_ticket_count"].tolist() == [8, 16, 32]
    assert recipe["ticket_level_payout_factor"].tolist() == [0.65, 0.65, 0.65]
    assert recipe["payout_factor_application"].tolist() == ["ONCE_PER_COMPLETE_TICKET"] * 3
    assert recipe["fixture_selection_performed"].eq(False).all()


def test_trusted_sqlite_receipt_refuses_nonempty_wal_sidecar(tmp_path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE quotes (id INTEGER PRIMARY KEY)")
    source.with_name(source.name + "-wal").write_bytes(b"unreceipted changes")

    with pytest.raises(ContractError, match="live unreceipted sidecars"):
        _trusted_sqlite_sha(source)
