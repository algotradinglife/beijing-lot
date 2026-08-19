"""Executed data-quality profiles for the #236 historical European proxy."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = ("initial", "10h", "1h")
OUTCOME_COLUMNS = {"3": "v1", "1": "v2", "0": "v3"}


def _read_parts(package: Path, table: str) -> pd.DataFrame:
    parts = sorted((package / table).glob("*.parquet"))
    if not parts:
        raise FileNotFoundError(f"no Parquet parts for {table}: {package}")
    return pd.concat([pd.read_parquet(path) for path in parts], ignore_index=True)


def _connect(path: Path) -> sqlite3.Connection:
    database = path.resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def _fixture_metadata(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        WITH unique_slots AS (
            SELECT issue, match_idx
            FROM matches
            WHERE issue IS NOT NULL AND trim(issue) <> '' AND match_idx IS NOT NULL
            GROUP BY issue, match_idx
            HAVING COUNT(*) = 1
        )
        SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx, m.kickoff_ts,
               m.handicap_line AS native_handicap_line_raw,
               m.handicap_line_norm AS native_handicap_line,
               m.handicap_norm_source
        FROM matches AS m
        JOIN unique_slots AS u ON u.issue = m.issue AND u.match_idx = m.match_idx
        ORDER BY m.issue, m.match_idx
        """,
        con,
    )


def _bookmaker_profile(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        WITH unique_slots AS (
            SELECT issue, match_idx
            FROM matches
            WHERE issue IS NOT NULL AND trim(issue) <> '' AND match_idx IS NOT NULL
            GROUP BY issue, match_idx
            HAVING COUNT(*) = 1
        ), unique_quotes AS (
            SELECT match_id, market, snapshot, bookmaker
            FROM market_snapshots
            WHERE market = 'euro_1x2' AND snapshot IN ('initial', '10h', '1h')
            GROUP BY match_id, market, snapshot, bookmaker
            HAVING COUNT(*) = 1
        ), eligible_quotes AS (
            SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx,
                   s.snapshot AS snapshot_kind, s.bookmaker AS bookmaker_id,
                   s.v1, s.v2, s.v3,
                   CASE WHEN s.v1 > 1.0 AND s.v1 < 1.0e308
                              AND s.v2 > 1.0 AND s.v2 < 1.0e308
                              AND s.v3 > 1.0 AND s.v3 < 1.0e308
                        THEN 1 ELSE 0 END AS valid_triplet
            FROM market_snapshots AS s
            JOIN unique_quotes AS q
              ON q.match_id = s.match_id AND q.market = s.market
             AND q.snapshot = s.snapshot AND q.bookmaker = s.bookmaker
            JOIN matches AS m ON m.match_id = s.match_id
            JOIN unique_slots AS u ON u.issue = m.issue AND u.match_idx = m.match_idx
            WHERE s.market = 'euro_1x2' AND s.snapshot IN ('initial', '10h', '1h')
        )
        SELECT snapshot_kind, bookmaker_id,
               COUNT(*) AS raw_bookmaker_rows,
               COUNT(DISTINCT issue_code || ':' || printf('%03d', match_idx)) AS source_matrix_fixture_count,
               SUM(valid_triplet) AS valid_bookmaker_rows,
               SUM(1 - valid_triplet) AS invalid_bookmaker_rows,
               SUM(v1 IS NULL) AS v1_missing,
               SUM(v2 IS NULL) AS v2_missing,
               SUM(v3 IS NULL) AS v3_missing,
               SUM(CASE WHEN valid_triplet = 1 THEN v1 ELSE 0 END) AS v1_sum,
               SUM(CASE WHEN valid_triplet = 1 THEN v2 ELSE 0 END) AS v2_sum,
               SUM(CASE WHEN valid_triplet = 1 THEN v3 ELSE 0 END) AS v3_sum,
               SUM(CASE WHEN valid_triplet = 1 THEN v1 * v1 ELSE 0 END) AS v1_sq_sum,
               SUM(CASE WHEN valid_triplet = 1 THEN v2 * v2 ELSE 0 END) AS v2_sq_sum,
               SUM(CASE WHEN valid_triplet = 1 THEN v3 * v3 ELSE 0 END) AS v3_sq_sum,
               MIN(CASE WHEN valid_triplet = 1 THEN v1 END) AS v1_min,
               MIN(CASE WHEN valid_triplet = 1 THEN v2 END) AS v2_min,
               MIN(CASE WHEN valid_triplet = 1 THEN v3 END) AS v3_min,
               MAX(CASE WHEN valid_triplet = 1 THEN v1 END) AS v1_max,
               MAX(CASE WHEN valid_triplet = 1 THEN v2 END) AS v2_max,
               MAX(CASE WHEN valid_triplet = 1 THEN v3 END) AS v3_max
        FROM eligible_quotes
        GROUP BY snapshot_kind, bookmaker_id
        ORDER BY CASE snapshot_kind WHEN 'initial' THEN 1 WHEN '10h' THEN 2 ELSE 3 END,
                 bookmaker_id
        """,
        con,
    )


def _auxiliary_market_support(con: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        WITH unique_slots AS (
            SELECT issue, match_idx
            FROM matches
            WHERE issue IS NOT NULL AND trim(issue) <> '' AND match_idx IS NOT NULL
            GROUP BY issue, match_idx
            HAVING COUNT(*) = 1
        ), unique_quotes AS (
            SELECT match_id, market, snapshot, bookmaker
            FROM market_snapshots
            WHERE market IN ('asian_handicap', 'over_under')
              AND snapshot IN ('initial', '10h', '1h')
            GROUP BY match_id, market, snapshot, bookmaker
            HAVING COUNT(*) = 1
        ), eligible_quotes AS (
            SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx,
                   s.market AS market_type, s.snapshot AS snapshot_kind,
                   CASE WHEN s.v1 > 0.0 AND s.v1 < 1.0e308
                              AND s.v2 IS NOT NULL AND abs(s.v2) < 1.0e308
                              AND s.v3 > 0.0 AND s.v3 < 1.0e308
                        THEN 1 ELSE 0 END AS valid_native_quote
            FROM market_snapshots AS s
            JOIN unique_quotes AS q
              ON q.match_id = s.match_id AND q.market = s.market
             AND q.snapshot = s.snapshot AND q.bookmaker = s.bookmaker
            JOIN matches AS m ON m.match_id = s.match_id
            JOIN unique_slots AS u ON u.issue = m.issue AND u.match_idx = m.match_idx
            WHERE s.market IN ('asian_handicap', 'over_under')
              AND s.snapshot IN ('initial', '10h', '1h')
        )
        SELECT market_type, snapshot_kind,
               COUNT(*) AS source_bookmaker_rows,
               COUNT(DISTINCT issue_code || ':' || printf('%03d', match_idx)) AS source_matrix_fixture_count,
               SUM(valid_native_quote) AS valid_native_bookmaker_rows,
               COUNT(DISTINCT CASE WHEN valid_native_quote = 1
                     THEN issue_code || ':' || printf('%03d', match_idx) END) AS valid_native_fixture_count
        FROM eligible_quotes
        GROUP BY market_type, snapshot_kind
        ORDER BY market_type,
                 CASE snapshot_kind WHEN 'initial' THEN 1 WHEN '10h' THEN 2 ELSE 3 END
        """,
        con,
    )


def _odds_distribution(bookmakers: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for horizon in HORIZONS:
        group = bookmakers.loc[bookmakers.snapshot_kind.eq(horizon)]
        for outcome, column in OUTCOME_COLUMNS.items():
            count = int(group["valid_bookmaker_rows"].sum())
            total = float(group[f"{column}_sum"].sum())
            square_total = float(group[f"{column}_sq_sum"].sum())
            mean = total / count if count else np.nan
            variance = max(square_total / count - mean * mean, 0.0) if count else np.nan
            rows.append(
                {
                    "snapshot_kind": horizon,
                    "outcome_code": outcome,
                    "valid_bookmaker_rows": count,
                    "mean_decimal_odds": mean,
                    "std_decimal_odds": float(np.sqrt(variance)),
                    "min_decimal_odds": float(group[f"{column}_min"].min()) if count else np.nan,
                    "max_decimal_odds": float(group[f"{column}_max"].max()) if count else np.nan,
                    "distribution_grade": "FULL_VALID_ROWS_MOMENTS_NO_QUANTILES",
                }
            )
    return pd.DataFrame(rows)


def build_profiles(workbook: Path, package: Path) -> dict[str, pd.DataFrame | dict[str, object]]:
    """Compute the complete contract profiling surface from immutable inputs."""
    probabilities = _read_parts(package, "probabilities")
    trace = _read_parts(package, "source_trace")
    translations = _read_parts(package, "translation_readiness")
    with _connect(workbook) as con:
        fixture_meta = _fixture_metadata(con)
        bookmakers = _bookmaker_profile(con)
        auxiliary = _auxiliary_market_support(con)

    fixture_meta["kickoff_year"] = pd.to_datetime(
        fixture_meta["kickoff_ts"], errors="coerce"
    ).dt.year.astype("Int64")
    fixture_meta.loc[~fixture_meta.kickoff_year.between(2014, 2025), "kickoff_year"] = pd.NA
    fixture_meta["year"] = fixture_meta.kickoff_year.astype("string").fillna("UNKNOWN")

    fixture_groups = probabilities[
        ["canonical_fixture_key", "issue_code", "match_idx", "snapshot_kind"]
    ].drop_duplicates()
    fixture_groups = fixture_groups.merge(
        fixture_meta[["issue_code", "match_idx", "year"]],
        on=["issue_code", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    fixture_groups["year"] = fixture_groups["year"].fillna("UNKNOWN")

    issue_coverage = (
        fixture_groups.groupby(["year", "issue_code", "snapshot_kind"], dropna=False)
        .agg(matched_fixture_count=("canonical_fixture_key", "nunique"))
        .reset_index()
        .sort_values(["year", "issue_code", "snapshot_kind"])
    )
    year_coverage = (
        fixture_groups.groupby(["year", "snapshot_kind"], dropna=False)
        .agg(
            issue_count=("issue_code", "nunique"),
            matched_fixture_count=("canonical_fixture_key", "nunique"),
        )
        .reset_index()
    )

    valid_coverage = probabilities.groupby("snapshot_kind").agg(
        matched_fixture_count=("canonical_fixture_key", "nunique"),
        probability_rows=("outcome_code", "size"),
        available_books_median=("n_available_books", "median"),
        available_books_p05=("n_available_books", lambda values: values.quantile(0.05)),
        available_books_p95=("n_available_books", lambda values: values.quantile(0.95)),
    )
    source_matrix_coverage = trace.groupby("snapshot_kind")["canonical_fixture_key"].nunique()
    eligible_count = int(len(fixture_meta))
    horizon_coverage = valid_coverage.join(
        source_matrix_coverage.rename("source_matrix_fixture_count")
    ).reset_index()
    horizon_coverage["eligible_fixture_count"] = eligible_count
    horizon_coverage["source_matrix_row_rate"] = (
        horizon_coverage.source_matrix_fixture_count / eligible_count
    )
    horizon_coverage["valid_proxy_match_rate"] = horizon_coverage.matched_fixture_count / eligible_count
    horizon_order = pd.Categorical(horizon_coverage.snapshot_kind, HORIZONS, ordered=True)
    horizon_coverage = horizon_coverage.assign(_order=horizon_order).sort_values("_order").drop(columns="_order")

    missingness = (
        bookmakers.groupby("snapshot_kind", sort=False)
        .agg(
            raw_bookmaker_rows=("raw_bookmaker_rows", "sum"),
            valid_bookmaker_rows=("valid_bookmaker_rows", "sum"),
            invalid_bookmaker_rows=("invalid_bookmaker_rows", "sum"),
            v1_missing=("v1_missing", "sum"),
            v2_missing=("v2_missing", "sum"),
            v3_missing=("v3_missing", "sum"),
        )
        .reset_index()
    )
    missingness["invalid_triplet_rate"] = (
        missingness.invalid_bookmaker_rows / missingness.raw_bookmaker_rows
    )
    missingness["missing_cell_rate"] = (
        missingness[["v1_missing", "v2_missing", "v3_missing"]].sum(axis=1)
        / (3 * missingness.raw_bookmaker_rows)
    )

    probability_distribution = (
        probabilities.groupby(["snapshot_kind", "outcome_code"])["probability"]
        .agg(
            count="size",
            mean="mean",
            std="std",
            minimum="min",
            p05=lambda values: values.quantile(0.05),
            p25=lambda values: values.quantile(0.25),
            median="median",
            p75=lambda values: values.quantile(0.75),
            p95=lambda values: values.quantile(0.95),
            maximum="max",
        )
        .reset_index()
    )

    line_availability = (
        translations.groupby(["snapshot_kind", "translation_status"])
        .size()
        .rename("fixture_horizon_count")
        .reset_index()
    )
    line_availability["within_horizon_rate"] = line_availability.fixture_horizon_count / line_availability.groupby(
        "snapshot_kind"
    ).fixture_horizon_count.transform("sum")
    line_provenance = (
        translations.assign(
            handicap_norm_source=translations.handicap_norm_source.fillna("UNKNOWN").replace("", "UNKNOWN")
        )
        .groupby(["snapshot_kind", "handicap_norm_source"])
        .size()
        .rename("fixture_horizon_count")
        .reset_index()
    )

    summary = {
        "eligible_unique_issue_slots": eligible_count,
        "matched_proxy_issue_slots": int(probabilities.canonical_fixture_key.nunique()),
        "matched_issue_count": int(probabilities.issue_code.nunique()),
        "bookmaker_count": int(bookmakers.bookmaker_id.nunique()),
        "calendar_year_min": int(fixture_meta.kickoff_year.min()),
        "calendar_year_max": int(fixture_meta.kickoff_year.max()),
        "unknown_year_fixture_count": int(fixture_meta.kickoff_year.isna().sum()),
    }
    auxiliary["eligible_fixture_count"] = eligible_count
    auxiliary["valid_native_fixture_rate"] = auxiliary.valid_native_fixture_count / eligible_count
    auxiliary["market_semantics"] = auxiliary.market_type.map(
        {
            "asian_handicap": "TWO_SIDED_HK_ODDS_PLUS_PROVIDER_LINE",
            "over_under": "TWO_SIDED_HK_ODDS_PLUS_TOTAL_LINE",
        }
    )
    auxiliary["handoff_decision"] = "PROFILED_NATIVE_AUXILIARY_NOT_MAPPED_TO_BJ_3WAY"
    return {
        "summary": summary,
        "horizon_coverage": horizon_coverage,
        "year_coverage": year_coverage,
        "issue_coverage": issue_coverage,
        "bookmaker_coverage": bookmakers,
        "missingness": missingness,
        "odds_distribution": _odds_distribution(bookmakers),
        "probability_distribution": probability_distribution,
        "line_availability": line_availability,
        "line_provenance": line_provenance,
        "auxiliary_market_support": auxiliary,
    }
