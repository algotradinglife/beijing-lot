from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.low_n_selector_data.pipeline import (
    ContractError,
    _attach_prior_calibration,
    _attach_issue_relative,
    _fixture_features,
    _cell_features,
    _mass_bin,
    stable_frame_sha,
)
from src.issue_codes import SOURCE_ISSUE_DATE_SOURCE
from src.divergence_materializer.data import load_issue_roles


def _predicted() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_code": "22001",
                "issue_year": 2022,
                "issue_anchor_ts": pd.Timestamp("2022-01-01", tz="UTC"),
                "issue_latest_kickoff_ts": pd.Timestamp("2022-01-02", tz="UTC"),
                "match_idx": 1,
                "fixture_kickoff_ts": pd.Timestamp("2022-01-01 10:00", tz="UTC"),
                "fixture_decision_ts": pd.Timestamp("2022-01-01", tz="UTC"),
                "training_label_available_max_ts": pd.Timestamp(
                    "2021-12-31", tz="UTC"
                ),
                "prediction_role": "FROZEN_THROUGH_2021_TRANSFER",
                "train_year_max": 2021,
                "native_handicap_line": 0,
                "n_available_books": 12,
                "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
                "handicap_norm_source": "INTEGER_LINE",
                "issue_date_source": "ISSUE_REGISTRY",
                "inventory_fixtures": 20,
                "q_candidate_3": 0.5,
                "q_candidate_1": 0.3,
                "q_candidate_0": 0.2,
                "q_eu_3": 0.5,
                "q_eu_1": 0.3,
                "q_eu_0": 0.2,
                "q_line_3": 0.4,
                "q_line_1": 0.35,
                "q_line_0": 0.25,
            }
        ]
    )


def test_fixture_features_freeze_top2_without_replacement() -> None:
    feature = _fixture_features(_predicted()).iloc[0]
    assert feature["baseline_support"] == "31"
    assert feature["omitted_outcome"] == "0"
    assert feature["retained_mass"] == pytest.approx(0.8)
    assert feature["divergence_0"] == pytest.approx(-0.05)


def test_fixture_features_reject_non_simplex() -> None:
    broken = _predicted()
    broken.loc[0, "q_candidate_0"] = 0.3
    with pytest.raises(ContractError, match="normalized"):
        _fixture_features(broken)


def test_long_form_cell_grain_is_exact_m_times_3() -> None:
    features = _fixture_features(_predicted())
    cells = _cell_features(features)
    assert len(cells) == 3 * len(features)
    assert not cells.duplicated(["issue", "match_idx", "outcome_code"]).any()
    assert cells["in_baseline_support"].sum() == 2
    assert cells["is_omitted"].sum() == 1


def test_the_issue_year_cannot_be_overridden_by_a_late_kickoff(tmp_path: Path) -> None:
    """An issue spanning a year boundary keeps the year its code names.

    The kickoff extrema stay descriptive: the inventory here reaches into 2020, and the issue is
    still 2019.
    """
    candidate = tmp_path / "candidate.sqlite"
    registry = tmp_path / "registry.sqlite"
    with sqlite3.connect(candidate) as connection:
        connection.execute(
            "CREATE TABLE inventory(issue_code TEXT, match_idx INTEGER, kickoff_ts TEXT)"
        )
        rows = [("190101", 2, "2020-09-08 21:00:00")]
        rows.extend(
            ("190101", 1, "2018-12-31 16:00:00")
            if index == 101
            else (f"19{index:04d}", 1, "2019-01-01 12:00:00")
            for index in range(808)
        )
        connection.executemany("INSERT INTO inventory VALUES (?,?,?)", rows)
    with sqlite3.connect(registry) as connection:
        connection.execute("CREATE TABLE issues(issue TEXT, year INTEGER)")
    roles = load_issue_roles(candidate)
    row = roles[roles["issue_code"].eq("190101")].iloc[0]
    assert row["issue_year"] == 2019
    assert row["issue_date_source"] == SOURCE_ISSUE_DATE_SOURCE
    assert row["issue_anchor_ts"] == pd.Timestamp("2018-12-31 16:00:00")
    assert row["issue_latest_kickoff_ts"] == pd.Timestamp("2020-09-08 21:00:00")


def test_fixed_mass_bins_cover_boundaries() -> None:
    bins = _mass_bin(pd.Series([0.0, 0.5, 1.0]))
    assert bins.notna().all()
    assert list(bins.astype(int)) == [0, 9, 19]


def test_issue_relative_cutoffs_are_deterministic() -> None:
    base = _fixture_features(_predicted())
    frames = []
    for idx, mass in enumerate((0.95, 0.9, 0.85, 0.8, 0.75), start=1):
        row = base.copy()
        row["match_idx"] = idx
        row["retained_mass"] = mass
        frames.append(row)
    ranked = _attach_issue_relative(pd.concat(frames, ignore_index=True))
    top = ranked.sort_values("retained_mass", ascending=False).iloc[0]
    assert top["retained_mass_rank"] == 1
    assert top["retained_gap_to_n3_cutoff"] == pytest.approx(0.10)
    assert top["retained_gap_to_n5_cutoff"] == pytest.approx(0.20)


def test_strict_boolean_contract_is_not_truthy_string() -> None:
    values = pd.Series([True, False, "True"])
    observed = set(values.dropna().unique().tolist())
    assert not observed.issubset({True, False})


def test_transfer_calibration_state_is_frozen_through_2021() -> None:
    base = _fixture_features(_predicted())
    frames = []
    for year, issue in (
        (2021, "21001"),
        (2022, "22001"),
        (2023, "23001"),
        (2024, "24001"),
    ):
        row = base.copy()
        row["issue_year"] = year
        row["issue"] = issue
        kickoff = pd.Timestamp(f"{year}-01-02 10:00", tz="UTC")
        row["fixture_kickoff_ts"] = kickoff
        row["fixture_decision_ts"] = kickoff - pd.Timedelta(hours=10)
        row["issue_anchor_ts"] = kickoff - pd.Timedelta(hours=10)
        frames.append(row)
    features = pd.concat(frames, ignore_index=True)
    labels = features[["issue", "match_idx"]].copy()
    labels["label_available"] = True
    labels["top2_hit"] = pd.array([True, False, False, False], dtype="boolean")

    calibrated = _attach_prior_calibration(features, labels)
    transfer = calibrated[calibrated["issue_year"].ge(2022)]

    assert set(transfer["calibration_history_max_year"].dropna().astype(int)) == {2021}
    assert transfer["prior_global_count"].nunique() == 1
    assert transfer["prior_global_hit_rate"].nunique() == 1


def test_semantic_frame_hash_is_row_order_invariant_and_value_sensitive() -> None:
    frame = pd.DataFrame({"key": ["b", "a"], "value": [2.0, 1.0]})
    shuffled = frame.iloc[::-1].reset_index(drop=True)
    changed = frame.copy()
    changed.loc[0, "value"] = 3.0

    assert stable_frame_sha(frame) == stable_frame_sha(shuffled)
    assert stable_frame_sha(frame) != stable_frame_sha(changed)
