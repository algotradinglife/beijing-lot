"""Portable outcome-boundary and common-adapter tests for #204 Gate A v5."""

from __future__ import annotations

import json
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
import pytest

from unified_model.contract import (
    CONTRACT_VERSION,
    MODEL_FEATURES,
    OUTCOME_ORDER,
    SP_TARGET,
)
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
FROZEN = ROOT / "results/bj204_gate_a_preoutcome_v5"
FIXTURES = ROOT / "tests/fixtures/bj204"


def test_bj204_gate_a_v5_manifest_is_canonical_and_outcome_unexposed() -> None:
    receipt = verify_package(FROZEN)
    assert receipt == {
        "contract_version": CONTRACT_VERSION,
        "files": 23,
        "status": "PASS",
    }
    card = json.loads((FROZEN / "freeze_card.json").read_text(encoding="utf-8"))
    assert card["source"]["labels_opened"] is False
    assert card["schema"]["sp_target"] == SP_TARGET
    assert tuple(card["schema"]["outcome_axis"]) == OUTCOME_ORDER
    assert tuple(SP_TARGET["outcome_axis"]) == OUTCOME_ORDER
    assert card["schema"]["model_features"] == list(MODEL_FEATURES)
    assert not list(FROZEN.rglob("*settlement*"))


def test_bj204_gate_a_v5_restores_full_344_issue_chronology() -> None:
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
    assert development.fallback_no_bet_rows.sum() == 1216
    assert test.fallback_no_bet_rows.sum() == 22
    targets = pd.read_csv(FROZEN / "development_target_identity_reconciliation.csv", dtype={"issue": str})
    assert len(targets) == 1024
    assert int(targets.official_target_identity_available.sum()) == 1021
    assert targets.labels_opened.astype(str).str.lower().eq("false").all()
    detail = pd.read_csv(FROZEN / "common_schema_field_coverage.csv")
    assert set(detail.feature) == set(COMMON_FEATURES)
    assert set(detail.outcome_code.astype(str)) == {"0", "1", "3"}
    validity = pd.read_csv(FROZEN / "common_probability_validity.csv")
    assert int(validity.market_triplet_valid_rows.sum()) == 101029 + 16968
    assert int(validity.fallback_no_bet_rows.sum()) == 1216 + 22
    features = pd.read_parquet(FROZEN / "common_cell_features.parquet")
    sequences = features.groupby(["issue", "match_idx"], sort=False)[
        "outcome_code"
    ].agg(tuple)
    assert sequences.map(lambda value: value == OUTCOME_ORDER).all()
    duplicates = pd.read_csv(
        FROZEN / "pclose_duplicate_resolution.csv", dtype={"source_issue": str}
    )
    assert len(duplicates) == 6
    assert set(duplicates.pclose_match_uid.astype(str)) == {
        "1163202",
        "1917703",
        "2223802",
    }
    assert duplicates.values_equal_within_issue_match_uid.all()
    assert duplicates.groupby("pclose_match_uid")[[
        "p_close_3", "p_close_1", "p_close_0", "beidan_hcap",
    ]].nunique(dropna=False).eq(1).all().all()
    assert duplicates.canonical_selected.sum() == 5
    assert set(duplicates.resolution) == {
        "ISSUE_PLUS_MATCH_UID",
        "EQUAL_VALUES_FIRST_SOURCE_ROW_WITHIN_ISSUE",
    }


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
    market_index = names.index("market_probability")
    expected_development = np.array(
        [
            [0.21327134947687568, 0.24865032386555025, 0.5380783266575742],
            [0.4296700874174867, 0.2837146638929515, 0.2866152486895618],
        ]
    )
    test_odds = np.array([[2.74, 3.24, 2.4], [2.92, 3.39, 2.26]])
    expected_test = (1.0 / test_odds) / (1.0 / test_odds).sum(axis=1)[:, None]
    np.testing.assert_allclose(
        dev_values[:, :, market_index], expected_development, rtol=0, atol=1e-15
    )
    np.testing.assert_allclose(
        test_values[:, :, market_index], expected_test, rtol=0, atol=1e-15
    )
    for issue in ("190101", "25043"):
        sequences = features.loc[features.issue.astype(str).eq(issue)].groupby(
            "match_idx", sort=False
        ).outcome_code.agg(tuple)
        assert sequences.map(lambda value: value == OUTCOME_ORDER).all()


@pytest.mark.parametrize(
    "invalid_triplet",
    (
        (np.inf, 0.25, 0.75),
        (-0.10, 0.40, 0.70),
        (0.20, 0.30, 0.40),
    ),
    ids=("nonfinite", "nonpositive", "off_simplex"),
)
def test_bj204_common_adapter_rejects_invalid_market_triplet_for_fallback(
    tmp_path: Path, invalid_triplet: tuple[float, float, float]
) -> None:
    identity, _ = _validate_source(SOURCE)
    mini = identity.loc[
        identity.issue.astype(str).eq("190101") & identity.match_idx.isin([1, 2])
    ].copy()
    history = _read_history_rows(FIXTURES / "history_proxy.csv", ((25043, 25043),))
    full = _read_full_3sp_identity(FIXTURES / "full_3sp_identity.csv")
    pclose = pd.read_csv(FIXTURES / "pclose_proxy.csv")
    pclose.loc[0, ["p_close_3", "p_close_1", "p_close_0"]] = invalid_triplet
    source = tmp_path / "invalid-pclose.csv"
    pclose.to_csv(source, index=False)
    features, masks, registry, _coverage, _duplicates = _common_adapter(
        SOURCE, mini, history, full, source, strict_census=False
    )
    invalid_cells = features[
        features.issue.astype(str).eq("190101") & features.match_idx.eq(1)
    ]
    aligned_masks = masks.set_index("cell_key").loc[invalid_cells.cell_key]
    assert invalid_cells.outcome_code.tolist() == list(OUTCOME_ORDER)
    assert invalid_cells.market_proxy_complete.eq(0.0).all()
    assert not aligned_masks.market_probability.any()
    invalid_registry = registry[
        registry.issue.astype(str).eq("190101") & registry.match_idx.eq(1)
    ]
    assert not invalid_registry.market_proxy_complete.any()


def test_bj204_common_adapter_resolves_reused_match_uid_by_issue(tmp_path: Path) -> None:
    """A reused source match UID must not overwrite the development issue row."""
    identity, _ = _validate_source(SOURCE)
    mini = identity.loc[
        identity.issue.astype(str).eq("190101") & identity.match_idx.isin([1, 2])
    ].copy()
    history = _read_history_rows(FIXTURES / "history_proxy.csv", ((25043, 25043),))
    full = _read_full_3sp_identity(FIXTURES / "full_3sp_identity.csv")
    pclose = pd.read_csv(FIXTURES / "pclose_proxy.csv")
    reused = pclose.iloc[[0]].copy()
    reused["issue"] = 999999
    reused[["p_close_3", "p_close_1", "p_close_0"]] = [[0.7, 0.2, 0.1]]
    source = tmp_path / "reused-match-uid.csv"
    pd.concat([pclose, reused], ignore_index=True).to_csv(source, index=False)
    features, _masks, _registry, _coverage, duplicates = _common_adapter(
        SOURCE, mini, history, full, source, strict_census=False,
    )
    first = features.loc[
        features.issue.astype(str).eq("190101") & features.match_idx.eq(1),
        "market_probability",
    ].to_numpy()
    np.testing.assert_allclose(first, [0.21327134947687568, 0.24865032386555025, 0.5380783266575742])
    audit = duplicates.loc[duplicates.pclose_match_uid.astype(str).eq("1584807")]
    assert audit.source_issue.astype(str).tolist() == ["190101", "999999"]
    assert audit.issue_match_uid_resolves.all()
    assert set(audit.resolution) == {"ISSUE_PLUS_MATCH_UID"}


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
    portable = (ROOT / "scripts/test_bj204_gate_a_portable.sh").read_text(encoding="utf-8")
    assert "PYTHON_BIN" in portable
    assert "without data/" in portable
    assert "/tmp" not in portable
    assert "--basetemp" not in portable


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
        "true_issue_match_census", "probability_validity_by_year",
        "field_outcome_completeness", "OUTCOME_ORDER",
    ):
        assert token in source
    output_text = "\n".join(
        str(output.get("text", ""))
        + str(output.get("data", {}).get("text/plain", ""))
        for cell in code
        for output in cell.outputs
    )
    assert "357705" in output_text
    assert "1392705" not in output_text
