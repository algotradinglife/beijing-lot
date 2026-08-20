"""Causal packing of variable-size Beijing issue M x 3 tensors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

OUTCOME_ORDER = ("3", "1", "0")

# Fail closed on names that directly reveal the current issue's settlement.
# Prior-settled path state is supplied through a separate, explicit interface.
FORBIDDEN_CURRENT_OUTCOME_TOKENS = (
    "actual_outcome",
    "realized_outcome",
    "result_code",
    "is_winner",
    "settlement_sp",
    "final_sp",
    "payout",
    "profit",
    "capital_change",
)


@dataclass(frozen=True)
class PackedIssues:
    """Padded issue tensors and masks in deterministic issue/match order."""

    issue_ids: tuple[str, ...]
    match_ids: tuple[tuple[str, ...], ...]
    cells: np.ndarray
    match_mask: np.ndarray
    feature_names: tuple[str, ...]


def pack_issue_cells(
    frame: pd.DataFrame,
    *,
    issue_col: str,
    match_col: str,
    outcome_col: str,
    feature_cols: Sequence[str],
) -> PackedIssues:
    """Pack one long pre-event cell table into a padded ``(I,M,3,F)`` array.

    Every observed match must have exactly the canonical three outcome rows.
    Missing feature values remain explicit as NaN so preprocessing can add
    missingness indicators without silently fabricating market information.
    """

    feature_names = tuple(feature_cols)
    _validate_columns(
        frame,
        issue_col=issue_col,
        match_col=match_col,
        outcome_col=outcome_col,
        feature_names=feature_names,
    )
    ordered = frame.assign(
        **{outcome_col: frame[outcome_col].astype(str)},
    ).copy()
    outcome_rank = {outcome: rank for rank, outcome in enumerate(OUTCOME_ORDER)}
    unknown = set(ordered[outcome_col].unique()).difference(OUTCOME_ORDER)
    if unknown:
        raise ValueError(f"unsupported outcome codes: {sorted(unknown)}")
    ordered["__outcome_rank"] = ordered[outcome_col].map(outcome_rank)
    ordered = ordered.sort_values(
        [issue_col, match_col, "__outcome_rank"], kind="stable"
    )
    duplicates = ordered.duplicated([issue_col, match_col, outcome_col], keep=False)
    if duplicates.any():
        raise ValueError("duplicate issue/match/outcome cells are not allowed")

    issue_groups = list(ordered.groupby(issue_col, sort=False, dropna=False))
    if not issue_groups:
        raise ValueError("at least one issue is required")
    issue_ids = tuple(str(issue_id) for issue_id, _ in issue_groups)
    per_issue: list[np.ndarray] = []
    match_ids: list[tuple[str, ...]] = []
    for issue_id, issue_frame in issue_groups:
        groups = list(issue_frame.groupby(match_col, sort=False, dropna=False))
        matrices: list[np.ndarray] = []
        ids: list[str] = []
        for match_id, match_frame in groups:
            observed = tuple(match_frame[outcome_col])
            if observed != OUTCOME_ORDER:
                raise ValueError(
                    f"issue {issue_id!r} match {match_id!r} does not have "
                    f"canonical outcomes {OUTCOME_ORDER}"
                )
            matrices.append(match_frame.loc[:, feature_names].to_numpy(dtype=float))
            ids.append(str(match_id))
        per_issue.append(np.stack(matrices))
        match_ids.append(tuple(ids))

    max_matches = max(len(matrix) for matrix in per_issue)
    cells = np.full(
        (len(per_issue), max_matches, 3, len(feature_names)), np.nan, dtype=float
    )
    match_mask = np.zeros((len(per_issue), max_matches), dtype=bool)
    for row, matrix in enumerate(per_issue):
        cells[row, : len(matrix)] = matrix
        match_mask[row, : len(matrix)] = True
    return PackedIssues(
        issue_ids=issue_ids,
        match_ids=tuple(match_ids),
        cells=cells,
        match_mask=match_mask,
        feature_names=feature_names,
    )


def _validate_columns(
    frame: pd.DataFrame,
    *,
    issue_col: str,
    match_col: str,
    outcome_col: str,
    feature_names: tuple[str, ...],
) -> None:
    if not feature_names:
        raise ValueError("at least one feature column is required")
    required = {issue_col, match_col, outcome_col, *feature_names}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    forbidden = [
        name
        for name in feature_names
        if any(token in name.lower() for token in FORBIDDEN_CURRENT_OUTCOME_TOKENS)
    ]
    if forbidden:
        raise ValueError(f"current-outcome feature columns are forbidden: {forbidden}")
