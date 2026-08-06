"""Deterministic package builder for BJ-UNIFIED-TENSOR-DATA-001 (#203)."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .contract import (
    CONTRACT_VERSION,
    DATABASE_SHA256,
    FEATURE_NAMES,
    FEATURE_SPECS,
    HELDOUT_ISSUES,
    HELDOUT_2026_ISSUES,
    HELDOUT_POLICY,
    OUTCOME_ORDER,
    SOURCE_TIMEZONE,
    cell_join_key,
    forbidden_inference_names,
)
from .inference import load_issue_tensors
from .settlement_labels import (
    LABEL_COLUMNS,
    bind_development_labels,
    load_development_labels,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE_190 = ROOT / "results/bj190_gate_a_preoutcome_v3r1"
SOURCE_90 = ROOT / "results/bj90_downstream_safe_projection_v1r1"
ESTIMATOR = SOURCE_190 / "estimator_match_freeze.csv.gz"
ISSUE_CENSUS = SOURCE_190 / "issue_census.csv"
PREDICTED_SP = SOURCE_90 / "oos_prediction_vectors.csv.gz"

EXPECTED_MATCH_ROWS = 110_906
EXPECTED_ESTIMATOR_ROWS = 101_970
EXPECTED_EXTENSION_ROWS = 275
EXPECTED_HELDOUT_EXTENSION_ROWS = 8_661
EXPECTED_HISTORICAL_HELDOUT_ROWS = 5_608
EXPECTED_LIVE_HELDOUT_ROWS = 3_053
EXPECTED_BASE_ISSUES = 344
EXPECTED_ISSUES = 394
EXPECTED_HELDOUT_ISSUES = 52
EXPECTED_IDENTITY_EXTENSION_SHA256 = (
    "0f45f442e60c4dd35950053ef7fb76b519352ef2123db4d7a54a0277fcc5caa0"
)
EXPECTED_HELDOUT_IDENTITY_EXTENSION_SHA256 = (
    "af628c9a2974e31f59b64b17dccad4546f1400844916ae21315c1eab469c3fc1"
)
SUPERSEDED_V1_HEAD = "38dc5ae1223a96cf361db851215143bd73afb05d"
SUPERSEDED_V1_MANIFEST_SHA256 = (
    "48011ec58013cc8ed8c8e46e6e89c4844c104937e6c01787817b64b246798510"
)
SUPERSEDED_V1_SHA256SUMS_SHA256 = (
    "dfb6ffeb977423f7e71064771949361c0105ceaa124f2ca9447dafaa0859ffbc"
)
EXPECTED_SOURCE_HASHES = {
    "bj190_estimator_match_freeze": (
        "fd0ee672ab8a98b64cf4e84f9352cd089a68fefe34130b19b46f970595953bb1"
    ),
    "bj190_estimator_manifest": (
        "490579f7813d260d11965377462f7aa3b20161dd4672e2b42b600b493d24f1bc"
    ),
    "bj190_issue_census": (
        "5054b3a3d0aa695f5f9ef51e79632e4a89757e4b11b7f965ced874c43ef8fc93"
    ),
    "bj90_predicted_sp": (
        "2375e5570a9fb964f1beb5f4a20e5019755f62213ebde1463a609d23d1e2807b"
    ),
    "bj90_manifest": (
        "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2"
    ),
    "database": DATABASE_SHA256,
}


class TensorBuildError(RuntimeError):
    """Raised when source or generated package bytes violate the contract."""


def digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value), encoding="utf-8", newline="\n")


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.12g")


def _feature_coverage(identity: pd.DataFrame, masks: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for split in ("development", "heldout"):
        selected = identity["split"].eq(split).to_numpy()
        for feature in FEATURE_NAMES:
            present = int(masks.loc[selected, feature].sum())
            total = int(selected.sum())
            rows.append(
                {
                    "split": split,
                    "feature": feature,
                    "present_cells": present,
                    "total_cells": total,
                    "coverage_rate": present / total if total else np.nan,
                }
            )
    coverage = pd.DataFrame(rows)
    coverage["coverage_rate"] = coverage["coverage_rate"].map(
        lambda value: float(f"{value:.12g}")
    )
    return coverage


def _assert_feature_coverage(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    columns = [
        "split",
        "feature",
        "present_cells",
        "total_cells",
        "coverage_rate",
    ]
    if list(actual.columns) != columns or len(actual) != len(expected):
        raise TensorBuildError("feature coverage does not match inference masks")
    if not actual.loc[:, ["split", "feature"]].astype(str).equals(
        expected.loc[:, ["split", "feature"]].astype(str)
    ):
        raise TensorBuildError("feature coverage does not match inference masks")
    for column in ("present_cells", "total_cells"):
        if not np.array_equal(
            pd.to_numeric(actual[column], errors="coerce").to_numpy(),
            expected[column].to_numpy(),
        ):
            raise TensorBuildError("feature coverage does not match inference masks")
    if not bool(
        np.isclose(
            pd.to_numeric(actual["coverage_rate"], errors="coerce").to_numpy(),
            expected["coverage_rate"].to_numpy(),
            rtol=0.0,
            atol=0.0,
            equal_nan=True,
        ).all()
    ):
        raise TensorBuildError("feature coverage does not match inference masks")


def write_parquet(path: Path, frame: pd.DataFrame) -> None:
    """Write stable package-first columnar bytes with the pinned PyArrow stack."""

    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, preserve_index=False)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=9,
        use_dictionary=True,
        write_statistics=True,
        version="2.6",
        data_page_version="2.0",
        row_group_size=65_536,
    )


def _verified_source(path: Path) -> pd.DataFrame:
    manifest_path = path.parent / "SHA256SUMS.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorBuildError(f"invalid source manifest: {manifest_path}") from exc
    if manifest.get(path.name) != digest(path):
        raise TensorBuildError(f"source payload hash mismatch: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _hkt_to_utc(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, format="mixed", errors="raise")
    localized = parsed.dt.tz_localize(
        SOURCE_TIMEZONE, ambiguous="raise", nonexistent="raise"
    ).dt.tz_convert("UTC")
    return localized.dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _numeric(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values.replace("", np.nan), errors="coerce")


def _sqlite_ro(database: Path) -> sqlite3.Connection:
    database_uri = f"{database.resolve().as_uri()}?mode=ro&immutable=1"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _database_guard(database: Path) -> None:
    if not database.is_file():
        raise TensorBuildError(f"source database is unavailable: {database}")
    actual = digest(database)
    if actual != DATABASE_SHA256:
        raise TensorBuildError(
            f"source database identity mismatch: expected {DATABASE_SHA256}, got {actual}"
        )


def _source_hashes() -> dict[str, str]:
    actual = {
        "bj190_estimator_match_freeze": digest(ESTIMATOR),
        "bj190_estimator_manifest": digest(SOURCE_190 / "SHA256SUMS.json"),
        "bj190_issue_census": digest(ISSUE_CENSUS),
        "bj90_predicted_sp": digest(PREDICTED_SP),
        "bj90_manifest": digest(SOURCE_90 / "SHA256SUMS.json"),
        "database": DATABASE_SHA256,
    }
    if actual != EXPECTED_SOURCE_HASHES:
        raise TensorBuildError("frozen upstream source identity drift")
    return actual


def unavailable_reason(
    home_team_id: object,
    away_team_id: object,
    native_handicap_line: object,
    euro_odds: Iterable[object],
) -> str:
    """Classify causal source gaps without treating NaN as a usable value."""

    reasons: list[str] = []
    if (
        pd.isna(home_team_id)
        or home_team_id == ""
        or pd.isna(away_team_id)
        or away_team_id == ""
    ):
        reasons.append("MISSING_TEAM_IDENTITY")
    if any(pd.isna(value) or value == "" or float(value) <= 1 for value in euro_odds):
        reasons.append("MISSING_1H_EURO")
    if pd.isna(native_handicap_line) or native_handicap_line == "":
        reasons.append("MISSING_NATIVE_LINE")
    return ";".join(reasons)


def extract_unavailable_identity(
    database: Path, issue_census: pd.DataFrame
) -> pd.DataFrame:
    """Retain every row excluded from #190's executable estimator universe."""

    _database_guard(database)
    issues = issue_census["issue"].astype(str).tolist()
    placeholders = ",".join("?" for _ in issues)
    query = f"""
        SELECT CAST(m.match_id AS TEXT) AS match_id,
               CAST(m.issue AS TEXT) AS issue,
               CAST(m.match_idx AS INTEGER) AS match_idx,
               m.kickoff_ts,
               m.league,
               CAST(m.home_team_id AS TEXT) AS home_team_id,
               CAST(m.away_team_id AS TEXT) AS away_team_id,
               m.handicap_line_norm AS native_handicap_line,
               e1.v1_avg AS euro_1h_odds3,
               e1.v2_avg AS euro_1h_odds1,
               e1.v3_avg AS euro_1h_odds0
          FROM matches m
          LEFT JOIN market_consensus e1
            ON e1.match_id=m.match_id
           AND e1.market='euro_1x2'
           AND e1.snapshot='1h'
         WHERE m.issue IN ({placeholders})
           AND (
                m.kickoff_ts IS NULL
             OR m.home_team_id IS NULL
             OR m.away_team_id IS NULL
             OR m.handicap_line_norm IS NULL
             OR e1.match_id IS NULL
             OR COALESCE(e1.n_complete, 0) <= 0
             OR COALESCE(e1.v1_avg, 0) <= 1
             OR COALESCE(e1.v2_avg, 0) <= 1
             OR COALESCE(e1.v3_avg, 0) <= 1
           )
         ORDER BY CAST(m.issue AS INTEGER), m.match_idx, m.match_id
    """
    if forbidden_inference_names(
        (
            "match_id", "issue", "match_idx", "kickoff_ts", "league",
            "home_team_id", "away_team_id", "native_handicap_line",
            "euro_1h_odds3",
            "euro_1h_odds1", "euro_1h_odds0",
        )
    ):
        raise TensorBuildError("internal inference whitelist crosses outcome boundary")
    with _sqlite_ro(database) as connection:
        rows = [dict(row) for row in connection.execute(query, issues)]
    extension = pd.DataFrame(rows)
    if len(extension) != EXPECTED_EXTENSION_ROWS:
        raise TensorBuildError(
            f"unavailable identity denominator drift: {len(extension)}"
        )
    metadata = issue_census.set_index("issue")
    extension["issue_instance"] = extension["issue"].map(
        metadata["issue_instance"]
    )
    extension["year"] = extension["issue"].map(metadata["year"])
    extension["fold"] = extension["issue"].map(metadata["fold"])
    extension["feature_cutoff_ts"] = extension["issue"].map(
        metadata["feature_cutoff_ts"]
    )
    extension["extension_status"] = [
        unavailable_reason(
            row.home_team_id,
            row.away_team_id,
            row.native_handicap_line,
            (row.euro_1h_odds3, row.euro_1h_odds1, row.euro_1h_odds0),
        )
        for row in extension.itertuples(index=False)
    ]
    columns = [
        "match_id", "issue", "issue_instance", "year", "fold", "match_idx",
        "kickoff_ts", "feature_cutoff_ts", "league", "home_team_id",
        "away_team_id", "native_handicap_line", "euro_1h_odds3",
        "euro_1h_odds1", "euro_1h_odds0", "extension_status",
    ]
    return extension.loc[:, columns]


def _sqlite_snapshot_ro(database: Path) -> sqlite3.Connection:
    """Open a WAL-aware read transaction for a mutable source database."""

    if not database.is_file():
        raise TensorBuildError(f"source database is unavailable: {database}")
    connection = sqlite3.connect(
        f"{database.resolve().as_uri()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def extract_heldout_identity(
    historical_database: Path, live_database: Path
) -> pd.DataFrame:
    """Freeze the complete local post-boundary sequence without target fields.

    The historical 2026 workbook has no trustworthy observation timestamp, so
    it contributes retrospective identity only.  The live database contributes
    its per-row ``created_ts`` observation time.  Neither source contributes a
    market-price or settlement feature through this adapter.
    """

    historical_issues = HELDOUT_2026_ISSUES[:33]
    live_issues = HELDOUT_2026_ISSUES[33:]
    historical_placeholders = ",".join("?" for _ in historical_issues)
    live_placeholders = ",".join("?" for _ in live_issues)
    historical_query = f"""
        SELECT CAST(match_id AS TEXT) AS match_id,
               CAST(issue AS TEXT) AS issue,
               CAST(match_idx AS INTEGER) AS match_idx,
               kickoff_ts,
               league,
               CAST(home_team_id AS TEXT) AS home_team_id,
               CAST(away_team_id AS TEXT) AS away_team_id
          FROM matches
         WHERE issue IN ({historical_placeholders})
         ORDER BY CAST(issue AS INTEGER), match_idx, match_id
    """
    live_query = f"""
        SELECT CAST(match_id AS TEXT) AS match_id,
               CAST(issue AS TEXT) AS issue,
               CAST(match_idx AS INTEGER) AS match_idx,
               kickoff_ts,
               league,
               home,
               away,
               created_ts
          FROM matches
         WHERE issue IN ({live_placeholders})
         ORDER BY CAST(issue AS INTEGER), match_idx, match_id
    """
    with _sqlite_ro(historical_database) as connection:
        historical_inventory = tuple(
            str(row["issue"])
            for row in connection.execute(
                """
                SELECT DISTINCT CAST(issue AS TEXT) AS issue
                  FROM matches
                 WHERE CAST(issue AS TEXT) LIKE '26%'
                   AND CAST(issue AS INTEGER) <= 26051
                 ORDER BY CAST(issue AS INTEGER)
                """
            )
        )
        historical = pd.DataFrame(
            [dict(row) for row in connection.execute(
                historical_query, historical_issues
            )]
        )
    with _sqlite_snapshot_ro(live_database) as connection:
        live_inventory = tuple(
            str(row["issue"])
            for row in connection.execute(
                """
                SELECT DISTINCT CAST(issue AS TEXT) AS issue
                  FROM matches
                 WHERE CAST(issue AS INTEGER) BETWEEN 26051 AND 26069
                 ORDER BY CAST(issue AS INTEGER)
                """
            )
        )
        live = pd.DataFrame(
            [dict(row) for row in connection.execute(live_query, live_issues)]
        )
    if historical_inventory != HELDOUT_2026_ISSUES[:34]:
        raise TensorBuildError("historical held-out source inventory drift")
    if live_inventory != live_issues:
        raise TensorBuildError("live held-out source inventory drift")
    if len(historical) != EXPECTED_HISTORICAL_HELDOUT_ROWS:
        raise TensorBuildError("historical held-out identity denominator drift")
    if len(live) != EXPECTED_LIVE_HELDOUT_ROWS:
        raise TensorBuildError("live held-out identity denominator drift")
    if tuple(historical["issue"].drop_duplicates()) != historical_issues:
        raise TensorBuildError("historical held-out issue sequence drift")
    if tuple(live["issue"].drop_duplicates()) != live_issues:
        raise TensorBuildError("live held-out issue sequence drift")
    if historical["match_id"].duplicated().any() or live["match_id"].duplicated().any():
        raise TensorBuildError("held-out match identity is not unique")
    required_historical = (
        historical["kickoff_ts"].astype(str).ne("")
        & historical["match_idx"].notna()
    )
    required_live = (
        live["kickoff_ts"].astype(str).ne("")
        & live["created_ts"].astype(str).ne("")
        & live["match_idx"].notna()
    )
    if not bool(required_historical.all()) or not bool(required_live.all()):
        raise TensorBuildError("held-out identity lacks required timestamp/order")

    historical_cutoffs = historical.groupby("issue", sort=False)[
        "kickoff_ts"
    ].transform("min")
    historical = historical.assign(
        issue_instance=historical["issue"] + "@CANONICAL_2026",
        year="2026",
        fold="OOS_2026",
        feature_cutoff_ts=historical_cutoffs,
        native_handicap_line="",
        extension_status="HELDOUT_RETROSPECTIVE_IDENTITY_ONLY",
        identity_source="modeling_plus_2026.matches",
        identity_observed_ts_utc="",
        identity_timing_status="RETROSPECTIVE_IDENTITY_ONLY",
    )
    live_created_utc = pd.to_datetime(
        live["created_ts"], utc=True, errors="raise"
    )
    live_created_hkt = live_created_utc.dt.tz_convert(SOURCE_TIMEZONE)
    live["identity_observed_ts_utc"] = live_created_utc.dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    live["feature_cutoff_ts"] = (
        live_created_hkt.groupby(live["issue"], sort=False)
        .transform("max")
        .dt.tz_localize(None)
        .dt.strftime("%Y-%m-%d %H:%M:%S")
    )
    live = live.assign(
        issue_instance=live["issue"] + "@CANONICAL_2026",
        year="2026",
        fold="OOS_2026",
        home_team_id="NAME:" + live["home"].fillna("").astype(str).str.strip(),
        away_team_id="NAME:" + live["away"].fillna("").astype(str).str.strip(),
        native_handicap_line="",
        extension_status="HELDOUT_TIMESTAMPED_IDENTITY_ONLY",
        identity_source="beidan_live.matches",
        identity_timing_status="TIMESTAMPED_IDENTITY_ONLY",
    )
    columns = [
        "match_id", "issue", "issue_instance", "year", "fold", "match_idx",
        "kickoff_ts", "feature_cutoff_ts", "league", "home_team_id",
        "away_team_id", "native_handicap_line", "extension_status",
        "identity_source", "identity_observed_ts_utc", "identity_timing_status",
    ]
    extension = pd.concat(
        [historical.loc[:, columns], live.loc[:, columns]], ignore_index=True
    )
    if len(extension) != EXPECTED_HELDOUT_EXTENSION_ROWS:
        raise TensorBuildError("held-out identity extension denominator drift")
    if forbidden_inference_names(extension.columns):
        raise TensorBuildError("held-out identity whitelist crosses target boundary")
    return extension


def _load_inputs(
    database: Path | None,
    identity_extension: Path | None,
    heldout_historical_database: Path | None = None,
    heldout_live_database: Path | None = None,
    heldout_identity_extension: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    estimator = _verified_source(ESTIMATOR)
    issue_census = _verified_source(ISSUE_CENSUS)
    predictions = _verified_source(PREDICTED_SP)
    if len(estimator) != EXPECTED_ESTIMATOR_ROWS:
        raise TensorBuildError("#190 estimator denominator drift")
    if len(issue_census) != EXPECTED_BASE_ISSUES:
        raise TensorBuildError("#190 issue census denominator drift")
    if database is not None:
        extension = extract_unavailable_identity(database, issue_census)
    elif identity_extension is not None:
        if digest(identity_extension) != EXPECTED_IDENTITY_EXTENSION_SHA256:
            raise TensorBuildError("frozen identity extension hash mismatch")
        extension = pd.read_parquet(identity_extension)
    else:
        raise TensorBuildError("database or frozen identity extension is required")
    if len(extension) != EXPECTED_EXTENSION_ROWS:
        raise TensorBuildError("identity extension denominator drift")
    if heldout_historical_database is not None and heldout_live_database is not None:
        heldout_extension = extract_heldout_identity(
            heldout_historical_database, heldout_live_database
        )
    elif heldout_identity_extension is not None:
        if digest(heldout_identity_extension) != (
            EXPECTED_HELDOUT_IDENTITY_EXTENSION_SHA256
        ):
            raise TensorBuildError("frozen held-out identity extension hash mismatch")
        heldout_extension = pd.read_parquet(heldout_identity_extension)
    else:
        raise TensorBuildError(
            "held-out source databases or frozen held-out identity extension are required"
        )
    if len(heldout_extension) != EXPECTED_HELDOUT_EXTENSION_ROWS:
        raise TensorBuildError("held-out identity extension denominator drift")
    return estimator, issue_census, predictions, extension, heldout_extension


def _prepare_matches(
    estimator: pd.DataFrame,
    issue_census: pd.DataFrame,
    predictions: pd.DataFrame,
    extension: pd.DataFrame,
    heldout_extension: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if forbidden_inference_names(estimator.columns):
        raise TensorBuildError("#190 inference source contains forbidden fields")
    estimator["extension_status"] = ""
    estimator["identity_source"] = "bj190.frozen_match_identity"
    estimator["identity_observed_ts_utc"] = ""
    estimator["identity_timing_status"] = "CUTOFF_BOUND_IDENTITY"
    extension["identity_source"] = "canonical_database.unavailable_identity"
    extension["identity_observed_ts_utc"] = ""
    extension["identity_timing_status"] = "CUTOFF_BOUND_IDENTITY"
    common = set(estimator.columns)
    for column in common.difference(extension.columns):
        extension[column] = ""
    for column in common.difference(heldout_extension.columns):
        heldout_extension[column] = ""
    matches = pd.concat(
        [
            estimator,
            extension.loc[:, estimator.columns],
            heldout_extension.loc[:, estimator.columns],
        ],
        ignore_index=True,
    )
    for column in (
        "euro_1h_odds3", "euro_1h_odds1", "euro_1h_odds0",
    ):
        extension_values = extension.set_index("match_id")[column]
        target = matches["match_id"].astype(str).isin(extension_values.index)
        matches.loc[target, column] = matches.loc[target, "match_id"].map(
            extension_values
        )
    if len(matches) != EXPECTED_MATCH_ROWS or not matches["match_id"].is_unique:
        raise TensorBuildError("complete match identity denominator drift")
    for column in ("league", "home_team_id", "away_team_id"):
        matches[column] = matches[column].fillna("").astype(str).replace("None", "")
    issue_meta = issue_census.set_index("issue")
    matches["source_b0_status"] = matches["issue"].map(
        issue_meta["source_b0_status"]
    ).fillna("HELDOUT_IDENTITY_ONLY")
    predictions = predictions.rename(
        columns={
            "deployed_sp_3": "predicted_sp3",
            "deployed_sp_1": "predicted_sp1",
            "deployed_sp_0": "predicted_sp0",
        }
    )
    prediction_cols = ["match_id", "predicted_sp3", "predicted_sp1", "predicted_sp0"]
    if predictions["match_id"].duplicated().any():
        raise TensorBuildError("#90 predicted-SP identity is not unique")
    matches = matches.merge(
        predictions.loc[:, prediction_cols], on="match_id", how="left",
        validate="one_to_one", sort=False,
    )
    matches["kickoff_ts_utc"] = _hkt_to_utc(matches["kickoff_ts"])
    matches["feature_cutoff_ts_utc"] = _hkt_to_utc(matches["feature_cutoff_ts"])
    matches["split"] = np.where(
        matches["issue"].astype(str).isin(HELDOUT_ISSUES), "heldout", "development"
    )
    issue_order = (
        matches[["issue", "feature_cutoff_ts_utc"]]
        .drop_duplicates()
    )
    issue_order["issue_numeric"] = pd.to_numeric(issue_order["issue"], errors="raise")
    issue_order = issue_order.sort_values(
        ["feature_cutoff_ts_utc", "issue_numeric"], kind="mergesort"
    ).drop(columns="issue_numeric").reset_index(drop=True)
    issue_order["issue_order"] = np.arange(len(issue_order), dtype=np.int32)
    matches = matches.merge(issue_order, on=["issue", "feature_cutoff_ts_utc"])
    matches["match_idx"] = pd.to_numeric(matches["match_idx"], errors="raise").astype(int)
    matches["match_id_sort"] = matches["match_id"].astype(str)
    matches = matches.sort_values(
        ["issue_order", "match_idx", "match_id_sort"], kind="mergesort"
    ).reset_index(drop=True)
    matches["match_order"] = matches.groupby("issue", sort=False).cumcount()
    matches["issue_match_count"] = matches.groupby("issue", sort=False)[
        "match_id"
    ].transform("size")
    if matches.groupby("issue").size().size != EXPECTED_ISSUES:
        raise TensorBuildError("complete issue denominator drift")
    league_values = sorted(value for value in matches["league"].unique() if value)
    team_values = sorted(
        {
            value
            for column in ("home_team_id", "away_team_id")
            for value in matches[column].astype(str)
            if value
        },
        key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value),
    )
    league_dict = pd.DataFrame(
        {"league": league_values, "league_index": np.arange(len(league_values))}
    )
    team_dict = pd.DataFrame(
        {"team_id": team_values, "team_index": np.arange(len(team_values))}
    )
    breadth_values = sorted(
        value
        for value in matches["market_signature_breadth"].astype(str).unique()
        if value not in {"", "MISSING"}
    )
    breadth_dict = pd.DataFrame(
        {
            "market_signature_breadth_bucket": breadth_values,
            "market_signature_breadth_index": np.arange(len(breadth_values)),
        }
    )
    matches["league_index"] = matches["league"].map(
        dict(zip(league_dict["league"], league_dict["league_index"], strict=True))
    )
    team_map = dict(zip(team_dict["team_id"], team_dict["team_index"], strict=True))
    matches["home_team_index"] = matches["home_team_id"].astype(str).map(team_map)
    matches["away_team_index"] = matches["away_team_id"].astype(str).map(team_map)
    matches["market_signature_breadth_index"] = matches[
        "market_signature_breadth"
    ].map(
        dict(
            zip(
                breadth_dict["market_signature_breadth_bucket"],
                breadth_dict["market_signature_breadth_index"],
                strict=True,
            )
        )
    )
    return matches, league_dict, team_dict, breadth_dict


def _cell_tables(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cells = matches.loc[matches.index.repeat(len(OUTCOME_ORDER))].copy().reset_index(
        drop=True
    )
    cells["outcome_code"] = np.tile(OUTCOME_ORDER, len(matches))
    cells["outcome_order"] = np.tile(np.arange(3, dtype=np.int8), len(matches))
    cells["cell_join_key"] = [
        cell_join_key(str(issue), str(match), str(code))
        for issue, match, code in zip(
            cells["issue_instance"], cells["match_id"], cells["outcome_code"],
            strict=True,
        )
    ]
    kickoff = pd.to_datetime(cells["kickoff_ts_utc"], utc=True)
    cutoff = pd.to_datetime(cells["feature_cutoff_ts_utc"], utc=True)
    one_hour_available_ts = kickoff - pd.Timedelta(hours=1)
    predicted_sp_available_ts = kickoff - pd.Timedelta(hours=10)
    one_hour_safe = one_hour_available_ts.le(cutoff)
    predicted_sp_safe = predicted_sp_available_ts.le(cutoff)
    cells["euro_1h_available_ts_utc"] = one_hour_available_ts.dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    cells["predicted_sp_available_ts_utc"] = predicted_sp_available_ts.dt.strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    line_available = _numeric(cells["native_handicap_line"]).notna()
    calibrated_available = pd.Series(False, index=cells.index)
    for code in OUTCOME_ORDER:
        selected = cells["outcome_code"].eq(code)
        calibrated_available.loc[selected] = _numeric(
            cells.loc[selected, f"calibrated_p{code}"]
        ).notna()
    cells["availability_status"] = np.where(
        line_available & calibrated_available & one_hour_safe,
        "AVAILABLE", "UNAVAILABLE",
    )
    missing_reason = cells["extension_status"].replace(
        "", "MISSING_NATIVE_LINE_OR_CALIBRATED_ESTIMATOR"
    )
    cells["unavailable_reason"] = np.where(
        line_available & calibrated_available,
        "",
        missing_reason,
    )
    late = ~one_hour_safe
    cells.loc[late, "unavailable_reason"] = cells.loc[
        late, "unavailable_reason"
    ].map(
        lambda value: ";".join(
            part
            for part in (str(value), "ONE_HOUR_SNAPSHOT_AFTER_ISSUE_CUTOFF")
            if part
        )
    )
    identity_columns = [
        "cell_join_key", "issue", "issue_instance", "year", "fold", "split",
        "issue_order",
        "match_id", "match_idx", "match_order", "outcome_code", "outcome_order",
        "feature_cutoff_ts_utc", "kickoff_ts_utc", "availability_status",
        "unavailable_reason", "source_b0_status", "identity_source",
        "identity_observed_ts_utc", "identity_timing_status",
        "euro_1h_available_ts_utc", "predicted_sp_available_ts_utc",
    ]
    identity = cells.loc[:, identity_columns].reset_index(drop=True)

    values = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    values["outcome_code_numeric"] = cells["outcome_code"].astype(float).to_numpy()
    code_sources = {
        "calibrated_market_probability": "calibrated_p",
        "euro_1h_odds": "euro_1h_odds",
        "fundamental_probability": "fundamental_p",
        "probability_residual": "calibrated_delta_p",
        "probability_residual_z": "calibrated_z",
        "predicted_final_sp": "predicted_sp",
    }
    for feature, prefix in code_sources.items():
        target = np.full(len(cells), np.nan, dtype=np.float64)
        for code in OUTCOME_ORDER:
            selected = cells["outcome_code"].eq(code).to_numpy()
            target[selected] = _numeric(cells.loc[selected, f"{prefix}{code}"]).to_numpy()
        values[feature] = target
    values.loc[
        ~values["predicted_final_sp"].gt(1.0), "predicted_final_sp"
    ] = np.nan
    odds = np.column_stack(
        [
            _numeric(cells[f"euro_1h_odds{code}"]).to_numpy(dtype=np.float64)
            for code in OUTCOME_ORDER
        ]
    )
    valid_odds = np.isfinite(odds).all(axis=1) & (odds > 1).all(axis=1)
    normalized = np.full_like(odds, np.nan)
    inverse = 1.0 / odds[valid_odds]
    normalized[valid_odds] = inverse / inverse.sum(axis=1, keepdims=True)
    devig = normalized[
        np.arange(len(cells)), cells["outcome_order"].to_numpy(dtype=int)
    ]
    values["devig_euro_probability"] = devig
    values["bj_sp_snapshot"] = np.nan
    values["bj_sp_snapshot_age_minutes"] = np.nan
    scalar_sources = {
        "native_handicap_line": "native_handicap_line",
        "line_residual_mu": "line_residual_mu",
        "line_residual_z": "line_residual_z",
        "market_uncertainty": "market_uncertainty_proxy",
        "market_signature_breadth": "market_signature_breadth_index",
    }
    for feature, source in scalar_sources.items():
        values[feature] = _numeric(cells[source]).to_numpy()
    values["market_signature_dispersion"] = cells[
        "market_signature_dispersion"
    ].map({"D_LOW": 0.0, "D_MID": 1.0, "D_HIGH": 2.0}).to_numpy()
    one_hour_features = (
        "calibrated_market_probability", "devig_euro_probability", "euro_1h_odds",
        "probability_residual", "probability_residual_z", "market_uncertainty",
        "market_signature_breadth", "market_signature_dispersion",
    )
    values.loc[~one_hour_safe, one_hour_features] = np.nan
    values.loc[~predicted_sp_safe, "predicted_final_sp"] = np.nan
    values["history_training_rows_log1p"] = np.log1p(
        _numeric(cells["history_training_rows"])
    )
    values["min_history_n_log1p"] = np.log1p(_numeric(cells["min_history_n"]))
    for feature in ("league_index", "home_team_index", "away_team_index"):
        values[feature] = _numeric(cells[feature]).to_numpy()
    kickoff_delay = (kickoff - cutoff).dt.total_seconds() / 3600.0
    values["kickoff_delay_hours"] = kickoff_delay.where(kickoff_delay >= 0)
    denominator = np.maximum(_numeric(cells["issue_match_count"]).to_numpy() - 1, 1)
    values["match_position_fraction"] = (
        _numeric(cells["match_order"]).to_numpy() / denominator
    )
    values["calendar_year"] = _numeric(cells["year"]).to_numpy()
    registry_only = cells["identity_timing_status"].astype(str).isin(
        {"RETROSPECTIVE_IDENTITY_ONLY", "TIMESTAMPED_IDENTITY_ONLY"}
    )
    registry_features = set(FEATURE_NAMES).difference(
        {
            "outcome_code_numeric",
            "kickoff_delay_hours",
            "match_position_fraction",
            "calendar_year",
        }
    )
    values.loc[registry_only, sorted(registry_features)] = np.nan
    values = values.loc[:, ["cell_join_key", *FEATURE_NAMES]]
    for feature in FEATURE_NAMES:
        values[feature] = values[feature].astype(np.float32)
    masks = pd.DataFrame({"cell_join_key": identity["cell_join_key"]})
    for feature in FEATURE_NAMES:
        masks[feature] = np.isfinite(values[feature].to_numpy(dtype=np.float64))
    return identity, values, masks


def _namespace_manifest(namespace: Path, name: str) -> dict[str, Any]:
    files = {
        path.relative_to(namespace).as_posix(): digest(path)
        for path in sorted(namespace.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "namespace": name,
        "files": files,
    }
    write_json(namespace / "MANIFEST.json", manifest)
    return manifest


def _heldout_registry(identity: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for issue in HELDOUT_ISSUES:
        scoped = identity[identity["issue"].astype(str).eq(issue)]
        if scoped.empty:
            raise TensorBuildError(f"held-out identity is absent: {issue}")
        rows.append(
            {
                "issue": issue,
                "issue_instance": scoped.iloc[0]["issue_instance"],
                "feature_cutoff_ts_utc": scoped.iloc[0]["feature_cutoff_ts_utc"],
                "identity_sources": ";".join(
                    sorted(scoped["identity_source"].astype(str).unique())
                ),
                "identity_timing_statuses": ";".join(
                    sorted(scoped["identity_timing_status"].astype(str).unique())
                ),
                "first_identity_observed_ts_utc": min(
                    (
                        value
                        for value in scoped["identity_observed_ts_utc"].astype(str)
                        if value
                    ),
                    default="",
                ),
                "last_identity_observed_ts_utc": max(
                    (
                        value
                        for value in scoped["identity_observed_ts_utc"].astype(str)
                        if value
                    ),
                    default="",
                ),
                "match_count": scoped["match_id"].nunique(),
                "cell_count": len(scoped),
                "ordered_identity_sha256": sha256(
                    "\n".join(scoped["cell_join_key"].astype(str)).encode("utf-8")
                ).hexdigest(),
                "label_status": "ABSENT_BY_CONTRACT",
            }
        )
    return pd.DataFrame(rows)


def build_inference(
    output: Path,
    *,
    database: Path | None = None,
    identity_extension: Path | None = None,
    heldout_historical_database: Path | None = None,
    heldout_live_database: Path | None = None,
    heldout_identity_extension: Path | None = None,
) -> dict[str, Any]:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise TensorBuildError(f"output is not empty: {output}")
    inference = output / "inference"
    sources = output / "sources"
    audit = output / "audit"
    for directory in (inference, sources, audit):
        directory.mkdir(parents=True, exist_ok=True)
    estimator, issue_census, predictions, extension, heldout_extension = _load_inputs(
        database,
        identity_extension,
        heldout_historical_database,
        heldout_live_database,
        heldout_identity_extension,
    )
    write_parquet(sources / "unavailable_match_identity.parquet", extension)
    write_parquet(sources / "heldout_match_identity.parquet", heldout_extension)
    matches, league_dict, team_dict, breadth_dict = _prepare_matches(
        estimator, issue_census, predictions, extension, heldout_extension
    )
    identity, values, masks = _cell_tables(matches)
    forbidden = forbidden_inference_names(
        list(identity.columns) + list(values.columns) + list(masks.columns)
    )
    if forbidden:
        raise TensorBuildError(f"generated inference fields are forbidden: {forbidden}")
    write_parquet(inference / "cell_identity.parquet", identity)
    write_parquet(inference / "feature_values.parquet", values)
    write_parquet(inference / "feature_masks.parquet", masks)
    issue_offsets = (
        identity.groupby(
            ["issue", "issue_instance", "split", "issue_order", "feature_cutoff_ts_utc"],
            sort=False,
        )
        .agg(
            cell_start=("cell_join_key", lambda s: int(s.index.min())),
            cell_count=("cell_join_key", "size"),
            match_count=("match_id", "nunique"),
        )
        .reset_index()
    )
    write_parquet(inference / "issue_offsets.parquet", issue_offsets)
    write_parquet(inference / "league_dictionary.parquet", league_dict)
    write_parquet(inference / "team_dictionary.parquet", team_dict)
    write_parquet(inference / "market_breadth_dictionary.parquet", breadth_dict)
    feature_dictionary = pd.DataFrame(
        [
            {
                "feature_order": index,
                "feature": spec.name,
                "dtype": spec.dtype,
                "minimum": spec.minimum,
                "maximum": spec.maximum,
                "source": spec.source,
                "timing_rule": spec.timing_rule,
                "admissible_use": spec.admissible_use,
                "missingness": spec.missingness,
            }
            for index, spec in enumerate(FEATURE_SPECS)
        ]
    )
    write_csv(output / "feature_dictionary.csv", feature_dictionary)
    write_csv(audit / "feature_coverage.csv", _feature_coverage(identity, masks))
    write_csv(
        audit / "year_distribution.csv",
        matches.groupby(["split", "year"], sort=True).size().rename("match_rows").reset_index(),
    )
    write_csv(
        audit / "league_distribution.csv",
        matches.groupby(["split", "league"], sort=True).size().rename("match_rows").reset_index(),
    )
    lines = matches["native_handicap_line"].replace("", "MISSING")
    line_distribution = (
        pd.DataFrame({"split": matches["split"], "native_line": lines})
        .groupby(["split", "native_line"], sort=True)
        .size().rename("match_rows").reset_index()
    )
    write_csv(audit / "line_distribution.csv", line_distribution)
    leakage = feature_dictionary.loc[
        :, ["feature", "source", "timing_rule", "admissible_use"]
    ].copy()
    leakage["forbidden_name_check"] = "PASS"
    one_hour_late = pd.to_datetime(
        identity["euro_1h_available_ts_utc"], utc=True
    ).gt(pd.to_datetime(identity["feature_cutoff_ts_utc"], utc=True))
    ten_hour_late = pd.to_datetime(
        identity["predicted_sp_available_ts_utc"], utc=True
    ).gt(pd.to_datetime(identity["feature_cutoff_ts_utc"], utc=True))
    one_hour_features = {
        "calibrated_market_probability", "devig_euro_probability", "euro_1h_odds",
        "probability_residual", "probability_residual_z", "market_uncertainty",
        "market_signature_breadth", "market_signature_dispersion",
    }
    leakage["source_after_cutoff_cells"] = [
        int(one_hour_late.sum())
        if feature in one_hour_features
        else int(ten_hour_late.sum())
        if feature == "predicted_final_sp"
        else 0
        for feature in leakage["feature"]
    ]
    leakage["unmasked_after_cutoff_cells"] = [
        int(masks.loc[one_hour_late, feature].sum())
        if feature in one_hour_features
        else int(masks.loc[ten_hour_late, feature].sum())
        if feature == "predicted_final_sp"
        else 0
        for feature in leakage["feature"]
    ]
    leakage["cutoff_check"] = np.where(
        leakage["unmasked_after_cutoff_cells"].eq(0), "PASS", "FAIL"
    )
    if not leakage["cutoff_check"].eq("PASS").all():
        raise TensorBuildError("generated feature crosses issue cutoff")
    write_csv(audit / "leakage_audit.csv", leakage)
    write_csv(audit / "heldout_registry.csv", _heldout_registry(identity))
    source_hashes = _source_hashes()
    source_hashes["causal_identity_extension"] = digest(
        sources / "unavailable_match_identity.parquet"
    )
    source_hashes["heldout_identity_extension"] = digest(
        sources / "heldout_match_identity.parquet"
    )
    write_csv(
        audit / "source_census.csv",
        pd.DataFrame(
            [
                {"source": key, "sha256": value}
                for key, value in sorted(source_hashes.items())
            ]
        ),
    )
    write_json(
        output / "schema.json",
        {
            "contract_version": CONTRACT_VERSION,
            "representation": "ragged columnar; loader materializes X_i[J_i,3,F]",
            "outcome_order": list(OUTCOME_ORDER),
            "feature_order": list(FEATURE_NAMES),
            "value_dtype": "float32",
            "mask_dtype": "bool",
            "masked_value_on_load": 0.0,
            "source_timezone": SOURCE_TIMEZONE,
            "stored_timezone": "UTC",
            "deterministic_order": [
                "feature_cutoff_ts_utc", "numeric issue", "match_idx", "match_id",
                "outcome_order 3,1,0", "feature_order",
            ],
            "join_key": "sha256(contract|issue_instance|match_id|outcome_code)",
            "snapshot_cutoffs": {
                "one_hour_market": "kickoff_ts_utc - 1h",
                "predicted_sp_inputs": "kickoff_ts_utc - 10h",
                "rule": "mask when snapshot cutoff is later than issue cutoff",
            },
            "heldout_issues": list(HELDOUT_ISSUES),
            "heldout_policy": HELDOUT_POLICY,
        },
    )
    _namespace_manifest(inference, "outcome_unexposed_inference")
    return {
        "match_rows": len(matches),
        "cell_rows": len(identity),
        "issues": identity["issue"].nunique(),
        "heldout_issues": identity.loc[identity["split"].eq("heldout"), "issue"].nunique(),
    }


def build_development_labels(output: Path, *, database: Path) -> dict[str, Any]:
    output = output.resolve()
    labels_dir = output / "labels"
    if labels_dir.exists() and any(labels_dir.iterdir()):
        raise TensorBuildError("label namespace already exists")
    labels_dir.mkdir(parents=True, exist_ok=True)
    _database_guard(database)
    identity = pd.read_parquet(output / "inference/cell_identity.parquet")
    development = identity[identity["split"].eq("development")].copy()
    development_issues = development["issue"].astype(str).drop_duplicates().tolist()
    if set(development_issues).intersection(HELDOUT_ISSUES):
        raise TensorBuildError("held-out issue entered label query")
    placeholders = ",".join("?" for _ in development_issues)
    query = f"""
        SELECT CAST(match_id AS TEXT) AS match_id,
               CAST(issue AS TEXT) AS issue,
               CAST(result_code AS TEXT) AS result_code,
               winning_sp,
               official_sp_3,
               official_sp_1,
               official_sp_0,
               winning_sp_source,
               settlement_quality,
               has_trusted_settlement
          FROM match_features
         WHERE issue IN ({placeholders})
         ORDER BY CAST(issue AS INTEGER), match_idx, match_id
    """
    with _sqlite_ro(database) as connection:
        truth = pd.DataFrame(
            [dict(row) for row in connection.execute(query, development_issues)]
        )
    match_ids = set(development["match_id"].astype(str))
    truth = truth[truth["match_id"].astype(str).isin(match_ids)].copy()
    if truth["match_id"].duplicated().any() or len(truth) != len(match_ids):
        raise TensorBuildError("development settlement identity coverage drift")
    cells = development.merge(
        truth, on=["issue", "match_id"], how="left", validate="many_to_one", sort=False
    )
    trusted = (
        cells["result_code"].astype(str).isin(OUTCOME_ORDER)
        & _numeric(cells["winning_sp"]).gt(0)
        & cells["settlement_quality"].astype(str).eq("trusted")
        & _numeric(cells["has_trusted_settlement"]).eq(1)
    )
    labels = pd.DataFrame(
        {
            "cell_join_key": cells["cell_join_key"].astype(str),
            "issue": cells["issue"].astype(str),
            "issue_instance": cells["issue_instance"].astype(str),
            "match_id": cells["match_id"].astype(str),
            "outcome_code": cells["outcome_code"].astype(str),
            "result_code": np.where(trusted, cells["result_code"].astype(str), ""),
            "is_winner": trusted & cells["outcome_code"].eq(cells["result_code"]),
        }
    )
    final_sp = np.full(len(cells), np.nan, dtype=np.float64)
    for code in OUTCOME_ORDER:
        selected = cells["outcome_code"].eq(code)
        final_sp[selected] = _numeric(cells.loc[selected, f"official_sp_{code}"])
    winner = labels["is_winner"].to_numpy(dtype=bool)
    missing_winner_sp = winner & ~np.isfinite(final_sp)
    final_sp[missing_winner_sp] = _numeric(cells.loc[missing_winner_sp, "winning_sp"])
    final_sp[~trusted.to_numpy()] = np.nan
    labels["final_sp"] = final_sp
    labels["final_sp_available"] = np.isfinite(final_sp) & (final_sp > 0)
    winning_zero = np.where(
        trusted.to_numpy(),
        np.where(winner, _numeric(cells["winning_sp"]).to_numpy(), 0.0),
        np.nan,
    )
    labels["winning_zero_return_units"] = winning_zero
    labels["payout_factor"] = np.float64(0.65)
    labels["payout_after_65_units"] = winning_zero * 0.65
    labels["tax_rate"] = np.float64(0.20)
    labels["tax_cliff_gross_yuan"] = np.float64(10_000.0)
    labels["tax_realized_yuan"] = np.nan
    labels["tax_realized_available"] = False
    labels["settlement_status"] = np.where(
        trusted, "SETTLED_TRUSTED", "UNAVAILABLE_CANONICAL_SETTLEMENT"
    )
    labels["settlement_quality"] = cells["settlement_quality"].fillna("").astype(str)
    labels["settlement_source"] = cells["winning_sp_source"].fillna("").astype(str)
    labels = labels.loc[:, LABEL_COLUMNS]
    write_parquet(labels_dir / "development_labels.parquet", labels)
    manifest = _namespace_manifest(labels_dir, "development_only_settlement_labels")
    manifest["heldout_label_status"] = "ABSENT_BY_CONTRACT"
    manifest["heldout_issues"] = list(HELDOUT_ISSUES)
    manifest["settlement_contract"] = {
        "winning_zero_return": "winning_sp for winning outcome, otherwise zero",
        "payout_factor": "0.65 applied exactly once",
        "tax": (
            "20% only when one realized ticket gross reaches CNY 10,000; cell "
            "labels cannot realize ticket-level aggregation, so tax stays masked"
        ),
    }
    write_json(labels_dir / "MANIFEST.json", manifest)
    return {
        "label_cells": len(labels),
        "trusted_cells": int(labels["settlement_status"].eq("SETTLED_TRUSTED").sum()),
        "heldout_label_cells": 0,
    }


def _downstream_readiness(coverage: pd.DataFrame) -> dict[str, Any]:
    coverage_lookup = {
        (str(row.split), str(row.feature)): float(row.coverage_rate)
        for row in coverage.itertuples(index=False)
    }
    core_market_coverage = {
        feature: coverage_lookup[("development", feature)]
        for feature in (
            "calibrated_market_probability",
            "devig_euro_probability",
            "euro_1h_odds",
            "predicted_final_sp",
            "bj_sp_snapshot",
        )
    }
    return {
        "decision": "BLOCKED_PENDING_DATA_CAPABILITY",
        "downstream_issue": 204,
        "reason": (
            "The frozen development tensor does not provide representative causal "
            "market-price support for the contracted market-anchored probability "
            "and pre-event SP heads. A declared masked feature is not an available "
            "training input."
        ),
        "development_core_market_coverage": core_market_coverage,
        "required_data_capability": {
            "proposed_contract_id": "BJ-UNIFIED-MARKET-COVERAGE-001",
            "project": "BJ Data Platform",
            "scope": [
                "extend causally timestamped 1h EURO/market probability over development history",
                "extend timestamped pre-event Beijing SP snapshots with exact source digests",
                "publish matched issue/match/outcome coverage and replay evidence",
                "define a PI-approved representative-support gate before #204 activation",
            ],
            "graph_disposition": (
                "PI must create the native Data issue and make #204 blockedBy it; "
                "Engineer does not mutate PI-owned graph contracts."
            ),
        },
        "heldout_disposition": (
            "The complete 2025-04+ local sequence is frozen for identity and label "
            "embargo only. Its 2026 rows do not repair development feature coverage."
        ),
    }


def _decision_report(readiness: dict[str, Any]) -> str:
    core_market_coverage = readiness["development_core_market_coverage"]
    report_lines = [
        "# #203 downstream readiness decision",
        "",
        "Decision: **#204 remains BLOCKED_PENDING_DATA_CAPABILITY**.",
        "",
        "The current development coverage is:",
        "",
        "| core input | causal unmasked coverage |",
        "| --- | ---: |",
        *[
            f"| `{feature}` | {rate:.6%} |"
            for feature, rate in core_market_coverage.items()
        ],
        "",
        "These rates do not support representing #204 as a usable market-anchored "
        "probability/SP learning capability. The 2026 held-out extension is identity "
        "only and does not change that conclusion.",
        "",
        "Required PI-owned Data capability: `BJ-UNIFIED-MARKET-COVERAGE-001` "
        "under **BJ Data Platform**, covering causally timestamped development "
        "1h EURO/market probability and pre-event Beijing SP, exact provenance, "
        "matched coverage, and a PI-approved representative-support gate. PI must "
        "create the native Issue and graph edge; this package only records the "
        "evidence-backed disposition.",
        "",
    ]
    return "\n".join(report_lines)


def write_analysis_artifacts(output: Path) -> None:
    """Publish bounded decision tables and a package-versioned coverage figure."""

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    analysis = output / "analysis"
    analysis.mkdir(parents=True, exist_ok=True)
    coverage = pd.read_csv(output / "audit/feature_coverage.csv")
    summary = (
        coverage.groupby("split", sort=True)
        .agg(
            total_cells=("total_cells", "max"),
            feature_count=("feature", "size"),
            fully_covered_features=(
                "coverage_rate", lambda values: int((values == 1.0).sum())
            ),
            fully_masked_features=(
                "coverage_rate", lambda values: int((values == 0.0).sum())
            ),
            mean_feature_coverage=("coverage_rate", "mean"),
        )
        .reset_index()
    )
    write_csv(analysis / "coverage_summary.csv", summary)
    readiness = _downstream_readiness(coverage)
    write_json(analysis / "downstream_readiness.json", readiness)
    (analysis / "DECISION_REPORT.md").write_text(
        _decision_report(readiness), encoding="utf-8", newline="\n"
    )

    pivot = coverage.pivot(index="feature", columns="split", values="coverage_rate")
    pivot = pivot.loc[list(FEATURE_NAMES)]
    figure, axis = plt.subplots(figsize=(9.5, 9.0), constrained_layout=True)
    y = np.arange(len(pivot), dtype=float)
    width = 0.38
    axis.barh(
        y - width / 2,
        pivot["development"].to_numpy(),
        height=width,
        label="development",
    )
    axis.barh(
        y + width / 2,
        pivot["heldout"].to_numpy(),
        height=width,
        label="heldout identity only",
    )
    axis.set(
        yticks=y,
        yticklabels=pivot.index,
        xlim=(0.0, 1.01),
        xlabel="unmasked cell coverage",
        title="#203 causal feature coverage by frozen split",
    )
    axis.invert_yaxis()
    axis.grid(axis="x", alpha=0.25)
    axis.legend(loc="lower right")
    figure.savefig(
        analysis / "feature_coverage.png",
        dpi=150,
        metadata={"Software": f"matplotlib {matplotlib.__version__}"},
    )
    plt.close(figure)


def _implementation_paths() -> dict[str, Path]:
    return {
        "builder": Path(__file__).resolve(),
        "contract": Path(__file__).with_name("contract.py").resolve(),
        "inference_loader": Path(__file__).with_name("inference.py").resolve(),
        "label_loader": Path(__file__).with_name("settlement_labels.py").resolve(),
        "build_cli": ROOT / "scripts/build_bj203_causal_tensor.py",
        "notebook_executor": ROOT / "scripts/execute_bj203_notebook.py",
        "environment_lock": ROOT / "requirements.txt",
    }


def finalize_package(output: Path) -> dict[str, Any]:
    output = output.resolve()
    inference_manifest = output / "inference/MANIFEST.json"
    label_manifest = output / "labels/MANIFEST.json"
    if not inference_manifest.is_file() or not label_manifest.is_file():
        raise TensorBuildError("both physical namespaces are required before finalize")
    source_extension = output / "sources/unavailable_match_identity.parquet"
    heldout_source_extension = output / "sources/heldout_match_identity.parquet"
    write_analysis_artifacts(output)
    implementation_paths = _implementation_paths()
    write_json(
        output / "MANIFEST.json",
        {
            "contract_version": CONTRACT_VERSION,
            "issue": 203,
            "scope": "data capability only; no model, ranking, ROI or execution",
            "inference_namespace_manifest_sha256": digest(inference_manifest),
            "label_namespace_manifest_sha256": digest(label_manifest),
            "identity_extension_sha256": digest(source_extension),
            "heldout_identity_extension_sha256": digest(
                heldout_source_extension
            ),
            "downstream_readiness_sha256": digest(
                output / "analysis/downstream_readiness.json"
            ),
            "decision_report_sha256": digest(
                output / "analysis/DECISION_REPORT.md"
            ),
            "source_hashes": _source_hashes(),
            "implementation_hashes": {
                name: digest(path) for name, path in implementation_paths.items()
            },
            "heldout": {
                "issues": list(HELDOUT_ISSUES),
                "label_status": "ABSENT_BY_CONTRACT",
                "policy": HELDOUT_POLICY,
            },
            "supersedes": {
                "contract_version": "bj203-causal-tensor-v1",
                "path": "results/bj203_causal_tensor_v1",
                "exact_head": SUPERSEDED_V1_HEAD,
                "manifest_sha256": SUPERSEDED_V1_MANIFEST_SHA256,
                "sha256sums_sha256": SUPERSEDED_V1_SHA256SUMS_SHA256,
                "status": "PRESERVED_IMMUTABLE_SUPERSEDED_EVIDENCE",
            },
            "scientific_stack": {
                "pandas": pd.__version__,
                "numpy": np.__version__,
                "pyarrow": pa.__version__,
                "matplotlib": metadata.version("matplotlib"),
                "nbclient": metadata.version("nbclient"),
                "nbformat": metadata.version("nbformat"),
                "python": sys.version.split()[0],
                "artifact_format": "Parquet 2.6 / Zstandard",
                "random_seed": "NOT_APPLICABLE_DETERMINISTIC_TRANSFORM",
                "device": "CPU",
            },
        },
    )
    data_card = f"""# #203 causal issue tensor data card

This immutable package materializes one ragged `X_i[J_i, 3, {len(FEATURE_NAMES)}]`
float32 tensor plus an equal-shape Boolean mask for each of {EXPECTED_ISSUES}
canonical issues. Outcome order is `3, 1, 0`; match order is `match_idx,
match_id`; issue order is cutoff then numeric issue.

## Causal boundary

`inference/` is outcome-unexposed and is the only namespace read by the default
loader. `labels/` is imported explicitly and contains development-only result,
final-SP and settlement fields. The exact 52-issue held-out sequence is recorded
in `audit/heldout_registry.csv`: 25041-25042 plus every locally inventoried 2026
issue from 26011 through 26069. Their labels are absent, not encrypted or hidden
in the same payload. The prior `results/bj203_causal_tensor_v1` package is
preserved unchanged as superseded two-issue evidence; v2 is the operative handoff.
Its complete byte census remains independently checkable with the
`verify-superseded` command and is locked to original HEAD `{SUPERSEDED_V1_HEAD}`.

The 8,661 added 2026 matches are deliberately identity only. Rows 26011-26049
come from the retrospective modelling inventory and carry no asserted observation
timestamp. Rows 26051-26069 come from the timestamped live match inventory and
bind `created_ts`, but expose no market, SP, line, league or team decision feature.
Only the canonical outcome axis, issue/match order, calendar year and nonnegative
kickoff delay can be unmasked. The loader fails closed if an identity-only row
exposes any other feature.

Historical official Beijing 3SP has no trustworthy observation timestamp and is
therefore label-only. The pre-event `bj_sp_snapshot` slots remain present but
fully masked. Match-safe 1h EURO and 10h predicted-SP inputs are also masked
whenever their snapshot cutoff follows the issue-level cutoff; the leakage audit
reports those negative coverage counts explicitly. All {EXPECTED_EXTENSION_ROWS}
rows excluded from #190's estimator
universe are retained with explicit missing-team, missing-1h-EURO and/or
missing-line reasons; no future or terminal value repairs them.

## Learner handoff

Use `unified_tensor.load_issue_tensors(package, split="development")`. It
returns values and masks with shapes `[J_i, 3, F]`; masked values are zeroed only
at load time. The probability/SP learner must treat calibrated market
probability as the incumbent, preserve zero-residual fallback, and must not
import `unified_tensor.settlement_labels` until an authorized validation path.

The executed analysis notebook is
`notebooks/research/issue-203/bj203_causal_tensor_contract.ipynb`. It verifies
the package, renders `analysis/coverage_summary.csv` and embeds the frozen
coverage figure without opening held-out labels.

The issue-level cutoff makes most match-relative market snapshots causally
unavailable (roughly 1% coverage for 1h market cells and 8% for 10h predicted
SP in development; Beijing SP is 0%). The explicit capability decision is that
**#204 remains blocked**. See `analysis/downstream_readiness.json` and
`analysis/DECISION_REPORT.md`. The required PI-owned Data capability is proposed
as `BJ-UNIFIED-MARKET-COVERAGE-001`: causally timestamped development 1h
EURO/market probability and pre-event Beijing SP, exact provenance, matched
coverage, and a PI-approved representative-support gate. PI must create that
native Issue and make #204 blockedBy it; this Engineer-owned package does not
mutate Issue Graph contracts. Reinterpreting the cutoff or backfilling terminal
prices is prohibited.

## Limitations

This package does not assert that all features are present. Coverage tables make
missing predicted SP, native line, and timestamped Beijing SP explicit. It does
not train a model, build tickets, calculate ROI, or authorize betting.
"""
    (output / "DATA_CARD.md").write_text(data_card, encoding="utf-8", newline="\n")
    replay = """# Deterministic replay

Create and use the repository's pinned environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PY=.venv/bin/python
$PY scripts/build_bj203_causal_tensor.py verify --package results/bj203_causal_tensor_v2
$PY scripts/build_bj203_causal_tensor.py verify-superseded \
  --package results/bj203_causal_tensor_v1
$PY scripts/execute_bj203_notebook.py

# Clean detached inference replay without the 6.8 GB runtime database.
# Replace the output placeholder with any new empty directory:
$PY scripts/build_bj203_causal_tensor.py build-inference \\
  --output <empty-replay-directory> \\
  --identity-extension results/bj203_causal_tensor_v2/sources/unavailable_match_identity.parquet \\
  --heldout-identity-extension results/bj203_causal_tensor_v2/sources/heldout_match_identity.parquet
$PY scripts/build_bj203_causal_tensor.py compare-inference \\
  --frozen results/bj203_causal_tensor_v2 \\
  --replay <empty-replay-directory>
```

The comparison command requires an exact file census and byte identity for every
inference, source, audit, schema and feature-dictionary artifact. Label generation
is intentionally a separate command that requires the exact read-only runtime
database and excludes held-out issues in its SQL query.
"""
    (output / "REPLAY.md").write_text(replay, encoding="utf-8", newline="\n")
    sums = {
        path.relative_to(output).as_posix(): digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    write_json(output / "SHA256SUMS.json", sums)
    return verify_package(output)


def verify_superseded_package(output: Path) -> dict[str, Any]:
    """Verify preserved v1 bytes without treating v1 as the operative contract."""

    output = output.expanduser().resolve()
    try:
        sums_path = output / "SHA256SUMS.json"
        manifest_path = output / "MANIFEST.json"
        sums = json.loads(sums_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorBuildError("invalid superseded v1 package") from exc
    paths = list(output.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise TensorBuildError("superseded v1 package must not contain symlinks")
    files = {
        path.relative_to(output).as_posix()
        for path in paths
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if not isinstance(sums, dict) or set(sums) != files:
        raise TensorBuildError("superseded v1 file census drift")
    for relative, expected in sums.items():
        if digest(output / relative) != expected:
            raise TensorBuildError(f"superseded v1 hash mismatch: {relative}")
    if digest(sums_path) != SUPERSEDED_V1_SHA256SUMS_SHA256:
        raise TensorBuildError("superseded v1 root identity drift")
    if digest(manifest_path) != SUPERSEDED_V1_MANIFEST_SHA256:
        raise TensorBuildError("superseded v1 manifest identity drift")
    if manifest.get("contract_version") != "bj203-causal-tensor-v1":
        raise TensorBuildError("superseded v1 contract declaration drift")
    if manifest.get("heldout", {}).get("issues") != ["25041", "25042"]:
        raise TensorBuildError("superseded v1 held-out declaration drift")
    return {
        "contract_version": "bj203-causal-tensor-v1",
        "exact_head": SUPERSEDED_V1_HEAD,
        "files": len(files),
        "status": "SUPERSEDED_EVIDENCE_PASS",
    }


def compare_inference_replay(frozen: Path, replay: Path) -> dict[str, Any]:
    """Require byte-identical deterministic output from a detached inference replay."""

    frozen = frozen.expanduser().resolve()
    replay = replay.expanduser().resolve()
    root_files = {"feature_dictionary.csv", "schema.json"}

    def selected_files(root: Path) -> set[str]:
        paths = list(root.rglob("*"))
        if any(path.is_symlink() for path in paths):
            raise TensorBuildError("detached inference replay must not use symlinks")
        return {
            path.relative_to(root).as_posix()
            for path in paths
            if path.is_file()
            and (
                path.relative_to(root).parts[0] in {"inference", "sources", "audit"}
                or path.relative_to(root).as_posix() in root_files
            )
        }

    expected = selected_files(frozen)
    actual = selected_files(replay)
    if not expected or actual != expected:
        raise TensorBuildError("detached inference replay file census mismatch")
    aliases = [
        relative
        for relative in sorted(expected)
        if (frozen / relative).samefile(replay / relative)
    ]
    if aliases:
        raise TensorBuildError(
            f"detached inference replay must not alias frozen files: {aliases}"
        )
    mismatches = [
        relative
        for relative in sorted(expected)
        if digest(frozen / relative) != digest(replay / relative)
    ]
    if mismatches:
        raise TensorBuildError(
            f"detached inference replay byte mismatch: {mismatches}"
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "compared_files": len(expected),
        "status": "BYTE_IDENTICAL_PASS",
    }


def _assert_exact_cell_identity(
    actual: pd.DataFrame, expected: pd.DataFrame
) -> None:
    if list(actual.columns) != list(expected.columns) or not (
        actual.reset_index(drop=True).astype(str).equals(
            expected.reset_index(drop=True).astype(str)
        )
    ):
        raise TensorBuildError("package cell identity differs from frozen sources")


def _assert_exact_feature_table(
    actual: pd.DataFrame,
    expected: pd.DataFrame,
    *,
    name: str,
) -> None:
    if list(actual.columns) != list(expected.columns) or not actual[
        "cell_join_key"
    ].astype(str).equals(expected["cell_join_key"].astype(str)):
        raise TensorBuildError(f"package {name} differ from frozen sources")
    actual_features = actual.loc[:, FEATURE_NAMES].to_numpy()
    expected_features = expected.loc[:, FEATURE_NAMES].to_numpy()
    if not np.array_equal(actual_features, expected_features, equal_nan=True):
        raise TensorBuildError(f"package {name} differ from frozen sources")


def _assert_exact_heldout_registry(
    actual: pd.DataFrame, expected: pd.DataFrame
) -> None:
    if list(actual.columns) != list(expected.columns) or not (
        actual.reset_index(drop=True).astype(str).equals(
            expected.reset_index(drop=True).astype(str)
        )
    ):
        raise TensorBuildError("held-out registry does not bind exact frozen identity")


def _validate_source_bound_identity(output: Path, identity: pd.DataFrame) -> None:
    """Bind every issue and match axis field to the exact frozen upstream sources."""

    estimator, issue_census, predictions, extension, heldout_extension = _load_inputs(
        None,
        output / "sources/unavailable_match_identity.parquet",
        heldout_identity_extension=output / "sources/heldout_match_identity.parquet",
    )
    expected_matches, _, _, _ = _prepare_matches(
        estimator, issue_census, predictions, extension, heldout_extension
    )
    expected_identity, expected_values, expected_masks = _cell_tables(expected_matches)
    _assert_exact_cell_identity(identity, expected_identity)
    _assert_exact_feature_table(
        pd.read_parquet(output / "inference/feature_values.parquet"),
        expected_values,
        name="feature values",
    )
    _assert_exact_feature_table(
        pd.read_parquet(output / "inference/feature_masks.parquet"),
        expected_masks,
        name="feature masks",
    )
    actual_registry = pd.read_csv(
        output / "audit/heldout_registry.csv", dtype=str, keep_default_na=False
    )
    expected_registry = _heldout_registry(identity).astype(str)
    _assert_exact_heldout_registry(actual_registry, expected_registry)


def verify_package(output: Path) -> dict[str, Any]:
    output = output.resolve()
    try:
        sums = json.loads((output / "SHA256SUMS.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorBuildError("invalid root SHA256SUMS") from exc
    if not isinstance(sums, dict):
        raise TensorBuildError("invalid root SHA256SUMS")
    package_paths = list(output.rglob("*"))
    if any(path.is_symlink() for path in package_paths):
        raise TensorBuildError("root package must not contain symlinks")
    actual_files = {
        path.relative_to(output).as_posix()
        for path in package_paths
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if set(sums) != actual_files:
        raise TensorBuildError("root package file census does not match SHA256SUMS")
    for relative, expected in sums.items():
        path = output / relative
        if not path.is_file() or digest(path) != expected:
            raise TensorBuildError(f"package hash mismatch: {relative}")
    try:
        manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorBuildError("invalid root manifest") from exc
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise TensorBuildError("root manifest contract version drift")
    heldout_manifest = manifest.get("heldout")
    if not isinstance(heldout_manifest, dict) or heldout_manifest.get(
        "issues"
    ) != list(HELDOUT_ISSUES):
        raise TensorBuildError("root held-out identity declaration drift")
    expected_supersedes = {
        "contract_version": "bj203-causal-tensor-v1",
        "path": "results/bj203_causal_tensor_v1",
        "exact_head": SUPERSEDED_V1_HEAD,
        "manifest_sha256": SUPERSEDED_V1_MANIFEST_SHA256,
        "sha256sums_sha256": SUPERSEDED_V1_SHA256SUMS_SHA256,
        "status": "PRESERVED_IMMUTABLE_SUPERSEDED_EVIDENCE",
    }
    if manifest.get("supersedes") != expected_supersedes:
        raise TensorBuildError("superseded v1 identity declaration drift")
    readiness_path = output / "analysis/downstream_readiness.json"
    report_path = output / "analysis/DECISION_REPORT.md"
    coverage = pd.read_csv(output / "audit/feature_coverage.csv")
    coverage_identity = pd.read_parquet(output / "inference/cell_identity.parquet")
    coverage_masks = pd.read_parquet(output / "inference/feature_masks.parquet")
    expected_coverage = _feature_coverage(coverage_identity, coverage_masks)
    _assert_feature_coverage(coverage, expected_coverage)
    expected_readiness = _downstream_readiness(expected_coverage)
    try:
        actual_readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TensorBuildError("invalid downstream readiness artifact") from exc
    if actual_readiness != expected_readiness:
        raise TensorBuildError("downstream readiness does not match frozen coverage")
    if report_path.read_text(encoding="utf-8") != _decision_report(
        expected_readiness
    ):
        raise TensorBuildError("downstream decision report semantic drift")
    if manifest.get("downstream_readiness_sha256") != digest(readiness_path):
        raise TensorBuildError("downstream readiness identity drift")
    if manifest.get("decision_report_sha256") != digest(report_path):
        raise TensorBuildError("downstream decision report identity drift")
    current_implementation_hashes = {
        name: digest(path) for name, path in _implementation_paths().items()
    }
    if manifest.get("implementation_hashes") != current_implementation_hashes:
        raise TensorBuildError("package implementation identity drift")
    if manifest.get("source_hashes") != _source_hashes():
        raise TensorBuildError("package source identity drift")
    if manifest.get("identity_extension_sha256") != digest(
        output / "sources/unavailable_match_identity.parquet"
    ):
        raise TensorBuildError("package identity extension drift")
    if manifest.get("heldout_identity_extension_sha256") != digest(
        output / "sources/heldout_match_identity.parquet"
    ):
        raise TensorBuildError("package held-out identity extension drift")
    namespace_manifests = {
        "inference_namespace_manifest_sha256": output / "inference/MANIFEST.json",
        "label_namespace_manifest_sha256": output / "labels/MANIFEST.json",
    }
    if any(manifest.get(field) != digest(path) for field, path in namespace_manifests.items()):
        raise TensorBuildError("package namespace manifest identity drift")
    tensors = load_issue_tensors(output)
    labels = load_development_labels(output)
    inference_identity = pd.read_parquet(output / "inference/cell_identity.parquet")
    _validate_source_bound_identity(output, inference_identity)
    bind_development_labels(inference_identity, labels)
    if len(tensors) != EXPECTED_ISSUES:
        raise TensorBuildError("issue tensor census drift")
    match_rows = sum(len(tensor.match_ids) for tensor in tensors)
    if match_rows != EXPECTED_MATCH_ROWS:
        raise TensorBuildError("match tensor census drift")
    heldout = [tensor for tensor in tensors if tensor.split == "heldout"]
    if len(heldout) != EXPECTED_HELDOUT_ISSUES:
        raise TensorBuildError("held-out issue census drift")
    if {tensor.issue for tensor in heldout} != set(HELDOUT_ISSUES):
        raise TensorBuildError("held-out issue identity set drift")
    if labels["issue"].astype(str).isin(HELDOUT_ISSUES).any():
        raise TensorBuildError("held-out label embargo failed")
    return {
        "contract_version": CONTRACT_VERSION,
        "issues": len(tensors),
        "matches": match_rows,
        "cells": match_rows * len(OUTCOME_ORDER),
        "features": len(FEATURE_NAMES),
        "development_label_cells": len(labels),
        "heldout_issues": len(heldout),
        "heldout_label_cells": 0,
        "status": "PASS",
    }
