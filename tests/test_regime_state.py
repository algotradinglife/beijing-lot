from __future__ import annotations

import numpy as np
import pandas as pd

from src.regime_state.contract import MARKET_FEATURES
from src.regime_state.data import add_lagged_state
from src.regime_state.model import _block_shift, decide, model_lag_columns


def _minimal_panel(rows: int = 50) -> pd.DataFrame:
    frame = pd.DataFrame({
        "issue_code": [str(20000 + index) for index in range(rows)],
        "issue_year": [2020 + index // 10 for index in range(rows)],
        "issue_anchor_ts": pd.date_range("2020-01-01", periods=rows, freq="7D").astype(str),
    })
    sources = [
        "eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual",
        "allocator_delta", "eu_logloss", "line_logloss", "eu_top1_residual",
        "line_top1_residual", "pnl_l000", "pnl_l100", "top2_n7_pnl",
        "top2_n7_hit", "top2_n7_miss_distance",
    ]
    for offset, source in enumerate(sources):
        frame[source] = np.arange(rows, dtype=float) + offset
    return frame


def test_lagged_state_excludes_same_issue_value() -> None:
    panel = _minimal_panel()
    output, _ = add_lagged_state(panel)
    assert output.loc[10, "lag_eu_brier_roll5_mean"] == np.mean([5, 6, 7, 8, 9])
    assert output.loc[10, "lag_eu_brier_roll5_mean"] != np.mean([6, 7, 8, 9, 10])
    observed = pd.to_datetime(output.lag_eu_brier_last_observation_ts, utc=True)
    anchor = pd.to_datetime(output.issue_anchor_ts, utc=True)
    assert (observed.dropna() < anchor[observed.notna()]).all()


def test_model_features_never_include_year_or_issue_identity() -> None:
    _, lag = add_lagged_state(_minimal_panel())
    features = [*MARKET_FEATURES, *model_lag_columns(lag)]
    assert "issue_year" not in features
    assert "issue_code" not in features
    assert not any("last_observation_ts" in column for column in features)


def test_same_anchor_issues_share_state_and_cannot_see_each_other() -> None:
    panel = _minimal_panel()
    panel.loc[11, "issue_anchor_ts"] = panel.loc[10, "issue_anchor_ts"]
    output, _ = add_lagged_state(panel)
    columns = ["lag_eu_brier_roll5_mean", "lag_allocator_delta_ewm5"]
    assert output.loc[10, columns].equals(output.loc[11, columns])
    observed = pd.to_datetime(output.loc[11, "lag_eu_brier_last_observation_ts"], utc=True)
    anchor = pd.to_datetime(output.loc[11, "issue_anchor_ts"], utc=True)
    assert observed < anchor


def test_block_shift_keeps_rows_but_destroys_lag_alignment() -> None:
    frame = pd.DataFrame({"current": np.arange(12), "lag": np.arange(12) * 10})
    shifted = _block_shift(frame, ["lag"], block_size=3)
    assert shifted.current.equals(frame.current)
    assert sorted(shifted.lag) == sorted(frame.lag)
    assert not shifted.lag.equals(frame.lag)


def test_sparse_allocator_response_selects_redesign() -> None:
    state = pd.DataFrame({"allocator_delta": [0.0] * 40 + [1.0] * 2})
    metric_rows = []
    for target in ("eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual", "allocator_delta"):
        for year in (2023, 2024):
            metric_rows.extend([
                {"target": target, "issue_year": year, "condition": "CURRENT_RIDGE", "mse": 1.0},
                {"target": target, "issue_year": year, "condition": "COMBINED_HGBR", "mse": 0.8},
            ])
    persistence = pd.DataFrame([
        {"target": target, "lag_issues": 1, "autocorrelation": 0.2}
        for target in ("eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual")
    ])
    bootstrap = pd.DataFrame([
        {"target": target, "issue_year": year, "ci95_low": 0.1}
        for target in ("eu_brier", "line_brier") for year in (2023, 2024)
    ])
    result = decide(state, pd.DataFrame(metric_rows), persistence, bootstrap)
    assert result["disposition"] == "SPARSE_RESPONSE_REDESIGN"
