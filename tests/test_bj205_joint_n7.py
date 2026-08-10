from __future__ import annotations

from pathlib import Path
from typing import TextIO

import nbformat
import numpy as np
import pandas as pd
import pytest

from scripts import execute_bj205_notebook
from unified_value.joint_n7 import (
    CONFIGS,
    N,
    OUTCOMES,
    Inputs,
    JointN7Error,
    _config_products,
    _fallback_mix,
    _normalize,
    build_issue_tickets,
    build_value_matrix,
    load_match_panel,
    run,
)


def _panel(matches: int = N) -> pd.DataFrame:
    rows = []
    for match_idx in range(1, matches + 1):
        row: dict[str, object] = {
            "issue": "x",
            "year": 2025,
            "issue_order": 1.0,
            "match_idx": match_idx,
            "split": "LOCKED_TEST",
            "result_code": "3",
            "label_available": True,
            "market_eligible": True,
            "model_used": False,
            "fallback_reason": "OOD",
            "seed_count": 3,
        }
        for code, probability, sp in zip(
            OUTCOMES, (0.2, 0.3, 0.5), (5.0, 3.0, 2.0), strict=True
        ):
            row[f"market_probability_{code}"] = probability
            row[f"fallback_mixed_probability_{code}"] = probability
            row[f"predicted_final_sp_{code}"] = sp
            row[f"official_final_sp_{code}"] = sp
            row[f"seed_std__fallback_mixed_probability_{code}"] = 0.0
            row[f"seed_std__predicted_final_sp_{code}"] = 0.0
        rows.append(row)
    return pd.DataFrame(rows)


def _source_frames(matches: int = N) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger_rows = []
    cell_rows = []
    for match_idx in range(1, matches + 1):
        for seed in range(3):
            row: dict[str, object] = {
                "issue": "x",
                "year": 2025,
                "issue_order": 1.0,
                "match_idx": match_idx,
                "split": "LOCKED_TEST",
                "model_id": "LOGISTIC_RESIDUAL",
                "seed": seed,
                "result_code": "3",
                "label_available": True,
                "market_eligible": True,
                "model_used": True,
                "fallback_reason": "NONE",
            }
            for code, probability, sp in zip(
                OUTCOMES, (0.2, 0.3, 0.5), (5.0, 3.0, 2.0), strict=True
            ):
                row[f"market_probability_{code}"] = probability
                row[f"fallback_mixed_probability_{code}"] = probability
                row[f"delta_logit_{code}"] = 0.0
                row[f"predicted_final_sp_{code}"] = sp
                row[f"official_final_sp_{code}"] = sp
            ledger_rows.append(row)
        for code, sp in zip(OUTCOMES, (5.0, 3.0, 2.0), strict=True):
            cell_rows.append(
                {
                    "issue": "x",
                    "match_idx": match_idx,
                    "outcome_code": code,
                    "predicted_final_sp_input": sp,
                }
            )
    return pd.DataFrame(ledger_rows), pd.DataFrame(cell_rows)


def _write_sources(
    tmp_path: Path, ledger: pd.DataFrame, cells: pd.DataFrame
) -> tuple[Path, Path]:
    ledger_path = tmp_path / "ledger.parquet"
    cells_path = tmp_path / "cells.parquet"
    ledger.to_parquet(ledger_path, index=False)
    cells.to_parquet(cells_path, index=False)
    return ledger_path, cells_path


def test_exhaustive_n7_identity_and_product_normalize() -> None:
    assert CONFIGS.shape == (3**N, N)
    p = np.tile(np.asarray([[0.2, 0.3, 0.5]]), (N, 1))
    joint = _normalize(_config_products(p))
    assert np.isclose(joint.sum(), 1.0)
    assert np.isclose(joint[0], 0.2**N)


def test_fallback_is_exact_market_bytes() -> None:
    market = _normalize(np.arange(1, 3**N + 1, dtype=float))
    candidate = market[::-1].copy()
    record = {"context": np.asarray([9.0, 9.0, 9.0]), "market_joint": market}
    mixed, supported = _fallback_mix(
        [record], [candidate], (np.zeros(3), np.ones(3))
    )
    assert not supported[0]
    assert mixed[0].tobytes() == market.tobytes()


def test_zero_residual_cell_matrix_uses_exact_market_probability() -> None:
    value = build_value_matrix(_panel(1))
    assert value.calibrated_true_probability.to_list() == [0.2, 0.3, 0.5]
    assert value.fallback_applied.all()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("market_probability_3", 0.3),  # row sum 1.1
        ("market_probability_3", np.nan),
        ("fallback_mixed_probability_1", np.inf),
        ("fallback_mixed_probability_0", 0.0),
    ],
)
def test_malformed_probability_triplets_fail_before_ticket_construction(
    column: str, value: float
) -> None:
    panel = _panel()
    panel.loc[0, column] = value
    with pytest.raises(JointN7Error, match="finite/positive/simplex"):
        build_issue_tickets(panel)


def test_duplicate_nuisance_seed_source_key_is_rejected(tmp_path: Path) -> None:
    ledger, cells = _source_frames()
    ledger = pd.concat([ledger, ledger.iloc[[0]]], ignore_index=True)
    ledger_path, cells_path = _write_sources(tmp_path, ledger, cells)
    with pytest.raises(JointN7Error, match="not unique"):
        load_match_panel(ledger_path, cells_path)


def test_empty_source_is_rejected(tmp_path: Path) -> None:
    ledger, cells = _source_frames()
    ledger_path, cells_path = _write_sources(tmp_path, ledger.iloc[0:0], cells)
    with pytest.raises(JointN7Error, match="ledger is empty"):
        load_match_panel(ledger_path, cells_path)


def test_fewer_than_seven_eligible_matches_emits_no_bet() -> None:
    tickets, census = build_issue_tickets(_panel(N - 1))
    assert tickets == {}
    assert census.ticket_status.to_list() == ["NO_BET_LT7"]
    assert census.eligible_matches.to_list() == [N - 1]


def test_runner_cleans_stage_after_input_exception(tmp_path: Path) -> None:
    ledger, cells = _source_frames()
    ledger.loc[0, "market_probability_3"] = 0.3
    ledger_path, cells_path = _write_sources(tmp_path, ledger, cells)
    output = tmp_path / "evidence"
    with pytest.raises(JointN7Error, match="finite/positive/simplex"):
        run(Inputs(ledger_path, cells_path, output))
    assert not output.exists()
    assert not (tmp_path / ".evidence.stage").exists()


def test_notebook_atomic_writer_preserves_target_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    notebook = tmp_path / "analysis.ipynb"
    notebook.write_text("ORIGINAL", encoding="utf-8")

    def interrupted_write(document: object, stream: TextIO) -> None:
        del document
        stream.write("PARTIAL")
        raise RuntimeError("interrupted")

    monkeypatch.setattr(nbformat, "write", interrupted_write)
    with pytest.raises(RuntimeError, match="interrupted"):
        execute_bj205_notebook._atomic_write_notebook(
            nbformat.v4.new_notebook(), notebook
        )
    assert notebook.read_text(encoding="utf-8") == "ORIGINAL"
    assert list(tmp_path.glob(".*.ipynb.*.ipynb.tmp")) == []
