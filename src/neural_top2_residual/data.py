"""Causal M×3 feature and label assembly for Issue #334."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contract import ALL_YEARS, FEATURE_COLUMNS, FORBIDDEN_FEATURE_TOKENS, OUTCOMES

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", REPO_ROOT)).resolve()
INFERENCE = RUNTIME_ROOT / "data/derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
SETTLEMENT = RUNTIME_ROOT / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"


def load_causal_cells(years: tuple[int, ...] = ALL_YEARS) -> pd.DataFrame:
    """Load the accepted 10h M×3 panel without applying later research support filters."""

    columns = [
        "issue_code", "match_idx", "snapshot_kind", "issue_anchor_ts", "issue_year",
        "native_handicap_line", "n_available_books", "mapping_accepted",
        "outcome_code", "q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence",
    ]
    frame = pq.read_table(
        INFERENCE,
        filters=[("issue_year", "in", list(years)), ("snapshot_kind", "=", "10h")],
        columns=columns,
    ).to_pandas()
    frame = frame.rename(
        columns={
            "issue_code": "issue",
            "outcome_code": "outcome",
            "q_eu_bjline": "q_eu",
            "q_line_only_control": "q_line",
        }
    )
    frame["issue"] = frame["issue"].astype(str)
    frame["outcome"] = frame["outcome"].astype(str)
    frame = frame[
        frame["outcome"].isin(OUTCOMES)
        & frame["mapping_accepted"].fillna(False)
        & frame[["q_eu", "q_line", "eu_vs_line_divergence"]].notna().all(axis=1)
    ].copy()
    frame = frame.drop_duplicates(["issue", "match_idx", "outcome"], keep="first")
    complete = frame.groupby(["issue", "match_idx"])["outcome"].transform("nunique").eq(3)
    frame = frame[complete].copy()
    frame["divergence"] = frame["q_eu"] - frame["q_line"]
    frame["abs_divergence"] = frame["divergence"].abs()
    frame["mapping_accepted"] = frame["mapping_accepted"].astype(float)
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)

    match_wide = frame.pivot_table(
        index=["issue", "match_idx"], columns="outcome", values="q_eu", aggfunc="first"
    )
    entropy = -(match_wide * np.log(match_wide.clip(lower=1e-12))).sum(axis=1)
    issue_summary = (
        frame.drop_duplicates(["issue", "match_idx"])
        .groupby("issue", as_index=False)
        .agg(
            issue_matches=("match_idx", "size"),
            issue_books_mean=("n_available_books", "mean"),
            issue_line_abs_mean=("native_handicap_line", lambda x: x.abs().mean()),
        )
    )
    issue_entropy = entropy.rename("match_entropy").reset_index().groupby("issue", as_index=False).agg(
        issue_entropy_mean=("match_entropy", "mean")
    )
    issue_divergence = frame.groupby("issue", as_index=False).agg(
        issue_divergence_abs_mean=("abs_divergence", "mean")
    )
    frame = frame.merge(issue_summary, on="issue", validate="many_to_one")
    frame = frame.merge(issue_entropy, on="issue", validate="many_to_one")
    frame = frame.merge(issue_divergence, on="issue", validate="many_to_one")
    for outcome in OUTCOMES:
        frame[f"outcome_{outcome}"] = frame["outcome"].eq(outcome).astype(float)
    frame["market_value_anchor"] = frame["q_eu"] / frame["q_line"].clip(lower=1e-4)
    frame = frame.sort_values(["issue_year", "issue_anchor_ts", "issue", "match_idx", "outcome"])
    if frame.duplicated(["issue", "match_idx", "outcome"]).any():
        raise AssertionError("causal cell key is not unique")
    assert_feature_boundary(frame)
    return frame.reset_index(drop=True)


def attach_labels(cells: pd.DataFrame) -> pd.DataFrame:
    """Attach labels after the causal feature surface is complete."""

    issues = sorted(cells["issue"].unique())
    placeholders = ",".join("?" for _ in issues)
    with sqlite3.connect(f"file:{SETTLEMENT.resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        settlement = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(official_sp_3 AS REAL) AS official_sp_3,
                   CAST(official_sp_1 AS REAL) AS official_sp_1,
                   CAST(official_sp_0 AS REAL) AS official_sp_0,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted
            FROM match_features
            WHERE CAST(issue AS TEXT) IN ({placeholders})
            """,
            connection,
            params=issues,
        )
    settlement = settlement.drop_duplicates(["issue", "match_idx"], keep="first")
    fallback = pd.Series(np.nan, index=settlement.index, dtype=float)
    for outcome in OUTCOMES:
        mask = settlement["result_code"].eq(outcome)
        fallback.loc[mask] = pd.to_numeric(
            settlement.loc[mask, f"official_sp_{outcome}"], errors="coerce"
        )
    settlement["winning_sp"] = pd.to_numeric(settlement["winning_sp"], errors="coerce").fillna(fallback)
    settlement["settlement_available"] = (
        settlement["trusted"].eq(1)
        & settlement["result_code"].isin(OUTCOMES)
        & settlement["winning_sp"].gt(0)
    )
    labelled = cells.merge(
        settlement[["issue", "match_idx", "result_code", "winning_sp", "settlement_available"]],
        on=["issue", "match_idx"], how="left", validate="many_to_one",
    )
    labelled["settlement_available"] = labelled["settlement_available"].fillna(False)
    labelled["target_probability"] = (
        labelled["outcome"].eq(labelled["result_code"])
        & labelled["settlement_available"]
    ).astype(float)
    labelled["target_value"] = np.where(
        labelled["target_probability"].eq(1), labelled["winning_sp"], 0.0
    )
    labelled["availability_reason"] = np.select(
        [
            labelled["settlement_available"],
            labelled["result_code"].isna(),
            ~labelled["result_code"].isin(OUTCOMES),
            pd.to_numeric(labelled["winning_sp"], errors="coerce").le(0),
        ],
        ["OBSERVABLE", "SOURCE_ABSENT", "INVALID_RESULT", "INVALID_SP"],
        default="UNTRUSTED",
    )
    return labelled


def assert_feature_boundary(frame: pd.DataFrame) -> None:
    missing = sorted(set(FEATURE_COLUMNS) - set(frame.columns))
    if missing:
        raise AssertionError(f"missing features: {missing}")
    for name in FEATURE_COLUMNS:
        lower = name.lower()
        if any(token in lower for token in FORBIDDEN_FEATURE_TOKENS):
            raise AssertionError(f"forbidden feature: {name}")


def source_receipt(cells: pd.DataFrame) -> dict[str, object]:
    feature_projection = cells[
        ["issue", "match_idx", "outcome", "issue_anchor_ts", "issue_year", *FEATURE_COLUMNS]
    ].copy()
    feature_hash = hashlib.sha256(
        pd.util.hash_pandas_object(feature_projection, index=False).values.tobytes()
    ).hexdigest()
    return {
        "inference_path": str(INFERENCE.relative_to(RUNTIME_ROOT)),
        "settlement_path": str(SETTLEMENT.relative_to(RUNTIME_ROOT)),
        "feature_projection_sha256": feature_hash,
        "cells": int(len(cells)),
        "matches": int(cells[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "issues": int(cells["issue"].nunique()),
        "years": sorted(int(value) for value in cells["issue_year"].unique()),
        "feature_columns": list(FEATURE_COLUMNS),
        "external_sources_committed_to_git": False,
    }
