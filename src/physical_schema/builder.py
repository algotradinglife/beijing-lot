"""Build and verify the Issue #253 representative physical package."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from source_schema import publication

from .contract import (
    CONTRACT_VERSION,
    CONTROL_DDL,
    LABELS_DDL,
    NAMESPACES,
    OUTCOME_CODES,
    PACKAGE_SCHEMA,
    feature_schema,
    label_schema,
    schema_json,
)

PACKAGE_RELATIVE = Path("derived/bj253_physical_schema_v1")
IDENTITY_RELATIVE = Path("derived/bj251_canonical_identity_v3")
XLSM_RELATIVE = Path("derived/beidan_xlsm/beidan_xlsm.sqlite")
LIVE_RELATIVE = Path("beidan_live.db")
PROHIBITED_FEATURE_COLUMNS = {
    "result_code",
    "result_label",
    "winning_sp",
    "settled_at_utc",
    "score",
    "payout",
    "payout_factor",
}


class PhysicalSchemaError(ValueError):
    """Raised when the prototype physical contract is violated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _row_digest(values: Iterable[object]) -> str:
    payload = json.dumps(list(values), ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_data_root(data_root: str | Path | None = None) -> Path:
    """Resolve the sole external storage interface without machine defaults."""
    raw = str(data_root) if data_root is not None else os.environ.get("BEIJING_LOT_DATA_ROOT")
    if not raw:
        raise PhysicalSchemaError("BEIJING_LOT_DATA_ROOT is required")
    root = Path(raw).expanduser()
    if not root.is_absolute():
        raise PhysicalSchemaError("BEIJING_LOT_DATA_ROOT must be absolute")
    root = root.resolve()
    if not root.exists() or not root.is_dir():
        raise PhysicalSchemaError(f"external data root does not exist: {root}")
    return root


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise PhysicalSchemaError(f"required source is missing: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _historical_source_rows(path: Path) -> pd.DataFrame:
    with _connect_readonly(path) as connection:
        candidates = pd.read_sql_query(
            """
            WITH eligible AS (
                SELECT m.issue, m.match_idx
                FROM matches AS m
                JOIN market_consensus AS c ON c.match_id = m.match_id
                JOIN official_500_settlements AS o
                  ON o.issue = m.issue AND o.match_idx = m.match_idx
                WHERE c.market = 'euro_1x2'
                  AND c.snapshot IN ('initial','10h','1h')
                  AND c.v1_avg > 1.0 AND c.v2_avg > 1.0 AND c.v3_avg > 1.0
                  AND o.result_code IN ('3','1','0')
                  AND m.issue IS NOT NULL AND m.match_idx IS NOT NULL
                GROUP BY m.issue, m.match_idx
                HAVING COUNT(DISTINCT c.snapshot) = 3
            )
            SELECT issue, match_idx
            FROM eligible
            ORDER BY issue, match_idx
            LIMIT 4
            """,
            connection,
            dtype={"issue": "string", "match_idx": "int64"},
        )
        if len(candidates) != 4:
            raise PhysicalSchemaError("historical source cannot supply four complete proxy slots")
        clauses = " OR ".join("(m.issue = ? AND m.match_idx = ?)" for _ in candidates.itertuples())
        params: list[object] = []
        for row in candidates.itertuples(index=False):
            params.extend([str(row.issue), int(row.match_idx)])
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx, m.match_id,
                   m.kickoff_ts, m.handicap_line_norm AS handicap_line,
                   c.snapshot AS snapshot_horizon,
                   c.v1_avg AS value_3, c.v2_avg AS value_1, c.v3_avg AS value_0
            FROM matches AS m
            JOIN market_consensus AS c ON c.match_id = m.match_id
            WHERE c.market = 'euro_1x2'
              AND c.snapshot IN ('initial','10h','1h')
              AND ({clauses})
            ORDER BY CAST(m.issue AS INTEGER), m.match_idx,
                     CASE c.snapshot WHEN 'initial' THEN 1 WHEN '10h' THEN 2 ELSE 3 END
            """,
            connection,
            params=params,
        )
    if len(frame) != 12:
        raise PhysicalSchemaError("historical proxy extraction is not four slots × three horizons")
    return frame


def _strict_source_rows(path: Path) -> pd.DataFrame:
    base = """
        SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx, m.match_id,
               CAST(m.fid AS TEXT) AS provider_fixture_id, m.kickoff_ts,
               m.handicap_line, s.snapshot_ts,
               s.sp_3, s.sp_1, s.sp_0, s.eu_h, s.eu_d, s.eu_a
        FROM snapshots AS s JOIN matches AS m ON m.match_id = s.match_id
        WHERE datetime(s.snapshot_ts, '+8 hours') < datetime(m.kickoff_ts)
          AND s.eu_h > 1.0 AND s.eu_d > 1.0 AND s.eu_a > 1.0
          AND {condition}
        ORDER BY s.snapshot_ts, CAST(m.issue AS INTEGER), m.match_idx
        LIMIT {limit}
    """
    complete_condition = "s.sp_3 > 1.0 AND s.sp_1 > 1.0 AND s.sp_0 > 1.0"
    incomplete_condition = "(s.sp_3 IS NULL OR s.sp_1 IS NULL OR s.sp_0 IS NULL)"
    with _connect_readonly(path) as connection:
        complete = pd.read_sql_query(
            base.format(condition=complete_condition, limit=3), connection
        )
        incomplete = pd.read_sql_query(
            base.format(condition=incomplete_condition, limit=1), connection
        )
    frame = pd.concat([complete, incomplete], ignore_index=True)
    if len(frame) != 4 or frame[["issue_code", "match_idx"]].duplicated().any():
        raise PhysicalSchemaError("strict source cannot supply three complete and one incomplete slot")
    return frame


def _label_rows(path: Path, issue_pairs: pd.DataFrame) -> pd.DataFrame:
    clauses = " OR ".join("(issue = ? AND match_idx = ?)" for _ in issue_pairs.itertuples())
    params: list[object] = []
    for row in issue_pairs.itertuples(index=False):
        params.extend([str(row.issue_code), int(row.match_idx)])
    with _connect_readonly(path) as connection:
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue_code, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   winning_sp, fetched_at, raw_row_hash
            FROM official_500_settlements
            WHERE ({clauses})
            ORDER BY CAST(issue AS INTEGER), match_idx
            """,
            connection,
            params=params,
        )
    return frame


def _identity_rows(path: Path, pairs: pd.DataFrame) -> pd.DataFrame:
    if not path.exists():
        raise PhysicalSchemaError(f"accepted #251 identity package is missing: {path}")
    identity = pd.read_csv(
        path,
        dtype={"issue_code": "string", "issue_slot_id": "string", "match_idx": "int64"},
    )
    requested = pairs.assign(issue_code=pairs["issue_code"].astype("string"))[
        ["issue_code", "match_idx"]
    ].drop_duplicates()
    selected = requested.merge(
        identity[["issue_code", "match_idx", "issue_slot_id", "fixture_entity_id"]],
        on=["issue_code", "match_idx"],
        how="left",
        validate="one_to_one",
    )
    if selected["issue_slot_id"].isna().any():
        raise PhysicalSchemaError("representative source row lacks accepted issue-local identity")
    if selected["fixture_entity_id"].notna().any():
        raise PhysicalSchemaError("#251 boundary changed: canonical fixture entity unexpectedly populated")
    return selected


def extract_representative_sources(root: Path) -> dict[str, pd.DataFrame]:
    """Read a deterministic, small real-data slice from the external root."""
    proxy = _historical_source_rows(root / XLSM_RELATIVE)
    strict = _strict_source_rows(root / LIVE_RELATIVE)
    pairs = pd.concat(
        [proxy[["issue_code", "match_idx"]], strict[["issue_code", "match_idx"]]],
        ignore_index=True,
    ).drop_duplicates()
    identity = _identity_rows(
        root / IDENTITY_RELATIVE / "tables" / "issue_slot_identity.csv", pairs
    )
    proxy_pairs = proxy[["issue_code", "match_idx"]].drop_duplicates()
    labels = _label_rows(root / XLSM_RELATIVE, proxy_pairs)
    return {"proxy": proxy, "strict": strict, "identity": identity, "labels": labels}


def _local_kickoff_to_utc(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="raise", format="mixed")
    return parsed.dt.tz_localize(
        "Asia/Shanghai", ambiguous="raise", nonexistent="raise"
    ).dt.tz_convert("UTC")


def _observations_and_features(
    proxy: pd.DataFrame, strict: pd.DataFrame, identity: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    slot_map = {
        (str(row.issue_code), int(row.match_idx)): str(row.issue_slot_id)
        for row in identity.itertuples(index=False)
    }
    observations: list[dict[str, object]] = []
    features: list[dict[str, object]] = []
    slots: dict[str, dict[str, object]] = {}

    proxy = proxy.copy()
    proxy["kickoff_at_utc"] = _local_kickoff_to_utc(proxy.pop("kickoff_ts"))
    for row in proxy.itertuples(index=False):
        key = (str(row.issue_code), int(row.match_idx))
        slot_id = slot_map[key]
        slots[slot_id] = {
            "issue_slot_id": slot_id,
            "issue_code": key[0],
            "match_idx": key[1],
            "provider_fixture_id": None,
            "kickoff_at_utc": row.kickoff_at_utc,
            "identity_status": "ISSUE_LOCAL_SLOT",
        }
        observation_id = (
            f"obs:proxy:{key[0]}:{key[1]:03d}:{row.snapshot_horizon}:eu"
        )
        observation = {
            "observation_id": observation_id,
            "issue_slot_id": slot_id,
            "source_id": "beidan_xlsm_euro_1x2",
            "namespace": "historical_proxy",
            "snapshot_horizon": str(row.snapshot_horizon),
            "time_semantics": "SOURCE_RELATIVE_LABEL",
            "causal_grade": "RETROSPECTIVE_PROXY",
            "observed_at_utc": pd.NaT,
            "kickoff_at_utc": row.kickoff_at_utc,
            "handicap_line": float(row.handicap_line) if pd.notna(row.handicap_line) else None,
            "source_event_key": str(row.match_id),
        }
        observations.append(observation)
        for outcome, column in zip(OUTCOME_CODES, ("value_3", "value_1", "value_0"), strict=True):
            value = float(getattr(row, column))
            cell_id = f"bjcell:{key[0]}:{key[1]:03d}:BJ_HANDICAP_3WAY:{outcome}"
            features.append(
                {
                    **observation,
                    "issue_code": key[0],
                    "match_idx": key[1],
                    "play_code": "BJ_HANDICAP_3WAY",
                    "outcome_code": outcome,
                    "outcome_cell_id": cell_id,
                    "feature_name": "eu_decimal_odds",
                    "value": value,
                    "availability_mask": True,
                    "missing_reason": None,
                    "provenance_hash": _row_digest(
                        ["beidan_xlsm_euro_1x2", row.match_id, row.snapshot_horizon, outcome, value]
                    ),
                }
            )

    strict = strict.copy()
    strict["kickoff_at_utc"] = _local_kickoff_to_utc(strict.pop("kickoff_ts"))
    strict["observed_at_utc"] = pd.to_datetime(
        strict.pop("snapshot_ts"), utc=True, errors="raise", format="mixed"
    )
    for row in strict.itertuples(index=False):
        key = (str(row.issue_code), int(row.match_idx))
        slot_id = slot_map[key]
        provider_fixture_id = (
            str(row.provider_fixture_id) if pd.notna(row.provider_fixture_id) else None
        )
        source_event_key = provider_fixture_id or str(row.match_id)
        slots[slot_id] = {
            "issue_slot_id": slot_id,
            "issue_code": key[0],
            "match_idx": key[1],
            "provider_fixture_id": provider_fixture_id,
            "kickoff_at_utc": row.kickoff_at_utc,
            "identity_status": "UNKNOWN_ALIAS",
        }
        observation_id = f"obs:strict:{key[0]}:{key[1]:03d}:{row.match_id}:{row.observed_at_utc.value}"
        observation = {
            "observation_id": observation_id,
            "issue_slot_id": slot_id,
            "source_id": "beidan_live_db",
            "namespace": "strict_forward",
            "snapshot_horizon": "poll",
            "time_semantics": "POLL_STARTED_AT_UTC",
            "causal_grade": "POLL_STARTED_AGAINST_CURRENT_SCHEDULE_REFERENCE",
            "observed_at_utc": row.observed_at_utc,
            "kickoff_at_utc": row.kickoff_at_utc,
            "handicap_line": float(row.handicap_line) if pd.notna(row.handicap_line) else None,
            "source_event_key": source_event_key,
        }
        observations.append(observation)
        for feature_name, columns in (
            ("bj_sp", ("sp_3", "sp_1", "sp_0")),
            ("eu_decimal_odds", ("eu_h", "eu_d", "eu_a")),
        ):
            for outcome, column in zip(OUTCOME_CODES, columns, strict=True):
                raw = getattr(row, column)
                available = pd.notna(raw) and float(raw) > 1.0
                value = float(raw) if available else None
                cell_id = f"bjcell:{key[0]}:{key[1]:03d}:BJ_HANDICAP_3WAY:{outcome}"
                features.append(
                    {
                        **observation,
                        "issue_code": key[0],
                        "match_idx": key[1],
                        "play_code": "BJ_HANDICAP_3WAY",
                        "outcome_code": outcome,
                        "outcome_cell_id": cell_id,
                        "feature_name": feature_name,
                        "value": value,
                        "availability_mask": bool(available),
                        "missing_reason": None if available else "SOURCE_VALUE_MISSING_OR_INVALID",
                        "provenance_hash": _row_digest(
                            [
                                "beidan_live_db",
                                source_event_key,
                                row.observed_at_utc,
                                feature_name,
                                outcome,
                                value,
                            ]
                        ),
                    }
                )

    observation_frame = pd.DataFrame(observations).drop_duplicates("observation_id")
    feature_frame = pd.DataFrame(features)
    slot_frame = pd.DataFrame(slots.values()).sort_values(
        ["issue_code", "match_idx"], kind="stable"
    ).reset_index(drop=True)
    return slot_frame, observation_frame, feature_frame


def _label_frame(labels: pd.DataFrame, identity: pd.DataFrame) -> pd.DataFrame:
    slot_map = {
        (str(row.issue_code), int(row.match_idx)): str(row.issue_slot_id)
        for row in identity.itertuples(index=False)
    }
    rows: list[dict[str, object]] = []
    for row in labels.itertuples(index=False):
        key = (str(row.issue_code), int(row.match_idx))
        if pd.isna(row.result_code):
            continue
        result_code = str(row.result_code)
        if key not in slot_map or result_code not in OUTCOME_CODES:
            continue
        settled = pd.Timestamp(row.fetched_at)
        if settled.tzinfo is None:
            settled = settled.tz_localize("Asia/Shanghai").tz_convert("UTC")
        else:
            settled = settled.tz_convert("UTC")
        rows.append(
            {
                "issue_slot_id": slot_map[key],
                "issue_code": key[0],
                "match_idx": key[1],
                "result_code": result_code,
                "winning_sp": float(row.winning_sp) if pd.notna(row.winning_sp) else None,
                "settled_at_utc": settled,
                "source_id": "official_500_settlements",
                "provenance_hash": str(row.raw_row_hash)
                if pd.notna(row.raw_row_hash)
                else _row_digest([*key, result_code, row.winning_sp, settled]),
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "issue_slot_id",
            "issue_code",
            "match_idx",
            "result_code",
            "winning_sp",
            "settled_at_utc",
            "source_id",
            "provenance_hash",
        ],
    )


def _sqlite_timestamp(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise PhysicalSchemaError("SQLite timestamp must be timezone-aware")
    return timestamp.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _write_sqlite(
    path: Path,
    slots: pd.DataFrame,
    observations: pd.DataFrame,
    features: pd.DataFrame,
) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(CONTROL_DDL)
        sources = pd.DataFrame(
            [
                {
                    "source_id": "beidan_xlsm_euro_1x2",
                    "namespace": "historical_proxy",
                    "causal_grade": "RETROSPECTIVE_PROXY",
                    "time_semantics": "SOURCE_RELATIVE_LABEL",
                    "source_role": "EU_1X2_OUTCOME_PROXY",
                    "source_receipt": "representative_source_snapshot",
                },
                {
                    "source_id": "beidan_live_db",
                    "namespace": "strict_forward",
                    "causal_grade": "POLL_STARTED_AGAINST_CURRENT_SCHEDULE_REFERENCE",
                    "time_semantics": "POLL_STARTED_AT_UTC",
                    "source_role": "BJ_SP_AND_EU_POLL",
                    "source_receipt": "representative_source_snapshot",
                },
            ]
        )
        sqlite_slots = slots.copy()
        sqlite_slots["kickoff_at_utc"] = sqlite_slots["kickoff_at_utc"].map(_sqlite_timestamp)
        plays = slots[["issue_slot_id"]].copy()
        plays["play_id"] = plays["issue_slot_id"].str.replace("bjslot:", "bjplay:", regex=False) + ":BJ_HANDICAP_3WAY"
        plays["play_code"] = "BJ_HANDICAP_3WAY"
        cells = []
        for row in plays.itertuples(index=False):
            for outcome in OUTCOME_CODES:
                cells.append(
                    {
                        "outcome_cell_id": row.play_id.replace("bjplay:", "bjcell:") + f":{outcome}",
                        "play_id": row.play_id,
                        "issue_slot_id": row.issue_slot_id,
                        "outcome_code": outcome,
                    }
                )
        cell_frame = pd.DataFrame(cells)
        sqlite_observations = observations.copy()
        for column in ("observed_at_utc", "kickoff_at_utc"):
            sqlite_observations[column] = sqlite_observations[column].map(_sqlite_timestamp)
        sqlite_features = features[
            [
                "observation_id",
                "outcome_cell_id",
                "feature_name",
                "value",
                "availability_mask",
                "missing_reason",
                "provenance_hash",
            ]
        ].copy()
        sqlite_features["availability_mask"] = sqlite_features["availability_mask"].astype(int)
        snapshots = observations[
            ["issue_slot_id", "namespace", "snapshot_horizon", "observed_at_utc"]
        ].copy()
        snapshots["issue_code"] = snapshots["issue_slot_id"].str.split(":").str[1]
        snapshots = snapshots.drop_duplicates(
            ["issue_code", "namespace", "snapshot_horizon", "observed_at_utc"]
        )
        snapshots["snapshot_id"] = snapshots.apply(
            lambda row: "snap:"
            + _row_digest(
                [row.issue_code, row.namespace, row.snapshot_horizon, row.observed_at_utc]
            )[:20],
            axis=1,
        )
        snapshots["decision_at_utc"] = snapshots["observed_at_utc"].map(_sqlite_timestamp)
        snapshots["segment_id"] = None
        snapshots["rule_version"] = CONTRACT_VERSION
        snapshots = snapshots[
            [
                "snapshot_id",
                "issue_code",
                "namespace",
                "snapshot_horizon",
                "decision_at_utc",
                "segment_id",
                "rule_version",
            ]
        ]
        sources.to_sql("source_registry", connection, if_exists="append", index=False)
        sqlite_slots.to_sql("issue_slot", connection, if_exists="append", index=False)
        plays[["play_id", "issue_slot_id", "play_code"]].to_sql(
            "play", connection, if_exists="append", index=False
        )
        cell_frame.to_sql("outcome_cell", connection, if_exists="append", index=False)
        sqlite_observations.to_sql("observation", connection, if_exists="append", index=False)
        sqlite_features.to_sql("feature_cell", connection, if_exists="append", index=False)
        snapshots.to_sql("snapshot_manifest", connection, if_exists="append", index=False)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise PhysicalSchemaError("control SQLite foreign-key check failed")
        connection.commit()
    finally:
        connection.close()


def _write_labels_sqlite(path: Path, labels: pd.DataFrame) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(LABELS_DDL)
        sqlite_labels = labels.copy()
        sqlite_labels["settled_at_utc"] = sqlite_labels["settled_at_utc"].map(_sqlite_timestamp)
        sqlite_labels.to_sql("settlement_label", connection, if_exists="append", index=False)
        connection.commit()
    finally:
        connection.close()


def _parquet_write(frame: pd.DataFrame, path: Path, schema: pa.Schema) -> None:
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False, safe=True)
    pq.write_table(table, path, compression="zstd")


def _feature_parquet_frame(features: pd.DataFrame) -> pd.DataFrame:
    frame = features[
        [
            "issue_slot_id",
            "issue_code",
            "match_idx",
            "play_code",
            "outcome_code",
            "observation_id",
            "source_id",
            "namespace",
            "snapshot_horizon",
            "time_semantics",
            "causal_grade",
            "observed_at_utc",
            "kickoff_at_utc",
            "handicap_line",
            "feature_name",
            "value",
            "availability_mask",
            "missing_reason",
            "provenance_hash",
        ]
    ].copy()
    frame["issue_code"] = frame["issue_code"].astype("string")
    frame["match_idx"] = frame["match_idx"].astype("int32")
    frame["observed_at_utc"] = pd.to_datetime(frame["observed_at_utc"], utc=True)
    frame["kickoff_at_utc"] = pd.to_datetime(frame["kickoff_at_utc"], utc=True)
    frame["availability_mask"] = frame["availability_mask"].astype(bool)
    return frame.sort_values(
        ["namespace", "issue_code", "match_idx", "snapshot_horizon", "feature_name", "outcome_code"],
        kind="stable",
    ).reset_index(drop=True)


def _label_parquet_frame(labels: pd.DataFrame) -> pd.DataFrame:
    frame = labels.copy()
    frame["issue_code"] = frame["issue_code"].astype("string")
    frame["match_idx"] = frame["match_idx"].astype("int32")
    frame["settled_at_utc"] = pd.to_datetime(frame["settled_at_utc"], utc=True)
    return frame.sort_values(["issue_code", "match_idx"], kind="stable").reset_index(drop=True)


def _file_inventory(package: Path) -> dict[str, str]:
    return {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "MANIFEST.json"
    }


def build_representative_package(
    data_root: str | Path | None = None,
    *,
    output: str | Path | None = None,
    force: bool = True,
) -> Path:
    """Build the real-data representative package outside Git."""
    root = resolve_data_root(data_root)
    target = Path(output).resolve() if output is not None else root / PACKAGE_RELATIVE
    sources = extract_representative_sources(root)
    slots, observations, features = _observations_and_features(
        sources["proxy"], sources["strict"], sources["identity"]
    )
    labels = _label_frame(sources["labels"], sources["identity"])
    feature_parquet = _feature_parquet_frame(features)
    label_parquet = _label_parquet_frame(labels)

    def populate(staging: Path) -> None:
        for directory in ("raw", "features", "labels", "schemas"):
            (staging / directory).mkdir(parents=True, exist_ok=True)
        _parquet_write(sources["identity"], staging / "raw" / "identity_slice.parquet", pa.Schema.from_pandas(sources["identity"], preserve_index=False))
        _parquet_write(sources["proxy"], staging / "raw" / "proxy_source_slice.parquet", pa.Schema.from_pandas(sources["proxy"], preserve_index=False))
        _parquet_write(sources["strict"], staging / "raw" / "strict_source_slice.parquet", pa.Schema.from_pandas(sources["strict"], preserve_index=False))
        _parquet_write(sources["labels"], staging / "labels" / "raw_settlement_slice.parquet", pa.Schema.from_pandas(sources["labels"], preserve_index=False))
        _write_sqlite(staging / "control.sqlite", slots, observations, features)
        _write_labels_sqlite(staging / "labels" / "labels.sqlite", labels)
        _parquet_write(feature_parquet, staging / "features" / "m3_feature_cells.parquet", feature_schema())
        _parquet_write(label_parquet, staging / "labels" / "settlement_labels.parquet", label_schema())
        publication.atomic_write_text(staging / "schemas" / "control.sql", CONTROL_DDL.strip() + "\n")
        publication.atomic_write_text(staging / "schemas" / "labels.sql", LABELS_DDL.strip() + "\n")
        publication.atomic_write_text(staging / "schemas" / "parquet_schema.json", schema_json())
        profile = profile_package_frames(slots, observations, feature_parquet, label_parquet)
        publication.atomic_write_json(staging / "PROFILE.json", profile)
        manifest = {
            "schema": PACKAGE_SCHEMA,
            "contract_version": CONTRACT_VERSION,
            "data_root_interface": "BEIJING_LOT_DATA_ROOT",
            "external_package_relative": PACKAGE_RELATIVE.as_posix(),
            "row_grain": "issue_code × match_idx × outcome_code × observation × feature_name",
            "outcome_codes": list(OUTCOME_CODES),
            "namespaces": list(NAMESPACES),
            "canonical_entity_policy": "UNAVAILABLE_NULL_NO_LABEL_INFERENCE",
            "label_separation": "SEPARATE_SQLITE_AND_PARQUET_NAMESPACE",
            "source_relative_paths": {
                "identity": IDENTITY_RELATIVE.as_posix(),
                "historical_proxy": XLSM_RELATIVE.as_posix(),
                "strict_forward": LIVE_RELATIVE.as_posix(),
            },
            "profile": profile,
            "files": _file_inventory(staging),
        }
        publication.atomic_write_json(staging / "MANIFEST.json", manifest)
        verify_package(staging)

    return publication.atomic_publish_directory(target, populate, force=force)


def load_feature_cells(package: str | Path) -> pd.DataFrame:
    """The model-facing reader intentionally has no path to settlement files."""
    path = Path(package) / "features" / "m3_feature_cells.parquet"
    frame = pd.read_parquet(path)
    prohibited = PROHIBITED_FEATURE_COLUMNS.intersection(frame.columns)
    if prohibited:
        raise PhysicalSchemaError(f"feature view contains prohibited label columns: {sorted(prohibited)}")
    return frame


def profile_package_frames(
    slots: pd.DataFrame,
    observations: pd.DataFrame,
    features: pd.DataFrame,
    labels: pd.DataFrame,
) -> dict[str, object]:
    available = features["availability_mask"].astype(bool)
    namespace_counts = {
        str(key): int(value) for key, value in features.groupby("namespace").size().items()
    }
    feature_counts = {
        str(key): int(value) for key, value in features.groupby("feature_name").size().items()
    }
    return {
        "issue_slots": int(len(slots)),
        "issues": int(slots["issue_code"].nunique()),
        "observations": int(len(observations)),
        "feature_cells": int(len(features)),
        "available_feature_cells": int(available.sum()),
        "missing_feature_cells": int((~available).sum()),
        "settlement_labels": int(len(labels)),
        "namespace_feature_cells": namespace_counts,
        "feature_name_cells": feature_counts,
    }


def verify_package(package: str | Path) -> dict[str, object]:
    """Verify the representative package's model-relevant invariants."""
    package = Path(package)
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("contract_version") != CONTRACT_VERSION:
        raise PhysicalSchemaError("package contract identity mismatch")
    if manifest.get("data_root_interface") != "BEIJING_LOT_DATA_ROOT":
        raise PhysicalSchemaError("external-root interface mismatch")
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict) or expected_files != _file_inventory(package):
        raise PhysicalSchemaError("package file inventory/hash closure mismatch")

    control = sqlite3.connect(package / "control.sqlite")
    try:
        if control.execute("PRAGMA foreign_key_check").fetchall():
            raise PhysicalSchemaError("control SQLite foreign-key check failed")
        tables = {
            row[0]
            for row in control.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "settlement_label" in tables:
            raise PhysicalSchemaError("settlement table leaked into control SQLite")
        triplets = control.execute(
            "SELECT play_id, GROUP_CONCAT(outcome_code, '') FROM (SELECT play_id, outcome_code FROM outcome_cell ORDER BY play_id, CASE outcome_code WHEN '3' THEN 1 WHEN '1' THEN 2 ELSE 3 END) GROUP BY play_id"
        ).fetchall()
        if not triplets or any(codes != "310" for _, codes in triplets):
            raise PhysicalSchemaError("play does not contain exactly the 3/1/0 cells")
        sqlite_counts = {
            table: int(control.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("issue_slot", "observation", "feature_cell")
        }
    finally:
        control.close()

    labels_connection = sqlite3.connect(package / "labels" / "labels.sqlite")
    try:
        label_tables = {
            row[0]
            for row in labels_connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "feature_cell" in label_tables or "settlement_label" not in label_tables:
            raise PhysicalSchemaError("label SQLite namespace is not physically isolated")
    finally:
        labels_connection.close()

    feature_path = package / "features" / "m3_feature_cells.parquet"
    if pq.read_schema(feature_path) != feature_schema():
        raise PhysicalSchemaError("feature Parquet schema mismatch")
    label_path = package / "labels" / "settlement_labels.parquet"
    if pq.read_schema(label_path) != label_schema():
        raise PhysicalSchemaError("label Parquet schema mismatch")
    features = load_feature_cells(package)
    labels = pd.read_parquet(label_path)
    if len(features) != sqlite_counts["feature_cell"]:
        raise PhysicalSchemaError("SQLite/Parquet feature row count mismatch")
    if features.duplicated(
        ["observation_id", "issue_slot_id", "outcome_code", "feature_name"]
    ).any():
        raise PhysicalSchemaError("duplicate analytical feature cell")
    if not features["outcome_code"].isin(OUTCOME_CODES).all():
        raise PhysicalSchemaError("invalid outcome code")
    if not features["namespace"].isin(NAMESPACES).all():
        raise PhysicalSchemaError("invalid temporal namespace")
    proxy = features["namespace"].eq("historical_proxy")
    strict = features["namespace"].eq("strict_forward")
    if features.loc[proxy, "observed_at_utc"].notna().any():
        raise PhysicalSchemaError("historical proxy claims a wall-clock observation")
    if features.loc[strict, "observed_at_utc"].isna().any():
        raise PhysicalSchemaError("strict-forward feature lacks observed_at")
    if (features.loc[strict, "observed_at_utc"] >= features.loc[strict, "kickoff_at_utc"]).any():
        raise PhysicalSchemaError("strict-forward feature is not pre-kickoff")
    available = features["availability_mask"].astype(bool)
    if features.loc[available, "value"].isna().any() or features.loc[~available, "value"].notna().any():
        raise PhysicalSchemaError("availability mask/value mismatch")
    if features.loc[available, "missing_reason"].notna().any() or features.loc[~available, "missing_reason"].isna().any():
        raise PhysicalSchemaError("missing reason is not explicit")

    profile_connection = sqlite3.connect(package / "control.sqlite")
    try:
        slots = pd.read_sql_query("SELECT * FROM issue_slot", profile_connection)
        observations = pd.read_sql_query("SELECT * FROM observation", profile_connection)
    finally:
        profile_connection.close()
    profile = profile_package_frames(slots, observations, features, labels)
    if profile != manifest.get("profile"):
        raise PhysicalSchemaError("profile does not match verified package")
    return {"status": "PASS", **profile}
