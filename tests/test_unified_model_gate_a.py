"""Portable outcome-boundary and common-adapter tests for #204 Gate A v4."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd

from unified_model.contract import CONTRACT_VERSION, MODEL_FEATURES, SP_TARGET
from unified_model.gate_a import (
    COMMON_FEATURES,
    FULL_3SP_IDENTITY_COLUMNS,
    HISTORY_COLUMNS,
    PCLOSE_COLUMNS,
    _common_adapter,
    _read_full_3sp_identity,
    _read_history_rows,
    _validate_source,
    load_common_issue,
    verify_package,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/bj203_causal_tensor_v2"
FROZEN = ROOT / "results/bj204_gate_a_preoutcome_v4"
FIXTURES = ROOT / "tests/fixtures/bj204"


def test_bj204_gate_a_v4_manifest_is_canonical_and_outcome_unexposed() -> None:
    receipt = verify_package(FROZEN)
    assert receipt == {
        "contract_version": CONTRACT_VERSION,
        "files": 22,
        "status": "PASS",
    }
    card = json.loads((FROZEN / "freeze_card.json").read_text(encoding="utf-8"))
    assert card["source"]["labels_opened"] is False
    assert card["schema"]["sp_target"] == SP_TARGET
    assert card["schema"]["model_features"] == list(MODEL_FEATURES)
    assert not list(FROZEN.rglob("*settlement*"))


def test_bj204_gate_a_v4_restores_full_344_issue_chronology() -> None:
    splits = pd.read_csv(FROZEN / "split_manifest.csv", dtype={"issue": str})
    development = splits.loc[splits.role.eq("DEVELOPMENT_CV")]
    test = splits.loc[splits.role.eq("RETROSPECTIVE_TEST_LOCKED")]
    assert development.issue.nunique() == 344
    assert development.groupby("year").issue.nunique().to_dict() == {
        2019: 55, 2020: 44, 2021: 58, 2022: 58, 2023: 55, 2024: 59, 2025: 15,
    }
    assert test.issue.nunique() == 75
    assert test.issue.astype(int).between(25043, 25125).sum() == 42
    assert test.issue.astype(int).between(26011, 26049).sum() == 33
    assert splits.labels_permitted_gate_a.astype(str).str.lower().eq("false").all()


def test_bj204_common_schema_coverage_and_target_identity_censuses() -> None:
    coverage = pd.read_csv(FROZEN / "common_schema_coverage_by_period.csv")
    development = coverage.loc[coverage.role.eq("DEVELOPMENT_CV")]
    test = coverage.loc[coverage.role.eq("RETROSPECTIVE_TEST_LOCKED")]
    assert development.matches.sum() == 102245
    assert development.complete_market_rows.sum() == 101029
    assert test.matches.sum() == 16990
    assert test.complete_market_rows.sum() == 16968
    targets = pd.read_csv(FROZEN / "development_target_identity_reconciliation.csv", dtype={"issue": str})
    assert len(targets) == 1024
    assert int(targets.official_target_identity_available.sum()) == 1021
    assert targets.labels_opened.astype(str).str.lower().eq("false").all()
    detail = pd.read_csv(FROZEN / "common_schema_field_coverage.csv")
    assert set(detail.feature) == set(COMMON_FEATURES)
    assert set(detail.outcome_code.astype(str)) == {"0", "1", "3"}


def test_bj204_common_adapter_loads_development_and_test_through_one_api(tmp_path: Path) -> None:
    identity, _ = _validate_source(SOURCE)
    mini = identity.loc[
        identity.issue.astype(str).eq("190101") & identity.match_idx.isin([1, 2])
    ].copy()
    history = _read_history_rows(FIXTURES / "history_proxy.csv", ((25043, 25043),))
    full = _read_full_3sp_identity(FIXTURES / "full_3sp_identity.csv")
    features, masks, _registry, _coverage, _duplicates = _common_adapter(
        SOURCE, mini, history, full, FIXTURES / "pclose_proxy.csv", strict_census=False,
    )
    package = tmp_path / "adapter"
    package.mkdir()
    features.to_parquet(package / "common_cell_features.parquet", index=False)
    masks.to_parquet(package / "common_cell_masks.parquet", index=False)
    dev_values, dev_masks, names = load_common_issue(package, "190101")
    test_values, test_masks, test_names = load_common_issue(package, "25043")
    assert names == test_names == COMMON_FEATURES == MODEL_FEATURES
    assert dev_values.shape == test_values.shape == (2, 3, len(COMMON_FEATURES))
    assert dev_masks.shape == test_masks.shape == dev_values.shape
    assert np.isfinite(dev_values[:, :, 0]).all()
    assert np.isfinite(test_values[:, :, 0]).all()
    assert dev_masks[:, :, 0].all() and test_masks[:, :, 0].all()
    assert dev_values[:, :, 2].all() and not dev_values[:, :, 3].any()
    assert test_values[:, :, 3].all() and not test_values[:, :, 2].any()


def test_bj204_fixture_sources_use_only_documented_pre_event_columns() -> None:
    assert HISTORY_COLUMNS == (
        "issue", "match_idx", "league", "kickoff_ts", "handicap_line",
        "avg_eu_home", "avg_eu_draw", "avg_eu_away",
    )
    assert FULL_3SP_IDENTITY_COLUMNS == ("expect", "match_no", "match_uid")
    assert PCLOSE_COLUMNS == ("match_id", "issue", "p_close_3", "p_close_1", "p_close_0", "beidan_hcap")
    assert not {"score", "result_code", "winning_sp", "final_sp"}.intersection(HISTORY_COLUMNS)


def test_bj204_full_replay_requires_explicit_sources_without_parent_discovery() -> None:
    script = (ROOT / "scripts/freeze_bj204_model_gate_a.py").read_text(encoding="utf-8")
    assert "_default_data_source" not in script
    assert 'freeze.add_argument("--history-source", type=Path, required=True)' in script
    assert 'freeze.add_argument("--full-3sp-identity-source", type=Path, required=True)' in script
    assert 'freeze.add_argument("--pclose-source", type=Path, required=True)' in script


def test_bj204_data_build_notebook_is_executed_and_audits_construction() -> None:
    notebook = nbformat.read(ROOT / "notebooks/research/issue-204/bj204_track_a_gate_a.ipynb", as_version=4)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert [cell.execution_count for cell in code] == list(range(1, len(code) + 1))
    assert not [output for cell in code for output in cell.outputs if output.output_type == "error"]
    source = "\n".join("".join(cell.source) for cell in code)
    for token in (
        "common_cell_features", "common_schema_coverage", "load_common_issue",
        "development_target_identity", "FULL_EXPLICIT_IMMUTABLE_SOURCES",
        "BOUNDED_COMMITTED_FIXTURES", "BJ204_HISTORY_SOURCE",
    ):
        assert token in source
