"""Outcome-unexposed loader for #214 decision-epoch tensors."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .contract import (
    COHORTS,
    CONTRACT_VERSION,
    EPOCH_RULES,
    FEATURE_NAMES,
    OUTCOME_ORDER,
    epoch_cell_key,
    forbidden_inference_names,
)


class DecisionEpochContractError(RuntimeError):
    """Raised when an epoch package violates the public inference boundary."""


@dataclass(frozen=True)
class DecisionEpochTensor:
    epoch_id: str
    issue: str
    cohort: str
    rule: str
    decision_epoch_utc: str
    match_ids: tuple[str, ...]
    match_indices: tuple[int, ...]
    values: np.ndarray
    masks: np.ndarray
    feature_names: tuple[str, ...] = FEATURE_NAMES
    outcome_order: tuple[str, ...] = OUTCOME_ORDER

    def __post_init__(self) -> None:
        expected = (len(self.match_ids), len(OUTCOME_ORDER), len(FEATURE_NAMES))
        if self.values.shape != expected or self.masks.shape != expected:
            raise DecisionEpochContractError(
                f"invalid epoch tensor shape: {self.epoch_id}"
            )
        if self.values.dtype != np.float32 or self.masks.dtype != np.bool_:
            raise DecisionEpochContractError("tensor dtypes must be float32 and bool")
        if not np.isfinite(self.values[self.masks]).all():
            raise DecisionEpochContractError("unmasked tensor values must be finite")


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _read_namespace(package: Path) -> tuple[dict[str, object], dict[str, pd.DataFrame]]:
    root = package.expanduser()
    if root.is_symlink():
        raise DecisionEpochContractError("package root must not be a symlink")
    root = root.resolve()
    if "labels" in {part.lower() for part in root.parts}:
        raise DecisionEpochContractError("epoch loader refuses label namespaces")
    namespace = root if root.name == "inference" else root / "inference"
    if namespace.is_symlink() or not namespace.is_dir():
        raise DecisionEpochContractError("inference namespace is unavailable")
    manifest_path = namespace / "MANIFEST.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DecisionEpochContractError("invalid inference manifest") from exc
    if (
        manifest.get("contract_version") != CONTRACT_VERSION
        or manifest.get("namespace") != "decision_epoch_outcome_unexposed_inference"
    ):
        raise DecisionEpochContractError("unsupported inference namespace")
    files = manifest.get("files")
    required = {
        "epoch_identity.parquet",
        "roster.parquet",
        "cell_identity.parquet",
        "feature_values.parquet",
        "feature_masks.parquet",
    }
    if not isinstance(files, dict) or set(files) != required:
        raise DecisionEpochContractError("inference file census drift")
    paths = list(namespace.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise DecisionEpochContractError("inference namespace contains a symlink")
    actual = {
        path.relative_to(namespace).as_posix()
        for path in paths
        if path.is_file() and path.name != "MANIFEST.json"
    }
    if actual != required or forbidden_inference_names(actual):
        raise DecisionEpochContractError("inference payload census is invalid")
    for relative, expected in files.items():
        if _digest(namespace / relative) != expected:
            raise DecisionEpochContractError(
                f"inference payload hash mismatch: {relative}"
            )
    tables = {name: pd.read_parquet(namespace / name) for name in sorted(required)}
    return manifest, tables


def _validate_tables(tables: dict[str, pd.DataFrame]) -> None:
    epochs = tables["epoch_identity.parquet"]
    roster = tables["roster.parquet"]
    identity = tables["cell_identity.parquet"]
    values = tables["feature_values.parquet"]
    masks = tables["feature_masks.parquet"]
    expected_epochs = [
        "epoch_id",
        "issue",
        "cohort",
        "epoch_rule",
        "epoch_ordinal",
        "decision_epoch_utc",
        "source_freeze_cutoff_utc",
        "evaluation_status",
        "epoch_source",
        "segment_idx",
        "denominator_match_indices_json",
        "denominator_sha256",
    ]
    expected_roster = [
        "epoch_id",
        "issue",
        "cohort",
        "match_id",
        "match_idx",
        "decision_epoch_utc",
        "kickoff_ts_utc",
        "identity_observed_ts_utc",
        "sale_status",
        "parlay_allowed",
        "eligibility_observed_ts_utc",
        "market_observed_ts_utc",
        "source_row_sha256",
    ]
    expected_identity = [
        "cell_join_key",
        "epoch_id",
        "issue",
        "cohort",
        "epoch_rule",
        "decision_epoch_utc",
        "match_id",
        "match_idx",
        "match_order",
        "kickoff_ts_utc",
        "outcome_code",
        "outcome_order",
    ]
    if list(epochs.columns) != expected_epochs or not epochs["epoch_id"].is_unique:
        raise DecisionEpochContractError("epoch identity schema drift")
    if list(roster.columns) != expected_roster:
        raise DecisionEpochContractError("strict roster schema drift")
    if list(identity.columns) != expected_identity:
        raise DecisionEpochContractError("cell identity schema drift")
    if list(values.columns) != ["cell_join_key", *FEATURE_NAMES]:
        raise DecisionEpochContractError("feature value schema drift")
    if list(masks.columns) != ["cell_join_key", *FEATURE_NAMES]:
        raise DecisionEpochContractError("feature mask schema drift")
    if forbidden_inference_names(
        [
            *epochs.columns,
            *roster.columns,
            *identity.columns,
            *values.columns,
            *masks.columns,
        ]
    ):
        raise DecisionEpochContractError("forbidden inference field")
    if not bool(epochs["cohort"].isin(COHORTS).all()) or not bool(
        epochs["epoch_rule"].isin(EPOCH_RULES).all()
    ):
        raise DecisionEpochContractError("epoch cohort/rule drift")
    if not roster["epoch_id"].isin(epochs["epoch_id"]).all():
        raise DecisionEpochContractError("roster references an unknown epoch")
    if not identity["epoch_id"].isin(epochs["epoch_id"]).all():
        raise DecisionEpochContractError("cells reference an unknown epoch")
    if not values["cell_join_key"].equals(identity["cell_join_key"]) or not masks[
        "cell_join_key"
    ].equals(identity["cell_join_key"]):
        raise DecisionEpochContractError("feature tables do not bind cell identity")

    for table, observed_columns in (
        (
            roster,
            ("identity_observed_ts_utc", "eligibility_observed_ts_utc", "market_observed_ts_utc"),
        ),
    ):
        decision = pd.to_datetime(table["decision_epoch_utc"], utc=True, errors="raise")
        kickoff = pd.to_datetime(table["kickoff_ts_utc"], utc=True, errors="raise")
        if bool(kickoff.le(decision).any()):
            raise DecisionEpochContractError("started match appears in strict roster")
        for column in observed_columns:
            observed = pd.to_datetime(table[column], utc=True, errors="raise")
            if bool(observed.gt(decision).any()):
                raise DecisionEpochContractError(
                    f"post-epoch observation appears in strict roster: {column}"
                )
    if not roster.empty and not bool(
        roster["sale_status"].eq("open").all()
        and roster["parlay_allowed"].eq("allowed").all()
    ):
        raise DecisionEpochContractError("strict roster contains ineligible match")

    expected_keys = [
        epoch_cell_key(str(row.epoch_id), str(row.match_id), str(row.outcome_code))
        for row in identity.itertuples(index=False)
    ]
    if identity["cell_join_key"].astype(str).tolist() != expected_keys:
        raise DecisionEpochContractError("epoch cell join key drift")
    for (_epoch, _match), group in identity.groupby(
        ["epoch_id", "match_id"], sort=False
    ):
        if tuple(group["outcome_code"].astype(str)) != OUTCOME_ORDER or tuple(
            group["outcome_order"].astype(int)
        ) != tuple(range(len(OUTCOME_ORDER))):
            raise DecisionEpochContractError("canonical outcome axis drift")
    numeric_values = values.loc[:, FEATURE_NAMES].to_numpy(dtype=np.float32)
    bool_masks = masks.loc[:, FEATURE_NAMES].to_numpy(dtype=bool)
    if not np.isfinite(numeric_values[bool_masks]).all():
        raise DecisionEpochContractError("unmasked feature is nonfinite")
    if bool(np.isfinite(numeric_values[~bool_masks]).any()):
        raise DecisionEpochContractError("masked feature must be null")


def load_epoch_tensors(package: Path) -> tuple[DecisionEpochTensor, ...]:
    """Validate and materialize all epoch tensors, including empty strict rosters."""

    _manifest, tables = _read_namespace(package)
    _validate_tables(tables)
    epochs = tables["epoch_identity.parquet"]
    roster = tables["roster.parquet"]
    identity = tables["cell_identity.parquet"]
    values = tables["feature_values.parquet"]
    masks = tables["feature_masks.parquet"]
    outputs: list[DecisionEpochTensor] = []
    for epoch in epochs.itertuples(index=False):
        epoch_roster = roster[roster["epoch_id"].eq(epoch.epoch_id)].sort_values(
            ["match_idx", "match_id"], kind="mergesort"
        )
        epoch_cells = identity[identity["epoch_id"].eq(epoch.epoch_id)]
        indices = epoch_cells.index.to_numpy(dtype=int)
        match_count = len(epoch_roster)
        shape = (match_count, len(OUTCOME_ORDER), len(FEATURE_NAMES))
        epoch_values = (
            values.loc[indices, FEATURE_NAMES]
            .to_numpy(dtype=np.float32)
            .reshape(shape)
        )
        epoch_masks = (
            masks.loc[indices, FEATURE_NAMES].to_numpy(dtype=bool).reshape(shape)
        )
        outputs.append(
            DecisionEpochTensor(
                epoch_id=str(epoch.epoch_id),
                issue=str(epoch.issue),
                cohort=str(epoch.cohort),
                rule=str(epoch.epoch_rule),
                decision_epoch_utc=str(epoch.decision_epoch_utc),
                match_ids=tuple(epoch_roster["match_id"].astype(str)),
                match_indices=tuple(epoch_roster["match_idx"].astype(int)),
                values=epoch_values,
                masks=epoch_masks,
            )
        )
    return tuple(outputs)


__all__ = [
    "DecisionEpochContractError",
    "DecisionEpochTensor",
    "load_epoch_tensors",
]
