import numpy as np
import pandas as pd
import pytest

from issue282.data import OUTCOME_ORDER, pack_issue_cells


def _cells() -> pd.DataFrame:
    rows = []
    for issue, matches in (("26001", ("a", "b")), ("26002", ("c",))):
        for match in matches:
            for index, outcome in enumerate(OUTCOME_ORDER):
                rows.append(
                    {
                        "issue": issue,
                        "match": match,
                        "outcome": outcome,
                        "market_p": 0.5 - index * 0.1,
                        "divergence": index * 0.02,
                    }
                )
    return pd.DataFrame(rows)


def test_pack_variable_size_issue_tensor() -> None:
    packed = pack_issue_cells(
        _cells().sample(frac=1.0, random_state=282),
        issue_col="issue",
        match_col="match",
        outcome_col="outcome",
        feature_cols=("market_p", "divergence"),
    )
    assert packed.issue_ids == ("26001", "26002")
    assert packed.cells.shape == (2, 2, 3, 2)
    assert packed.match_mask.tolist() == [[True, True], [True, False]]
    assert np.isnan(packed.cells[1, 1]).all()


def test_pack_rejects_current_issue_outcome_leakage() -> None:
    frame = _cells().assign(settlement_sp=0.0)
    with pytest.raises(ValueError, match="current-outcome"):
        pack_issue_cells(
            frame,
            issue_col="issue",
            match_col="match",
            outcome_col="outcome",
            feature_cols=("market_p", "settlement_sp"),
        )


def test_pack_rejects_incomplete_match() -> None:
    frame = _cells().iloc[:-1]
    with pytest.raises(ValueError, match="canonical outcomes"):
        pack_issue_cells(
            frame,
            issue_col="issue",
            match_col="match",
            outcome_col="outcome",
            feature_cols=("market_p", "divergence"),
        )
