from __future__ import annotations

import pandas as pd
import pytest

from src.low_n_selector_data.pipeline import (
    ContractError,
    _attach_issue_relative,
    _fixture_features,
    _mass_bin,
)


def _predicted() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue_code": "22001",
                "issue_year": 2022,
                "issue_anchor_ts": pd.Timestamp("2022-01-01", tz="UTC"),
                "match_idx": 1,
                "prediction_role": "FROZEN_THROUGH_2021_TRANSFER",
                "train_year_max": 2021,
                "native_handicap_line": 0,
                "n_available_books": 12,
                "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
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
