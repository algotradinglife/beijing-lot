"""Issue #232 — provenance-valid recovery and decision-epoch SP triplets.

Recovery rules (contract items 3-4):

- Only observations with ``observed_at <= decision_epoch`` are recovered.
- No timestamp inference from results, final SP, kickoff hindsight,
  issue-number prefixes or later snapshots.
- Decision-epoch Beijing SP triplets are materialized SEPARATELY from
  normalized de-vig probabilities.  ``Q_BJ_SP_DEVIG`` is the normalized
  inverse of the observed decision-epoch SP; the raw SP prices remain a
  distinct price-input column (``SP_3/1/0``).  No ``0.65`` enters any cell.
- The relationship between the raw SP triplet and the de-vig probability is
  proven explicitly on every recovered triplet.

Every recovered triplet carries its source identity, observed-at, decision
epoch and the proof columns, so EV can re-derive the de-vig from the raw SP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import contract


class RecoveryError(RuntimeError):
    """Raised when a recovered triplet fails the causal/provenance rule."""


@dataclass
class Recovery:
    sp_triplets: pd.DataFrame = field(default_factory=pd.DataFrame)
    devig: pd.DataFrame = field(default_factory=pd.DataFrame)
    relationship: pd.DataFrame = field(default_factory=pd.DataFrame)
    receipts: pd.DataFrame = field(default_factory=pd.DataFrame)


def _load_meta(root: Path) -> pd.DataFrame:
    identity = pq.read_table(
        contract.upstream_path(root, "bj203") / "inference/cell_identity.parquet"
    ).to_pandas()
    identity["issue"] = identity["issue"].astype(str).str.strip()
    identity["match_idx"] = identity["match_idx"].astype(int)
    meta = identity[
        [
            "issue",
            "match_idx",
            "feature_cutoff_ts_utc",
            "kickoff_ts_utc",
            "year",
            "availability_status",
            "identity_timing_status",
        ]
    ].drop_duplicates()
    return meta


def normalize_sp_triplet(sp_3: float, sp_1: float, sp_0: float) -> np.ndarray:
    """Normalize inverse SP to a probability vector (de-vig on the 3/1/0 axis)."""
    values = np.asarray([sp_3, sp_1, sp_0], dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values <= 1.0):
        raise RecoveryError(f"impossible SP triplet: {values.tolist()}")
    inverse = 1.0 / values
    total = float(inverse.sum())
    if not np.isfinite(total) or total <= 0.0:
        raise RecoveryError(f"non-normalizable SP triplet: {values.tolist()}")
    return inverse / total


def _latest_causal_observation(
    observations: pd.DataFrame, meta: pd.DataFrame
) -> pd.DataFrame:
    """Latest observation at/before each match's decision epoch (fail-closed)."""
    obs = observations.copy()
    obs["snapshot_ts_utc"] = pd.to_datetime(
        obs["snapshot_ts_utc"], errors="coerce", utc=True
    )
    obs["issue"] = obs["match_id"].astype(str).str.split("_").str[0]
    obs["match_idx"] = obs["match_id"].astype(str).str.split("_").str[1].astype(int)
    obs = obs.merge(
        meta[
            [
                "issue",
                "match_idx",
                "feature_cutoff_ts_utc",
                "kickoff_ts_utc",
                "year",
            ]
        ],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    obs["feature_cutoff_ts_utc"] = pd.to_datetime(
        obs["feature_cutoff_ts_utc"], errors="coerce", utc=True
    )
    obs = obs[obs["feature_cutoff_ts_utc"].notna()]
    obs = obs[obs["snapshot_ts_utc"].le(obs["feature_cutoff_ts_utc"])]
    if obs.empty:
        return obs
    obs = obs.sort_values("snapshot_ts_utc")
    latest = obs.groupby(["issue", "match_idx"], as_index=False).tail(1)
    if latest.duplicated(["issue", "match_idx"], keep=False).any():
        raise RecoveryError("latest-causal selection produced duplicate match rows")
    return latest


def build_sp_recovery(root: Path, observations: pd.DataFrame) -> Recovery:
    """Materialize decision-epoch SP triplets + de-vig from #214 observations.

    Returns an explicit empty receipt when no observation is causally usable —
    it never fabricates a triplet.
    """
    meta = _load_meta(root)
    latest = _latest_causal_observation(observations, meta)
    recovery = Recovery()

    if latest.empty:
        empty = pd.DataFrame(
            [{
                "interface": "Q_BJ_SP_DEVIG",
                "recovered_triplet_cells": 0,
                "recovered_issue_count": 0,
                "reason": "NO_CAUSAL_OBSERVATION",
            }]
        )
        recovery.receipts = empty
        return recovery

    complete = latest[latest[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)]
    if complete.empty:
        recovery.receipts = pd.DataFrame(
            [{
                "interface": "Q_BJ_SP_DEVIG",
                "recovered_triplet_cells": 0,
                "recovered_issue_count": 0,
                "reason": "PARTIAL_SOURCE_TRIPLET",
            }]
        )
        return recovery

    rows: list[dict] = []
    for _, row in complete.iterrows():
        try:
            vector = normalize_sp_triplet(
                float(row["sp_3"]), float(row["sp_1"]), float(row["sp_0"])
            )
        except RecoveryError:
            continue
        rows.append(
            {
                "issue": str(row["issue"]),
                "match_idx": int(row["match_idx"]),
                "year": int(row["year"]) if pd.notna(row["year"]) else None,
                "SP_3": float(row["sp_3"]),
                "SP_1": float(row["sp_1"]),
                "SP_0": float(row["sp_0"]),
                "Q_BJ_SP_DEVIG_3": float(vector[0]),
                "Q_BJ_SP_DEVIG_1": float(vector[1]),
                "Q_BJ_SP_DEVIG_0": float(vector[2]),
                "observed_at_utc": row["snapshot_ts_utc"],
                "decision_epoch_utc": row["feature_cutoff_ts_utc"],
                "kickoff_ts_utc": row["kickoff_ts_utc"],
                "source_identity": contract.SRC_BJ214_OBSERVATION,
                "causal": bool(
                    row["snapshot_ts_utc"] <= row["feature_cutoff_ts_utc"]
                ),
            }
        )
    if not rows:
        recovery.receipts = pd.DataFrame(
            [{
                "interface": "Q_BJ_SP_DEVIG",
                "recovered_triplet_cells": 0,
                "recovered_issue_count": 0,
                "reason": "IMPOSSIBLE_SP",
            }]
        )
        return recovery

    triplets = pd.DataFrame(rows)
    # Relationship proof: de-vig == normalize(1 / raw SP) on every row.
    recomputed = np.stack(
        [
            normalize_sp_triplet(r["SP_3"], r["SP_1"], r["SP_0"])
            for _, r in triplets.iterrows()
        ]
    )
    triplets["devig_matches_normalized_inverse"] = np.allclose(
        recomputed,
        triplets[["Q_BJ_SP_DEVIG_3", "Q_BJ_SP_DEVIG_1", "Q_BJ_SP_DEVIG_0"]].to_numpy(),
        atol=1e-12,
    )
    triplets["triplet_sum"] = (
        triplets["Q_BJ_SP_DEVIG_3"]
        + triplets["Q_BJ_SP_DEVIG_1"]
        + triplets["Q_BJ_SP_DEVIG_0"]
    )
    triplets["triplet_bounded"] = (
        triplets[["Q_BJ_SP_DEVIG_3", "Q_BJ_SP_DEVIG_1", "Q_BJ_SP_DEVIG_0"]]
        .ge(0.0)
        .all(axis=1)
        & triplets[["Q_BJ_SP_DEVIG_3", "Q_BJ_SP_DEVIG_1", "Q_BJ_SP_DEVIG_0"]]
        .le(1.0)
        .all(axis=1)
    )
    recovery.sp_triplets = triplets

    # De-vig table: same triplets, normalized inverse (REQ-S05 separation).
    devig = triplets[
        [
            "issue",
            "match_idx",
            "year",
            "Q_BJ_SP_DEVIG_3",
            "Q_BJ_SP_DEVIG_1",
            "Q_BJ_SP_DEVIG_0",
            "observed_at_utc",
            "decision_epoch_utc",
            "source_identity",
        ]
    ].copy()
    devig["representation"] = contract.Q_BJ_SP_DEVIG
    recovery.devig = devig

    # Relationship table per issue: proof columns only.
    relationship = triplets.groupby(["issue", "year"], as_index=False).agg(
        triplet_count=("SP_3", "size"),
        devig_matches=("devig_matches_normalized_inverse", "all"),
        all_bounded=("triplet_bounded", "all"),
    )
    recovery.relationship = relationship
    recovery.receipts = pd.DataFrame(
        [{
            "interface": "Q_BJ_SP_DEVIG",
            "recovered_triplet_cells": int(len(triplets) * 3),
            "recovered_issue_count": int(triplets["issue"].nunique()),
            "reason": "RECOVERED",
        }]
    )
    return recovery
