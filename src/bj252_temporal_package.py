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
    PROXY_GRADE,
    PROXY_SEMANTICS,
    STRICT_GRADE,
    STRICT_SEMANTICS,
    build_issue_view,
    build_segment_views,
    validate_observations,
)

CONTRACT_VERSION = "BJ-UNIFIED-TEMPORAL-SEMANTICS-001-v2"
PACKAGE_SCHEMA = "bj252_temporal_evidence_v2"
LEAD_HOURS = (1, 6, 12, 24)
DROP_REASONS = {
    "AVAILABLE",
    "NO_OBSERVATION_BY_CUTOFF",
    "OBSERVATION_UNAVAILABLE_OR_INCOMPLETE",
    "CUTOFF_NOT_PRE_KICKOFF",
}


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


def _selection_summary(selection: pd.DataFrame) -> pd.DataFrame:
    return (
        selection.groupby(["issue_code", "lead_hours", "decision_at_utc"], as_index=False)
        .agg(
            fixture_count=("fixture_id", "size"),
            available_fixture_count=("drop_reason", lambda value: int(value.eq("AVAILABLE").sum())),
            total_cell_count=("fixture_id", lambda value: int(len(value) * 3)),
            observed_cell_count=("observed_cell_count_by_cutoff", "sum"),
            model_available_cell_count=("model_available_cell_count", "sum"),
            median_staleness_minutes=("staleness_minutes", "median"),
        )
    )


def _drop_summary(selection: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    return (
        selection.groupby([*keys, "drop_reason"], as_index=False)
        .agg(
            fixture_count=("fixture_id", "size"),
            total_cell_count=("fixture_id", lambda value: int(len(value) * 3)),
            observed_cell_count=("observed_cell_count_by_cutoff", "sum"),
            model_available_cell_count=("model_available_cell_count", "sum"),
        )
    )


def profile_tables(strict_rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build all issue/segment fixture-cell curves from one strict namespace."""
    strict = validate_observations(strict_rows, namespace="strict_forward")
    fixtures = strict[
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
    for issue_code, group in strict.groupby("issue_code", sort=True):
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
    strict_rows: pd.DataFrame,
    proxy_summary: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> None:
    (staging / "tables").mkdir(parents=True, exist_ok=True)
    strict = validate_observations(strict_rows, namespace="strict_forward")
    tables = profile_tables(strict)
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
    required_proxy = {"snapshot_horizon", "fixture_count"}
    if not required_proxy <= set(proxy.columns):
        raise ValueError(
            f"proxy summary missing columns: {sorted(required_proxy - set(proxy.columns))}"
        )
    if set(proxy["snapshot_horizon"]) != set(ACCEPTED_PROXY_HORIZONS):
        raise ValueError("proxy summary must contain exactly initial/10h/1h")
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
    publication.atomic_write_csv(one_hour, staging / "tables" / "strict_selection.csv")
    publication.atomic_write_csv(issue_coverage, staging / "tables" / "issue_coverage.csv")
    publication.atomic_write_csv(proxy, staging / "tables" / "proxy_horizon_summary.csv")
    for filename, frame in tables.items():
        publication.atomic_write_csv(frame, staging / "tables" / filename)
    manifest = {
        "schema": PACKAGE_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "strict_namespace": "strict_forward",
        "proxy_namespace": "historical_proxy_aggregate_summary",
        "source_receipt": dict(source_receipt),
        "policy": "candidate leads 1/6/12/24h; segment fallback 1h",
        "schedule_authority": "CURRENT_SCHEDULE_REFERENCE_NOT_RESCHEDULE_ASOF",
        "source_authentication": "STABLE_BUILD_INTERVAL_NOT_EXTERNAL_TRUST_ANCHOR",
        "proxy_summary_records": proxy.to_dict(orient="records"),
        "table_row_counts": {
            "strict_selection": int(len(one_hour)),
            "cutoff_selection": int(len(tables["cutoff_selection.csv"])),
            "segment_selection": int(len(tables["segment_selection.csv"])),
        },
    }
    publication.atomic_write_json(staging / "MANIFEST.json", manifest)
    rehash_package(staging)


def write_package(
    package: Path,
    *,
    strict_rows: pd.DataFrame,
    proxy_coverage: pd.DataFrame,
    source_receipt: Mapping[str, str],
) -> Path:
    """Atomically publish a semantically verified candidate package."""

    def populate(staging: Path) -> None:
        _populate(staging, strict_rows, proxy_coverage, source_receipt)
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
        "latest_observed_at_utc_by_cutoff",
        "selected_observed_at_utc",
    ):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
    for column in (
        "available_cell_count",
        "observed_cell_count_by_cutoff",
        "model_available_cell_count",
        "staleness_minutes",
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
        "latest_observed_at_utc_by_cutoff",
        "selected_observed_at_utc",
        "observed_cell_count_by_cutoff",
        "model_available_cell_count",
        "staleness_minutes",
        "drop_reason",
        "snapshot_horizon",
        "time_semantics",
        "causal_grade",
        "source_id",
        "availability_mask",
        "available_cell_count",
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
    if frame.loc[available, "selected_observed_at_utc"].isna().any():
        raise AssertionError("available selection lacks observation")
    if (~available & frame["selected_observed_at_utc"].notna()).any():
        raise AssertionError("dropped selection retains observation")
    if not frame.loc[available, "availability_mask"].all():
        raise AssertionError("available selection has false availability mask")
    if not pd.to_numeric(frame.loc[available, "available_cell_count"], errors="raise").eq(3).all():
        raise AssertionError("available selection lacks three cells")
    if not pd.to_numeric(frame.loc[available, "model_available_cell_count"], errors="raise").eq(3).all():
        raise AssertionError("available model-cell count mismatch")
    if not pd.to_numeric(frame.loc[~available, "model_available_cell_count"], errors="raise").eq(0).all():
        raise AssertionError("dropped row retains model-available cells")
    if not frame.loc[available, "time_semantics"].eq(STRICT_SEMANTICS).all():
        raise AssertionError("available selection has non-strict time semantics")
    if not frame.loc[available, "causal_grade"].eq(STRICT_GRADE).all():
        raise AssertionError("available selection has wrong schedule-reference grade")
    if (frame.loc[available, "selected_observed_at_utc"] > frame.loc[available, "decision_at_utc"]).any():
        raise AssertionError("future observation in selection")
    if (frame["decision_at_utc"] >= frame["kickoff_at_utc"]).any():
        raise AssertionError("cutoff is not pre-kickoff")
    expected_staleness = (
        frame.loc[available, "decision_at_utc"]
        - frame.loc[available, "selected_observed_at_utc"]
    ).dt.total_seconds() / 60.0
    observed_staleness = pd.to_numeric(
        frame.loc[available, "staleness_minutes"], errors="raise"
    )
    if not expected_staleness.round(9).equals(observed_staleness.round(9)):
        raise AssertionError("staleness value disagrees with selected observation")
    incomplete = frame["drop_reason"].eq("OBSERVATION_UNAVAILABLE_OR_INCOMPLETE")
    no_observation = frame["drop_reason"].eq("NO_OBSERVATION_BY_CUTOFF")
    if frame.loc[incomplete, "latest_observed_at_utc_by_cutoff"].isna().any():
        raise AssertionError("incomplete reason lacks an observed snapshot")
    if frame.loc[no_observation, "latest_observed_at_utc_by_cutoff"].notna().any():
        raise AssertionError("no-observation reason retains an observed snapshot")
    cells = pd.to_numeric(frame["observed_cell_count_by_cutoff"], errors="coerce").fillna(0)
    if (~cells.isin([0, 1, 2, 3])).any():
        raise AssertionError("observed cell count outside [0,3]")


def _normalize_for_compare(frame: pd.DataFrame) -> pd.DataFrame:
    value = frame.copy().reset_index(drop=True)
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
    if manifest.get("source_authentication") != "STABLE_BUILD_INTERVAL_NOT_EXTERNAL_TRUST_ANCHOR":
        raise AssertionError("source-authentication claim mismatch")
    receipt = manifest.get("source_receipt")
    if not isinstance(receipt, dict) or not receipt:
        raise AssertionError("source receipt missing")
    if any(value != "ABSENT" and not re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in receipt.values()):
        raise AssertionError("source receipt digest malformed")

    tables = package / "tables"
    strict = _read_selection(tables / "strict_selection.csv")
    cutoff = _read_selection(tables / "cutoff_selection.csv")
    segment = _read_selection(tables / "segment_selection.csv")
    for frame in (strict, cutoff, segment):
        _validate_selection(frame)
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
    _assert_same(strict, one_hour.reset_index(drop=True), "one-hour strict selection")

    issue_coverage = pd.read_csv(tables / "issue_coverage.csv")
    expected_issue = (
        strict.assign(available=strict["drop_reason"].eq("AVAILABLE"))
        .groupby(["issue_code", "decision_at_utc"], as_index=False)
        .agg(
            total_fixture_count=("fixture_id", "size"),
            available_fixture_count=("available", "sum"),
        )
    )
    _assert_same(issue_coverage, expected_issue, "issue coverage")

    proxy = pd.read_csv(tables / "proxy_horizon_summary.csv")
    if set(proxy["snapshot_horizon"]) != set(ACCEPTED_PROXY_HORIZONS):
        raise AssertionError("proxy horizon outside frozen vocabulary")
    if not proxy["time_semantics"].eq(PROXY_SEMANTICS).all() or not proxy["causal_grade"].eq(PROXY_GRADE).all():
        raise AssertionError("proxy namespace semantics mismatch")
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
        "strict_selection": len(strict),
        "cutoff_selection": len(cutoff),
        "segment_selection": len(segment),
    }:
        raise AssertionError("selection row counts disagree with manifest receipt")

    duration = pd.read_csv(tables / "issue_duration.csv")
    first = pd.to_datetime(duration["first_kickoff_at_utc"], utc=True, errors="raise")
    last = pd.to_datetime(duration["last_kickoff_at_utc"], utc=True, errors="raise")
    expected_hours = (last - first).dt.total_seconds() / 3600
    if not expected_hours.round(9).equals(
        pd.to_numeric(duration["issue_duration_hours"], errors="raise").round(9)
    ):
        raise AssertionError("issue duration mismatch")
    return {
        "status": "PASS",
        "strict_selection_rows": len(strict),
        "cutoff_selection_rows": len(cutoff),
        "segment_selection_rows": len(segment),
        "proxy_summary_rows": len(proxy),
    }
