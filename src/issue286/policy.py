"""Exact-budget candidate selection and issue-level capital diagnostics."""

from __future__ import annotations

import hashlib
import math

import pandas as pd


def select_positive_prefix(
    candidates: pd.DataFrame,
    *,
    score_column: str,
    k: int,
    maximum_share: float,
) -> pd.DataFrame:
    """Fund only positive-score unique candidates within the final ticket quota."""

    if score_column not in candidates:
        raise ValueError(f"missing score column: {score_column}")
    if k <= 0 or not 0 <= maximum_share <= 1:
        raise ValueError("K/share outside the frozen policy boundary")
    quota = int(math.floor(k * maximum_share + 1e-12))
    if quota == 0:
        return candidates.iloc[0:0].copy()
    eligible = candidates.loc[candidates[score_column].gt(0)].copy()
    return eligible.sort_values(
        [score_column, "candidate_identity"],
        ascending=[False, True],
        kind="stable",
    ).head(quota)


def same_budget_random(
    candidates: pd.DataFrame, *, funded_count: int, issue: str, action_key: str
) -> pd.DataFrame:
    """Choose an exact post-dedup random control quota deterministically."""

    if funded_count < 0 or funded_count > len(candidates):
        raise ValueError("random-control quota is infeasible")
    if funded_count == 0:
        return candidates.iloc[0:0].copy()
    ranked = candidates.copy()
    ranked["_random_key"] = ranked["candidate_identity"].map(
        lambda identity: hashlib.sha256(
            f"286|{issue}|{action_key}|{identity}".encode()
        ).hexdigest()
    )
    return ranked.sort_values("_random_key", kind="stable").head(funded_count).drop(
        columns="_random_key"
    )


def chronological_capital_path(
    issue_rows: pd.DataFrame,
    *,
    pnl_column: str,
    initial_capital: float = 100_000.0,
) -> pd.DataFrame:
    """Return an asserted chronological issue-level capital path."""

    required = {"issue", "issue_year", pnl_column}
    missing = sorted(required - set(issue_rows.columns))
    if missing:
        raise ValueError(f"capital path missing columns: {missing}")
    path = issue_rows.copy()
    path["issue_numeric"] = pd.to_numeric(path["issue"], errors="raise")
    path = path.sort_values(["issue_year", "issue_numeric"]).reset_index(drop=True)
    order = path[["issue_year", "issue_numeric"]].to_records(index=False).tolist()
    if order != sorted(order):
        raise AssertionError("issue capital path is not chronological")
    path["capital_cny"] = initial_capital + path[pnl_column].cumsum()
    return path
