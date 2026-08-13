"""Issue #208: census + issue-panel loading from the frozen #205 surface.

Generalizes the #206 panel loader to arbitrary N eligibility and exposes the
pre-event cell surface used for counterfactual ticket construction.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .contract import (
    CAUSAL_TENSOR_PACKAGE,
    DEVELOPMENT_SPLITS,
    EMBARGOED_SPLITS,
    N_GRID,
    OUTCOMES,
    TAX_FACTOR,
    UPSTREAM_207_PACKAGE,
    VALUE_MATRIX,
    VALUE_MATRIX_SHA256,
)


class CensusError(RuntimeError):
    """Raised when the frozen surface fails closed."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


@dataclass(frozen=True)
class IssuePanel:
    split: str
    issue: str
    year: int
    match_idx: np.ndarray
    control_probability: np.ndarray  # M x 3
    experimental_probability: np.ndarray  # M x 3
    predicted_sp: np.ndarray  # M x 3
    sp_seed_std: np.ndarray  # M x 3
    official_sp: np.ndarray  # M x 3
    realized: np.ndarray  # M x 3 bool
    labels_available: bool
    match_ids: np.ndarray  # M (identity strings)
    excluded_matches: tuple[dict[str, Any], ...] = ()


def load_value_matrix(root: Path) -> pd.DataFrame:
    path = root / VALUE_MATRIX
    actual = digest(path)
    if actual != VALUE_MATRIX_SHA256:
        raise CensusError(
            f"value matrix sha mismatch: {actual} != {VALUE_MATRIX_SHA256}"
        )
    frame = pd.read_parquet(path)
    required = {
        "issue", "year", "split", "match_idx", "outcome_code",
        "control_probability", "control_probability_source",
        "control_probability_source_grade", "control_probability_promoted",
        "experimental_probability", "predicted_final_sp", "sp_seed_std",
        "official_final_sp_label", "realized_outcome",
    }
    if frame.empty or not required.issubset(frame.columns):
        raise CensusError("value matrix missing required columns")
    outcome_rank = {code: rank for rank, code in enumerate(OUTCOMES)}
    frame["_outcome_rank"] = frame.outcome_code.map(outcome_rank)
    if frame._outcome_rank.isna().any():
        raise CensusError("unsupported outcome code")
    return frame


def build_panels(frame: pd.DataFrame) -> dict[tuple[str, str], IssuePanel]:
    """Build per (split, issue) M x 3 panels with #206 exclusion semantics."""
    panels: dict[tuple[str, str], IssuePanel] = {}
    for (split, issue), group in frame.groupby(["split", "issue"], sort=False):
        group = group.sort_values(["match_idx", "_outcome_rank"], kind="mergesort")
        sizes = group.groupby("match_idx", sort=False).size()
        if not sizes.eq(3).all():
            raise CensusError(f"issue {issue} does not have complete M×3 rows")
        probability = group.control_probability.to_numpy(dtype=float).reshape(-1, 3)
        experimental_probability = group.experimental_probability.to_numpy(
            dtype=float
        ).reshape(-1, 3)
        sp = group.predicted_final_sp.to_numpy(dtype=float).reshape(-1, 3)
        sp_seed_std = group.sp_seed_std.to_numpy(dtype=float).reshape(-1, 3)
        official_sp = group.official_final_sp_label.to_numpy(dtype=float).reshape(-1, 3)
        realized = group.realized_outcome.to_numpy(dtype=bool).reshape(-1, 3)
        match_idx = group.match_idx.drop_duplicates().to_numpy(dtype=int)

        fully_missing_safe = np.isnan(probability).all(axis=1)
        malformed_safe = ~np.isfinite(probability) & ~fully_missing_safe[:, None]
        if malformed_safe.any():
            raise CensusError(f"issue {issue} has non-finite control_probability")
        retained = ~fully_missing_safe
        excluded_matches = tuple(
            {
                "split": str(split),
                "issue": str(issue),
                "year": int(group.year.iloc[0]),
                "match_idx": int(match_idx[row]),
                "exclusion_reason": "SAFE_CONTROL_PROBABILITY_ALL_MISSING",
            }
            for row in np.flatnonzero(fully_missing_safe)
        )
        probability = probability[retained]
        experimental_probability = experimental_probability[retained]
        sp = sp[retained]
        sp_seed_std = sp_seed_std[retained]
        official_sp = official_sp[retained]
        realized = realized[retained]
        match_idx = match_idx[retained]

        if not (probability > 0).all():
            raise CensusError(f"issue {issue} has non-positive control_probability")
        if not np.isclose(probability.sum(axis=1), 1.0, rtol=0.0, atol=1e-10).all():
            raise CensusError(f"issue {issue} has non-normalized control rows")
        if not np.isfinite(sp).all() or not (sp > 0).all():
            raise CensusError(f"issue {issue} has non-finite/non-positive predicted_sp")
        if not np.isfinite(experimental_probability).all():
            raise CensusError(f"issue {issue} non-finite experimental_probability")
        if str(split) in EMBARGOED_SPLITS:
            labels_available = False
        else:
            labels_available = bool(realized.sum(axis=1).sum() > 0)

        match_ids = (
            group["match_idx"].drop_duplicates().astype(str).to_numpy()
        )
        panels[(str(split), str(issue))] = IssuePanel(
            split=str(split),
            issue=str(issue),
            year=int(group.year.iloc[0]),
            match_idx=match_idx,
            control_probability=probability,
            experimental_probability=experimental_probability,
            predicted_sp=sp,
            sp_seed_std=sp_seed_std,
            official_sp=official_sp,
            realized=realized,
            labels_available=labels_available,
            match_ids=match_ids,
            excluded_matches=excluded_matches,
        )
    return panels


def eligibility(panels: dict[tuple[str, str], IssuePanel]) -> pd.DataFrame:
    """Per (split, issue, N) eligibility census: M >= N and labels available."""
    rows: list[dict[str, Any]] = []
    for (split, issue), panel in panels.items():
        m = len(panel.match_idx)
        for n in N_GRID:
            rows.append(
                {
                    "split": panel.split,
                    "issue": panel.issue,
                    "year": panel.year,
                    "M": m,
                    "N": n,
                    "eligible": m >= n,
                    "labels_available": panel.labels_available,
                }
            )
    return pd.DataFrame(rows)


def census_table(panels: dict[tuple[str, str], IssuePanel]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for (split, issue), panel in panels.items():
        rows.append(
            {
                "split": panel.split,
                "issue": panel.issue,
                "year": panel.year,
                "M": len(panel.match_idx),
                "labels_available": panel.labels_available,
                "excluded_matches": len(panel.excluded_matches),
            }
        )
    return pd.DataFrame(rows)


def load_upstream_tickets(root: Path) -> pd.DataFrame:
    """Bind the exact #207 CONTROLLING K8 ticket identities."""
    path = root / UPSTREAM_207_PACKAGE / "active_research_ticket_requests.parquet"
    if not path.exists():
        raise CensusError(f"upstream tickets unavailable: {path}")
    frame = pd.read_parquet(path)
    if "panel_role" not in frame.columns:
        raise CensusError("upstream tickets missing panel_role")
    return frame


def load_upstream_ledger(root: Path) -> pd.DataFrame:
    path = root / UPSTREAM_207_PACKAGE / "issue_capital_ledger.parquet"
    if not path.exists():
        raise CensusError(f"upstream ledger unavailable: {path}")
    return pd.read_parquet(path)


def load_causal_tensor_cells(root: Path) -> pd.DataFrame:
    """Load pre-event causal tensor cells (feature_values + identity) for state x.

    Only development cohorts and pre-event feature columns are consumed;
    2024/2025/2026 rows are dropped at the identity boundary.
    """
    pkg = root / CAUSAL_TENSOR_PACKAGE / "inference"
    feature_values = pd.read_parquet(pkg / "feature_values.parquet")
    cell_identity = pd.read_parquet(pkg / "cell_identity.parquet")
    if feature_values.empty or cell_identity.empty:
        raise CensusError("causal tensor inference tables are empty")
    merged = cell_identity.merge(
        feature_values, on="cell_join_key", how="inner"
    )
    merged["year"] = merged["year"].astype(int)
    merged = merged[merged["year"] <= 2023].copy()
    return merged


def panel_ticket_features(panel: IssuePanel) -> pd.DataFrame:
    """Per-match pre-event feature summary rows for state construction."""
    rows = []
    for row in range(len(panel.match_idx)):
        rows.append(
            {
                "match_idx": int(panel.match_idx[row]),
                "max_control_prob": float(np.max(panel.control_probability[row])),
                "mean_control_prob": float(np.mean(panel.control_probability[row])),
                "max_predicted_sp": float(np.max(panel.predicted_sp[row])),
                "mean_predicted_sp": float(np.mean(panel.predicted_sp[row])),
                "mean_sp_seed_std": float(np.mean(panel.sp_seed_std[row])),
                "probability_hhi": float(
                    np.sum(panel.control_probability[row] ** 2)
                ),
            }
        )
    return pd.DataFrame(rows)


def issue_summary(panel: IssuePanel) -> dict[str, float]:
    """Issue-level pre-event distribution summaries (state x ingredients)."""
    p = panel.control_probability
    sp = panel.predicted_sp
    sstd = panel.sp_seed_std
    match_max = np.max(p, axis=1)
    match_hhi = np.sum(p**2, axis=1)
    return {
        "M": float(len(panel.match_idx)),
        "mean_max_control_prob": float(np.mean(match_max)),
        "max_max_control_prob": float(np.max(match_max)),
        "std_max_control_prob": float(np.std(match_max)),
        "mean_probability_hhi": float(np.mean(match_hhi)),
        "mean_predicted_sp": float(np.mean(sp)),
        "max_predicted_sp": float(np.max(sp)),
        "mean_sp_seed_std": float(np.mean(sstd)),
        "outcome_hhi": float(np.mean(np.sum(p**2, axis=1))),
        "labels_available": float(panel.labels_available),
    }


__all__ = [
    "CensusError", "IssuePanel", "build_panels", "census_table", "digest",
    "eligibility", "issue_summary", "load_causal_tensor_cells",
    "load_upstream_ledger", "load_upstream_tickets", "load_value_matrix",
    "panel_ticket_features",
]
