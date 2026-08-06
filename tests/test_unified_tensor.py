from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3

import numpy as np
import pandas as pd
import pytest

from unified_tensor.builder import (
    _assert_exact_cell_identity,
    _assert_exact_heldout_registry,
    _namespace_manifest,
    _load_inputs,
    TensorBuildError,
    digest,
    _sqlite_ro,
    unavailable_reason,
    write_json,
    write_parquet,
)
from unified_tensor.contract import (
    CONTRACT_VERSION,
    FEATURE_NAMES,
    FEATURE_SPECS,
    HELDOUT_ISSUES,
    OUTCOME_ORDER,
    cell_join_key,
    forbidden_inference_names,
)
from unified_tensor.inference import TensorContractError, load_issue_tensors
from unified_tensor.settlement_labels import (
    LABEL_COLUMNS,
    LabelContractError,
    bind_development_labels,
    load_development_labels,
)


def _identity(split: str = "development", issue: str = "24001") -> pd.DataFrame:
    issue_instance = f"{issue}@CANONICAL_2024"
    rows = []
    for order, code in enumerate(OUTCOME_ORDER):
        rows.append(
            {
                "cell_join_key": cell_join_key(issue_instance, "1", code),
                "issue": issue,
                "issue_instance": issue_instance,
                "year": "2024",
                "fold": "OOS_2024",
                "split": split,
                "issue_order": 0,
                "match_id": "1",
                "match_idx": 1,
                "match_order": 0,
                "outcome_code": code,
                "outcome_order": order,
                "feature_cutoff_ts_utc": "2024-01-01T00:00:00Z",
                "kickoff_ts_utc": "2024-01-01T01:00:00Z",
                "availability_status": "AVAILABLE",
                "unavailable_reason": "",
                "source_b0_status": "NO_BET_FROZEN",
                "identity_source": "fixture",
                "identity_observed_ts_utc": "",
                "identity_timing_status": "CUTOFF_BOUND_IDENTITY",
                "euro_1h_available_ts_utc": "2023-12-31T23:00:00Z",
                "predicted_sp_available_ts_utc": "2023-12-31T14:00:00Z",
            }
        )
    return pd.DataFrame(rows)


def _write_inference(root: Path, *, forbidden_field: str | None = None) -> pd.DataFrame:
    namespace = root / "inference"
    identity = _identity()
    values = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    masks = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    for spec in FEATURE_SPECS:
        if spec.minimum is not None and spec.maximum is not None:
            sample = (spec.minimum + spec.maximum) / 2
        elif spec.minimum is not None:
            sample = spec.minimum + 1
        elif spec.maximum is not None:
            sample = spec.maximum - 1
        else:
            sample = 0.5
        values[spec.name] = np.float32(sample)
        masks[spec.name] = True
    values["outcome_code_numeric"] = identity["outcome_code"].astype(np.float32)
    for feature in (
        "calibrated_market_probability",
        "devig_euro_probability",
        "fundamental_probability",
    ):
        values[feature] = np.asarray([0.2, 0.3, 0.5], dtype=np.float32)
    values["probability_residual"] = np.asarray(
        [0.01, -0.02, 0.01], dtype=np.float32
    )
    values["calendar_year"] = np.float32(2024.0)
    values["match_position_fraction"] = np.float32(0.0)
    values["kickoff_delay_hours"] = np.float32(1.0)
    masks.loc[1, "predicted_final_sp"] = False
    values.loc[1, "predicted_final_sp"] = np.nan
    if forbidden_field:
        values[forbidden_field] = 1.0
    write_parquet(namespace / "cell_identity.parquet", identity)
    write_parquet(namespace / "feature_values.parquet", values)
    write_parquet(namespace / "feature_masks.parquet", masks)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    return identity


def _append_second_match(root: Path, *, cutoff: str | None = None) -> None:
    namespace = root / "inference"
    identity = pd.read_parquet(namespace / "cell_identity.parquet")
    values = pd.read_parquet(namespace / "feature_values.parquet")
    masks = pd.read_parquet(namespace / "feature_masks.parquet")
    second_identity = identity.copy()
    second_identity["match_id"] = "2"
    second_identity["match_idx"] = 2
    second_identity["match_order"] = 1
    if cutoff is not None:
        second_identity["feature_cutoff_ts_utc"] = cutoff
    second_identity["cell_join_key"] = [
        cell_join_key(str(row.issue_instance), "2", str(row.outcome_code))
        for row in second_identity.itertuples(index=False)
    ]
    second_values = values.copy()
    second_masks = masks.copy()
    second_values["cell_join_key"] = second_identity["cell_join_key"]
    second_masks["cell_join_key"] = second_identity["cell_join_key"]
    second_values["match_position_fraction"] = np.float32(1.0)
    write_parquet(
        namespace / "cell_identity.parquet",
        pd.concat([identity, second_identity], ignore_index=True),
    )
    write_parquet(
        namespace / "feature_values.parquet",
        pd.concat([values, second_values], ignore_index=True),
    )
    write_parquet(
        namespace / "feature_masks.parquet",
        pd.concat([masks, second_masks], ignore_index=True),
    )
    _namespace_manifest(namespace, "outcome_unexposed_inference")


def _append_second_issue(root: Path) -> None:
    namespace = root / "inference"
    identity = pd.read_parquet(namespace / "cell_identity.parquet")
    values = pd.read_parquet(namespace / "feature_values.parquet")
    masks = pd.read_parquet(namespace / "feature_masks.parquet")
    second_identity = identity.copy()
    second_identity["issue"] = "24002"
    second_identity["issue_instance"] = "24002@CANONICAL_2024"
    second_identity["issue_order"] = 1
    second_identity["match_id"] = "2"
    second_identity["feature_cutoff_ts_utc"] = "2024-01-02T00:00:00Z"
    second_identity["kickoff_ts_utc"] = "2024-01-02T01:00:00Z"
    second_identity["euro_1h_available_ts_utc"] = "2024-01-01T23:00:00Z"
    second_identity["predicted_sp_available_ts_utc"] = "2024-01-01T14:00:00Z"
    second_identity["cell_join_key"] = [
        cell_join_key(str(row.issue_instance), "2", str(row.outcome_code))
        for row in second_identity.itertuples(index=False)
    ]
    second_values = values.copy()
    second_masks = masks.copy()
    second_values["cell_join_key"] = second_identity["cell_join_key"]
    second_masks["cell_join_key"] = second_identity["cell_join_key"]
    write_parquet(
        namespace / "cell_identity.parquet",
        pd.concat([identity, second_identity], ignore_index=True),
    )
    write_parquet(
        namespace / "feature_values.parquet",
        pd.concat([values, second_values], ignore_index=True),
    )
    write_parquet(
        namespace / "feature_masks.parquet",
        pd.concat([masks, second_masks], ignore_index=True),
    )
    _namespace_manifest(namespace, "outcome_unexposed_inference")


def _write_labels(root: Path, identity: pd.DataFrame, *, heldout: bool = False) -> pd.DataFrame:
    namespace = root / "labels"
    labels = pd.DataFrame(
        {
            "cell_join_key": identity["cell_join_key"],
            "issue": "25041" if heldout else identity["issue"],
            "issue_instance": identity["issue_instance"],
            "match_id": identity["match_id"],
            "outcome_code": identity["outcome_code"],
            "result_code": "3",
            "is_winner": identity["outcome_code"].eq("3"),
            "final_sp": [2.1, 3.2, 3.4],
            "final_sp_available": True,
            "winning_zero_return_units": [2.1, 0.0, 0.0],
            "payout_factor": 0.65,
            "payout_after_65_units": [1.365, 0.0, 0.0],
            "tax_rate": 0.20,
            "tax_cliff_gross_yuan": 10_000.0,
            "tax_realized_yuan": np.nan,
            "tax_realized_available": False,
            "settlement_status": "SETTLED_TRUSTED",
            "settlement_quality": "trusted",
            "settlement_source": "fixture",
        }
    ).loc[:, LABEL_COLUMNS]
    write_parquet(namespace / "development_labels.parquet", labels)
    manifest = _namespace_manifest(namespace, "development_only_settlement_labels")
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    write_json(namespace / "MANIFEST.json", manifest)
    return labels


def test_inference_loader_materializes_ragged_shape_and_mask(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    tensors = load_issue_tensors(tmp_path)
    assert len(tensors) == 1
    tensor = tensors[0]
    assert tensor.values.shape == (1, 3, len(FEATURE_NAMES))
    assert tensor.masks.shape == tensor.values.shape
    assert tensor.values.dtype == np.float32
    assert tensor.masks.dtype == np.bool_
    predicted_sp = FEATURE_NAMES.index("predicted_final_sp")
    assert tensor.values[0, 1, predicted_sp] == 0.0
    assert not tensor.masks[0, 1, predicted_sp]
    assert tensor.fold == "OOS_2024"
    assert tensor.match_provenance[0].match_id == tensor.match_ids[0]
    assert tensor.match_provenance[0].match_order == 0


def test_parquet_writer_is_byte_deterministic(tmp_path: Path) -> None:
    frame = _identity()
    first, second = tmp_path / "first.parquet", tmp_path / "second.parquet"
    write_parquet(first, frame)
    write_parquet(second, frame)
    assert digest(first) == digest(second)


def test_source_bound_identity_rejects_provenance_tamper() -> None:
    expected = _identity()
    actual = expected.copy()
    actual["availability_status"] = "UNAVAILABLE"
    with pytest.raises(TensorBuildError, match="cell identity differs"):
        _assert_exact_cell_identity(actual, expected)


def test_source_bound_registry_rejects_tamper() -> None:
    expected = pd.DataFrame(
        {"issue": ["25041"], "ordered_identity_sha256": ["exact"]}
    )
    actual = expected.copy()
    actual["ordered_identity_sha256"] = "tampered"
    with pytest.raises(TensorBuildError, match="registry does not bind"):
        _assert_exact_heldout_registry(actual, expected)


def test_golden_forbidden_field_moved_into_inference_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/bj203_contract/forbidden_move.json").read_text()
    )
    assert fixture["expected_result"] == "FAIL_CLOSED"
    for field in fixture["forbidden_inference_fields"]:
        assert forbidden_inference_names([field]) == [field]
    _write_inference(tmp_path, forbidden_field="final_sp")
    with pytest.raises(TensorContractError, match="forbidden inference fields"):
        load_issue_tensors(tmp_path)


def test_inference_loader_refuses_label_namespace(tmp_path: Path) -> None:
    labels = tmp_path / "labels"
    labels.mkdir()
    with pytest.raises(TensorContractError, match="refuses the label namespace"):
        load_issue_tensors(labels)


def test_direct_loaders_reject_namespace_root_symlinks(tmp_path: Path) -> None:
    source = tmp_path / "source"
    identity = _write_inference(source)
    _write_labels(source, identity)
    package = tmp_path / "package"
    package.mkdir()
    (package / "inference").symlink_to(
        source / "inference", target_is_directory=True
    )
    (package / "labels").symlink_to(source / "labels", target_is_directory=True)
    with pytest.raises(TensorContractError, match="namespace root"):
        load_issue_tensors(package)
    with pytest.raises(LabelContractError, match="namespace root"):
        load_development_labels(package)


def test_inference_loader_rejects_unmanifested_payload(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    (tmp_path / "inference/result.bin").write_bytes(b"forbidden")
    with pytest.raises(TensorContractError, match="file census"):
        load_issue_tensors(tmp_path)


def test_development_labels_bind_exact_ordered_identity(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    expected = _write_labels(tmp_path, identity)
    labels = load_development_labels(tmp_path)
    bound = bind_development_labels(identity, labels)
    assert bound["cell_join_key"].tolist() == expected["cell_join_key"].tolist()
    moved = labels.iloc[::-1].reset_index(drop=True)
    with pytest.raises(LabelContractError, match="exactly cover ordered"):
        bind_development_labels(identity, moved)


def test_heldout_outcome_rows_are_rejected_even_with_valid_hash(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    _write_labels(tmp_path, identity, heldout=True)
    with pytest.raises(LabelContractError, match="held-out labels"):
        load_development_labels(tmp_path)


def test_join_key_deletion_or_identity_move_is_detected(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    labels = _write_labels(tmp_path, identity)
    labels.loc[0, "cell_join_key"] = cell_join_key(
        str(labels.loc[0, "issue_instance"]), "999", str(labels.loc[0, "outcome_code"])
    )
    write_parquet(tmp_path / "labels/development_labels.parquet", labels)
    manifest = _namespace_manifest(
        tmp_path / "labels", "development_only_settlement_labels"
    )
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    write_json(tmp_path / "labels/MANIFEST.json", manifest)
    with pytest.raises(LabelContractError, match="exact identity"):
        load_development_labels(tmp_path)


def test_label_loader_rejects_double_applied_payout_factor(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    labels = _write_labels(tmp_path, identity)
    labels["payout_after_65_units"] = labels["payout_after_65_units"] * 0.65
    write_parquet(tmp_path / "labels/development_labels.parquet", labels)
    manifest = _namespace_manifest(
        tmp_path / "labels", "development_only_settlement_labels"
    )
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    write_json(tmp_path / "labels/MANIFEST.json", manifest)
    with pytest.raises(LabelContractError, match="exactly once"):
        load_development_labels(tmp_path)


def test_label_loader_rejects_nonzero_trusted_loser_return(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    labels = _write_labels(tmp_path, identity)
    labels.loc[1, "winning_zero_return_units"] = 1.0
    labels.loc[1, "payout_after_65_units"] = 0.65
    write_parquet(tmp_path / "labels/development_labels.parquet", labels)
    manifest = _namespace_manifest(
        tmp_path / "labels", "development_only_settlement_labels"
    )
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    write_json(tmp_path / "labels/MANIFEST.json", manifest)
    with pytest.raises(LabelContractError, match="losing cells must have zero"):
        load_development_labels(tmp_path)


def test_label_loader_rejects_targets_on_unavailable_settlement(tmp_path: Path) -> None:
    identity = _write_inference(tmp_path)
    labels = _write_labels(tmp_path, identity)
    labels["settlement_status"] = "UNAVAILABLE_CANONICAL_SETTLEMENT"
    labels["settlement_quality"] = "missing_sp"
    labels["is_winner"] = False
    write_parquet(tmp_path / "labels/development_labels.parquet", labels)
    manifest = _namespace_manifest(
        tmp_path / "labels", "development_only_settlement_labels"
    )
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    write_json(tmp_path / "labels/MANIFEST.json", manifest)
    with pytest.raises(LabelContractError, match="must not carry targets"):
        load_development_labels(tmp_path)


def test_contract_version_is_manifest_bound(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    manifest_path = tmp_path / "inference/MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["contract_version"] = CONTRACT_VERSION + "-tampered"
    write_json(manifest_path, manifest)
    with pytest.raises(TensorContractError, match="unsupported"):
        load_issue_tensors(tmp_path)


def test_unavailable_reason_treats_nan_as_missing() -> None:
    assert unavailable_reason("", "2", np.nan, (np.nan, 3.0, 2.0)) == (
        "MISSING_TEAM_IDENTITY;MISSING_1H_EURO;MISSING_NATIVE_LINE"
    )
    assert unavailable_reason("1", "2", 0.0, (2.0, 3.0, 4.0)) == ""


def test_inference_loader_rejects_unmasked_late_snapshot(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    identity_path = tmp_path / "inference/cell_identity.parquet"
    identity = pd.read_parquet(identity_path)
    identity["euro_1h_available_ts_utc"] = "2024-01-01T00:30:00Z"
    write_parquet(identity_path, identity)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="crosses issue cutoff"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_identity_observed_after_cutoff(
    tmp_path: Path,
) -> None:
    _write_inference(tmp_path)
    identity_path = tmp_path / "inference/cell_identity.parquet"
    identity = pd.read_parquet(identity_path)
    identity["identity_timing_status"] = "TIMESTAMPED_IDENTITY_ONLY"
    identity["identity_observed_ts_utc"] = "2024-01-01T00:00:01Z"
    write_parquet(identity_path, identity)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="appears after issue cutoff"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_reordered_outcome_axis(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    namespace = tmp_path / "inference"
    for name in ("cell_identity.parquet", "feature_values.parquet", "feature_masks.parquet"):
        payload = pd.read_parquet(namespace / name).iloc[[1, 0, 2]].reset_index(drop=True)
        write_parquet(namespace / name, payload)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="canonical 3,1,0 order"):
        load_issue_tensors(tmp_path)


def test_inference_loader_enforces_feature_ranges(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values.loc[0, "calibrated_market_probability"] = 1.5
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="above contract maximum"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_decision_feature_on_identity_only_row(
    tmp_path: Path,
) -> None:
    _write_inference(tmp_path)
    identity_path = tmp_path / "inference/cell_identity.parquet"
    identity = pd.read_parquet(identity_path)
    identity["identity_timing_status"] = "TIMESTAMPED_IDENTITY_ONLY"
    identity["identity_observed_ts_utc"] = "2024-01-01T00:00:00Z"
    write_parquet(identity_path, identity)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(
        TensorContractError, match="identity-only held-out row exposes"
    ):
        load_issue_tensors(tmp_path)


def test_inference_loader_binds_numeric_outcome_feature_to_axis(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values["outcome_code_numeric"] = np.float32(0.0)
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="bind identity axis"):
        load_issue_tensors(tmp_path)


def test_inference_loader_enforces_probability_simplex(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values["fundamental_probability"] = np.float32(0.2)
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="simplex"):
        load_issue_tensors(tmp_path)


def test_inference_loader_enforces_residual_zero_sum(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values.loc[0, "probability_residual"] += np.float32(0.05)
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="residual is not zero-sum"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_residual_mask_drift(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    namespace = tmp_path / "inference"
    masks = pd.read_parquet(namespace / "feature_masks.parquet")
    values = pd.read_parquet(namespace / "feature_values.parquet")
    masks.loc[0, "probability_residual"] = False
    values.loc[0, "probability_residual"] = np.nan
    write_parquet(namespace / "feature_masks.parquet", masks)
    write_parquet(namespace / "feature_values.parquet", values)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="residual masks"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_invalid_hidden_residual_simplex(
    tmp_path: Path,
) -> None:
    _write_inference(tmp_path)
    namespace = tmp_path / "inference"
    values = pd.read_parquet(namespace / "feature_values.parquet")
    values["probability_residual"] = np.asarray(
        [0.5, -0.5, 0.0], dtype=np.float32
    )
    write_parquet(namespace / "feature_values.parquet", values)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="baseline is not a probability"):
        load_issue_tensors(tmp_path)


def test_inference_loader_binds_fold_to_year(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    identity_path = tmp_path / "inference/cell_identity.parquet"
    identity = pd.read_parquet(identity_path)
    identity["fold"] = "OOS_2023"
    write_parquet(identity_path, identity)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="fold does not bind"):
        load_issue_tensors(tmp_path)


@pytest.mark.parametrize(
    ("feature", "value", "message"),
    [
        ("calendar_year", 2023.0, "calendar-year"),
        ("match_position_fraction", 0.5, "match-position"),
        ("kickoff_delay_hours", 0.5, "kickoff-delay"),
    ],
)
def test_inference_loader_binds_identity_derived_features(
    tmp_path: Path, feature: str, value: float, message: str
) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values[feature] = np.float32(value)
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match=message):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_issue_level_cutoff_drift(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    _append_second_match(tmp_path, cutoff="2024-01-01T00:10:00Z")
    with pytest.raises(TensorContractError, match="issue identity field is inconsistent"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_noncanonical_match_axis(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    _append_second_match(tmp_path)
    namespace = tmp_path / "inference"
    identity_path = namespace / "cell_identity.parquet"
    identity = pd.read_parquet(identity_path)
    identity.loc[identity["match_id"].eq("1"), "match_idx"] = 2
    identity.loc[identity["match_id"].eq("2"), "match_idx"] = 1
    write_parquet(identity_path, identity)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="canonical source order"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_noncanonical_issue_axis(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    _append_second_issue(tmp_path)
    namespace = tmp_path / "inference"
    identity = pd.read_parquet(namespace / "cell_identity.parquet")
    values = pd.read_parquet(namespace / "feature_values.parquet")
    masks = pd.read_parquet(namespace / "feature_masks.parquet")
    order = [*range(3, 6), *range(0, 3)]
    identity = identity.iloc[order].reset_index(drop=True)
    values = values.iloc[order].reset_index(drop=True)
    masks = masks.iloc[order].reset_index(drop=True)
    identity.loc[identity["issue"].eq("24002"), "issue_order"] = 0
    identity.loc[identity["issue"].eq("24001"), "issue_order"] = 1
    write_parquet(namespace / "cell_identity.parquet", identity)
    write_parquet(namespace / "feature_values.parquet", values)
    write_parquet(namespace / "feature_masks.parquet", masks)
    _namespace_manifest(namespace, "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="canonical cutoff order"):
        load_issue_tensors(tmp_path)


def test_inference_loader_rejects_hidden_value_under_false_mask(tmp_path: Path) -> None:
    _write_inference(tmp_path)
    values_path = tmp_path / "inference/feature_values.parquet"
    values = pd.read_parquet(values_path)
    values.loc[1, "predicted_final_sp"] = 2.4
    write_parquet(values_path, values)
    _namespace_manifest(tmp_path / "inference", "outcome_unexposed_inference")
    with pytest.raises(TensorContractError, match="must not carry values"):
        load_issue_tensors(tmp_path)


def test_detached_replay_rejects_tampered_identity_extension(tmp_path: Path) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "results/bj203_causal_tensor_v1/sources/unavailable_match_identity.parquet"
    )
    tampered = tmp_path / "identity.parquet"
    shutil.copyfile(source, tampered)
    with tampered.open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(TensorBuildError, match="identity extension hash mismatch"):
        _load_inputs(None, tampered)


@pytest.mark.parametrize("separator", ["#", "?"])
def test_readonly_sqlite_uri_percent_encodes_reserved_characters(
    tmp_path: Path, separator: str,
) -> None:
    decoy = tmp_path / "source.db"
    intended = tmp_path / f"source.db{separator}trusted-copy"
    for database, marker in ((decoy, "decoy"), (intended, "intended")):
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE identity(marker TEXT NOT NULL)")
            connection.execute("INSERT INTO identity(marker) VALUES (?)", (marker,))
    with _sqlite_ro(intended) as connection:
        marker = connection.execute("SELECT marker FROM identity").fetchone()[0]
    assert marker == "intended"
