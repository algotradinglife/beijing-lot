"""Outcome-unexposed loader for ragged #203 issue tensors.

This module never opens the label namespace.  It validates the inference
namespace manifest and schema before materializing ``X_i[J_i, 3, F]`` plus an
identically shaped Boolean mask.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .contract import (
    CONTRACT_VERSION,
    FEATURE_NAMES,
    FEATURE_SPECS,
    HELDOUT_ISSUES,
    OUTCOME_ORDER,
    cell_join_key,
    forbidden_inference_names,
)


class TensorContractError(RuntimeError):
    """Raised when a package fails closed at the inference boundary."""


@dataclass(frozen=True)
class MatchProvenance:
    match_id: str
    match_idx: int
    match_order: int
    kickoff_ts_utc: str
    availability_status: str
    unavailable_reason: str
    source_b0_status: str
    identity_source: str
    identity_observed_ts_utc: str
    identity_timing_status: str
    euro_1h_available_ts_utc: str
    predicted_sp_available_ts_utc: str


@dataclass(frozen=True)
class IssueTensor:
    issue: str
    issue_instance: str
    fold: str
    split: str
    feature_cutoff_ts_utc: str
    match_ids: tuple[str, ...]
    match_indices: tuple[int, ...]
    match_provenance: tuple[MatchProvenance, ...]
    values: np.ndarray
    masks: np.ndarray
    feature_names: tuple[str, ...] = FEATURE_NAMES
    outcome_order: tuple[str, ...] = OUTCOME_ORDER

    def __post_init__(self) -> None:
        expected = (len(self.match_ids), len(OUTCOME_ORDER), len(FEATURE_NAMES))
        if self.values.shape != expected or self.masks.shape != expected:
            raise TensorContractError(
                f"invalid tensor shape for {self.issue_instance}: "
                f"values={self.values.shape}, masks={self.masks.shape}, "
                f"expected={expected}"
            )
        if self.values.dtype != np.float32 or self.masks.dtype != np.bool_:
            raise TensorContractError("tensor dtypes must be float32 and bool")
        if not np.isfinite(self.values[self.masks]).all():
            raise TensorContractError("unmasked tensor values must be finite")
        if len(self.match_provenance) != len(self.match_ids):
            raise TensorContractError("match provenance does not cover tensor rows")


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _inference_dir(package: Path) -> Path:
    expanded = package.expanduser()
    if expanded.is_symlink():
        raise TensorContractError("inference package root must not be a symlink")
    resolved = expanded.resolve()
    if "labels" in {part.lower() for part in resolved.parts}:
        raise TensorContractError("inference loader refuses the label namespace")
    candidate = resolved if resolved.name == "inference" else resolved / "inference"
    if candidate.is_symlink():
        raise TensorContractError("inference namespace root must not be a symlink")
    if not candidate.is_dir():
        raise TensorContractError(f"inference namespace not found: {candidate}")
    return candidate


def _verified_tables(package: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    namespace = _inference_dir(package)
    manifest_path = namespace / "MANIFEST.json"
    if manifest_path.is_symlink():
        raise TensorContractError("inference manifest must be a regular package file")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorContractError("missing or invalid inference manifest") from exc
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise TensorContractError("unsupported inference contract version")
    if manifest.get("namespace") != "outcome_unexposed_inference":
        raise TensorContractError("inference namespace declaration is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise TensorContractError("inference manifest files are invalid")
    required = (
        "cell_identity.parquet",
        "feature_values.parquet",
        "feature_masks.parquet",
    )
    allowed = {
        *required,
        "issue_offsets.parquet",
        "league_dictionary.parquet",
        "market_breadth_dictionary.parquet",
        "team_dictionary.parquet",
    }
    namespace_paths = list(namespace.rglob("*"))
    if any(path.is_symlink() for path in namespace_paths):
        raise TensorContractError("inference namespace must not contain symlinks")
    actual_files = {
        path.relative_to(namespace).as_posix()
        for path in namespace_paths
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if not set(required).issubset(files) or set(files) != actual_files:
        raise TensorContractError("inference file census does not match manifest")
    if not set(files).issubset(allowed):
        raise TensorContractError("inference manifest contains an unexpected payload")
    forbidden_files = forbidden_inference_names(actual_files)
    if forbidden_files:
        raise TensorContractError(f"forbidden inference payload names: {forbidden_files}")
    for name in files:
        path = namespace / name
        if not path.is_file() or files.get(name) != _digest(path):
            raise TensorContractError(f"inference payload hash mismatch: {name}")
    auxiliary_schemas = {
        "issue_offsets.parquet": [
            "issue", "issue_instance", "split", "issue_order",
            "feature_cutoff_ts_utc", "cell_start", "cell_count", "match_count",
        ],
        "league_dictionary.parquet": ["league", "league_index"],
        "team_dictionary.parquet": ["team_id", "team_index"],
        "market_breadth_dictionary.parquet": [
            "market_signature_breadth_bucket",
            "market_signature_breadth_index",
        ],
    }
    for name, expected_columns in auxiliary_schemas.items():
        if name in files:
            columns = list(pd.read_parquet(namespace / name).columns)
            if columns != expected_columns or forbidden_inference_names(columns):
                raise TensorContractError(f"auxiliary inference schema drift: {name}")
    identity = pd.read_parquet(namespace / required[0])
    values = pd.read_parquet(namespace / required[1])
    masks = pd.read_parquet(namespace / required[2])
    forbidden = forbidden_inference_names(
        list(identity.columns) + list(values.columns) + list(masks.columns)
    )
    if forbidden:
        raise TensorContractError(f"forbidden inference fields: {forbidden}")
    return identity, values, masks


def _validate_cells(
    identity: pd.DataFrame, values: pd.DataFrame, masks: pd.DataFrame
) -> None:
    identity_fields = {
        "cell_join_key", "issue", "issue_instance", "year", "fold", "split",
        "issue_order",
        "match_id", "match_idx", "match_order", "outcome_code", "outcome_order",
        "feature_cutoff_ts_utc", "kickoff_ts_utc", "availability_status",
        "unavailable_reason", "source_b0_status", "euro_1h_available_ts_utc",
        "predicted_sp_available_ts_utc", "identity_source",
        "identity_observed_ts_utc", "identity_timing_status",
    }
    if set(identity.columns) != identity_fields:
        raise TensorContractError("cell identity schema does not match contract")
    if list(values.columns) != ["cell_join_key", *FEATURE_NAMES]:
        raise TensorContractError("feature value axis/order does not match contract")
    if list(masks.columns) != ["cell_join_key", *FEATURE_NAMES]:
        raise TensorContractError("feature mask axis/order does not match contract")
    if not identity["cell_join_key"].is_unique:
        raise TensorContractError("cell join keys are not unique")
    if not bool(identity["split"].astype(str).isin({"development", "heldout"}).all()):
        raise TensorContractError("inference split is invalid")
    timing_status = identity["identity_timing_status"].astype(str)
    if not bool(
        timing_status.isin(
            {
                "CUTOFF_BOUND_IDENTITY",
                "RETROSPECTIVE_IDENTITY_ONLY",
                "TIMESTAMPED_IDENTITY_ONLY",
            }
        ).all()
    ) or not bool(identity["identity_source"].astype(str).ne("").all()):
        raise TensorContractError("identity provenance declaration is invalid")
    observed = identity["identity_observed_ts_utc"].astype(str)
    timestamped = timing_status.eq("TIMESTAMPED_IDENTITY_ONLY")
    if not bool(observed.loc[timestamped].ne("").all()) or bool(
        observed.loc[timing_status.eq("RETROSPECTIVE_IDENTITY_ONLY")].ne("").any()
    ):
        raise TensorContractError("identity observation timestamp contract drift")
    if pd.to_datetime(
        observed.loc[timestamped], utc=True, errors="coerce"
    ).isna().any():
        raise TensorContractError("timestamped identity observation is invalid")
    timestamped_observed = pd.to_datetime(
        observed.loc[timestamped], utc=True, errors="raise"
    )
    timestamped_cutoff = pd.to_datetime(
        identity.loc[timestamped, "feature_cutoff_ts_utc"],
        utc=True,
        errors="raise",
    )
    if bool(timestamped_observed.gt(timestamped_cutoff).any()):
        raise TensorContractError("timestamped identity appears after issue cutoff")
    expected_instances = (
        identity["issue"].astype(str)
        + "@CANONICAL_"
        + identity["year"].astype(str)
    )
    if not bool(identity["issue_instance"].astype(str).eq(expected_instances).all()):
        raise TensorContractError("issue instance does not bind issue and year")
    expected_folds = "OOS_" + identity["year"].astype(str)
    if not bool(identity["fold"].astype(str).eq(expected_folds).all()):
        raise TensorContractError("fold does not bind canonical year")
    heldout_rows = identity["issue"].astype(str).isin(HELDOUT_ISSUES)
    if not bool(identity.loc[heldout_rows, "split"].astype(str).eq("heldout").all()):
        raise TensorContractError("held-out issue is not assigned to heldout split")
    if not bool(
        identity.loc[~heldout_rows, "split"].astype(str).eq("development").all()
    ):
        raise TensorContractError("development issue is assigned to heldout split")
    expected_keys = identity["cell_join_key"].astype(str).tolist()
    if values["cell_join_key"].astype(str).tolist() != expected_keys:
        raise TensorContractError("feature values are not identity-aligned")
    if masks["cell_join_key"].astype(str).tolist() != expected_keys:
        raise TensorContractError("feature masks are not identity-aligned")
    expected_outcome_order = {code: index for index, code in enumerate(OUTCOME_ORDER)}
    for row in identity.itertuples(index=False):
        code = str(row.outcome_code)
        if expected_outcome_order.get(code) != int(row.outcome_order):
            raise TensorContractError("canonical outcome ordering drift")
        expected = cell_join_key(str(row.issue_instance), str(row.match_id), code)
        if str(row.cell_join_key) != expected:
            raise TensorContractError("cell join key does not bind exact identity")
    cell_groups = identity.groupby(
        ["issue_instance", "match_id"], sort=False, dropna=False
    )
    if not bool(cell_groups.size().eq(len(OUTCOME_ORDER)).all()):
        raise TensorContractError("each match must contain exactly three outcome cells")
    outcome_sequences = cell_groups["outcome_code"].agg(
        lambda values: tuple(values.astype(str))
    )
    if not bool(outcome_sequences.map(lambda value: value == OUTCOME_ORDER).all()):
        raise TensorContractError("match cells do not follow canonical 3,1,0 order")
    for field in (
        "issue", "year", "fold", "split", "issue_order", "match_idx",
        "match_order", "feature_cutoff_ts_utc", "kickoff_ts_utc",
        "availability_status", "unavailable_reason", "source_b0_status",
        "identity_source", "identity_observed_ts_utc", "identity_timing_status",
        "euro_1h_available_ts_utc", "predicted_sp_available_ts_utc",
    ):
        if not bool(cell_groups[field].nunique(dropna=False).eq(1).all()):
            raise TensorContractError(f"match identity field is inconsistent: {field}")
    issue_groups = identity.groupby("issue_instance", sort=False, dropna=False)
    for field in (
        "issue", "year", "fold", "split", "issue_order", "feature_cutoff_ts_utc",
    ):
        if not bool(issue_groups[field].nunique(dropna=False).eq(1).all()):
            raise TensorContractError(f"issue identity field is inconsistent: {field}")
    match_rows = identity.drop_duplicates(["issue_instance", "match_id"])
    for _, issue_rows in match_rows.groupby("issue_instance", sort=False):
        if issue_rows["match_order"].astype(int).tolist() != list(
            range(len(issue_rows))
        ):
            raise TensorContractError("match ordering is not contiguous within issue")
        canonical = (
            issue_rows.assign(
                _match_idx=pd.to_numeric(issue_rows["match_idx"], errors="raise"),
                _match_id=issue_rows["match_id"].astype(str),
            )
            .sort_values(["_match_idx", "_match_id"], kind="mergesort")
            ["match_id"]
            .astype(str)
            .tolist()
        )
        if issue_rows["match_id"].astype(str).tolist() != canonical:
            raise TensorContractError("match axis is not in canonical source order")
    issue_rows = identity.drop_duplicates("issue_instance")
    if issue_rows["issue_order"].astype(int).tolist() != list(
        range(len(issue_rows))
    ):
        raise TensorContractError("issue ordering is not contiguous")
    canonical_issues = (
        issue_rows.assign(
            _cutoff=pd.to_datetime(
                issue_rows["feature_cutoff_ts_utc"], utc=True, errors="raise"
            ),
            _issue=pd.to_numeric(issue_rows["issue"], errors="raise"),
        )
        .sort_values(["_cutoff", "_issue"], kind="mergesort")["issue_instance"]
        .astype(str)
        .tolist()
    )
    if issue_rows["issue_instance"].astype(str).tolist() != canonical_issues:
        raise TensorContractError("issue axis is not in canonical cutoff order")
    mask_values = masks.loc[:, FEATURE_NAMES]
    if not all(dtype == np.dtype("bool") for dtype in mask_values.dtypes):
        raise TensorContractError("feature masks must be Boolean")
    if not all(
        dtype == np.dtype("float32")
        for dtype in values.loc[:, FEATURE_NAMES].dtypes
    ):
        raise TensorContractError("feature values must be float32")
    numeric = values.loc[:, FEATURE_NAMES].apply(pd.to_numeric, errors="coerce")
    present = mask_values.to_numpy(dtype=bool)
    numeric_array = numeric.to_numpy(dtype=np.float64)
    if not np.isfinite(numeric_array[present]).all():
        raise TensorContractError("unmasked feature values must be finite")
    if np.isfinite(numeric_array[~present]).any():
        raise TensorContractError("masked feature slots must not carry values")
    registry_only = identity["identity_timing_status"].astype(str).isin(
        {"RETROSPECTIVE_IDENTITY_ONLY", "TIMESTAMPED_IDENTITY_ONLY"}
    ).to_numpy()
    registry_forbidden = [
        feature
        for feature in FEATURE_NAMES
        if feature not in {
            "outcome_code_numeric",
            "kickoff_delay_hours",
            "match_position_fraction",
            "calendar_year",
        }
    ]
    if bool(mask_values.loc[registry_only, registry_forbidden].to_numpy().any()):
        raise TensorContractError(
            "identity-only held-out row exposes a decision feature"
        )
    for column_index, spec in enumerate(FEATURE_SPECS):
        feature_values = numeric_array[:, column_index]
        feature_present = present[:, column_index]
        if spec.minimum is not None and bool(
            (feature_values[feature_present] < spec.minimum).any()
        ):
            raise TensorContractError(f"feature below contract minimum: {spec.name}")
        if spec.maximum is not None and bool(
            (feature_values[feature_present] > spec.maximum).any()
        ):
            raise TensorContractError(f"feature above contract maximum: {spec.name}")
    outcome_axis = values["outcome_code_numeric"].to_numpy(dtype=np.float32)
    expected_axis = identity["outcome_code"].astype(np.float32).to_numpy()
    outcome_present = mask_values["outcome_code_numeric"].to_numpy(dtype=bool)
    if not bool(outcome_present.all()) or not np.array_equal(
        outcome_axis, expected_axis
    ):
        raise TensorContractError("outcome-code feature does not bind identity axis")
    calendar_column = FEATURE_NAMES.index("calendar_year")
    calendar_present = present[:, calendar_column]
    calendar_expected = identity["year"].astype(np.float32).to_numpy()
    if not bool(calendar_present.all()) or not np.array_equal(
        numeric_array[:, calendar_column].astype(np.float32), calendar_expected
    ):
        raise TensorContractError("calendar-year feature does not bind identity")
    match_position_column = FEATURE_NAMES.index("match_position_fraction")
    issue_match_counts = identity.groupby(
        "issue_instance", sort=False, dropna=False
    )["match_id"].transform("nunique").to_numpy(dtype=np.float64)
    expected_position = identity["match_order"].to_numpy(dtype=np.float64) / np.maximum(
        issue_match_counts - 1.0, 1.0
    )
    if not bool(present[:, match_position_column].all()) or not np.allclose(
        numeric_array[:, match_position_column], expected_position, rtol=0, atol=1e-7
    ):
        raise TensorContractError("match-position feature does not bind identity")
    kickoff_column = FEATURE_NAMES.index("kickoff_delay_hours")
    kickoff = pd.to_datetime(identity["kickoff_ts_utc"], utc=True, errors="raise")
    issue_cutoff = pd.to_datetime(
        identity["feature_cutoff_ts_utc"], utc=True, errors="raise"
    )
    expected_delay = (kickoff - issue_cutoff).dt.total_seconds().to_numpy() / 3600.0
    expected_delay_present = np.isfinite(expected_delay) & (expected_delay >= 0)
    if not np.array_equal(
        present[:, kickoff_column], expected_delay_present
    ) or not np.array_equal(
        numeric_array[expected_delay_present, kickoff_column].astype(np.float32),
        expected_delay[expected_delay_present].astype(np.float32),
    ):
        raise TensorContractError("kickoff-delay feature does not bind identity")
    probability_features = (
        "calibrated_market_probability",
        "devig_euro_probability",
        "fundamental_probability",
    )
    for feature in probability_features:
        column = FEATURE_NAMES.index(feature)
        group_present = present[:, column].reshape(-1, len(OUTCOME_ORDER))
        if not bool((group_present == group_present[:, :1]).all()):
            raise TensorContractError(
                f"probability mask is not outcome-complete: {feature}"
            )
        complete = group_present[:, 0]
        group_values = numeric_array[:, column].reshape(-1, len(OUTCOME_ORDER))
        if not np.allclose(
            group_values[complete].sum(axis=1),
            1.0,
            rtol=0,
            atol=2e-6,
        ):
            raise TensorContractError(
                f"probability simplex does not sum to one: {feature}"
            )
    calibrated_column = FEATURE_NAMES.index("calibrated_market_probability")
    residual_column = FEATURE_NAMES.index("probability_residual")
    residual_z_column = FEATURE_NAMES.index("probability_residual_z")
    if not np.array_equal(
        present[:, calibrated_column], present[:, residual_column]
    ) or not np.array_equal(
        present[:, residual_column], present[:, residual_z_column]
    ):
        raise TensorContractError("calibrated residual masks do not share identity")
    residual_present = present[:, residual_column].reshape(
        -1, len(OUTCOME_ORDER)
    )[:, 0]
    residual_values = numeric_array[:, residual_column].reshape(
        -1, len(OUTCOME_ORDER)
    )
    if not np.allclose(
        residual_values[residual_present].sum(axis=1),
        0.0,
        rtol=0,
        atol=2e-6,
    ):
        raise TensorContractError("calibrated probability residual is not zero-sum")
    calibrated_values = numeric_array[:, calibrated_column].reshape(
        -1, len(OUTCOME_ORDER)
    )
    hidden_consensus = (
        calibrated_values[residual_present] - residual_values[residual_present]
    )
    if bool(
        (hidden_consensus < -2e-6).any()
        or (hidden_consensus > 1.0 + 2e-6).any()
    ) or not np.allclose(
        hidden_consensus.sum(axis=1), 1.0, rtol=0, atol=2e-6
    ):
        raise TensorContractError("frozen residual baseline is not a probability simplex")
    cutoff = pd.to_datetime(identity["feature_cutoff_ts_utc"], utc=True, errors="raise")
    one_hour = pd.to_datetime(
        identity["euro_1h_available_ts_utc"], utc=True, errors="coerce"
    )
    ten_hour = pd.to_datetime(
        identity["predicted_sp_available_ts_utc"], utc=True, errors="coerce"
    )
    one_hour_late = one_hour.notna() & one_hour.gt(cutoff)
    ten_hour_late = ten_hour.notna() & ten_hour.gt(cutoff)
    one_hour_features = (
        "calibrated_market_probability", "devig_euro_probability", "euro_1h_odds",
        "probability_residual", "probability_residual_z", "market_uncertainty",
        "market_signature_breadth", "market_signature_dispersion",
    )
    if bool(mask_values.loc[one_hour_late, one_hour_features].to_numpy().any()):
        raise TensorContractError("1h market feature crosses issue cutoff")
    if bool(mask_values.loc[one_hour.isna(), one_hour_features].to_numpy().any()):
        raise TensorContractError("1h market feature lacks a valid availability time")
    if bool(mask_values.loc[ten_hour_late, "predicted_final_sp"].any()):
        raise TensorContractError("predicted-SP feature crosses issue cutoff")
    if bool(mask_values.loc[ten_hour.isna(), "predicted_final_sp"].any()):
        raise TensorContractError("predicted-SP feature lacks a valid availability time")


def load_issue_tensors(
    package: str | Path,
    *,
    split: str | None = None,
    issues: Iterable[str] | None = None,
) -> tuple[IssueTensor, ...]:
    """Load one or more ragged tensors without opening settlement labels."""

    identity, values, masks = _verified_tables(Path(package))
    _validate_cells(identity, values, masks)
    if split is not None:
        if split not in {"development", "heldout"}:
            raise TensorContractError(f"unsupported split: {split}")
        keep = identity["split"].astype(str).eq(split)
        identity, values, masks = identity[keep], values[keep], masks[keep]
    if issues is not None:
        requested = {str(issue) for issue in issues}
        keep = identity["issue"].astype(str).isin(requested)
        identity, values, masks = identity[keep], values[keep], masks[keep]
    output: list[IssueTensor] = []
    for issue_instance, frame in identity.groupby("issue_instance", sort=False):
        positions = frame.index.to_numpy()
        matches = frame.drop_duplicates("match_order").sort_values("match_order")
        j = len(matches)
        value_array = values.loc[positions, FEATURE_NAMES].to_numpy(
            dtype=np.float32, copy=True
        ).reshape(j, len(OUTCOME_ORDER), len(FEATURE_NAMES))
        mask_array = masks.loc[positions, FEATURE_NAMES].to_numpy(
            dtype=bool, copy=True
        ).reshape(j, len(OUTCOME_ORDER), len(FEATURE_NAMES))
        value_array[~mask_array] = np.float32(0.0)
        first = frame.iloc[0]
        output.append(
            IssueTensor(
                issue=str(first["issue"]),
                issue_instance=str(issue_instance),
                fold=str(first["fold"]),
                split=str(first["split"]),
                feature_cutoff_ts_utc=str(first["feature_cutoff_ts_utc"]),
                match_ids=tuple(matches["match_id"].astype(str)),
                match_indices=tuple(matches["match_idx"].astype(int)),
                match_provenance=tuple(
                    MatchProvenance(
                        match_id=str(row.match_id),
                        match_idx=int(row.match_idx),
                        match_order=int(row.match_order),
                        kickoff_ts_utc=str(row.kickoff_ts_utc),
                        availability_status=str(row.availability_status),
                        unavailable_reason=str(row.unavailable_reason),
                        source_b0_status=str(row.source_b0_status),
                        identity_source=str(row.identity_source),
                        identity_observed_ts_utc=str(row.identity_observed_ts_utc),
                        identity_timing_status=str(row.identity_timing_status),
                        euro_1h_available_ts_utc=str(row.euro_1h_available_ts_utc),
                        predicted_sp_available_ts_utc=str(
                            row.predicted_sp_available_ts_utc
                        ),
                    )
                    for row in matches.itertuples(index=False)
                ),
                values=value_array,
                masks=mask_array,
            )
        )
    return tuple(output)


def load_issue_tensor(package: str | Path, issue: str) -> IssueTensor:
    tensors = load_issue_tensors(package, issues=(issue,))
    if len(tensors) != 1:
        raise TensorContractError(
            f"expected one issue tensor for {issue}, found {len(tensors)}"
        )
    return tensors[0]
