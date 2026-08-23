from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.low_n_eu_value import pipeline
from src.low_n_eu_value.contract import CAUSAL_GRADE, HORIZON, OUTCOMES, SOURCE_TIMESTAMP_SEMANTICS


def _frames() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    cells = pd.DataFrame(
        [
            {
                "issue": "22001", "issue_year": 2022, "decision_anchor_timestamp_utc": "2022-01-01T12:00:00+00:00", "match_idx": 1,
                "source_match_id": "m1", "outcome_code": code, "outcome_order": position, "source_horizon": HORIZON,
                "source_timestamp_utc": None, "source_timestamp_semantics": SOURCE_TIMESTAMP_SEMANTICS,
                "source_role": "Nowscore_Titan_historical_market_proxy", "source_provenance": "test", "causal_grade": CAUSAL_GRADE,
                "prediction_role_354": "FROZEN_THROUGH_2021_TRANSFER", "train_year_max_354": 2021,
                "average_european_decimal_odds": odds, "contributing_bookmaker_count": 2, "raw_bookmaker_rows": 2,
                "invalid_bookmaker_rows": 0, "missing_bookmaker_fraction": 0.0, "quality_grade": "B", "raw_group_sha256": "a" * 64,
                "raw_implied_probability": 1 / odds, "average_odds_overround": 1.0, "average_odds_devig_probability": probability,
                "source_consensus_devig_probability": probability, "calibrated_probability_354": probability,
                "p_times_odds_contribution": probability * odds, "top2_member": code in "31", "top2_support": "31",
                "top2_retained_mass": 0.8, "top2_reliability": 0.79, "top2_full_cartesian_contribution": 1.0,
                "ticket_level_payout_factor": 0.65, "payout_factor_application": "ONCE_PER_COMPLETE_TICKET",
            }
            for position, (code, odds, probability) in enumerate(zip(OUTCOMES, (2.0, 4.0, 4.0), (0.5, 0.25, 0.25), strict=True))
        ]
    )
    quality = pd.DataFrame([{"issue": "22001", "match_idx": 1, "raw_bookmaker_rows": 2, "contributing_bookmaker_count": 2, "invalid_bookmaker_rows": 0, "missing_bookmaker_fraction": 0.0, "quality_grade": "B", "source_horizon": HORIZON, "source_timestamp_semantics": SOURCE_TIMESTAMP_SEMANTICS, "source_provenance": "test"}])
    recipe = pipeline.build_n_recipe()
    profile = pd.DataFrame([{"issue_year": 2022, "quality_grade": "B", "issues": 1, "fixtures": 1, "cells": 3, "mean_contributing_books": 2.0, "mean_missing_bookmaker_fraction": 0.0, "mean_overround": 1.0, "mean_top2_reliability": 0.79}])
    return {"value_cells": cells, "quality": quality, "n_recipe": recipe, "year_profile": profile}, {"source": "trusted-test-root"}


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    frames, source = _frames()
    target = tmp_path / "package"
    target.mkdir()
    pq.write_table(pa.Table.from_pandas(frames["value_cells"], preserve_index=False), target / "value_cells.parquet")
    frames["quality"].to_csv(target / "quality_by_fixture.csv", index=False)
    frames["year_profile"].to_csv(target / "year_profile.csv", index=False)
    frames["n_recipe"].to_csv(target / "n3_n5_full_cartesian_recipe.csv", index=False)
    (target / "SOURCE_RECEIPT.json").write_text(json.dumps(source), encoding="utf-8")
    freeze = {"value_cells_sha256": pipeline.stable_frame_sha(frames["value_cells"]), "quality_sha256": pipeline.stable_frame_sha(frames["quality"]), "n_recipe_sha256": pipeline.stable_frame_sha(frames["n_recipe"]), "year_profile_sha256": pipeline.stable_frame_sha(frames["year_profile"])}
    (target / "FREEZE_RECEIPT.json").write_text(json.dumps(freeze), encoding="utf-8")
    repo = Path(__file__).resolve().parents[1]
    files = {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest() for path in target.iterdir() if path.is_file()}
    (target / "MANIFEST.json").write_text(json.dumps({"files": files, "implementation_files": pipeline._implementation_hashes(repo)}), encoding="utf-8")
    monkeypatch.setattr(pipeline, "_scientific_frames", lambda *_: (frames, source))
    return target


def _remanifest(target: Path, *, rewrite_freeze: bool = False) -> None:
    if rewrite_freeze:
        frames = {
            "value_cells": pq.read_table(target / "value_cells.parquet").to_pandas(),
            "quality": pd.read_csv(target / "quality_by_fixture.csv", dtype={"issue": "string"}),
            "year_profile": pd.read_csv(target / "year_profile.csv"),
            "n_recipe": pd.read_csv(target / "n3_n5_full_cartesian_recipe.csv"),
        }
        freeze = json.loads((target / "FREEZE_RECEIPT.json").read_text())
        freeze.update({f"{name}_sha256": pipeline.stable_frame_sha(frame) for name, frame in frames.items()})
        (target / "FREEZE_RECEIPT.json").write_text(json.dumps(freeze), encoding="utf-8")
    manifest = json.loads((target / "MANIFEST.json").read_text())
    manifest["files"] = {str(path.relative_to(target)): hashlib.sha256(path.read_bytes()).hexdigest() for path in target.iterdir() if path.is_file() and path.name != "MANIFEST.json"}
    (target / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("column,replacement", [
    # A forged payout / realized-value field is rejected even after the freeze
    # receipt and manifest are rewritten to its altered bytes.
    ("p_times_odds_contribution", 999.0),
    ("ticket_level_payout_factor", 0.99),
    # A forged raw ledger trace or source description is similarly rejected.
    ("raw_group_sha256", "b" * 64),
    ("source_provenance", "forged-source-trace"),
    # The causal time label cannot be changed to future information.
    ("source_timestamp_semantics", "FUTURE_INFORMATION"),
])
def test_verifier_rejects_fully_remanifested_semantic_tampering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, column: str, replacement: object) -> None:
    target = _package(tmp_path, monkeypatch)
    cells = pq.read_table(target / "value_cells.parquet").to_pandas()
    cells.loc[0, column] = replacement
    pq.write_table(pa.Table.from_pandas(cells, preserve_index=False), target / "value_cells.parquet")
    _remanifest(target, rewrite_freeze=True)

    with pytest.raises(AssertionError):
        pipeline.verify_package(Path(__file__).resolve().parents[1], target, Path("unused-features"), Path("unused-source"))


def test_verifier_rejects_forged_ledger_row_that_preserves_local_p_times_odds_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _package(tmp_path, monkeypatch)
    cells = pq.read_table(target / "value_cells.parquet").to_pandas()
    cells.loc[0, "calibrated_probability_354"] = 0.4
    cells.loc[0, "p_times_odds_contribution"] = 0.8
    pq.write_table(pa.Table.from_pandas(cells, preserve_index=False), target / "value_cells.parquet")
    _remanifest(target, rewrite_freeze=True)

    with pytest.raises(AssertionError):
        pipeline.verify_package(Path(__file__).resolve().parents[1], target, Path("unused-features"), Path("unused-source"))


def test_verifier_rejects_forged_source_receipt_after_manifest_rewrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _package(tmp_path, monkeypatch)
    (target / "SOURCE_RECEIPT.json").write_text(json.dumps({"source": "forged-source-root"}), encoding="utf-8")
    _remanifest(target, rewrite_freeze=True)

    with pytest.raises(AssertionError):
        pipeline.verify_package(Path(__file__).resolve().parents[1], target, Path("unused-features"), Path("unused-source"))


def test_committed_profile_notebook_contains_replayable_executed_code() -> None:
    notebook_path = Path(__file__).resolve().parents[1] / "notebooks/research/low-n-eu-value/low_n_eu_value_profile.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]

    assert any("pq.read_table" in "".join(cell["source"]) for cell in code_cells)
    assert all(cell["execution_count"] is not None for cell in code_cells)
    assert not any(output.get("output_type") == "error" for cell in code_cells for output in cell["outputs"])
