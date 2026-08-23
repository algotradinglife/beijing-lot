from __future__ import annotations

import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from src.low_n_eu_value_data import pipeline
from src.low_n_eu_value_data.pipeline import (
    ContractError,
    build_value_cells,
    nfold_cartesian_expected_payout,
    stable_frame_sha,
    verify_cell_frame,
)


def _selector_features() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue": "22001",
                "issue_year": 2022,
                "issue_anchor_ts": "2022-01-01T12:00:00Z",
                "match_idx": 1,
                "baseline_support": "31",
                "q_candidate_3": 0.50,
                "q_candidate_1": 0.30,
                "q_candidate_0": 0.20,
                "n_available_books": 2,
                "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
                "prediction_role": "FROZEN_THROUGH_2021_TRANSFER",
                "train_year_max": 2021,
                "calibration_history_max_year": 2021,
            }
        ]
    )


def _odds() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "issue": "22001",
                "match_idx": 1,
                "source_match_ids": "candidate:11",
                "source_payload_sha256s": "a,b",
                "source_bookmakers": "A,B",
                "raw_bookmaker_row_count": 2,
                "contributing_bookmaker_count": 2,
                "average_decimal_odds_3": 2.0,
                "average_decimal_odds_1": 4.0,
                "average_decimal_odds_0": 5.0,
            }
        ]
    )


def test_build_value_cells_preserves_outcome_order_and_cartesian_math() -> None:
    cells = build_value_cells(_selector_features(), _odds())

    assert cells.outcome_code.tolist() == ["3", "1", "0"]
    assert cells.loc[cells.outcome_code.eq("3"), "raw_implied_probability"].iloc[0] == pytest.approx(0.5)
    assert cells.overround.nunique() == 1
    assert cells.overround.iloc[0] == pytest.approx(0.95)
    assert cells.devig_probability.sum() == pytest.approx(1.0)
    assert cells.loc[cells.outcome_code.eq("3"), "p_times_odds"].iloc[0] == pytest.approx(1.0)
    assert cells.top2_coverage_reliability.nunique() == 1
    assert cells.top2_coverage_reliability.iloc[0] == pytest.approx(0.8)
    assert cells.top2_expected_gross_factor.iloc[0] == pytest.approx(2.2)
    assert set(cells.ticket_level_once_65_factor) == {0.65}
    assert nfold_cartesian_expected_payout([2.0, 2.0, 2.0]) == pytest.approx(5.2)
    assert nfold_cartesian_expected_payout([2.0, 2.0, 2.0]) != pytest.approx(0.65**3 * 8.0)
    verify_cell_frame(cells)


def test_build_value_cells_rejects_source_book_count_mismatch() -> None:
    odds = _odds()
    odds.loc[0, "contributing_bookmaker_count"] = 1

    with pytest.raises(ContractError, match="bookmaker count"):
        build_value_cells(_selector_features(), odds)


def test_verifier_rejects_tampered_value_label_and_provenance() -> None:
    cells = build_value_cells(_selector_features(), _odds())

    for column, value in (
        ("p_times_odds", 99.0),
        ("top2_support", "30"),
        ("source_match_ids", "future-source"),
        ("source_observed_at_utc", pd.Timestamp("2022-01-01T12:00:01")),
    ):
        tampered = cells.copy()
        tampered.loc[0, column] = value
        with pytest.raises(ContractError):
            verify_cell_frame(tampered)


def test_source_bound_verifier_rejects_remanifested_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An attacker can update package hashes, but not the external source replay."""

    repo = Path(__file__).resolve().parents[1]
    original = repo / "results" / "low_n_eu_value_data"
    if not original.is_dir():
        pytest.skip("requires the committed Issue #358 package")
    package = tmp_path / "package"
    shutil.copytree(original, package)
    original_manifest = json.loads((original / "MANIFEST.json").read_text(encoding="utf-8"))
    original_source = json.loads((original / "SOURCE_RECEIPT.json").read_text(encoding="utf-8"))
    original_freeze = json.loads((original / "FREEZE_RECEIPT.json").read_text(encoding="utf-8"))
    frames = {
        "implementation_hashes": original_manifest["implementation_files"],
        "source_receipt": original_source,
        "freeze_receipt": original_freeze,
        "coverage": pd.read_csv(original / "analysis" / "coverage.csv"),
    }
    monkeypatch.setattr(pipeline, "locate_data_root", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(pipeline, "_scientific_frames", lambda *_args, **_kwargs: frames)

    cells = pd.read_parquet(package / "cells" / "eu_value_cells.parquet")
    cells.loc[0, "source_match_ids"] = "remanitested-source-trace"
    cells.to_parquet(package / "cells" / "eu_value_cells.parquet", index=False)
    forged_freeze = dict(original_freeze)
    forged_freeze["cell_frame_sha256"] = stable_frame_sha(cells)
    (package / "FREEZE_RECEIPT.json").write_text(
        json.dumps(forged_freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    forged_manifest = dict(original_manifest)
    forged_manifest["files"] = {
        str(path.relative_to(package)): pipeline.sha256_file(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    (package / "MANIFEST.json").write_text(
        json.dumps(forged_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="cell frame does not replay"):
        pipeline.verify_package(repo, package, tmp_path)


def test_source_bound_verifier_rejects_remanifested_nfold_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = Path(__file__).resolve().parents[1]
    original = repo / "results" / "low_n_eu_value_data"
    if not original.is_dir():
        pytest.skip("requires the committed Issue #358 package")
    package = tmp_path / "package"
    shutil.copytree(original, package)
    manifest = json.loads((original / "MANIFEST.json").read_text(encoding="utf-8"))
    frames = {
        "implementation_hashes": manifest["implementation_files"],
        "source_receipt": json.loads((original / "SOURCE_RECEIPT.json").read_text(encoding="utf-8")),
        "freeze_receipt": json.loads((original / "FREEZE_RECEIPT.json").read_text(encoding="utf-8")),
        "coverage": pd.read_csv(original / "analysis" / "coverage.csv"),
        "missingness": pd.read_csv(original / "analysis" / "missingness.csv"),
        "nfold": pd.read_csv(original / "analysis" / "nfold.csv"),
        "field_dictionary": pd.read_csv(original / "analysis" / "field_dictionary.csv"),
    }
    monkeypatch.setattr(pipeline, "locate_data_root", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(pipeline, "_scientific_frames", lambda *_args, **_kwargs: frames)
    forged_nfold = pd.read_csv(package / "analysis" / "nfold.csv")
    forged_nfold.loc[forged_nfold.n.eq(3), "ticket_payout_factor"] = 0.65**3
    forged_nfold.to_csv(package / "analysis" / "nfold.csv", index=False)
    forged_manifest = dict(manifest)
    forged_manifest["files"] = {
        str(path.relative_to(package)): pipeline.sha256_file(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    (package / "MANIFEST.json").write_text(
        json.dumps(forged_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(AssertionError, match="analysis/nfold.csv does not replay"):
        pipeline.verify_package(repo, package, tmp_path)
