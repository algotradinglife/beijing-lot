"""Focused outcome-boundary, source-census, and replay tests for #204 Gate A."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import nbformat
import pandas as pd

from unified_model.contract import (
    CONTRACT_VERSION,
    DEVELOPMENT_ISSUE_MAX,
    RESERVE_ISSUE_MIN,
    RETROSPECTIVE_TEST_RANGES,
    SP_TARGET,
)
from unified_model.gate_a import HISTORY_COLUMNS, build_package, verify_package
from scripts.freeze_bj204_model_gate_a import _atomic_build, _default_history_source
from scripts.execute_bj204_notebook import execute_notebook


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/bj203_causal_tensor_v2"
HISTORY = _default_history_source()
FROZEN = ROOT / "results/bj204_gate_a_preoutcome_v2"


def _build(package: Path) -> dict[str, object]:
    return build_package(package, source_package=SOURCE, history_source=HISTORY)


def test_bj204_history_proxy_has_an_explicit_pre_event_column_allowlist() -> None:
    assert HISTORY_COLUMNS == (
        "issue", "match_idx", "league", "kickoff_ts", "handicap_line",
        "avg_eu_home", "avg_eu_draw", "avg_eu_away",
    )
    assert not {"score", "result_code", "winning_sp", "final_sp"}.intersection(HISTORY_COLUMNS)


def test_bj204_gate_a_freezes_correct_issue_chronology_without_opening_labels(tmp_path: Path) -> None:
    package = tmp_path / "gate-a"
    receipt = _build(package)

    assert receipt["status"] == "GATE_A_OUTCOME_UNEXPOSED_PASS"
    assert verify_package(package)["status"] == "PASS"
    assert not list(package.rglob("*settlement*"))

    splits = pd.read_csv(package / "split_manifest.csv", dtype={"issue": str})
    assert splits["labels_permitted_gate_a"].astype(str).str.lower().eq("false").all()
    test = splits.loc[splits.role.eq("RETROSPECTIVE_TEST_LOCKED")]
    assert test["issue"].nunique() == 75
    assert test["issue"].astype(int).between(25043, 25125).sum() == 42
    assert test["issue"].astype(int).between(26011, 26049).sum() == 33
    assert splits.loc[splits.role.eq("DEVELOPMENT_CV"), "issue"].astype(int).max() == DEVELOPMENT_ISSUE_MAX
    assert not (splits["issue"].astype(int) >= RESERVE_ISSUE_MIN).any()
    assert test["labels_permitted_gate_b"].all()

    card = json.loads((package / "freeze_card.json").read_text(encoding="utf-8"))
    assert card["contract_version"] == CONTRACT_VERSION
    assert card["source"]["labels_opened"] is False
    assert card["chronology"]["retrospective_test_issue_ranges"] == [list(row) for row in RETROSPECTIVE_TEST_RANGES]


def test_bj204_gate_a_reconciles_all_75_proxy_identities_and_missing_reasons(tmp_path: Path) -> None:
    package = tmp_path / "gate-a"
    _build(package)
    reconciliation = pd.read_csv(package / "identity_reconciliation.csv", dtype={"issue": str}).fillna("")
    test = reconciliation.loc[reconciliation.role.eq("RETROSPECTIVE_TEST_LOCKED")]
    assert len(test) == 75
    assert int(test["history_rows"].sum()) == 11382 + 5608
    early = test.loc[test["issue"].astype(int).between(25043, 25125)]
    late = test.loc[test["issue"].astype(int).between(26011, 26049)]
    assert len(early) == 42 and len(late) == 33
    assert early["missing_reason"].eq("UPSTREAM_203_INFERENCE_ABSENT; HISTORY_PROXY_ONLY").all()
    assert late["missing_reason"].eq("RETROSPECTIVE_PROXY_REQUIRED; INFERENCE_AUXILIARY_ONLY").all()
    assert test["labels_opened"].astype(str).str.lower().eq("false").all()


def test_bj204_gate_a_target_is_official_final_sp_and_proxy_is_only_an_input(tmp_path: Path) -> None:
    package = tmp_path / "gate-a"
    _build(package)
    schema = json.loads((package / "inference_schema.json").read_text(encoding="utf-8"))
    assert schema["sp_target"] == SP_TARGET
    assert schema["predicted_final_sp_semantics"] == "outcome-unexposed pre-event proxy input only"
    assert schema["sp_target"]["field"] == "final_sp"
    assert "predicted_final_sp" in schema["model_features"]
    assert schema["sp_target"]["field"] not in schema["model_features"]
    quality = pd.read_csv(package / "target_only_quality_mask.csv")
    assert quality[["history_rows", "official_3sp_rows", "post_kickoff_updates"]].values.tolist() == [
        [11382, 11314, 8247], [5608, 5539, 4516]
    ]
    assert not list(package.rglob("*final_sp*"))


def test_bj204_gate_a_proxy_coverage_is_explicit_and_not_a_live_claim(tmp_path: Path) -> None:
    package = tmp_path / "gate-a"
    _build(package)
    coverage = pd.read_csv(package / "proxy_coverage_by_period.csv")
    assert coverage["period"].tolist() == ["25043-25125", "26011-26049"]
    assert coverage["rows"].tolist() == [11382, 5608]
    assert coverage["source_grade"].eq("RETROSPECTIVE_PROXY").all()
    assert coverage["labels_opened"].astype(str).str.lower().eq("false").all()
    assert coverage["baseline_proxy_rows"].gt(0).all()
    assert coverage["model_proxy_rows"].gt(0).all()
    assert (coverage["fallback_no_bet_rows"] >= 0).all()


def test_bj204_gate_a_is_deterministic_and_matches_authoritative_package(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _build(first)
    _build(second)
    for name in ("SHA256SUMS.json", "CONTENT_IDENTITY.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        assert (first / name).read_bytes() == (FROZEN / name).read_bytes()
    cv = pd.read_csv(first / "cv_manifest.csv")
    assert not cv["test_labels_opened"].any()
    assert set(cv["test_issue_boundary"]) == {"25043-26049"}


def test_bj204_atomic_wrapper_accepts_an_empty_stage_directory(tmp_path: Path) -> None:
    output = tmp_path / "immutable-package"
    receipt = _atomic_build(output, SOURCE, HISTORY)
    assert receipt["package"] == output.name
    assert verify_package(output)["status"] == "PASS"


def test_bj204_notebook_is_path_independent_and_clean_replay_is_deterministic(tmp_path: Path) -> None:
    frozen = ROOT / "notebooks/research/issue-204/bj204_track_a_gate_a.ipynb"
    notebook = nbformat.read(frozen, as_version=4)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert [cell.execution_count for cell in code] == list(range(1, len(code) + 1))
    assert not [
        output for cell in code for output in cell.outputs if output.output_type == "error"
    ]
    replay = tmp_path / frozen.name
    shutil.copyfile(frozen, replay)
    execute_notebook(replay)
    assert replay.read_bytes() == frozen.read_bytes()
