"""Deterministic, fail-closed loaders for the four upstream frozen packages.

Every loader verifies the package SHA256 manifest before returning data and
exposes only accepted, allow-listed columns of each upstream contract.
Reading is fail-closed: a hash mismatch or a schema deviation raises instead
of returning a silent fallback.

Rework changes (2026-08-15, class-1 sweep):
- ``load_bj203_match_meta`` returns ONE row per (issue, match_idx) with the
  exact match-level ``kickoff_ts_utc``, ``feature_cutoff_ts_utc`` (decision
  epoch), and per-feature observed-at timestamps (identity / euro_1h /
  predicted_sp).  The audited build joined #203 identity per-issue, which
  broadcast the first match's kickoff to the whole issue (107,194/107,853
  issue-match kickoffs mis-matched).
- ``load_bj203_feature_values`` binds #203's own per-cell feature values
  (devig_euro_probability, calibrated_market_probability, market_uncertainty,
  predicted_final_sp) — the accepted causal EU/uncertainty values that the
  audited handoff never carried.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from . import contract


class UpstreamBindingError(RuntimeError):
    """Raised when an upstream package fails hash or schema verification."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_member(package: Path, relative: str | Path) -> Path:
    """Resolve a manifest/schema member and require package containment."""
    root = package.resolve()
    member = Path(relative)
    if member.is_absolute():
        raise UpstreamBindingError(f"absolute package member forbidden: {relative}")
    target = (root / member).resolve()
    if not target.is_relative_to(root):
        raise UpstreamBindingError(f"package member escapes root: {relative}")
    return target


def verify_package_hashes(package: Path) -> dict[str, str]:
    """Verify every file listed in SHA256SUMS.json under ``package``."""
    sums_path = package / "SHA256SUMS.json"
    if not sums_path.exists():
        raise UpstreamBindingError(f"missing SHA256SUMS.json in {package}")
    expected = json.loads(sums_path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict):
        raise UpstreamBindingError("SHA256SUMS.json must be an object")
    actual: dict[str, str] = {}
    for relative, wanted in expected.items():
        target = package_member(package, relative)
        if not target.exists():
            raise UpstreamBindingError(f"manifest file missing: {relative}")
        actual[relative] = sha256_file(target)
        if actual[relative] != wanted:
            raise UpstreamBindingError(
                f"SHA256 mismatch for {relative}: got {actual[relative]}, "
                f"expected {wanted}"
            )
    return actual


def _require_columns(frame: pd.DataFrame, package_name: str, table: str,
                     columns: tuple[str, ...]) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise UpstreamBindingError(
            f"{package_name} {table} missing columns: {missing}"
        )


def _validate_three_cell_identity(
    frame: pd.DataFrame, package_name: str, table: str
) -> None:
    """Require one 3/1/0 row per issue-match and no duplicate cell identity."""
    identity = ["issue", "match_idx", "outcome_code"]
    _require_columns(frame, package_name, table, tuple(identity))
    if frame.empty:
        raise UpstreamBindingError(f"{package_name} {table} empty canonical cell axis")
    if frame.duplicated(identity, keep=False).any():
        raise UpstreamBindingError(f"{package_name} {table} duplicate source row")
    outcomes = (
        frame.assign(outcome_code=frame["outcome_code"].astype(str))
        .groupby(["issue", "match_idx"])["outcome_code"]
        .agg(lambda values: frozenset(values))
    )
    if not outcomes.map(
        lambda values: values == frozenset(contract.OUTCOME_CODES)
    ).all():
        raise UpstreamBindingError(
            f"{package_name} {table} partial triplet or invalid outcome domain"
        )


# ---------------------------------------------------------------------------
# #204 Gate A v5 — the operative probability interface (Q_BJ_CALIBRATED,
# native handicap line, predicted final SP input, source grade).
# ---------------------------------------------------------------------------
COMMON_CELL_FEATURES_COLUMNS = (
    "cell_key",
    "issue",
    "issue_instance",
    "year",
    "issue_order",
    "match_idx",
    "outcome_code",
    "role",
    "source_grade",
    "market_probability",
    "native_handicap_line",
    "source_is_pclose",
    "source_is_average_eu",
    "market_proxy_complete",
    "predicted_final_sp_input",
)
COMMON_CELL_MASKS_COLUMNS = (
    "cell_key",
    "market_probability",
    "native_handicap_line",
    "source_is_pclose",
    "source_is_average_eu",
    "market_proxy_complete",
    "predicted_final_sp_input",
)


def load_bj204_common_cells(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    package = contract.upstream_path(root, "bj204")
    verify_package_hashes(package)
    features = pq.read_table(
        package / "common_cell_features.parquet"
    ).to_pandas()
    masks = pq.read_table(package / "common_cell_masks.parquet").to_pandas()
    _require_columns(features, "bj204", "common_cell_features",
                     COMMON_CELL_FEATURES_COLUMNS)
    _require_columns(masks, "bj204", "common_cell_masks",
                     COMMON_CELL_MASKS_COLUMNS)
    _validate_three_cell_identity(features, "bj204", "common_cell_features")
    if features["cell_key"].astype(str).duplicated().any():
        raise UpstreamBindingError("bj204 common_cell_features duplicate cell_key")
    if masks["cell_key"].astype(str).duplicated().any():
        raise UpstreamBindingError("bj204 common_cell_masks duplicate cell_key")
    if set(features["cell_key"].astype(str)) != set(masks["cell_key"].astype(str)):
        raise UpstreamBindingError("bj204 feature/mask partial key-set mismatch")
    return features, masks


# ---------------------------------------------------------------------------
# #203 causal tensor v2 — canonical identity, cohort split, match-level
# timestamps, development labels (sealed boundary enforced by the caller),
# per-cell feature values.
# ---------------------------------------------------------------------------
CELL_IDENTITY_COLUMNS = (
    "cell_join_key",
    "issue",
    "issue_instance",
    "year",
    "fold",
    "split",
    "issue_order",
    "match_id",
    "match_idx",
    "match_order",
    "outcome_code",
    "outcome_order",
    "feature_cutoff_ts_utc",
    "kickoff_ts_utc",
    "availability_status",
    "unavailable_reason",
    "identity_observed_ts_utc",
    "identity_timing_status",
    "euro_1h_available_ts_utc",
    "predicted_sp_available_ts_utc",
)
# Columns carried in the match-level metadata frame (one row per match).
MATCH_META_COLUMNS = (
    "issue",
    "match_idx",
    "feature_cutoff_ts_utc",
    "kickoff_ts_utc",
    "identity_observed_ts_utc",
    "euro_1h_available_ts_utc",
    "predicted_sp_available_ts_utc",
    "identity_timing_status",
    "availability_status",
)
# Columns of #203 inference feature values used as accepted causal EU /
# uncertainty / predicted-SP values.
FEATURE_VALUE_COLUMNS = (
    "cell_join_key",
    "calibrated_market_probability",
    "devig_euro_probability",
    "euro_1h_odds",
    "predicted_final_sp",
    "native_handicap_line",
    "market_uncertainty",
    "probability_residual_z",
)


def load_bj203_identity(root: Path) -> pd.DataFrame:
    package = contract.upstream_path(root, "bj203")
    verify_package_hashes(package)
    identity = pq.read_table(
        package / "inference/cell_identity.parquet"
    ).to_pandas()
    _require_columns(identity, "bj203", "cell_identity", CELL_IDENTITY_COLUMNS)
    _validate_three_cell_identity(identity, "bj203", "cell_identity")
    if identity["cell_join_key"].astype(str).duplicated().any():
        raise UpstreamBindingError("bj203 cell_identity duplicate cell_join_key")
    return identity


def load_bj203_match_meta(root: Path) -> pd.DataFrame:
    """One row per (issue, match_idx) with exact match-level timestamps.

    #203 identity has three rows per match (one per outcome); the
    match-level timestamp columns are constant within a match (verified).
    Deduplicating on (issue, match_idx) yields the exact match-level meta.
    """
    identity = load_bj203_identity(root)
    meta = identity[list(MATCH_META_COLUMNS)].drop_duplicates()
    counts = identity.groupby(["issue", "match_idx"]).size()
    if (counts != 3).any():
        raise UpstreamBindingError(
            "#203 identity does not have exactly 3 rows per match"
        )
    if meta.duplicated(["issue", "match_idx"], keep=False).any():
        raise UpstreamBindingError(
            "#203 match metadata is non-constant within a three-cell match"
        )
    return meta


def load_bj203_feature_values(root: Path) -> pd.DataFrame:
    """Per-cell #203 feature values (accepted causal EU/uncertainty values)."""
    package = contract.upstream_path(root, "bj203")
    verify_package_hashes(package)
    values = pq.read_table(
        package / "inference/feature_values.parquet"
    ).to_pandas()
    _require_columns(values, "bj203", "feature_values", FEATURE_VALUE_COLUMNS)
    if values["cell_join_key"].astype(str).duplicated().any():
        raise UpstreamBindingError("#203 feature_values duplicate source row")
    return values[list(FEATURE_VALUE_COLUMNS)]


def load_bj203_labels(root: Path) -> pd.DataFrame:
    """Load development labels; caller enforces the sealed 2024 boundary."""
    package = contract.upstream_path(root, "bj203")
    verify_package_hashes(package)
    labels = pq.read_table(
        package / "labels/development_labels.parquet"
    ).to_pandas()
    missing = [c for c in contract.DEV_LABEL_INCLUDE_COLUMNS
               if c not in labels.columns]
    if missing:
        raise UpstreamBindingError(f"#203 labels missing columns: {missing}")
    if labels["cell_join_key"].astype(str).duplicated().any():
        raise UpstreamBindingError("#203 development_labels duplicate source row")
    return labels[list(contract.DEV_LABEL_INCLUDE_COLUMNS)]


# ---------------------------------------------------------------------------
# #214 decision-epoch tensor v1 — timestamped market observations
# (decision-epoch BJ SP and EU odds) + epoch identity + eligibility.
# ---------------------------------------------------------------------------
MARKET_OBSERVATION_COLUMNS = (
    "id",
    "match_id",
    "sp_3",
    "sp_1",
    "sp_0",
    "eu_h",
    "eu_d",
    "eu_a",
    "source",
    "snapshot_ts_utc",
)


def load_bj214_market_observations(root: Path) -> pd.DataFrame:
    package = contract.upstream_path(root, "bj214")
    verify_package_hashes(package)
    observations = pq.read_table(
        package / "sources/selected_market_observations.parquet"
    ).to_pandas()
    _require_columns(observations, "bj214", "market_observations",
                     MARKET_OBSERVATION_COLUMNS)
    if observations["id"].astype(str).duplicated().any():
        raise UpstreamBindingError("#214 duplicate observation id")
    if observations.duplicated(["match_id", "snapshot_ts_utc"], keep=False).any():
        raise UpstreamBindingError("#214 duplicate selected source row at one snapshot")
    return observations


def load_bj214_epoch_identity(root: Path) -> pd.DataFrame:
    package = contract.upstream_path(root, "bj214")
    verify_package_hashes(package)
    return pq.read_table(
        package / "inference/epoch_identity.parquet"
    ).to_pandas()


def load_bj214_eligibility(root: Path) -> pd.DataFrame:
    package = contract.upstream_path(root, "bj214")
    verify_package_hashes(package)
    return pq.read_table(
        package / "sources/selected_eligibility_observations.parquet"
    ).to_pandas()


# ---------------------------------------------------------------------------
# #180 team/matchup Gate A v2 — power-model probabilities in native 3/1/0
# space (P_POWER_BJLINE), unpromoted independent expert.  The freeze carries
# its own per-match ``feature_cutoff_ts`` (= the #180 common issue cutoff,
# verified to equal the first kickoff of the issue).
# ---------------------------------------------------------------------------
MATCH_PROBABILITY_FREEZE_COLUMNS = (
    "match_id",
    "issue",
    "match_idx",
    "kickoff_ts",
    "year",
    "league",
    "handicap_line_norm",
    "feature_cutoff_ts",
    "market_p3",
    "market_p1",
    "market_p0",
    "team_primary_p3",
    "team_primary_p1",
    "team_primary_p0",
)


def load_bj180_match_probabilities(root: Path) -> pd.DataFrame:
    package = contract.upstream_path(root, "bj180")
    verify_package_hashes(package)
    freeze = pd.read_csv(
        package / "match_probability_freeze.csv.gz", compression="gzip"
    )
    _require_columns(freeze, "bj180", "match_probability_freeze",
                     MATCH_PROBABILITY_FREEZE_COLUMNS)
    freeze["issue"] = freeze["issue"].astype(str)
    if freeze.duplicated(["issue", "match_idx"], keep=False).any():
        raise UpstreamBindingError("#180 duplicate source row")
    # ``match_id`` is #180's opaque database identity.  The published, explicit
    # issue/match_idx columns are the join contract; never reverse-engineer the
    # opaque ID into a synthetic issue key.
    return freeze
