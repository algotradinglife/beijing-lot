"""#252 temporal evidence writer and decision-facing semantic verifier."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

import pandas as pd

from source_schema import publication
from temporal_semantics import (
    ACCEPTED_PROXY_HORIZONS,
    POLL_GRADE,
    POLL_SEMANTICS,
    POLL_NAMESPACE,
    POLL_SOURCE_ID,
    PROXY_GRADE,
    PROXY_NAMESPACE,
    PROXY_SEMANTICS,
    PROXY_SOURCE_ID,
    build_issue_view,
    build_segment_views,
    validate_observations,
)

CONTRACT_VERSION = "BJ-UNIFIED-TEMPORAL-SEMANTICS-001-v3"
PACKAGE_SCHEMA = "bj252_temporal_evidence_v3"
LEAD_HOURS = (1, 6, 12, 24)
POLL_SNAPSHOT_COLUMNS = (
    "fixture_id",
    "issue_code",
    "match_idx",
    "snapshot_horizon",
    "time_semantics",
    "causal_grade",
    "source_id",
    "availability_mask",
    "storage_present_cell_count",
    "valid_sp_cell_count",
    "poll_started_at_utc",
    "kickoff_at_utc",
)
PROXY_ROLES = {
    "euro_1x2": ("EURO_1X2_OUTCOME_PROXY", "True"),
    "kelly_1x2": ("KELLY_1X2_DIAGNOSTIC", "False"),
    "asian_handicap": ("HANDICAP_LINE_TWO_PRICE_DIAGNOSTIC", "False"),
    "over_under": ("TOTAL_LINE_TWO_PRICE_DIAGNOSTIC", "False"),
}
DROP_REASONS = {
    "AVAILABLE",
    "NO_OBSERVATION_BY_CUTOFF",
    "OBSERVATION_UNAVAILABLE_OR_INCOMPLETE",
    "INVALID_VALUE",
    "CUTOFF_NOT_PRE_KICKOFF",
}
RECEIPT_COMPONENTS = ("main", "wal", "shm")
SOURCE_LANE_RECEIPT_REQUIREMENTS = {
    POLL_NAMESPACE: {
        "source_id": POLL_SOURCE_ID,
        "receipt_source_key": "beidan_live_db",
        "required_receipt_keys": [
            f"beidan_live_db:{component}" for component in RECEIPT_COMPONENTS
        ],
    },
    PROXY_NAMESPACE: {
        "source_id": PROXY_SOURCE_ID,
        "receipt_source_key": "beidan_xlsm_workbook",
        "required_receipt_keys": [
            f"beidan_xlsm_workbook:{component}" for component in RECEIPT_COMPONENTS
        ],
    },
}
REQUIRED_RECEIPT_KEYS = frozenset(
    key
    for lane in SOURCE_LANE_RECEIPT_REQUIREMENTS.values()
    for key in lane["required_receipt_keys"]
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rehash_package(package: Path) -> None:
    """Write the internal package-integrity checksum set."""
    sums = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    publication.atomic_write_json(package / "SHA256SUMS.json", sums)


def _validate_source_receipt(receipt: Mapping[str, str]) -> dict[str, str]:
    """Fail closed unless each declared source lane has its exact receipt set.

    This binds lane identity to the SQLite byte streams the profile can read.
    It deliberately does not claim that a re-signed internal receipt authenticates
    an external provider; it only rejects malformed or cross-lane evidence.
    """
    normalized = dict(receipt)
    if set(normalized) != REQUIRED_RECEIPT_KEYS:
        raise AssertionError("source receipt keys do not match declared source lanes")
    for lane in SOURCE_LANE_RECEIPT_REQUIREMENTS.values():
        required = lane["required_receipt_keys"]
        if required[0].split(":", 1)[0] != lane["receipt_source_key"]:
            raise AssertionError("source receipt lane requirement is inconsistent")
        main_value = normalized[required[0]]
        if not re.fullmatch(r"[0-9a-f]{64}", str(main_value)):
            raise AssertionError("source receipt main database digest malformed")
        for key in required[1:]:
            value = normalized[key]
            if value != "ABSENT" and not re.fullmatch(r"[0-9a-f]{64}", str(value)):
                raise AssertionError("source receipt sidecar digest malformed")
    return normalized


def _selection_summary(selection: pd.DataFrame) -> pd.DataFrame:
    return (
        selection.groupby(["issue_code", "lead_hours", "decision_at_utc"], as_index=False)
        .agg(
            fixture_count=("fixture_id", "size"),
            available_fixture_count=("drop_reason", lambda value: int(value.eq("AVAILABLE").sum())),
            total_cell_count=("fixture_id", lambda value: int(len(value) * 3)),
            storage_present_cell_count=("latest_storage_present_cell_count_by_cutoff", "sum"),
            valid_sp_cell_count=("latest_valid_sp_cell_count_by_cutoff", "sum"),
            model_available_cell_count=("model_available_cell_count", "sum"),
            median_poll_start_age_minutes=("poll_start_age_minutes", "median"),
        )
    )


def _drop_summary(selection: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        selection.groupby([*keys, "drop_reason"], as_index=False)
        .agg(
            fixture_count=("fixture_id", "size"),
            total_cell_count=("fixture_id", lambda value: int(len(value) * 3)),
            storage_present_cell_count=("latest_storage_present_cell_count_by_cutoff", "sum"),
            valid_sp_cell_count=("latest_valid_sp_cell_count_by_cutoff", "sum"),
            model_available_cell_count=("model_available_cell_count", "sum"),
        )
    )


def profile_tables(poll_rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build issue/segment curves from the bounded poll-start namespace."""
    polls = validate_observations(poll_rows, namespace="poll_start_forward")
    fixtures = polls[
        ["fixture_id", "issue_code", "match_idx", "kickoff_at_utc"]
    ].drop_duplicates("fixture_id")
    issue_duration = (
        fixtures.groupby("issue_code", as_index=False)
        .agg(
            fixture_count=("fixture_id", "size"),
            first_kickoff_at_utc=("kickoff_at_utc", "min"),
            last_kickoff_at_utc=("kickoff_at_utc", "max"),
        )
    )
    issue_duration["issue_duration_hours"] = (
        issue_duration["last_kickoff_at_utc"]
        - issue_duration["first_kickoff_at_utc"]
    ).dt.total_seconds() / 3600
    cutoff_rows: list[pd.DataFrame] = []
    segment_rows: list[pd.DataFrame] = []
    for issue_code, group in polls.groupby("issue_code", sort=True):
        for lead_hours in LEAD_HOURS:
            cutoff = group["kickoff_at_utc"].min() - pd.Timedelta(hours=lead_hours)
            view = build_issue_view(
                group, issue_code=str(issue_code), decision_at_utc=cutoff
            )
            view.insert(1, "lead_hours", lead_hours)
            cutoff_rows.append(view)
        segment_rows.append(
            build_segment_views(
                group,
                issue_code=str(issue_code),
                lead_minutes=60,
                timezone_name="Asia/Shanghai",
            )
        )
    cutoff_selection = pd.concat(cutoff_rows, ignore_index=True)
    segment_selection = pd.concat(segment_rows, ignore_index=True)
    return {
        "issue_duration.csv": issue_duration,
        "cutoff_selection.csv": cutoff_selection,
        "cutoff_coverage.csv": _selection_summary(cutoff_selection),
        "cutoff_drop_reasons.csv": _drop_summary(
            cutoff_selection, ["issue_code", "lead_hours"]
        ),
        "segment_selection.csv": segment_selection,
        "segment_drop_reasons.csv": _drop_summary(
            segment_selection, ["issue_code", "segment_idx"]
        ),
    }


def _populate(
    staging: Path,
    poll_rows: pd.DataFrame,
    proxy_summary: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> None:
    (staging / "tables").mkdir(parents=True, exist_ok=True)
    normalized_receipt = _validate_source_receipt(source_receipt)
    polls = validate_observations(poll_rows, namespace="poll_start_forward")
    tables = profile_tables(polls)
    one_hour = tables["cutoff_selection.csv"].loc[
        tables["cutoff_selection.csv"]["lead_hours"].eq(1)
    ].drop(columns="lead_hours")
    issue_coverage = (
        one_hour.assign(available=one_hour["drop_reason"].eq("AVAILABLE"))
        .groupby(["issue_code", "decision_at_utc"], as_index=False)
        .agg(
            total_fixture_count=("fixture_id", "size"),
            available_fixture_count=("available", "sum"),
        )
    )
    proxy = proxy_summary.copy()
    required_proxy = {
        "snapshot_horizon", "market", "field_role", "p34_m3_compatible", "fixture_count"
    }
    if not required_proxy <= set(proxy.columns):
        raise ValueError(
            f"proxy summary missing columns: {sorted(required_proxy - set(proxy.columns))}"
        )
    if set(proxy["snapshot_horizon"]) != set(ACCEPTED_PROXY_HORIZONS):
        raise ValueError("proxy summary must cover initial/10h/1h")
    if proxy.duplicated(["snapshot_horizon", "market"]).any():
        raise ValueError("proxy horizon-market summary must be unique")
    if proxy[["market", "field_role"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any():
        raise ValueError("proxy market and field role are required")
    compatibility = proxy["p34_m3_compatible"]
    if not pd.api.types.is_bool_dtype(compatibility.dtype):
        raise ValueError("p34_m3_compatible must use exact boolean dtype")
    proxy["p34_m3_compatible"] = compatibility.map({True: "True", False: "False"})
    for column in (
        "issue_count",
        "market_row_count",
        "complete_consensus_rows",
        "available_value_cells",
    ):
        if column not in proxy.columns:
            proxy[column] = 0
    proxy["time_semantics"] = PROXY_SEMANTICS
    proxy["causal_grade"] = PROXY_GRADE
    poll_snapshot = polls.loc[:, list(POLL_SNAPSHOT_COLUMNS)].copy()
    for column in ("poll_started_at_utc", "kickoff_at_utc"):
        poll_snapshot[column] = poll_snapshot[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    publication.atomic_write_parquet(
        poll_snapshot,
        staging / "tables" / "poll_start_input_snapshot.parquet",
    )
    publication.atomic_write_csv(one_hour, staging / "tables" / "poll_start_selection.csv")
    publication.atomic_write_csv(issue_coverage, staging / "tables" / "issue_coverage.csv")
    publication.atomic_write_csv(proxy, staging / "tables" / "proxy_horizon_market_summary.csv")
    for filename, frame in tables.items():
        publication.atomic_write_csv(frame, staging / "tables" / filename)
    manifest = {
        "schema": PACKAGE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "poll_start_namespace": "poll_start_forward",
        "proxy_namespace": "historical_proxy_horizon_market_summary",
        "historical_proxy_observation_source_id": PROXY_SOURCE_ID,
        "source_lane_receipt_requirements": SOURCE_LANE_RECEIPT_REQUIREMENTS,
        "source_receipt": normalized_receipt,
        "policy": "candidate leads 1/6/12/24h; segment fallback 1h",
        "schedule_authority": "CURRENT_SCHEDULE_REFERENCE_NOT_RESCHEDULE_ASOF",
        "clock_authority": "POLL_STARTED_NOT_RECEIVED_OR_COMMITTED",
        "cell_lineage": "LOCAL_MERGED_UPSTREAM_CELL_SOURCE_UNKNOWN",
        "source_authentication": "STABLE_BUILD_INTERVAL_NOT_EXTERNAL_TRUST_ANCHOR",
        "raw_cell_value_evidence": "COUNTS_ONLY_NOT_FROZEN_RAW_CELL_AUTHORITY",
        "poll_start_input_snapshot_rows": int(len(polls)),
        "poll_start_input_snapshot_sha256": _sha256(
            staging / "tables" / "poll_start_input_snapshot.parquet"
        ),
        "proxy_summary_records": proxy.to_dict(orient="records"),
        "table_row_counts": {
            "poll_start_selection": int(len(one_hour)),
            "cutoff_selection": int(len(tables["cutoff_selection.csv"])),
            "segment_selection": int(len(tables["segment_selection.csv"])),
        },
    }
    publication.atomic_write_json(staging / "MANIFEST.json", manifest)
    rehash_package(staging)


def write_package(
    package: Path,
    *,
    poll_rows: pd.DataFrame,
    proxy_coverage: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> Path:
    """Atomically publish a semantically verified candidate package."""

    def populate(staging: Path) -> None:
        _populate(staging, poll_rows, proxy_coverage, source_receipt)
        verify_package(staging)

    return publication.atomic_publish_directory(package, populate, force=True)


def _verify_hashes(package: Path) -> None:
    recorded = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.relative_to(package).as_posix(): _sha256(path)
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if recorded != actual:
        raise AssertionError("hash closure mismatch")


def _read_selection(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, keep_default_na=False)
    values = frame["availability_mask"].astype(str)
    if not values.isin({"True", "False"}).all():
        raise AssertionError("availability_mask must be canonical boolean text")
    frame["availability_mask"] = values.map({"True": True, "False": False}).astype(bool)
    for column in (
        "kickoff_at_utc",
        "decision_at_utc",
        "latest_poll_started_at_utc_by_cutoff",
        "selected_poll_started_at_utc",
    ):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    for column in (
        "storage_present_cell_count",
        "valid_sp_cell_count",
        "latest_storage_present_cell_count_by_cutoff",
        "latest_valid_sp_cell_count_by_cutoff",
        "model_available_cell_count",
        "poll_start_age_minutes",
        "lead_hours",
        "segment_idx",
    ):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _validate_selection(frame: pd.DataFrame) -> None:
    required = {
        "fixture_id",
        "issue_code",
        "kickoff_at_utc",
        "decision_at_utc",
        "latest_poll_started_at_utc_by_cutoff",
        "selected_poll_started_at_utc",
        "latest_storage_present_cell_count_by_cutoff",
        "latest_valid_sp_cell_count_by_cutoff",
        "model_available_cell_count",
        "poll_start_age_minutes",
        "drop_reason",
        "snapshot_horizon",
        "time_semantics",
        "causal_grade",
        "source_id",
        "availability_mask",
        "storage_present_cell_count",
        "valid_sp_cell_count",
    }
    if not required <= set(frame.columns):
        raise AssertionError("selection ledger schema mismatch")
    if not set(frame["drop_reason"]).issubset(DROP_REASONS):
        raise AssertionError("unknown drop reason")
    if frame.duplicated(
        [column for column in ("issue_code", "lead_hours", "segment_idx", "fixture_id") if column in frame]
    ).any():
        raise AssertionError("selection ledger identity duplicate")
    available = frame["drop_reason"].eq("AVAILABLE")
    if not frame["time_semantics"].eq(POLL_SEMANTICS).all():
        raise AssertionError("selection row has non-poll time semantics")
    if not frame["causal_grade"].eq(POLL_GRADE).all():
        raise AssertionError("selection row has wrong poll-start grade")
    if not frame["source_id"].eq(POLL_SOURCE_ID).all():
        raise AssertionError("selection row has wrong merged-source lineage claim")
    count_columns = (
        "storage_present_cell_count", "valid_sp_cell_count",
        "latest_storage_present_cell_count_by_cutoff",
        "latest_valid_sp_cell_count_by_cutoff", "model_available_cell_count",
    )
    counts = frame.loc[:, count_columns].apply(pd.to_numeric, errors="coerce")
    if counts.isna().any().any() or (~counts.isin([0, 1, 2, 3])).any().any():
        raise AssertionError("selection cell count outside [0,3]")
    if (counts["valid_sp_cell_count"] > counts["storage_present_cell_count"]).any():
        raise AssertionError("selected valid cells exceed stored cells")
    if (
        counts["latest_valid_sp_cell_count_by_cutoff"]
        > counts["latest_storage_present_cell_count_by_cutoff"]
    ).any():
        raise AssertionError("latest valid cells exceed stored cells")
    latest = frame["latest_poll_started_at_utc_by_cutoff"]
    if (latest.notna() & latest.gt(frame["decision_at_utc"])).any():
        raise AssertionError("latest poll starts after decision cutoff")
    if frame.loc[available, "selected_poll_started_at_utc"].isna().any():
        raise AssertionError("available selection lacks observation")
    if (~available & frame["selected_poll_started_at_utc"].notna()).any():
        raise AssertionError("dropped selection retains observation")
    if not frame["availability_mask"].eq(available).all():
        raise AssertionError("available selection has false availability mask")
    if not counts.loc[available, "storage_present_cell_count"].eq(3).all():
        raise AssertionError("available selection lacks three stored cells")
    if not counts.loc[available, "valid_sp_cell_count"].eq(3).all():
        raise AssertionError("available selection lacks three cells")
    if not counts.loc[available, "model_available_cell_count"].eq(3).all():
        raise AssertionError("available model-cell count mismatch")
    if not counts.loc[~available, [
        "storage_present_cell_count", "valid_sp_cell_count", "model_available_cell_count"
    ]].eq(0).all().all():
        raise AssertionError("dropped row retains model-available cells")
    if (frame.loc[available, "selected_poll_started_at_utc"] > frame.loc[available, "decision_at_utc"]).any():
        raise AssertionError("future observation in selection")
    if (frame["decision_at_utc"] >= frame["kickoff_at_utc"]).any():
        raise AssertionError("cutoff is not pre-kickoff")
    expected_staleness = (
        frame.loc[available, "decision_at_utc"]
        - frame.loc[available, "selected_poll_started_at_utc"]
    ).dt.total_seconds() / 60.0
    observed_staleness = pd.to_numeric(
        frame.loc[available, "poll_start_age_minutes"], errors="raise"
    )
    if not expected_staleness.round(9).equals(observed_staleness.round(9)):
        raise AssertionError("staleness value disagrees with selected observation")
    incomplete = frame["drop_reason"].eq("OBSERVATION_UNAVAILABLE_OR_INCOMPLETE")
    invalid_value = frame["drop_reason"].eq("INVALID_VALUE")
    no_observation = frame["drop_reason"].eq("NO_OBSERVATION_BY_CUTOFF")
    if frame.loc[incomplete | invalid_value, "latest_poll_started_at_utc_by_cutoff"].isna().any():
        raise AssertionError("incomplete reason lacks an observed snapshot")
    if frame.loc[no_observation, "latest_poll_started_at_utc_by_cutoff"].notna().any():
        raise AssertionError("no-observation reason retains an observed snapshot")
    if not counts.loc[incomplete, "latest_storage_present_cell_count_by_cutoff"].lt(3).all():
        raise AssertionError("incomplete reason has three stored cells")
    if not counts.loc[invalid_value, "latest_storage_present_cell_count_by_cutoff"].eq(3).all() or not counts.loc[
        invalid_value, "latest_valid_sp_cell_count_by_cutoff"
    ].lt(3).all():
        raise AssertionError("invalid-value reason has inconsistent cell counts")


def _normalize_for_compare(frame: pd.DataFrame) -> pd.DataFrame:
    value = frame.copy().reset_index(drop=True)
    for column in ("fixture_id", "issue_code"):
        if column in value:
            value[column] = value[column].astype(str)
    for column in value.columns:
        if "_at_utc" in column:
            value[column] = pd.to_datetime(value[column], utc=True, errors="coerce")
    return value


def _assert_same(actual: pd.DataFrame, expected: pd.DataFrame, label: str) -> None:
    try:
        pd.testing.assert_frame_equal(
            _normalize_for_compare(actual),
            _normalize_for_compare(expected),
            check_dtype=False,
            check_like=False,
        )
    except AssertionError as error:
        raise AssertionError(f"{label} reconciliation failed") from error


def verify_package(package: Path) -> dict[str, object]:
    """Verify integrity plus every decision-facing temporal table."""
    _verify_hashes(package)
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("contract_version") != CONTRACT_VERSION:
        raise AssertionError("contract identity mismatch")
    if manifest.get("schedule_authority") != "CURRENT_SCHEDULE_REFERENCE_NOT_RESCHEDULE_ASOF":
        raise AssertionError("schedule-authority claim mismatch")
    if manifest.get("clock_authority") != "POLL_STARTED_NOT_RECEIVED_OR_COMMITTED":
        raise AssertionError("clock-authority claim mismatch")
    if manifest.get("cell_lineage") != "LOCAL_MERGED_UPSTREAM_CELL_SOURCE_UNKNOWN":
        raise AssertionError("cell-lineage claim mismatch")
    if manifest.get("poll_start_namespace") != "poll_start_forward":
        raise AssertionError("poll-start namespace mismatch")
    if manifest.get("historical_proxy_observation_source_id") != PROXY_SOURCE_ID:
        raise AssertionError("historical-proxy source-role claim mismatch")
    if manifest.get("source_authentication") != "STABLE_BUILD_INTERVAL_NOT_EXTERNAL_TRUST_ANCHOR":
        raise AssertionError("source-authentication claim mismatch")
    if manifest.get("raw_cell_value_evidence") != "COUNTS_ONLY_NOT_FROZEN_RAW_CELL_AUTHORITY":
        raise AssertionError("raw-cell evidence claim mismatch")
    if manifest.get("source_lane_receipt_requirements") != SOURCE_LANE_RECEIPT_REQUIREMENTS:
        raise AssertionError("source receipt lane requirements mismatch")
    receipt = manifest.get("source_receipt")
    if not isinstance(receipt, dict):
        raise AssertionError("source receipt missing")
    _validate_source_receipt(receipt)

    tables = package / "tables"
    poll_snapshot_path = tables / "poll_start_input_snapshot.parquet"
    poll_snapshot = pd.read_parquet(poll_snapshot_path)
    if manifest.get("poll_start_input_snapshot_rows") != len(poll_snapshot):
        raise AssertionError("poll-start input snapshot row count mismatch")
    if manifest.get("poll_start_input_snapshot_sha256") != _sha256(poll_snapshot_path):
        raise AssertionError("poll-start input snapshot digest mismatch")
    if tuple(poll_snapshot.columns) != POLL_SNAPSHOT_COLUMNS:
        raise AssertionError("poll-start input snapshot schema mismatch")
    reconstructed = profile_tables(poll_snapshot)
    poll_start = _read_selection(tables / "poll_start_selection.csv")
    cutoff = _read_selection(tables / "cutoff_selection.csv")
    segment = _read_selection(tables / "segment_selection.csv")
    for frame in (poll_start, cutoff, segment):
        _validate_selection(frame)
    _assert_same(
        cutoff,
        reconstructed["cutoff_selection.csv"],
        "cutoff selection source replay",
    )
    _assert_same(
        segment,
        reconstructed["segment_selection.csv"],
        "segment selection source replay",
    )
    if set(pd.to_numeric(cutoff["lead_hours"], errors="raise")) != set(LEAD_HOURS):
        raise AssertionError("candidate lead grid mismatch")
    monotonic = (
        cutoff.groupby(["issue_code", "lead_hours"], as_index=False)
        .agg(available=("drop_reason", lambda value: int(value.eq("AVAILABLE").sum())))
        .sort_values(["issue_code", "lead_hours"], kind="stable")
    )
    if (monotonic.groupby("issue_code")["available"].diff().fillna(0) > 0).any():
        raise AssertionError("availability increases at an earlier cutoff")

    cutoff_coverage = pd.read_csv(tables / "cutoff_coverage.csv")
    cutoff_drops = pd.read_csv(tables / "cutoff_drop_reasons.csv")
    segment_drops = pd.read_csv(tables / "segment_drop_reasons.csv")
    _assert_same(cutoff_coverage, _selection_summary(cutoff), "cutoff coverage")
    _assert_same(
        cutoff_drops,
        _drop_summary(cutoff, ["issue_code", "lead_hours"]),
        "cutoff drop",
    )
    _assert_same(
        segment_drops,
        _drop_summary(segment, ["issue_code", "segment_idx"]),
        "segment drop",
    )
    one_hour = cutoff.loc[cutoff["lead_hours"].eq(1)].drop(columns="lead_hours")
    _assert_same(poll_start, one_hour.reset_index(drop=True), "one-hour poll-start selection")

    issue_coverage = pd.read_csv(tables / "issue_coverage.csv")
    expected_issue = (
        poll_start.assign(available=poll_start["drop_reason"].eq("AVAILABLE"))
        .groupby(["issue_code", "decision_at_utc"], as_index=False)
        .agg(
            total_fixture_count=("fixture_id", "size"),
            available_fixture_count=("available", "sum"),
        )
    )
    _assert_same(issue_coverage, expected_issue, "issue coverage")

    proxy = pd.read_csv(tables / "proxy_horizon_market_summary.csv")
    expected_proxy_columns = {
        "snapshot_horizon",
        "market",
        "fixture_count",
        "issue_count",
        "market_row_count",
        "complete_consensus_rows",
        "available_value_cells",
        "field_role",
        "p34_m3_compatible",
        "time_semantics",
        "causal_grade",
    }
    if set(proxy.columns) != expected_proxy_columns:
        raise AssertionError("proxy summary schema mismatch")
    if set(proxy["snapshot_horizon"]) != set(ACCEPTED_PROXY_HORIZONS):
        raise AssertionError("proxy horizon outside frozen vocabulary")
    if not proxy["time_semantics"].eq(PROXY_SEMANTICS).all() or not proxy["causal_grade"].eq(PROXY_GRADE).all():
        raise AssertionError("proxy namespace semantics mismatch")
    if proxy.duplicated(["snapshot_horizon", "market"]).any():
        raise AssertionError("proxy horizon-market key duplicate")
    if proxy[["market", "field_role"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any():
        raise AssertionError("proxy market/field role missing")
    compatibility = proxy["p34_m3_compatible"].astype(str)
    if not compatibility.isin({"True", "False"}).all():
        raise AssertionError("proxy p34 compatibility must be canonical boolean text")
    expected_role = proxy["market"].map(
        {market: role for market, (role, _) in PROXY_ROLES.items()}
    )
    expected_compatibility = proxy["market"].map(
        {market: compatible for market, (_, compatible) in PROXY_ROLES.items()}
    )
    if expected_role.isna().any() or not proxy["field_role"].eq(expected_role).all():
        raise AssertionError("proxy field role disagrees with market")
    if not compatibility.eq(expected_compatibility).all():
        raise AssertionError("proxy p34 compatibility disagrees with market role")
    proxy["p34_m3_compatible"] = compatibility
    numeric_proxy = proxy[
        [
            "fixture_count",
            "issue_count",
            "market_row_count",
            "complete_consensus_rows",
            "available_value_cells",
        ]
    ].apply(pd.to_numeric, errors="raise")
    if (numeric_proxy < 0).any().any():
        raise AssertionError("negative proxy coverage")
    if proxy.to_dict(orient="records") != manifest.get("proxy_summary_records"):
        raise AssertionError("proxy summary disagrees with manifest receipt")
    expected_rows = manifest.get("table_row_counts")
    if expected_rows != {
        "poll_start_selection": len(poll_start),
        "cutoff_selection": len(cutoff),
        "segment_selection": len(segment),
    }:
        raise AssertionError("selection row counts disagree with manifest receipt")

    duration = pd.read_csv(tables / "issue_duration.csv")
    _assert_same(
        duration,
        reconstructed["issue_duration.csv"],
        "issue duration source replay",
    )
    first = pd.to_datetime(duration["first_kickoff_at_utc"], utc=True, errors="raise")
    last = pd.to_datetime(duration["last_kickoff_at_utc"], utc=True, errors="raise")
    expected_hours = (last - first).dt.total_seconds() / 3600
    if not expected_hours.round(9).equals(
        pd.to_numeric(duration["issue_duration_hours"], errors="raise").round(9)
    ):
        raise AssertionError("issue duration mismatch")
    return {
        "status": "PASS",
        "poll_start_selection_rows": len(poll_start),
        "cutoff_selection_rows": len(cutoff),
        "segment_selection_rows": len(segment),
        "proxy_summary_rows": len(proxy),
    }
