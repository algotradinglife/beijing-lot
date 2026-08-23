"""Outcome-separated readers for the #238 historical experiment."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as pads

from .contract import (
    CALIBRATION_YEAR,
    FIT_END,
    HORIZONS,
    OUTCOMES,
    PROBABILITY_TOLERANCE,
    SEALED_START_YEAR,
    TUNE_YEAR,
)


class DataContractError(ValueError):
    """Raised when an input violates the frozen scientific boundary."""


def _connect_read_only(path: Path) -> sqlite3.Connection:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    return connection


def load_issue_roles(
    candidate_sqlite: Path,
    issue_registry_sqlite: Path,
) -> pd.DataFrame:
    """Assign whole issues to temporal roles using source timestamps, never IDs."""

    with _connect_read_only(candidate_sqlite) as connection:
        issues = pd.read_sql_query(
            """
            SELECT CAST(issue_code AS TEXT) AS issue_code,
                   COUNT(*) AS inventory_fixtures,
                   MAX(CASE
                         WHEN kickoff_ts >= '2013-01-01 00:00:00'
                         THEN kickoff_ts
                       END) AS issue_anchor_ts
            FROM inventory
            GROUP BY issue_code
            ORDER BY issue_code
            """,
            connection,
        )
    with _connect_read_only(issue_registry_sqlite) as connection:
        registry = pd.read_sql_query(
            """
            SELECT CAST(issue AS TEXT) AS issue_code, year AS registry_year
            FROM issues
            WHERE issue IS NOT NULL
            """,
            connection,
        )
    if issues["issue_code"].duplicated().any():
        raise DataContractError("candidate inventory has duplicate issue identities")
    if registry["issue_code"].duplicated().any():
        raise DataContractError("issue registry has duplicate issue identities")

    result = issues.merge(registry, on="issue_code", how="left", validate="one_to_one")
    result["issue_anchor_ts"] = pd.to_datetime(
        result["issue_anchor_ts"], errors="coerce"
    )
    anchor_year = result["issue_anchor_ts"].dt.year.astype("Int64")
    registry_year = pd.to_numeric(result["registry_year"], errors="coerce").astype(
        "Int64"
    )
    result["issue_year"] = anchor_year.fillna(registry_year)
    result["issue_date_source"] = np.where(
        anchor_year.notna(), "MAX_VALID_FIXTURE_KICKOFF", "SOURCE_ISSUE_REGISTRY_YEAR"
    )

    def role(year: object, anchor: object) -> str:
        if pd.isna(year):
            return "excluded_unknown_date"
        value = int(year)
        if value >= SEALED_START_YEAR:
            return "sealed_feature_only"
        if value == CALIBRATION_YEAR:
            return "calibration"
        if value == TUNE_YEAR:
            return "tune"
        if pd.notna(anchor) and pd.Timestamp(anchor) <= pd.Timestamp(FIT_END):
            return "fit"
        return "excluded_temporal_boundary"

    result["temporal_role"] = [
        role(year, anchor)
        for year, anchor in zip(result["issue_year"], result["issue_anchor_ts"])
    ]
    if len(result) != 808:
        raise DataContractError(f"expected 808 frozen issues, found {len(result)}")
    return result[
        [
            "issue_code",
            "inventory_fixtures",
            "issue_anchor_ts",
            "issue_year",
            "issue_date_source",
            "temporal_role",
        ]
    ]


def load_proxy_panel(
    proxy_root: Path,
    roles: pd.DataFrame,
    *,
    horizons: tuple[str, ...] = HORIZONS,
) -> pd.DataFrame:
    """Load #268's compact consensus triplets and normalized native line."""

    if not horizons or not set(horizons).issubset(HORIZONS):
        raise DataContractError(f"unexpected requested horizons: {horizons}")
    horizon_filter = pads.field("snapshot_kind").isin(list(horizons))

    probability_root = proxy_root / "probabilities"
    readiness_root = proxy_root / "translation_readiness"
    probability = (
        pads.dataset(probability_root, format="parquet")
        .to_table(
            filter=horizon_filter,
            columns=[
                "canonical_fixture_key",
                "issue_code",
                "match_idx",
                "snapshot_kind",
                "outcome_code",
                "probability",
                "n_available_books",
                "causal_grade",
            ]
        )
        .to_pandas()
    )
    readiness = (
        pads.dataset(readiness_root, format="parquet")
        .to_table(
            filter=horizon_filter,
            columns=[
                "canonical_fixture_key",
                "snapshot_kind",
                "native_handicap_line",
                "native_handicap_line_raw",
                "handicap_norm_source",
            ]
        )
        .to_pandas()
    )
    if not probability["snapshot_kind"].isin(horizons).all():
        raise DataContractError("unexpected relative horizon")
    if not probability["outcome_code"].isin(OUTCOMES).all():
        raise DataContractError("unexpected outcome code")
    key = ["canonical_fixture_key", "snapshot_kind"]
    if readiness.duplicated(key).any():
        raise DataContractError("translation readiness is not unique")
    if probability.duplicated([*key, "outcome_code"]).any():
        raise DataContractError("probability cells are not unique")

    probability["outcome_code"] = pd.Categorical(
        probability["outcome_code"], categories=list(OUTCOMES), ordered=True
    )
    wide = probability.pivot(
        index=[
            "canonical_fixture_key",
            "issue_code",
            "match_idx",
            "snapshot_kind",
            "n_available_books",
            "causal_grade",
        ],
        columns="outcome_code",
        values="probability",
    ).reset_index()
    wide.columns.name = None
    wide = wide.rename(columns={code: f"q_eu_{code}" for code in OUTCOMES})
    values = wide[[f"q_eu_{code}" for code in OUTCOMES]].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise DataContractError("proxy panel contains invalid probability cells")
    if not np.allclose(values.sum(axis=1), 1.0, atol=PROBABILITY_TOLERANCE):
        raise DataContractError("proxy triplets do not sum to one")

    wide = wide.merge(readiness, on=key, how="left", validate="one_to_one")
    wide["issue_code"] = wide["issue_code"].astype(str)
    wide = wide.merge(roles, on="issue_code", how="left", validate="many_to_one")
    if wide["temporal_role"].isna().any():
        raise DataContractError("proxy panel escaped the frozen issue inventory")
    line = pd.to_numeric(wide["native_handicap_line"], errors="coerce")
    wide["native_line_supported"] = (
        line.notna() & np.isfinite(line) & line.mod(1).eq(0) & line.between(-3.0, 3.0)
    )
    for code in OUTCOMES:
        wide[f"line_x_q_eu_{code}"] = (
            wide["native_handicap_line"] * wide[f"q_eu_{code}"]
        )
    return wide.sort_values(
        ["issue_code", "match_idx", "snapshot_kind"], kind="mergesort"
    ).reset_index(drop=True)


def load_development_labels(
    label_sqlite: Path, development_issues: set[str]
) -> pd.DataFrame:
    """Read only score cells belonging to pre-2024 issue partitions."""

    if not development_issues:
        raise DataContractError("development issue allow-list is empty")
    if len(development_issues) > 900:
        raise DataContractError("development issue allow-list exceeds bounded query")
    ordered = sorted(development_issues)
    placeholders = ",".join("?" for _ in ordered)
    query = (
        "SELECT CAST(issue AS TEXT) AS issue_code, match_idx, score "
        f"FROM matches WHERE CAST(issue AS TEXT) IN ({placeholders}) "
        "ORDER BY issue, match_idx"
    )
    with _connect_read_only(label_sqlite) as connection:
        labels = pd.read_sql_query(query, connection, params=ordered)
    if not set(labels["issue_code"]).issubset(development_issues):
        raise DataContractError("label query crossed the sealed issue allow-list")
    if labels.duplicated(["issue_code", "match_idx"]).any():
        raise DataContractError("development labels are not unique")
    score = (
        labels["score"].astype("string").str.extract(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")
    )
    labels["home_goals"] = pd.to_numeric(score[0], errors="coerce").astype("Int64")
    labels["away_goals"] = pd.to_numeric(score[1], errors="coerce").astype("Int64")
    labels["label_available"] = labels[["home_goals", "away_goals"]].notna().all(axis=1)
    return labels.drop(columns="score")


def attach_native_labels(panel: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Create handicap W/D/L targets only after the sealed role is excluded."""

    development = panel.loc[
        panel["temporal_role"].isin(["fit", "tune", "calibration"])
    ].copy()
    development = development.merge(
        labels,
        on=["issue_code", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    valid = (
        development["label_available"].fillna(False)
        & development["native_line_supported"]
        & development["home_goals"].notna()
        & development["away_goals"].notna()
    )
    development["target_outcome"] = pd.Series(
        pd.NA, index=development.index, dtype="string"
    )
    adjusted = (
        development.loc[valid, "home_goals"].astype(float)
        - development.loc[valid, "away_goals"].astype(float)
        + development.loc[valid, "native_handicap_line"].astype(float)
    )
    development.loc[valid & adjusted.gt(0), "target_outcome"] = "3"
    development.loc[valid & adjusted.eq(0), "target_outcome"] = "1"
    development.loc[valid & adjusted.lt(0), "target_outcome"] = "0"
    return development
