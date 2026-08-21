from pathlib import Path

import pandas as pd
import pytest

from issue284.outcome_surface import (
    development_holdout_rank_spearman,
    load_counterfactual_labels,
    summarize_actions,
    summarize_focus_modes,
)


def _panel() -> pd.DataFrame:
    rows = []
    for year, market, cell in [(2021, 0.2, -0.1), (2022, 0.3, 0.0), (2023, -0.4, 0.1)]:
        for mode, value in [("MARKET_PROBABILITY", market), ("CELL_VALUE", cell)]:
            rows.append(
                {
                    "issue": year * 100 + 1,
                    "issue_year": year,
                    "selector": "ALL",
                    "outcome_weight_mode": mode,
                    "n": 7,
                    "generator": "TOP_VALUE",
                    "k": 8,
                    "return_per_cny_mean": value,
                }
            )
    return pd.DataFrame(rows)


def test_summarize_actions_keeps_development_and_holdout_separate() -> None:
    summary = summarize_actions(_panel())
    market = summary.loc[
        summary["outcome_weight_mode"].eq("MARKET_PROBABILITY")
    ].iloc[0]
    assert market["development_roi_pct"] == pytest.approx(25.0)
    assert market["holdout_roi_pct"] == pytest.approx(-40.0)


def test_focus_bootstrap_uses_issue_rows() -> None:
    summary = summarize_focus_modes(_panel(), draws=100, seed=1)
    assert set(summary["outcome_weight_mode"]) == {
        "CELL_VALUE",
        "MARKET_PROBABILITY",
    }
    assert set(summary["issues"]) == {3}


def test_rank_transfer_is_finite() -> None:
    result = development_holdout_rank_spearman(summarize_actions(_panel()))
    assert result == pytest.approx(-1.0)


def test_loader_rejects_sealed_year(tmp_path: Path) -> None:
    panel = _panel().copy()
    panel.loc[0, "issue_year"] = 2024
    path = tmp_path / "labels.parquet"
    panel.to_parquet(path)
    with pytest.raises(ValueError, match=r"2024\+"):
        load_counterfactual_labels([path])
